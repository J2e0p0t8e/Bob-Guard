"""
Example usage of the Remediator module.

This script demonstrates how to use the remediation functionality
to automatically fix code violations detected by Bob-Guard.
"""

import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.analyzer import Violation
from src.bob_client import BobClient
from src.remediator import Remediator, quick_remediate


def example_basic_usage():
    """
    Basic example: Remediate violations with dry-run mode.
    """
    print("=" * 60)
    print("Example 1: Basic Remediation (Dry-Run)")
    print("=" * 60)
    
    # Create sample violations
    violations = [
        Violation(
            id="V001",
            rule_id="SEC-001",
            rule_name="SQL Injection",
            category="SECURITY",
            severity="CRITICAL",
            file_path="vulnerable_app.py",
            line_number=45,
            column=8,
            code_snippet='cursor.execute("SELECT * FROM users WHERE id = " + user_id)',
            context_before=["def get_user(user_id):"],
            context_after=["    return cursor.fetchone()"],
            description="SQL injection vulnerability detected",
            explanation="Direct string concatenation in SQL query allows injection attacks",
            recommendation="Use parameterized queries with placeholders",
            confidence=0.95
        ),
        Violation(
            id="V002",
            rule_id="SEC-002",
            rule_name="Hardcoded Credentials",
            category="SECURITY",
            severity="HIGH",
            file_path="config.py",
            line_number=12,
            column=0,
            code_snippet='API_KEY = "sk-1234567890abcdef"',
            context_before=["# API Configuration"],
            context_after=["API_ENDPOINT = 'https://api.example.com'"],
            description="Hardcoded API key detected",
            explanation="Sensitive credentials should not be stored in source code",
            recommendation="Use environment variables or secure key management",
            confidence=0.98
        )
    ]
    
    # Initialize Bob client
    bob_client = BobClient()
    
    # Create remediator in dry-run mode (safe, no changes applied)
    remediator = Remediator(violations, bob_client, dry_run=True)
    
    # Remediate all violations
    report = remediator.remediate_all()
    
    # Display results
    print(f"\nRemediation Report:")
    print(f"  Total Violations: {report.total_violations}")
    print(f"  Successful Fixes: {report.successful_fixes}")
    print(f"  Failed Fixes: {report.failed_fixes}")
    print(f"  Skipped: {report.skipped_fixes}")
    print(f"  Dry Run: {report.dry_run}")
    print(f"  Execution Time: {report.execution_time:.2f}s")
    
    # Show individual results
    print("\nIndividual Results:")
    for result in report.results:
        print(f"\n  Violation {result.violation_id}:")
        print(f"    File: {result.file_path}")
        print(f"    Status: {result.status}")
        print(f"    Confidence: {result.confidence:.2f}")
        if result.diff:
            print(f"    Diff Preview: {result.diff[:100]}...")


def example_apply_fixes():
    """
    Example: Apply fixes to actual files (not dry-run).
    """
    print("\n" + "=" * 60)
    print("Example 2: Apply Fixes (Production Mode)")
    print("=" * 60)
    
    violations = [
        Violation(
            id="V003",
            rule_id="QUAL-001",
            rule_name="Code Duplication",
            category="QUALITY",
            severity="MEDIUM",
            file_path="utils.py",
            line_number=100,
            column=0,
            code_snippet="def process_data(data):\n    # Duplicated logic",
            context_before=["# Data processing utilities"],
            context_after=["    return result"],
            description="Duplicated code detected",
            explanation="Same logic appears in multiple places",
            recommendation="Extract to shared function",
            confidence=0.85
        )
    ]
    
    bob_client = BobClient()
    
    # Create remediator with dry_run=False to apply changes
    remediator = Remediator(violations, bob_client, dry_run=False)
    
    print("\nWARNING: This will modify actual files!")
    print("Backups will be created with .backup extension")
    
    # In production, you would call:
    # report = remediator.remediate_all()
    
    print("\n(Skipped in example - set dry_run=False to apply)")


def example_quick_remediate():
    """
    Example: Use convenience function for quick remediation.
    """
    print("\n" + "=" * 60)
    print("Example 3: Quick Remediation")
    print("=" * 60)
    
    violations = [
        Violation(
            id="V004",
            rule_id="SEC-003",
            rule_name="Weak Cryptography",
            category="SECURITY",
            severity="HIGH",
            file_path="crypto.py",
            line_number=25,
            column=4,
            code_snippet="hash = md5(password).hexdigest()",
            context_before=["def hash_password(password):"],
            context_after=["    return hash"],
            description="Weak hashing algorithm",
            explanation="MD5 is cryptographically broken",
            recommendation="Use bcrypt or Argon2",
            confidence=0.99
        )
    ]
    
    # Quick remediation without managing client
    report = quick_remediate(
        violations,
        api_key=os.getenv('IBM_BOB_API_KEY'),
        dry_run=True
    )
    
    print(f"\nQuick Remediation Complete:")
    print(f"  Processed: {report.total_violations} violations")
    print(f"  Success Rate: {report.successful_fixes}/{report.total_violations}")


