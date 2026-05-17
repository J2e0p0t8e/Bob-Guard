"""
Bob-Guard Flask Web Application
Web interface for code analysis, remediation, and reporting.
"""

import os
import json
import logging
from pathlib import Path
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_file, session
from flask_cors import CORS
from werkzeug.utils import secure_filename

from src.analyzer import Analyzer, Violation
from src.remediator import CodeRemediator
from src.test_generator import TestGenerator
from src.reporter import ReportGenerator
from src.bob_client import BobClient, BobAPIError

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
CORS(app)

# Configuration
UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'output'
ALLOWED_EXTENSIONS = {'.py', '.js', '.ts', '.java', '.cpp', '.c', '.cs', '.go', '.rb', '.php'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['OUTPUT_FOLDER'] = OUTPUT_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Create necessary directories
Path(UPLOAD_FOLDER).mkdir(exist_ok=True)
Path(OUTPUT_FOLDER).mkdir(exist_ok=True)


def allowed_file(filename):
    """Check if file extension is allowed."""
    return Path(filename).suffix in ALLOWED_EXTENSIONS


@app.route('/')
def index():
    """Main landing page."""
    return render_template('index.html')


@app.route('/analyze')
def analyze_page():
    """Analysis page."""
    return render_template('index.html')


@app.route('/results')
def results_page():
    """Results page."""
    return render_template('results.html')


@app.route('/chat')
def chat_page():
    """Interactive chat page."""
    return render_template('chat.html')


@app.route('/api/analyze', methods=['POST'])
def api_analyze():
    """
    API endpoint to analyze code.
    Accepts either a file upload or repository path.
    """
    try:
        # Check if it's a file upload or repository path
        if 'file' in request.files:
            file = request.files['file']
            if file.filename == '':
                return jsonify({'error': 'No file selected'}), 400
            
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                filepath = Path(app.config['UPLOAD_FOLDER']) / filename
                file.save(filepath)
                
                # Analyze single file
                analyzer = Analyzer(repo_path=str(filepath.parent), rules=[])
                violations = analyzer.analyze_file(filepath)
                
                result = {
                    'success': True,
                    'file': filename,
                    'violations': [v.to_dict() for v in violations],
                    'total_violations': len(violations)
                }
                
                return jsonify(result)
        
        elif 'repo_path' in request.json:
            repo_path = request.json['repo_path']
            
            if not Path(repo_path).exists():
                return jsonify({'error': 'Repository path does not exist'}), 400
            
            # Analyze repository
            analyzer = Analyzer(repo_path=repo_path, rules=[])
            violations = analyzer.scan_repository()
            
            result = {
                'success': True,
                'repository': repo_path,
                'total_files': len(list(Path(repo_path).rglob('*'))),
                'analyzed_files': len(violations),
                'violations': [v.to_dict() for v in violations],
                'summary': {'total': len(violations)}
            }
            
            return jsonify(result)
        
        return jsonify({'error': 'No file or repository path provided'}), 400
    
    except Exception as e:
        logger.error(f"Analysis error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/remediate', methods=['POST'])
def api_remediate():
    """
    API endpoint to generate and apply fixes.
    """
    try:
        data = request.json
        violations_data = data.get('violations', [])
        auto_apply = data.get('auto_apply', False)
        min_confidence = data.get('min_confidence', 0.7)
        
        if not violations_data:
            return jsonify({'error': 'No violations provided'}), 400
        
        # Convert violation data back to Violation objects
        violations = []
        for v_data in violations_data:
            violation = Violation(
                id=v_data['id'],
                severity=v_data['severity'],
                category=v_data['category'],
                rule_id=v_data['rule_id'],
                rule_name=v_data['rule_name'],
                file_path=v_data['file_path'],
                line_number=v_data['line_number'],
                column=v_data.get('column'),
                code_snippet=v_data['code_snippet'],
                description=v_data['description'],
                recommendation=v_data['recommendation'],
                context_before=v_data.get('context_before', []),
                context_after=v_data.get('context_after', []),
                explanation=v_data.get('explanation', ''),
                confidence=v_data.get('confidence', 0.8)
            )
            violations.append(violation)
        
        # Generate fixes
        remediator = CodeRemediator()
        fixes = remediator.generate_fixes(violations, min_confidence)
        
        # Apply fixes if requested
        if auto_apply:
            remediation_result = remediator.apply_fixes(fixes, auto_apply=True)
        else:
            remediation_result = None
        
        result = {
            'success': True,
            'fixes_generated': len(fixes),
            'fixes': [f.to_dict() for f in fixes],
            'applied': auto_apply,
            'fixes_applied': remediation_result.fixes_applied if remediation_result else 0
        }
        
        return jsonify(result)
    
    except Exception as e:
        logger.error(f"Remediation error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/generate-tests', methods=['POST'])
def api_generate_tests():
    """
    API endpoint to generate unit tests.
    """
    try:
        data = request.json
        fixes_data = data.get('fixes', [])
        
        if not fixes_data:
            return jsonify({'error': 'No fixes provided'}), 400
        
        # Convert fix data back to Fix objects
        from src.remediator import Fix
        fixes = []
        for f_data in fixes_data:
            fix = Fix(
                violation_id=f_data['violation_id'],
                file_path=f_data['file_path'],
                original_code=f_data['original_code'],
                fixed_code=f_data['fixed_code'],
                explanation=f_data['explanation'],
                confidence=f_data['confidence'],
                applied=f_data.get('applied', False),
                backup_path=f_data.get('backup_path')
            )
            fixes.append(fix)
        
        # Generate tests
        test_generator = TestGenerator()
        test_result = test_generator.generate_tests_for_fixes(fixes)
        
        result = {
            'success': True,
            'tests_generated': test_result.tests_generated,
            'test_suites': [ts.to_dict() for ts in test_result.test_suites]
        }
        
        return jsonify(result)
    
    except Exception as e:
        logger.error(f"Test generation error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/chat', methods=['POST'])
def api_chat():
    """
    API endpoint for interactive chat with Bob.
    """
    try:
        data = request.json
        message = data.get('message', '')
        context = data.get('context', {})
        
        if not message:
            return jsonify({'error': 'No message provided'}), 400
        
        # Use Bob API for chat
        bob_client = BobClient()
        response = bob_client.chat(message, context)
        
        result = {
            'success': True,
            'response': response.get('response', ''),
            'suggestions': response.get('suggestions', [])
        }
        
        return jsonify(result)
    
    except BobAPIError as e:
        logger.error(f"Bob API error: {e}")
        return jsonify({'error': 'Bob API unavailable', 'message': str(e)}), 503
    except Exception as e:
        logger.error(f"Chat error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/reports')
def api_list_reports():
    """
    API endpoint to list available reports.
    """
    try:
        output_dir = Path(app.config['OUTPUT_FOLDER'])
        reports = []
        
        for report_file in output_dir.glob('*.html'):
            reports.append({
                'name': report_file.name,
                'path': str(report_file),
                'size': report_file.stat().st_size,
                'created': datetime.fromtimestamp(report_file.stat().st_ctime).isoformat()
            })
        
        return jsonify({'success': True, 'reports': reports})
    
    except Exception as e:
        logger.error(f"Error listing reports: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/reports/<filename>')
def api_get_report(filename):
    """
    API endpoint to download a specific report.
    """
    try:
        report_path = Path(app.config['OUTPUT_FOLDER']) / secure_filename(filename)
        
        if not report_path.exists():
            return jsonify({'error': 'Report not found'}), 404
        
        return send_file(report_path, as_attachment=True)
    
    except Exception as e:
        logger.error(f"Error retrieving report: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/health')
def api_health():
    """
    Health check endpoint.
    """
    return jsonify({
        'status': 'healthy',
        'version': '1.0.0',
        'timestamp': datetime.utcnow().isoformat()
    })


@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors."""
    return jsonify({'error': 'Not found'}), 404


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors."""
    logger.error(f"Internal error: {error}")
    return jsonify({'error': 'Internal server error'}), 500


if __name__ == '__main__':
    # Run the Flask app
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_ENV') == 'development'
    
    logger.info(f"Starting Bob-Guard web server on port {port}")
    app.run(host='0.0.0.0', port=port, debug=debug)

# Made with Bob
