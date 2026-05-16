"""
Code Analyzer Module
Scans legacy codebases for compliance violations and security vulnerabilities.
"""

import os
import ast
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, asdict
import subprocess

# Third-party imports
try:
    import bandit
    from bandit.core import manager as bandit_manager
except ImportError:
    bandit = None

try:
    import git
except ImportError:
    git = None

from src.bob_client import BobClient, BobAPIError

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class Violation:
    """Represents a compliance or security violation."""
    id: str
    severity: str  # 'critical', 'high', 'medium', 'low'
    category: str  # 'gdpr', 'hipaa', 'security', 'custom'
    rule_id: str
    rule_name: str
    file_path: str
    line_number: int
    column: Optional[int]
    code_snippet: str
    description: str
    recommendation: str
    cwe_id: Optional[str] = None
    cvss_score: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert violation to dictionary."""
        return asdict(self)


@dataclass
class AnalysisResult:
    """Contains the complete analysis results."""
    repository_path: str
    total_files: int
    analyzed_files: int
    violations: List[Violation]
    summary: Dict[str, Any]
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert analysis result to dictionary."""
        return {
            'repository_path': self.repository_path,
            'total_files': self.total_files,
            'analyzed_files': self.analyzed_files,
            'violations': [v.to_dict() for v in self.violations],
            'summary': self.summary,
            'timestamp': self.timestamp
        }


