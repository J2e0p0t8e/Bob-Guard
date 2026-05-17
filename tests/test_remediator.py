"""
Unit tests for the Remediator module.
Tests fix generation, application, and validation logic.
"""

import os
import tempfile
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from src.remediator import (
    Remediator, 
    RemediationResult, 
    RemediationReport,
    quick_remediate
)
from src.analyzer import Violation
from src.bob_client import BobClient, BobAPIError


@pytest.fixture
def sample_violations():
    """Create sample violations for testing."""
    return [
        Violation(
            id="V001",
            rule_id="SEC-001",
            rule_name="SQL Injection",
            category="SECURITY",
            severity="CRITICAL",
            file_path="test.py",
            line_number=10,
            column=5,
            code_snippet='cursor.execute("SELECT * FROM users WHERE id = " + user_id)',
            context_before=["def get_user(user_id):"],
            context_after=["    return cursor.fetchone()"],
            description="SQL injection vulnerability",
            explanation="Direct string concatenation in SQL query",
            recommendation="Use parameterized queries",
            confidence=0.95
        ),
        Violation(
            id="V002",
            rule_id="SEC-002",
            rule_name="Hardcoded Password",
            category="SECURITY",
            severity="HIGH",
            file_path="test.py",
            line_number=5,
            column=0,
            code_snippet='password = "admin123"',
            context_before=["# Configuration"],
            context_after=["username = 'admin'"],
            description="Hardcoded password detected",
            explanation="Password stored in plain text",
            recommendation="Use environment variables",
            confidence=0.98
        ),
        Violation(
            id="V003",
            rule_id="QUAL-001",
            rule_name="Code Complexity",
            category="QUALITY",
            severity="MEDIUM",
            file_path="utils.py",
            line_number=20,
            column=0,
            code_snippet="def complex_function():\n    # 50 lines of code",
            context_before=["# Utilities"],
            context_after=["    return result"],
            description="Function too complex",
            explanation="Cyclomatic complexity too high",
            recommendation="Refactor into smaller functions",
            confidence=0.85
        )
    ]


@pytest.fixture
def mock_bob_client():
    """Create a mock BobClient."""
    client = Mock(spec=BobClient)
    client.generate_fix.return_value = {
        'fixed_code': 'cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))',
        'explanation': 'Replaced string concatenation with parameterized query',
        'confidence': 0.95,
        'diff': '--- original\n+++ fixed\n...'
    }
    return client


class TestRemediationResult:
    """Tests for RemediationResult dataclass."""
    
    def test_creation(self):
        """Test creating a RemediationResult."""
        result = RemediationResult(
            violation_id="V001",
            file_path="test.py",
            original_code="bad code",
            fixed_code="good code",
            diff="--- bad\n+++ good",
            status="SUCCESS",
            confidence=0.95
        )
        
        assert result.violation_id == "V001"
        assert result.status == "SUCCESS"
        assert result.confidence == 0.95
        assert result.applied_at is not None
    
    def test_to_dict(self):
        """Test converting result to dictionary."""
        result = RemediationResult(
            violation_id="V001",
            file_path="test.py",
            original_code="bad",
            fixed_code="good",
            diff="diff",
            status="SUCCESS"
        )
        
        result_dict = result.to_dict()
        assert isinstance(result_dict, dict)
        assert result_dict['violation_id'] == "V001"
        assert result_dict['status'] == "SUCCESS"


class TestRemediationReport:
    """Tests for RemediationReport dataclass."""
    
    def test_creation(self):
        """Test creating a RemediationReport."""
        results = [
            RemediationResult("V001", "test.py", "old", "new", "diff", "SUCCESS"),
            RemediationResult("V002", "test.py", "old2", "new2", "diff2", "FAILED")
        ]
        
        report = RemediationReport(
            total_violations=2,
            successful_fixes=1,
            failed_fixes=1,
            skipped_fixes=0,
            dry_run=True,
            results=results,
            files_modified=["test.py"]
        )
        
        assert report.total_violations == 2
        assert report.successful_fixes == 1
        assert report.failed_fixes == 1
        assert len(report.results) == 2
    
    def test_to_dict(self):
        """Test converting report to dictionary."""
        results = [
            RemediationResult("V001", "test.py", "old", "new", "diff", "SUCCESS")
        ]
        
        report = RemediationReport(
            total_violations=1,
            successful_fixes=1,
            failed_fixes=0,
            skipped_fixes=0,
            dry_run=True,
            results=results,
            files_modified=["test.py"]
        )
        
        report_dict = report.to_dict()
        assert isinstance(report_dict, dict)
        assert report_dict['total_violations'] == 1
        assert len(report_dict['results']) == 1


