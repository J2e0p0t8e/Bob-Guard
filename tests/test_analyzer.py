"""
Unit tests for the CodeAnalyzer module
"""

import pytest
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.analyzer import CodeAnalyzer, Violation, AnalysisResult


class TestCodeAnalyzer:
    """Test cases for CodeAnalyzer class"""

    def setup_method(self):
        """Setup test fixtures"""
        self.analyzer = CodeAnalyzer(config_path='config/rules.json')

    def test_analyzer_initialization(self):
        """Test analyzer initializes correctly"""
        assert self.analyzer is not None
        assert self.analyzer.config is not None
        assert isinstance(self.analyzer.config, dict)

    def test_supported_extensions(self):
        """Test supported file extensions"""
        assert '.py' in CodeAnalyzer.SUPPORTED_EXTENSIONS
        assert '.js' in CodeAnalyzer.SUPPORTED_EXTENSIONS
        assert '.java' in CodeAnalyzer.SUPPORTED_EXTENSIONS

    def test_analyze_file_content(self):
        """Test analyzing a code snippet"""
        code = """
def unsafe_query(user_input):
    query = "SELECT * FROM users WHERE id = " + user_input
    return execute(query)
"""
        violations = self.analyzer.analyze_file_content(code, 'python', 'test.py')
        
        # Should detect potential SQL injection
        assert isinstance(violations, list)

    def test_violation_creation(self):
        """Test Violation dataclass"""
        violation = Violation(
            id='test-001',
            severity='high',
            category='security',
            rule_id='sec-001',
            rule_name='SQL Injection',
            file_path='test.py',
            line_number=10,
            column=5,
            code_snippet='query = "SELECT * FROM users"',
            description='Potential SQL injection',
            recommendation='Use parameterized queries'
        )
        
        assert violation.id == 'test-001'
        assert violation.severity == 'high'
        assert violation.category == 'security'

    def test_violation_to_dict(self):
        """Test converting violation to dictionary"""
        violation = Violation(
            id='test-001',
            severity='high',
            category='security',
            rule_id='sec-001',
            rule_name='SQL Injection',
            file_path='test.py',
            line_number=10,
            column=5,
            code_snippet='query = "SELECT * FROM users"',
            description='Potential SQL injection',
            recommendation='Use parameterized queries'
        )
        
        violation_dict = violation.to_dict()
        assert isinstance(violation_dict, dict)
        assert violation_dict['id'] == 'test-001'
        assert violation_dict['severity'] == 'high'

    def test_get_violations_by_severity(self):
        """Test filtering violations by severity"""
        self.analyzer.violations = [
            Violation('1', 'critical', 'security', 'r1', 'Rule 1', 'f1.py', 1, None, '', '', ''),
            Violation('2', 'high', 'gdpr', 'r2', 'Rule 2', 'f2.py', 2, None, '', '', ''),
            Violation('3', 'critical', 'hipaa', 'r3', 'Rule 3', 'f3.py', 3, None, '', '', ''),
        ]
        
        critical = self.analyzer.get_violations_by_severity('critical')
        assert len(critical) == 2
        assert all(v.severity == 'critical' for v in critical)

    def test_get_violations_by_category(self):
        """Test filtering violations by category"""
        self.analyzer.violations = [
            Violation('1', 'critical', 'security', 'r1', 'Rule 1', 'f1.py', 1, None, '', '', ''),
            Violation('2', 'high', 'gdpr', 'r2', 'Rule 2', 'f2.py', 2, None, '', '', ''),
            Violation('3', 'critical', 'security', 'r3', 'Rule 3', 'f3.py', 3, None, '', '', ''),
        ]
        
        security = self.analyzer.get_violations_by_category('security')
        assert len(security) == 2
        assert all(v.category == 'security' for v in security)


class TestAnalysisResult:
    """Test cases for AnalysisResult dataclass"""

    def test_analysis_result_creation(self):
        """Test creating an AnalysisResult"""
        result = AnalysisResult(
            repository_path='/test/repo',
            total_files=10,
            analyzed_files=8,
            violations=[],
            summary={'total': 0},
            timestamp='2024-01-01T00:00:00'
        )
        
        assert result.repository_path == '/test/repo'
        assert result.total_files == 10
        assert result.analyzed_files == 8

    def test_analysis_result_to_dict(self):
        """Test converting AnalysisResult to dictionary"""
        result = AnalysisResult(
            repository_path='/test/repo',
            total_files=10,
            analyzed_files=8,
            violations=[],
            summary={'total': 0},
            timestamp='2024-01-01T00:00:00'
        )
        
        result_dict = result.to_dict()
        assert isinstance(result_dict, dict)
        assert result_dict['repository_path'] == '/test/repo'
        assert result_dict['total_files'] == 10


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

# Made with Bob