class CodeAnalyzer:
    """
    Main analyzer class for detecting compliance and security issues.
    Integrates multiple analysis tools and IBM Bob API.
    """

    SUPPORTED_EXTENSIONS = {
        '.py': 'python',
        '.js': 'javascript',
        '.ts': 'typescript',
        '.java': 'java',
        '.cpp': 'cpp',
        '.c': 'c',
        '.cs': 'csharp',
        '.go': 'go',
        '.rb': 'ruby',
        '.php': 'php'
    }

    def __init__(self, config_path: Optional[str] = None, bob_client: Optional[BobClient] = None):
        """
        Initialize the code analyzer.
        
        Args:
            config_path: Path to rules configuration file
            bob_client: Optional BobClient instance (creates new if not provided)
        """
        self.config = self._load_config(config_path or 'config/rules.json')
        self.bob_client = bob_client or BobClient()
        self.violations: List[Violation] = []

    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load compliance rules configuration."""
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.warning(f"Config file not found: {config_path}. Using default config.")
            return self._get_default_config()
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in config file: {e}")
            return self._get_default_config()

    def _get_default_config(self) -> Dict[str, Any]:
        """Return default configuration."""
        return {
            'gdpr': {'enabled': True, 'rules': []},
            'hipaa': {'enabled': True, 'rules': []},
            'security': {'enabled': True, 'rules': []},
            'custom': {'enabled': False, 'rules': []}
        }

    def analyze_repository(self, repo_path: str) -> AnalysisResult:
        """
        Analyze an entire repository.
        
        Args:
            repo_path: Path to the repository
            
        Returns:
            AnalysisResult containing all violations found
        """
        logger.info(f"Starting analysis of repository: {repo_path}")
        self.violations = []
        
        repo_path_obj = Path(repo_path)
        if not repo_path_obj.exists():
            raise ValueError(f"Repository path does not exist: {repo_path}")

        # Collect all source files
        source_files = self._collect_source_files(repo_path_obj)
        logger.info(f"Found {len(source_files)} source files to analyze")

        # Analyze each file
        analyzed_count = 0
        for file_path in source_files:
            try:
                self._analyze_file(file_path)
                analyzed_count += 1
            except Exception as e:
                logger.error(f"Error analyzing {file_path}: {e}")

        # Generate summary
        summary = self._generate_summary()
        
        from datetime import datetime
        result = AnalysisResult(
            repository_path=str(repo_path),
            total_files=len(source_files),
            analyzed_files=analyzed_count,
            violations=self.violations,
            summary=summary,
            timestamp=datetime.utcnow().isoformat()
        )

        logger.info(f"Analysis complete. Found {len(self.violations)} violations.")
        return result

    def _collect_source_files(self, repo_path: Path) -> List[Path]:
        """Collect all source files from repository."""
        source_files = []
        
        # Directories to exclude
        exclude_dirs = {'.git', 'node_modules', 'venv', '__pycache__', 
                       'build', 'dist', '.vscode', '.idea', 'target'}
        
        for ext in self.SUPPORTED_EXTENSIONS.keys():
            for file_path in repo_path.rglob(f'*{ext}'):
                # Skip excluded directories
                if any(excluded in file_path.parts for excluded in exclude_dirs):
                    continue
                source_files.append(file_path)
        
        return source_files

    def _analyze_file(self, file_path: Path):
        """Analyze a single file for violations."""
        logger.debug(f"Analyzing file: {file_path}")
        
        # Read file content
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                code = f.read()
        except Exception as e:
            logger.error(f"Could not read file {file_path}: {e}")
            return

        # Determine language
        language = self.SUPPORTED_EXTENSIONS.get(file_path.suffix)
        if not language:
            return

        # Run static analysis tools
        self._run_static_analysis(file_path, code, language)
        
        # Use Bob API for intelligent analysis
        self._run_bob_analysis(file_path, code, language)

    def _run_static_analysis(self, file_path: Path, code: str, language: str):
        """Run static analysis tools (Bandit, etc.)."""
        if language == 'python' and bandit:
            self._run_bandit_analysis(file_path, code)

    def _run_bandit_analysis(self, file_path: Path, code: str):
        """Run Bandit security analysis for Python code."""
        # Placeholder for Bandit integration
        # In production, this would use Bandit's API
        logger.debug(f"Running Bandit analysis on {file_path}")
        pass

    def _run_bob_analysis(self, file_path: Path, code: str, language: str):
        """Use IBM Bob API for intelligent code analysis."""
        try:
            # Get enabled rule categories
            enabled_rules = []
            for category, config in self.config.items():
                if config.get('enabled', False):
                    enabled_rules.extend(config.get('rules', []))

            # Analyze with Bob
            result = self.bob_client.analyze_code(code, language, enabled_rules)
            
            # Process violations from Bob's response
            for violation_data in result.get('violations', []):
                violation = Violation(
                    id=violation_data.get('id', ''),
                    severity=violation_data.get('severity', 'medium'),
                    category=violation_data.get('category', 'security'),
                    rule_id=violation_data.get('rule_id', ''),
                    rule_name=violation_data.get('rule_name', ''),
                    file_path=str(file_path),
                    line_number=violation_data.get('line_number', 0),
                    column=violation_data.get('column'),
                    code_snippet=violation_data.get('code_snippet', ''),
                    description=violation_data.get('description', ''),
                    recommendation=violation_data.get('recommendation', ''),
                    cwe_id=violation_data.get('cwe_id'),
                    cvss_score=violation_data.get('cvss_score')
                )
                self.violations.append(violation)
                
        except BobAPIError as e:
            logger.error(f"Bob API error analyzing {file_path}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error in Bob analysis: {e}")

    def _generate_summary(self) -> Dict[str, Any]:
        """Generate summary statistics from violations."""
        summary = {
            'total_violations': len(self.violations),
            'by_severity': {'critical': 0, 'high': 0, 'medium': 0, 'low': 0},
            'by_category': {},
            'top_violations': []
        }

        # Count by severity
        for violation in self.violations:
            severity = violation.severity.lower()
            if severity in summary['by_severity']:
                summary['by_severity'][severity] += 1

        # Count by category
        for violation in self.violations:
            category = violation.category
            summary['by_category'][category] = summary['by_category'].get(category, 0) + 1

        # Get top violations (by severity)
        critical_violations = [v for v in self.violations if v.severity.lower() == 'critical']
        high_violations = [v for v in self.violations if v.severity.lower() == 'high']
        summary['top_violations'] = (critical_violations + high_violations)[:10]

        return summary

    def analyze_file_content(self, code: str, language: str, file_path: str = "unknown") -> List[Violation]:
        """
        Analyze a single code snippet.
        
        Args:
            code: Source code to analyze
            language: Programming language
            file_path: Optional file path for context
            
        Returns:
            List of violations found
        """
        self.violations = []
        file_path_obj = Path(file_path)
        self._run_bob_analysis(file_path_obj, code, language)
        return self.violations

    def get_violations_by_severity(self, severity: str) -> List[Violation]:
        """Get all violations of a specific severity."""
        return [v for v in self.violations if v.severity.lower() == severity.lower()]

    def get_violations_by_category(self, category: str) -> List[Violation]:
        """Get all violations of a specific category."""
        return [v for v in self.violations if v.category.lower() == category.lower()]

    def export_results(self, output_path: str, format: str = 'json'):
        """
        Export analysis results to file.
        
        Args:
            output_path: Path to output file
            format: Output format ('json' or 'csv')
        """
        if format == 'json':
            with open(output_path, 'w') as f:
                json.dump([v.to_dict() for v in self.violations], f, indent=2)
        elif format == 'csv':
            import csv
            with open(output_path, 'w', newline='') as f:
                if self.violations:
                    writer = csv.DictWriter(f, fieldnames=self.violations[0].to_dict().keys())
                    writer.writeheader()
                    for violation in self.violations:
                        writer.writerow(violation.to_dict())

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if hasattr(self.bob_client, 'close'):
            self.bob_client.close()

# Made with Bob