class TestRemediator:
    """Tests for Remediator class."""
    
    def test_initialization(self, sample_violations, mock_bob_client):
        """Test Remediator initialization."""
        remediator = Remediator(sample_violations, mock_bob_client, dry_run=True)
        
        assert len(remediator.violations) == 3
        assert remediator.dry_run is True
        assert remediator.bob_client == mock_bob_client
        assert len(remediator.results) == 0
    
    def test_sort_by_severity(self, sample_violations, mock_bob_client):
        """Test sorting violations by severity."""
        remediator = Remediator(sample_violations, mock_bob_client)
        sorted_violations = remediator._sort_by_severity(sample_violations)
        
        # CRITICAL should be first, then HIGH, then MEDIUM
        assert sorted_violations[0].severity == "CRITICAL"
        assert sorted_violations[1].severity == "HIGH"
        assert sorted_violations[2].severity == "MEDIUM"
    
    def test_group_by_file(self, sample_violations, mock_bob_client):
        """Test grouping violations by file."""
        remediator = Remediator(sample_violations, mock_bob_client)
        grouped = remediator._group_by_file(sample_violations)
        
        assert "test.py" in grouped
        assert "utils.py" in grouped
        assert len(grouped["test.py"]) == 2
        assert len(grouped["utils.py"]) == 1
    
    def test_generate_diff(self, mock_bob_client):
        """Test diff generation."""
        remediator = Remediator([], mock_bob_client)
        
        original = "line1\nline2\nline3"
        fixed = "line1\nline2_modified\nline3"
        
        diff = remediator._generate_diff(original, fixed, "test.py")
        
        assert "test.py" in diff
        assert "-line2" in diff or "line2" in diff
        assert "+line2_modified" in diff or "line2_modified" in diff
    
    def test_validate_python_syntax(self, mock_bob_client):
        """Test Python syntax validation."""
        remediator = Remediator([], mock_bob_client)
        
        # Valid Python
        assert remediator._validate_python_syntax("x = 1\nprint(x)") is True
        
        # Invalid Python
        assert remediator._validate_python_syntax("x = 1\nprint(x") is False
    
    def test_validate_javascript_syntax(self, mock_bob_client):
        """Test JavaScript syntax validation."""
        remediator = Remediator([], mock_bob_client)
        
        # Valid JavaScript
        assert remediator._validate_javascript_syntax("const x = {a: 1};") is True
        
        # Invalid JavaScript (mismatched braces)
        assert remediator._validate_javascript_syntax("const x = {a: 1;") is False
    
    def test_get_language_from_extension(self, mock_bob_client):
        """Test language detection from file extension."""
        remediator = Remediator([], mock_bob_client)
        
        assert remediator._get_language_from_extension(".py") == "python"
        assert remediator._get_language_from_extension(".js") == "javascript"
        assert remediator._get_language_from_extension(".java") == "java"
        assert remediator._get_language_from_extension(".unknown") is None
    
    @patch('builtins.open', create=True)
    @patch('os.path.exists')
    def test_remediate_file_dry_run(self, mock_exists, mock_open, mock_bob_client):
        """Test file remediation in dry-run mode."""
        mock_exists.return_value = True
        mock_open.return_value.__enter__.return_value.read.return_value = \
            'cursor.execute("SELECT * FROM users WHERE id = " + user_id)'
        
        violation = Violation(
            id="V001",
            rule_id="SEC-001",
            rule_name="SQL Injection",
            category="SECURITY",
            severity="CRITICAL",
            file_path="test.py",
            line_number=10,
            column=5,
            code_snippet='cursor.execute("SELECT * FROM users WHERE id = " + user_id)',
            context_before=[],
            context_after=[],
            description="SQL injection",
            explanation="Direct concatenation",
            recommendation="Use parameterized queries",
            confidence=0.95
        )
        
        remediator = Remediator([violation], mock_bob_client, dry_run=True)
        results = remediator.remediate_file("test.py", [violation])
        
        assert len(results) == 1
        assert results[0].status == "DRY_RUN"
        assert results[0].violation_id == "V001"
    
    def test_remediate_all_dry_run(self, sample_violations, mock_bob_client):
        """Test remediating all violations in dry-run mode."""
        remediator = Remediator(sample_violations, mock_bob_client, dry_run=True)
        
        with patch.object(remediator, 'remediate_file') as mock_remediate:
            mock_remediate.return_value = [
                RemediationResult("V001", "test.py", "old", "new", "diff", "DRY_RUN")
            ]
            
            report = remediator.remediate_all()
            
            assert report.dry_run is True
            assert report.total_violations >= 0
            assert mock_remediate.called
    
    @patch('shutil.copy2')
    @patch('builtins.open', create=True)
    def test_apply_patch(self, mock_open, mock_copy, mock_bob_client):
        """Test applying a patch with backup."""
        remediator = Remediator([], mock_bob_client, dry_run=False)
        
        original = "x = 1"
        patched = "x = 2"
        
        backup_path = remediator.apply_patch("test.py", original, patched)
        
        assert backup_path == "test.py.backup"
        assert mock_copy.called
        assert mock_open.called


class TestQuickRemediate:
    """Tests for quick_remediate convenience function."""
    
    @patch('src.remediator.BobClient')
    def test_quick_remediate(self, mock_client_class, sample_violations):
        """Test quick remediation function."""
        mock_client = Mock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_client.generate_fix.return_value = {
            'fixed_code': 'fixed',
            'explanation': 'explanation',
            'confidence': 0.9
        }
        
        with patch('os.path.exists', return_value=True), \
             patch('builtins.open', create=True) as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = "code"
            
            report = quick_remediate(sample_violations, api_key="test_key", dry_run=True)
            
            assert isinstance(report, RemediationReport)
            assert report.dry_run is True


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

# Made with Bob
