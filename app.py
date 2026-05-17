"""
Bob-Guard Flask Web Application
Web interface for code analysis, remediation, and reporting with background task processing.
"""

import os
import json
import logging
import uuid
import zipfile
import shutil
import subprocess
import threading
from collections import Counter
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict
from enum import Enum

from flask import Flask, render_template, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename

from src.analyzer import Analyzer, Violation
from src.remediator import CodeRemediator, Fix, RemediationSummary
from src.test_generator import TestGenerator
from src.reporter import ReportGenerator
from src.bob_client import BobClient, BobAPIError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
CORS(app)

# Configuration
UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'output'
TEMP_FOLDER = 'temp'
ALLOWED_EXTENSIONS = {'.zip', '.tar', '.gz'}
MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100MB max file size

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['OUTPUT_FOLDER'] = OUTPUT_FOLDER
app.config['TEMP_FOLDER'] = TEMP_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

# Create necessary directories
for folder in [UPLOAD_FOLDER, OUTPUT_FOLDER, TEMP_FOLDER]:
    Path(folder).mkdir(exist_ok=True)


class TaskStatus(Enum):
    """Task status enumeration."""
    PENDING = "pending"
    ANALYZING = "analyzing"
    REMEDIATING = "remediating"
    GENERATING_TESTS = "generating_tests"
    GENERATING_REPORT = "generating_report"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Task:
    """Background task representation."""
    task_id: str
    status: TaskStatus
    progress: int  # 0-100
    message: str
    repo_path: Optional[str] = None
    violations: Optional[list] = None
    fixes: Optional[list] = None
    tests: Optional[list] = None
    report_path: Optional[str] = None
    error: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    
    def __post_init__(self):
        if self.violations is None:
            self.violations = []
        if self.fixes is None:
            self.fixes = []
        if self.tests is None:
            self.tests = []
        if self.started_at is None:
            self.started_at = datetime.utcnow().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert task to dictionary."""
        return {
            'task_id': self.task_id,
            'status': self.status.value,
            'progress': self.progress,
            'message': self.message,
            'repo_path': self.repo_path,
            'violations_count': len(self.violations) if self.violations else 0,
            'fixes_count': len(self.fixes) if self.fixes else 0,
            'tests_count': len(self.tests) if self.tests else 0,
            'report_path': self.report_path,
            'error': self.error,
            'started_at': self.started_at,
            'completed_at': self.completed_at
        }


# Global task storage (in production, use Redis or database)
tasks: Dict[str, Task] = {}


def allowed_file(filename: str) -> bool:
    """Check if file extension is allowed."""
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


def extract_zip(zip_path: Path, extract_to: Path) -> Path:
    """Extract zip file and return the extracted directory path."""
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_to)
        
        # Find the root directory (handle single folder or multiple files)
        extracted_items = list(extract_to.iterdir())
        if len(extracted_items) == 1 and extracted_items[0].is_dir():
            return extracted_items[0]
        return extract_to
    
    except Exception as e:
        logger.error(f"Error extracting zip: {e}")
        raise


def is_github_repository_source(repo_source: str) -> bool:
    """Return True when the source looks like a GitHub repository URL."""
    normalized_source = repo_source.strip().lower()
    return (
        normalized_source.startswith('git@github.com:')
        or normalized_source.startswith('https://github.com/')
        or normalized_source.startswith('http://github.com/')
        or normalized_source.startswith('github.com/')
    )


def normalize_github_clone_url(repo_source: str) -> str:
    """Convert a GitHub repository source into a git clone URL."""
    source = repo_source.strip()

    if source.startswith('git@github.com:'):
        return source if source.endswith('.git') else f"{source}.git"

    if source.startswith('github.com/'):
        source = f"https://{source}"

    parsed = urlparse(source)
    path = parsed.path.rstrip('/')
    if path.endswith('.git'):
        return source
    return f"{parsed.scheme}://{parsed.netloc}{path}.git"


def clone_github_repository(repo_source: str, task_id: str) -> Path:
    """Clone a GitHub repository into the task temp directory and return the local path."""
    clone_url = normalize_github_clone_url(repo_source)
    target_dir = Path(app.config['TEMP_FOLDER']) / task_id / 'repo'

    if target_dir.exists():
        shutil.rmtree(target_dir)
    target_dir.parent.mkdir(parents=True, exist_ok=True)

    try:
        result = subprocess.run(
            ['git', 'clone', '--depth', '1', clone_url, str(target_dir)],
            check=True,
            capture_output=True,
            text=True,
        )
        if result.stdout:
            logger.info(result.stdout.strip())
        if result.stderr:
            logger.info(result.stderr.strip())
    except FileNotFoundError as e:
        raise RuntimeError("Git is not installed or not available in PATH") from e
    except subprocess.CalledProcessError as e:
        error_output = (e.stderr or e.stdout or str(e)).strip()
        raise RuntimeError(f"Failed to clone GitHub repository: {error_output}") from e

    if not target_dir.exists():
        raise RuntimeError("Git clone completed but the repository directory was not created")

    return target_dir


def resolve_repository_source(repo_source: str, task_id: str) -> Path:
    """Resolve a repository source into a local path ready for analysis."""
    source = repo_source.strip()

    if is_github_repository_source(source):
        return clone_github_repository(source, task_id)

    repo_path = Path(source)
    if not repo_path.exists():
        raise ValueError(f"Repository path does not exist: {repo_source}")

    if not repo_path.is_dir():
        raise ValueError(f"Repository path is not a directory: {repo_source}")

    return repo_path


def run_pipeline(task_id: str, repo_path: str, use_bob: bool = True):
    """
    Run the complete analysis pipeline in background.
    Updates task status as it progresses.
    """
    task = tasks[task_id]

    def update_analysis_progress(processed_files: int, total_files: int, current_file: Optional[str], violations_found: int):
        """Update the task with live analysis progress."""
        if total_files > 0:
            analysis_progress = 10 + int((processed_files / total_files) * 20)
        else:
            analysis_progress = 30

        task.status = TaskStatus.ANALYZING
        task.progress = min(analysis_progress, 30)

        if current_file:
            file_name = Path(current_file).name
            task.message = f"Analyzing codebase... ({processed_files}/{total_files}) {file_name}"
        elif total_files == 0:
            task.message = "No supported files found to analyze"
        else:
            task.message = f"Analyzing codebase... ({processed_files}/{total_files})"
    
    try:
        # Step 0: If repo_path is a GitHub URL, clone it here so UI can show progress
        if repo_path and is_github_repository_source(str(repo_path)):
            task.status = TaskStatus.ANALYZING
            task.progress = 5
            task.message = "Cloning GitHub repository..."
            logger.info(f"Task {task_id}: Cloning repository {repo_path}")

            try:
                cloned_path = clone_github_repository(str(repo_path), task_id)
                repo_path = str(cloned_path)
                task.progress = 8
                task.message = "Clone complete. Preparing repository for analysis..."
                logger.info(f"Task {task_id}: Cloned to {repo_path}")
            except Exception as e:
                logger.error(f"Task {task_id}: Clone failed: {e}")
                task.status = TaskStatus.FAILED
                task.error = str(e)
                task.message = f"Clone failed: {str(e)}"
                task.completed_at = datetime.utcnow().isoformat()
                return

        # Step 1: Analysis
        task.status = TaskStatus.ANALYZING
        task.progress = 10
        task.message = "Analyzing codebase..."
        logger.info(f"Task {task_id}: Starting analysis of {repo_path}")
        
        # Load rules
        rules_path = Path('config/rules.json')
        rules = []
        if rules_path.exists():
            with open(rules_path, 'r') as f:
                loaded = json.load(f)
                # Support both formats: a top-level object {"rules": [...]} or
                # directly a list of rule objects.
                if isinstance(loaded, dict) and 'rules' in loaded:
                    rules = loaded['rules']
                else:
                    rules = loaded
        
        # Initialize Bob client if needed
        bob_client = None
        if use_bob:
            try:
                bob_client = BobClient()
            except Exception as e:
                logger.warning(f"Bob client initialization failed: {e}")
        
        # Run analyzer
        analyzer = Analyzer(
            repo_path=repo_path,
            rules=rules,
            bob_client=bob_client,
            progress_callback=update_analysis_progress,
        )
        violations = analyzer.scan_repository()
        
        task.violations = [v.to_dict() for v in violations]
        task.progress = 30
        task.message = f"Found {len(violations)} violations"
        logger.info(f"Task {task_id}: Found {len(violations)} violations")
        
        # Step 2: Remediation
        task.status = TaskStatus.REMEDIATING
        task.progress = 40
        task.message = "Generating fixes..."
        
        remediator = CodeRemediator(bob_client=bob_client)
        fixes = remediator.generate_fixes(violations, min_confidence=0.7)
        
        task.fixes = [f.to_dict() for f in fixes]
        task.progress = 60
        task.message = f"Generated {len(fixes)} fixes"
        logger.info(f"Task {task_id}: Generated {len(fixes)} fixes")
        
        # Step 3: Test Generation
        task.status = TaskStatus.GENERATING_TESTS
        task.progress = 70
        task.message = "Generating tests..."
        
        test_generator = TestGenerator(bob_client=bob_client)
        test_result = test_generator.generate_tests_for_fixes(fixes)
        
        task.tests = [ts.to_dict() for ts in test_result.test_suites]
        task.progress = 85
        task.message = f"Generated {test_result.tests_generated} tests"
        logger.info(f"Task {task_id}: Generated {test_result.tests_generated} tests")
        
        # Step 4: Report Generation
        task.status = TaskStatus.GENERATING_REPORT
        task.progress = 90
        task.message = "Generating report..."
        
        reporter = ReportGenerator(output_dir=OUTPUT_FOLDER)
        
        # Generate all report formats
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # HTML report
        html_path = reporter.generate_analysis_report(
            violations=violations,
            format='html',
            repo_path=repo_path
        )
        
        # JSON report
        json_path = reporter.generate_analysis_report(
            violations=violations,
            format='json',
            repo_path=repo_path
        )
        
        # Markdown report
        md_path = reporter.generate_analysis_report(
            violations=violations,
            format='markdown',
            repo_path=repo_path
        )

        # Generate the dashboard report expected by the results page.
        scan_started_at = datetime.fromisoformat(task.started_at)
        scan_duration = max((datetime.utcnow() - scan_started_at).total_seconds(), 0.0)
        severity_counts = Counter(v.severity.upper() for v in violations)
        category_counts = Counter(v.category.upper() for v in violations)

        dashboard_report = {
            'scan_metadata': {
                'date': datetime.utcnow().isoformat(),
                'repo': repo_path,
                'duration_seconds': round(scan_duration, 2),
                'files_scanned': len(set(v.file_path for v in violations)),
            },
            'summary': {
                'total_files': len(set(v.file_path for v in violations)),
                'total_violations': len(violations),
                'fixes_applied': len(fixes),
                'tests_generated': test_result.tests_generated,
                'critical_violations': severity_counts.get('CRITICAL', 0),
                'manual_review_required': max(len(violations) - len(fixes), 0),
                'risk_score': min(
                    100,
                    severity_counts.get('CRITICAL', 0) * 25 +
                    severity_counts.get('HIGH', 0) * 15 +
                    severity_counts.get('MEDIUM', 0) * 8 +
                    severity_counts.get('LOW', 0) * 3
                ),
                'by_severity': {
                    'CRITICAL': severity_counts.get('CRITICAL', 0),
                    'HIGH': severity_counts.get('HIGH', 0),
                    'MEDIUM': severity_counts.get('MEDIUM', 0),
                    'LOW': severity_counts.get('LOW', 0),
                },
                'by_category': dict(category_counts),
            },
            'violations': [v.to_dict() for v in violations],
            'remediations': [f.to_dict() for f in fixes],
            'tests': test_result.to_dict() if hasattr(test_result, 'to_dict') else [t.to_dict() for t in test_result.test_suites],
        }

        dashboard_report_path = Path(OUTPUT_FOLDER) / 'report.json'
        with open(dashboard_report_path, 'w', encoding='utf-8') as f:
            json.dump(dashboard_report, f, indent=2)
        
        task.report_path = str(dashboard_report_path)
        task.progress = 100
        task.status = TaskStatus.COMPLETED
        task.message = "Analysis complete!"
        task.completed_at = datetime.utcnow().isoformat()
        
        logger.info(f"Task {task_id}: Pipeline completed successfully")
    
    except Exception as e:
        logger.error(f"Task {task_id}: Pipeline failed: {e}", exc_info=True)
        task.status = TaskStatus.FAILED
        task.error = str(e)
        task.message = f"Pipeline failed: {str(e)}"
        task.completed_at = datetime.utcnow().isoformat()


# ============================================================================
# ROUTES
# ============================================================================

@app.route('/')
def index():
    """Main landing page - upload interface."""
    return render_template('index.html')


@app.route('/results')
def results_page():
    """Results dashboard page."""
    return render_template('results.html')


@app.route('/chat-ui')
@app.route('/chat', methods=['GET'])
def chat_ui():
    """Interactive chat interface."""
    return render_template('chat.html')


@app.route('/static/<path:filename>')
def serve_static(filename):
    """Serve static files (CSS, JS)."""
    return send_from_directory('static', filename)


@app.route('/scan', methods=['POST'])
@app.route('/api/analyze', methods=['POST'])
def scan():
    """
    Main scan endpoint - accepts repo path or zip file upload.
    Starts background pipeline and returns task_id immediately.
    """
    try:
        task_id = str(uuid.uuid4())
        repo_path = None
        use_bob = request.form.get('use_bob', 'true').lower() == 'true'
        
        # Check if it's a zip file upload
        if 'file' in request.files:
            file = request.files['file']
            
            if file.filename == '':
                return jsonify({'error': 'No file selected'}), 400
            
            if not file.filename or not allowed_file(file.filename):
                return jsonify({
                    'error': 'Invalid file type. Please upload a .zip file'
                }), 400
            
            # Save uploaded file
            filename = secure_filename(file.filename)
            upload_path = Path(app.config['UPLOAD_FOLDER']) / f"{task_id}_{filename}"
            file.save(upload_path)
            
            # Extract zip
            extract_dir = Path(app.config['TEMP_FOLDER']) / task_id
            extract_dir.mkdir(exist_ok=True)
            
            try:
                repo_path = str(extract_zip(upload_path, extract_dir))
                logger.info(f"Extracted zip to: {repo_path}")
            except Exception as e:
                return jsonify({
                    'error': f'Failed to extract zip file: {str(e)}'
                }), 400
        
        # Check if it's a local repo path or GitHub repository URL
        elif request.is_json and ('repo_path' in request.json or 'repo_url' in request.json):
            # Accept either a local path or a GitHub URL; if it's a URL, cloning
            # will be performed inside the background pipeline so the UI can see progress.
            repo_source = request.json.get('repo_path') or request.json.get('repo_url')
            repo_path = repo_source
        
        else:
            return jsonify({
                'error': 'No file or repository path provided'
            }), 400
        
        # Create task
        task = Task(
            task_id=task_id,
            status=TaskStatus.PENDING,
            progress=0,
            message="Task queued",
            repo_path=repo_path
        )
        tasks[task_id] = task
        
        # Start pipeline in background thread
        thread = threading.Thread(
            target=run_pipeline,
            args=(task_id, repo_path, use_bob),
            daemon=True
        )
        thread.start()
        
        logger.info(f"Started task {task_id} for repo: {repo_path}")
        
        return jsonify({
            'success': True,
            'task_id': task_id,
            'message': 'Scan started successfully'
        }), 202
    
    except Exception as e:
        logger.error(f"Scan error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/status/<task_id>', methods=['GET'])
def get_status(task_id: str):
    """
    Get the status of a background task.
    Returns progress, current step, and results when complete.
    """
    try:
        if task_id not in tasks:
            return jsonify({'error': 'Task not found'}), 404
        
        task = tasks[task_id]
        response = task.to_dict()
        
        # Include full results if completed
        if task.status == TaskStatus.COMPLETED:
            response['violations'] = task.violations
            response['fixes'] = task.fixes
            response['tests'] = task.tests
        
        return jsonify(response)
    
    except Exception as e:
        logger.error(f"Status check error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/report', methods=['GET'])
def get_report():
    """
    Get the latest report as JSON.
    """
    try:
        # Find the most recent JSON report
        output_dir = Path(app.config['OUTPUT_FOLDER'])
        json_files = sorted(
            list(output_dir.glob('report.json')) + list(output_dir.glob('analysis_report_*.json')),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )
        
        if not json_files:
            return jsonify({'error': 'No reports found'}), 404
        
        latest_report = json_files[0]
        
        with open(latest_report, 'r') as f:
            report_data = json.load(f)
        
        return jsonify(report_data)
    
    except Exception as e:
        logger.error(f"Report retrieval error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/chat', methods=['POST'])
@app.route('/api/chat', methods=['POST'])
def chat():
    """
    Interactive chat endpoint - sends message to Bob and returns response.
    """
    try:
        if not request.is_json:
            return jsonify({'error': 'Content-Type must be application/json'}), 400
        
        data = request.json
        message = data.get('message', '')
        context = data.get('context', {})
        
        if not message:
            return jsonify({'error': 'No message provided'}), 400
        
        # Initialize Bob client
        try:
            bob_client = BobClient()
        except Exception as e:
            return jsonify({
                'error': 'Bob API unavailable',
                'message': str(e)
            }), 503
        
        # Send message to Bob
        response = bob_client.chat(message, context)
        
        return jsonify({
            'success': True,
            'response': response.get('response', ''),
            'suggestions': response.get('suggestions', []),
            'timestamp': datetime.utcnow().isoformat()
        })
    
    except BobAPIError as e:
        logger.error(f"Bob API error: {e}")
        return jsonify({
            'error': 'Bob API error',
            'message': str(e)
        }), 503
    
    except Exception as e:
        logger.error(f"Chat error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/reports', methods=['GET'])
@app.route('/api/reports', methods=['GET'])
def list_reports():
    """
    List all available reports.
    """
    try:
        output_dir = Path(app.config['OUTPUT_FOLDER'])
        reports = []
        
        for report_file in list(output_dir.glob('report.json')) + list(output_dir.glob('analysis_report_*')):
            reports.append({
                'name': report_file.name,
                'path': str(report_file),
                'size': report_file.stat().st_size,
                'type': report_file.suffix[1:],  # Remove the dot
                'created': datetime.fromtimestamp(
                    report_file.stat().st_ctime
                ).isoformat()
            })
        
        # Sort by creation time (newest first)
        reports.sort(key=lambda x: x['created'], reverse=True)
        
        return jsonify({
            'success': True,
            'reports': reports,
            'count': len(reports)
        })
    
    except Exception as e:
        logger.error(f"Error listing reports: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/reports/<filename>', methods=['GET'])
@app.route('/api/reports/<filename>', methods=['GET'])
def download_report(filename: str):
    """
    Download a specific report file.
    """
    try:
        report_path = Path(app.config['OUTPUT_FOLDER']) / secure_filename(filename)
        
        if not report_path.exists():
            return jsonify({'error': 'Report not found'}), 404
        
        return send_file(
            report_path,
            as_attachment=True,
            download_name=filename
        )
    
    except Exception as e:
        logger.error(f"Error downloading report: {e}")
        return jsonify({'error': str(e)}), 500


# API alias for analyze (frontend expects /api/analyze)
@app.route('/api/analyze', methods=['POST'])
def api_analyze():
    return scan()


# API endpoint for remediation (frontend posts violations to /api/remediate)
@app.route('/api/remediate', methods=['POST'])
def api_remediate():
    try:
        if request.is_json:
            data = request.json
        else:
            # support form submissions
            data = request.form.to_dict()

        violations = data.get('violations', []) or []
        auto_apply = data.get('auto_apply', False)
        try:
            min_confidence = float(data.get('min_confidence', 0.7))
        except Exception:
            min_confidence = 0.7

        # Lazy import to avoid heavy dependencies at module import
        from src.remediator import Remediator
        from src.bob_client import BobClient

        bob_client = BobClient()
        remediator = Remediator(violations, bob_client, dry_run=not bool(auto_apply))

        # Prefer high-level method if available
        if hasattr(remediator, 'remediate_all'):
            report = remediator.remediate_all(min_confidence=min_confidence)
        elif hasattr(remediator, 'remediate'):
            report = remediator.remediate(violations, min_confidence=min_confidence)
        else:
            report = {}

        out = report.to_dict() if hasattr(report, 'to_dict') else report

        return jsonify({'success': True, 'report': out})

    except Exception as e:
        logger.error(f"API remediate error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


# Serve chat UI at /chat as well as /chat-ui
@app.route('/chat', methods=['GET'])
def chat_page():
    return render_template('chat.html')


@app.route('/health', methods=['GET'])
def health_check():
    """
    Health check endpoint for monitoring.
    """
    return jsonify({
        'status': 'healthy',
        'version': '1.0.0',
        'timestamp': datetime.utcnow().isoformat(),
        'active_tasks': len([t for t in tasks.values() 
                            if t.status not in [TaskStatus.COMPLETED, TaskStatus.FAILED]])
    })


# ============================================================================
# ERROR HANDLERS
# ============================================================================

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors."""
    return jsonify({
        'error': 'Not found',
        'message': 'The requested resource was not found'
    }), 404


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors."""
    logger.error(f"Internal error: {error}", exc_info=True)
    return jsonify({
        'error': 'Internal server error',
        'message': 'An unexpected error occurred'
    }), 500


@app.errorhandler(413)
def request_entity_too_large(error):
    """Handle file too large errors."""
    return jsonify({
        'error': 'File too large',
        'message': f'Maximum file size is {MAX_CONTENT_LENGTH // (1024*1024)}MB'
    }), 413


# ============================================================================
# MAIN
# ============================================================================

if __name__ == '__main__':
    # Run the Flask app
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_ENV', 'development') == 'development'
    
    logger.info("=" * 60)
    logger.info("Bob-Guard Web Server Starting")
    logger.info("=" * 60)
    logger.info(f"Port: {port}")
    logger.info(f"Debug mode: {debug}")
    logger.info(f"Upload folder: {UPLOAD_FOLDER}")
    logger.info(f"Output folder: {OUTPUT_FOLDER}")
    logger.info("=" * 60)
    
    app.run(host='0.0.0.0', port=port, debug=debug)

# Made with Bob