def example_severity_prioritization():
    """
    Example: Demonstrate severity-based prioritization.
    """
    print("\n" + "=" * 60)
    print("Example 4: Severity Prioritization")
    print("=" * 60)
    
    # Create violations with different severities
    violations = [
        Violation(
            id="V005", rule_id="QUAL-002", rule_name="Code Style",
            category="QUALITY", severity="LOW", file_path="app.py",
            line_number=10, column=0, code_snippet="x=1",
            context_before=[], context_after=[],
            description="Missing spaces", explanation="PEP 8 violation",
            recommendation="Add spaces", confidence=0.9
        ),
        Violation(
            id="V006", rule_id="SEC-004", rule_name="XSS Vulnerability",
            category="SECURITY", severity="CRITICAL", file_path="app.py",
            line_number=50, column=0, code_snippet="return user_input",
            context_before=[], context_after=[],
            description="XSS risk", explanation="Unescaped output",
            recommendation="Escape HTML", confidence=0.95
        ),
        Violation(
            id="V007", rule_id="SEC-005", rule_name="Path Traversal",
            category="SECURITY", severity="HIGH", file_path="app.py",
            line_number=75, column=0, code_snippet="open(user_path)",
            context_before=[], context_after=[],
            description="Path traversal", explanation="Unsanitized path",
            recommendation="Validate path", confidence=0.92
        )
    ]
    
    bob_client = BobClient()
    remediator = Remediator(violations, bob_client, dry_run=True)
    
    # Violations are automatically sorted by severity
    sorted_violations = remediator._sort_by_severity(violations)
    
    print("\nProcessing Order (by severity):")
    for i, v in enumerate(sorted_violations, 1):
        print(f"  {i}. [{v.severity}] {v.rule_name} (ID: {v.id})")
    
    print("\nCRITICAL and HIGH severity issues are fixed first!")


def example_file_grouping():
    """
    Example: Demonstrate file-based grouping to avoid conflicts.
    """
    print("\n" + "=" * 60)
    print("Example 5: File Grouping")
    print("=" * 60)
    
    violations = [
        Violation(
            id="V008", rule_id="SEC-006", rule_name="Issue 1",
            category="SECURITY", severity="HIGH", file_path="module_a.py",
            line_number=10, column=0, code_snippet="code1",
            context_before=[], context_after=[],
            description="Issue 1", explanation="Explanation 1",
            recommendation="Fix 1", confidence=0.9
        ),
        Violation(
            id="V009", rule_id="SEC-007", rule_name="Issue 2",
            category="SECURITY", severity="HIGH", file_path="module_a.py",
            line_number=20, column=0, code_snippet="code2",
            context_before=[], context_after=[],
            description="Issue 2", explanation="Explanation 2",
            recommendation="Fix 2", confidence=0.9
        ),
        Violation(
            id="V010", rule_id="SEC-008", rule_name="Issue 3",
            category="SECURITY", severity="MEDIUM", file_path="module_b.py",
            line_number=30, column=0, code_snippet="code3",
            context_before=[], context_after=[],
            description="Issue 3", explanation="Explanation 3",
            recommendation="Fix 3", confidence=0.85
        )
    ]
    
    bob_client = BobClient()
    remediator = Remediator(violations, bob_client, dry_run=True)
    
    # Group violations by file
    grouped = remediator._group_by_file(violations)
    
    print("\nViolations Grouped by File:")
    for file_path, file_violations in grouped.items():
        print(f"\n  {file_path}:")
        for v in file_violations:
            print(f"    - {v.id}: {v.rule_name}")
    
    print("\nAll violations in the same file are fixed together")
    print("to avoid conflicts and ensure consistency!")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("Bob-Guard Remediation Module Examples")
    print("=" * 60)
    
    try:
        # Run examples
        example_basic_usage()
        example_apply_fixes()
        example_quick_remediate()
        example_severity_prioritization()
        example_file_grouping()
        
        print("\n" + "=" * 60)
        print("All examples completed successfully!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\nError running examples: {e}")
        print("Note: These examples require IBM_BOB_API_KEY to be set")
        print("and the Bob API to be accessible.")

# Made with Bob
