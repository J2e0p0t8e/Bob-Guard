"""
Report Generator Module
Generates detailed HTML and JSON reports for analysis results.
"""

import os
import json
import logging
import difflib
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
from jinja2 import Environment, FileSystemLoader, select_autoescape

from src.analyzer import AnalysisResult, Violation
from src.remediator import RemediationResult, Fix
from src.test_generator import TestGenerationResult, TestSuiteResult
from src.bob_client import BobClient, BobAPIError

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ReportGenerator:
    """
    Main report generator class for creating analysis reports.
    Supports HTML, JSON, and Markdown formats.
    """

    def __init__(self, template_dir: str = 'templates', output_dir: str = 'output'):
        """
        Initialize the report generator.
        
        Args:
            template_dir: Directory containing Jinja2 templates
            output_dir: Directory to store generated reports
        """
        self.template_dir = Path(template_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Initialize Jinja2 environment
        self.jinja_env = Environment(
            loader=FileSystemLoader(str(self.template_dir)),
            autoescape=select_autoescape(['html', 'xml'])
        )

    def generate_analysis_report(self, analysis_result: AnalysisResult, 
                                 format: str = 'html') -> str:
        """
        Generate a report for analysis results.
        
        Args:
            analysis_result: Analysis results to report
            format: Output format ('html', 'json', or 'markdown')
            
        Returns:
            Path to generated report file
        """
        logger.info(f"Generating {format} analysis report")

        if format == 'html':
            return self._generate_html_analysis_report(analysis_result)
        elif format == 'json':
            return self._generate_json_analysis_report(analysis_result)
        elif format == 'markdown':
            return self._generate_markdown_analysis_report(analysis_result)
        else:
            raise ValueError(f"Unsupported format: {format}")

    def _generate_html_analysis_report(self, analysis_result: AnalysisResult) -> str:
        """Generate HTML analysis report."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = self.output_dir / f'analysis_report_{timestamp}.html'

        # Prepare data for template
        context = {
            'title': 'Bob-Guard Analysis Report',
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'repository': analysis_result.repository_path,
            'total_files': analysis_result.total_files,
            'analyzed_files': analysis_result.analyzed_files,
            'total_violations': len(analysis_result.violations),
            'summary': analysis_result.summary,
            'violations': self._prepare_violations_for_template(analysis_result.violations),
            'severity_chart_data': self._prepare_severity_chart_data(analysis_result.summary),
            'category_chart_data': self._prepare_category_chart_data(analysis_result.summary)
        }

        # Render template
        try:
            template = self.jinja_env.get_template('results.html')
            html_content = template.render(**context)
        except Exception as e:
            logger.warning(f"Template rendering failed: {e}. Using fallback HTML.")
            html_content = self._generate_fallback_html(context)

        # Write to file
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html_content)

        logger.info(f"HTML report generated: {output_file}")
        return str(output_file)

    def _generate_json_analysis_report(self, analysis_result: AnalysisResult) -> str:
        """Generate JSON analysis report."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = self.output_dir / f'analysis_report_{timestamp}.json'

        # Write to file
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(analysis_result.to_dict(), f, indent=2)

        logger.info(f"JSON report generated: {output_file}")
        return str(output_file)

    def _generate_markdown_analysis_report(self, analysis_result: AnalysisResult) -> str:
        """Generate Markdown analysis report."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = self.output_dir / f'analysis_report_{timestamp}.md'

        lines = [
            '# Bob-Guard Analysis Report',
            '',
            f'**Generated:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
            f'**Repository:** {analysis_result.repository_path}',
            '',
            '## Summary',
            '',
            f'- **Total Files:** {analysis_result.total_files}',
            f'- **Analyzed Files:** {analysis_result.analyzed_files}',
            f'- **Total Violations:** {len(analysis_result.violations)}',
            '',
            '### Violations by Severity',
            ''
        ]

        # Add severity breakdown
        for severity, count in analysis_result.summary['by_severity'].items():
            lines.append(f'- **{severity.capitalize()}:** {count}')

        lines.extend(['', '### Violations by Category', ''])

        # Add category breakdown
        for category, count in analysis_result.summary['by_category'].items():
            lines.append(f'- **{category.upper()}:** {count}')

        lines.extend(['', '## Detailed Violations', ''])

        # Add detailed violations
        for i, violation in enumerate(analysis_result.violations, 1):
            lines.extend([
                f'### {i}. {violation.rule_name}',
                '',
                f'- **Severity:** {violation.severity}',
                f'- **Category:** {violation.category}',
                f'- **File:** {violation.file_path}',
                f'- **Line:** {violation.line_number}',
                '',
                f'**Description:** {violation.description}',
                '',
                f'**Recommendation:** {violation.recommendation}',
                '',
                '```',
                violation.code_snippet,
                '```',
                ''
            ])

        # Write to file
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))

        logger.info(f"Markdown report generated: {output_file}")
        return str(output_file)

    def generate_remediation_report(self, remediation_result: RemediationResult,
                                   format: str = 'html') -> str:
        """
        Generate a report for remediation results.
        
        Args:
            remediation_result: Remediation results to report
            format: Output format ('html', 'json', or 'markdown')
            
        Returns:
            Path to generated report file
        """
        logger.info(f"Generating {format} remediation report")

        if format == 'html':
            return self._generate_html_remediation_report(remediation_result)
        elif format == 'json':
            return self._generate_json_remediation_report(remediation_result)
        elif format == 'markdown':
            return self._generate_markdown_remediation_report(remediation_result)
        else:
            raise ValueError(f"Unsupported format: {format}")

    def _generate_html_remediation_report(self, remediation_result: RemediationResult) -> str:
        """Generate HTML remediation report."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = self.output_dir / f'remediation_report_{timestamp}.html'

        context = {
            'title': 'Bob-Guard Remediation Report',
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'total_violations': remediation_result.total_violations,
            'fixes_generated': remediation_result.fixes_generated,
            'fixes_applied': remediation_result.fixes_applied,
            'fixes_failed': remediation_result.fixes_failed,
            'fixes': remediation_result.fixes
        }

        html_content = self._generate_fallback_remediation_html(context)

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html_content)

        logger.info(f"HTML remediation report generated: {output_file}")
        return str(output_file)

    def _generate_json_remediation_report(self, remediation_result: RemediationResult) -> str:
        """Generate JSON remediation report."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = self.output_dir / f'remediation_report_{timestamp}.json'

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(remediation_result.to_dict(), f, indent=2)

        logger.info(f"JSON remediation report generated: {output_file}")
        return str(output_file)

    def _generate_markdown_remediation_report(self, remediation_result: RemediationResult) -> str:
        """Generate Markdown remediation report."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = self.output_dir / f'remediation_report_{timestamp}.md'

        lines = [
            '# Bob-Guard Remediation Report',
            '',
            f'**Generated:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
            '',
            '## Summary',
            '',
            f'- **Total Violations:** {remediation_result.total_violations}',
            f'- **Fixes Generated:** {remediation_result.fixes_generated}',
            f'- **Fixes Applied:** {remediation_result.fixes_applied}',
            f'- **Fixes Failed:** {remediation_result.fixes_failed}',
            '',
            '## Applied Fixes',
            ''
        ]

        for i, fix in enumerate(remediation_result.fixes, 1):
            status = '✅ Applied' if fix.applied else '⏳ Pending'
            lines.extend([
                f'### {i}. {Path(fix.file_path).name} - {status}',
                '',
                f'- **File:** {fix.file_path}',
                f'- **Confidence:** {fix.confidence:.2%}',
                '',
                f'**Explanation:** {fix.explanation}',
                ''
            ])

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))

        logger.info(f"Markdown remediation report generated: {output_file}")
        return str(output_file)

    def generate_combined_report(self, analysis_result: AnalysisResult,
                                remediation_result: Optional[RemediationResult] = None,
                                test_result: Optional[TestGenerationResult] = None,
                                format: str = 'html') -> str:
        """
        Generate a combined report with analysis, remediation, and test results.
        
        Args:
            analysis_result: Analysis results
            remediation_result: Optional remediation results
            test_result: Optional test generation results
            format: Output format
            
        Returns:
            Path to generated report file
        """
        logger.info(f"Generating combined {format} report")

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = self.output_dir / f'combined_report_{timestamp}.{format}'

        if format == 'json':
            combined_data = {
                'analysis': analysis_result.to_dict(),
                'remediation': remediation_result.to_dict() if remediation_result else None,
                'tests': test_result.to_dict() if test_result else None,
                'timestamp': datetime.utcnow().isoformat()
            }
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(combined_data, f, indent=2)
        else:
            # For HTML/Markdown, combine individual reports
            content = f"Combined report generated at {datetime.now()}\n\n"
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(content)

        logger.info(f"Combined report generated: {output_file}")
        return str(output_file)

    def _prepare_violations_for_template(self, violations: List[Violation]) -> List[Dict[str, Any]]:
        """Prepare violations data for template rendering."""
        return [
            {
                'id': v.id,
                'severity': v.severity,
                'severity_class': f'severity-{v.severity.lower()}',
                'category': v.category,
                'rule_name': v.rule_name,
                'file_path': v.file_path,
                'file_name': Path(v.file_path).name,
                'line_number': v.line_number,
                'description': v.description,
                'recommendation': v.recommendation,
                'code_snippet': v.code_snippet
            }
            for v in violations
        ]

    def _prepare_severity_chart_data(self, summary: Dict[str, Any]) -> Dict[str, int]:
        """Prepare severity data for charts."""
        return summary.get('by_severity', {})

    def _prepare_category_chart_data(self, summary: Dict[str, Any]) -> Dict[str, int]:
        """Prepare category data for charts."""
        return summary.get('by_category', {})

    def _generate_fallback_html(self, context: Dict[str, Any]) -> str:
        """Generate fallback HTML when template is not available."""
        html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{context['title']}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; }}
        h1 {{ color: #333; }}
        .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin: 20px 0; }}
        .summary-card {{ background: #f8f9fa; padding: 15px; border-radius: 5px; border-left: 4px solid #007bff; }}
        .violation {{ background: #fff; border: 1px solid #ddd; padding: 15px; margin: 10px 0; border-radius: 5px; }}
        .severity-critical {{ border-left: 4px solid #dc3545; }}
        .severity-high {{ border-left: 4px solid #fd7e14; }}
        .severity-medium {{ border-left: 4px solid #ffc107; }}
        .severity-low {{ border-left: 4px solid #28a745; }}
        code {{ background: #f4f4f4; padding: 2px 5px; border-radius: 3px; }}
        pre {{ background: #f4f4f4; padding: 10px; border-radius: 5px; overflow-x: auto; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>{context['title']}</h1>
        <p><strong>Generated:</strong> {context['timestamp']}</p>
        <p><strong>Repository:</strong> {context['repository']}</p>
        
        <div class="summary">
            <div class="summary-card">
                <h3>Total Files</h3>
                <p style="font-size: 2em; margin: 0;">{context['total_files']}</p>
            </div>
            <div class="summary-card">
                <h3>Analyzed Files</h3>
                <p style="font-size: 2em; margin: 0;">{context['analyzed_files']}</p>
            </div>
            <div class="summary-card">
                <h3>Total Violations</h3>
                <p style="font-size: 2em; margin: 0;">{context['total_violations']}</p>
            </div>
        </div>
        
        <h2>Violations</h2>
"""
        
        for violation in context['violations']:
            html += f"""
        <div class="violation {violation['severity_class']}">
            <h3>{violation['rule_name']}</h3>
            <p><strong>Severity:</strong> {violation['severity']} | <strong>Category:</strong> {violation['category']}</p>
            <p><strong>File:</strong> {violation['file_name']} (Line {violation['line_number']})</p>
            <p>{violation['description']}</p>
            <p><strong>Recommendation:</strong> {violation['recommendation']}</p>
            <pre><code>{violation['code_snippet']}</code></pre>
        </div>
"""
        
        html += """
    </div>
</body>
</html>
"""
        return html

    def _generate_fallback_remediation_html(self, context: Dict[str, Any]) -> str:
        """Generate fallback HTML for remediation report."""
        html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{context['title']}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; }}
        .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin: 20px 0; }}
        .summary-card {{ background: #f8f9fa; padding: 15px; border-radius: 5px; }}
        .fix {{ background: #fff; border: 1px solid #ddd; padding: 15px; margin: 10px 0; border-radius: 5px; }}
        .applied {{ border-left: 4px solid #28a745; }}
        .pending {{ border-left: 4px solid #ffc107; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>{context['title']}</h1>
        <p><strong>Generated:</strong> {context['timestamp']}</p>
        
        <div class="summary">
            <div class="summary-card">
                <h3>Fixes Generated</h3>
                <p style="font-size: 2em; margin: 0;">{context['fixes_generated']}</p>
            </div>
            <div class="summary-card">
                <h3>Fixes Applied</h3>
                <p style="font-size: 2em; margin: 0;">{context['fixes_applied']}</p>
            </div>
            <div class="summary-card">
                <h3>Fixes Failed</h3>
                <p style="font-size: 2em; margin: 0;">{context['fixes_failed']}</p>
            </div>
        </div>
        
        <h2>Fixes</h2>
"""
        
        for fix in context['fixes']:
            status_class = 'applied' if fix.applied else 'pending'
            status_text = '✅ Applied' if fix.applied else '⏳ Pending'
            html += f"""
        <div class="fix {status_class}">
            <h3>{Path(fix.file_path).name} - {status_text}</h3>
            <p><strong>Confidence:</strong> {fix.confidence:.2%}</p>
            <p>{fix.explanation}</p>
        </div>
"""
        
        html += """
    </div>
</body>
</html>
"""
        return html

# Made with Bob



class Reporter:
    """
    Comprehensive compliance report generator for Bob-Guard.
    Generates JSON and HTML reports with executive summaries.
    """

    def __init__(self, violations: List[Violation], remediations: List[RemediationResult],
                 test_results: Optional[TestSuiteResult], repo_path: str, output_dir: str = 'output'):
        """
        Initialize the Reporter.
        
        Args:
            violations: List of violations found during analysis
            remediations: List of remediation results with applied fixes
            test_results: Test execution results
            repo_path: Path to the analyzed repository
            output_dir: Directory to store generated reports
        """
        self.violations = violations
        self.remediations = remediations
        self.test_results = test_results
        self.repo_path = repo_path
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.scan_start_time = datetime.now()
        self.bob_client = BobClient()

    def generate_json_report(self) -> str:
        """
        Generate a comprehensive JSON report.
        
        Returns:
            Path to the generated report.json file
        """
        logger.info("Generating JSON compliance report")
        
        # Calculate metrics
        scan_duration = (datetime.now() - self.scan_start_time).total_seconds()
        files_scanned = len(set(v.file_path for v in self.violations))
        
        # Build summary
        summary = self._build_summary()
        
        # Build violations list
        violations_data = [self._violation_to_dict(v) for v in self.violations]
        
        # Build remediations list
        remediations_data = self._build_remediations_data()
        
        # Build tests data
        tests_data = self._build_tests_data()
        
        # Construct complete report
        report = {
            "scan_metadata": {
                "date": datetime.now().isoformat(),
                "repo": self.repo_path,
                "duration_seconds": round(scan_duration, 2),
                "files_scanned": files_scanned
            },
            "summary": summary,
            "violations": violations_data,
            "remediations": remediations_data,
            "tests": tests_data
        }
        
        # Write to file
        output_file = self.output_dir / 'report.json'
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2)
        
        logger.info(f"JSON report generated: {output_file}")
        return str(output_file)

    def generate_html_report(self) -> str:
        """
        Generate a professional HTML report with colored severity badges and diffs.
        
        Returns:
            Path to the generated report.html file
        """
        logger.info("Generating HTML compliance report")
        
        # Generate executive summary using IBM Bob
        executive_summary = self._generate_executive_summary()
        
        # Calculate metrics
        summary = self._build_summary()
        scan_duration = (datetime.now() - self.scan_start_time).total_seconds()
        files_scanned = len(set(v.file_path for v in self.violations))
        
        # Build HTML content
        html_content = self._build_html_report(
            executive_summary=executive_summary,
            summary=summary,
            scan_duration=scan_duration,
            files_scanned=files_scanned
        )
        
        # Write to file
        output_file = self.output_dir / 'report.html'
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        logger.info(f"HTML report generated: {output_file}")
        return str(output_file)

    def _build_summary(self) -> Dict[str, Any]:
        """Build summary statistics."""
        # Count by severity
        by_severity = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
        for v in self.violations:
            severity = v.severity.upper()
            if severity in by_severity:
                by_severity[severity] += 1
        
        # Count by category
        by_category = {}
        for v in self.violations:
            category = v.category.upper()
            by_category[category] = by_category.get(category, 0) + 1
        
        # Count fixes
        total_fixes = sum(len(r.fixes) for r in self.remediations)
        fixed_automatically = sum(len([f for f in r.fixes if f.applied]) for r in self.remediations)
        require_manual_review = total_fixes - fixed_automatically
        
        # Calculate risk score (0-100)
        risk_score = self._calculate_risk_score(by_severity, total_fixes, fixed_automatically)
        
        return {
            "total_violations": len(self.violations),
            "by_severity": by_severity,
            "by_category": by_category,
            "fixed_automatically": fixed_automatically,
            "require_manual_review": require_manual_review,
            "risk_score": risk_score
        }

    def _calculate_risk_score(self, by_severity: Dict[str, int], total_fixes: int, 
                             fixed_automatically: int) -> int:
        """
        Calculate overall risk score (0-100).
        Higher score = higher risk.
        """
        # Weight violations by severity
        severity_weights = {"CRITICAL": 10, "HIGH": 5, "MEDIUM": 2, "LOW": 1}
        weighted_violations = sum(by_severity.get(sev, 0) * weight 
                                 for sev, weight in severity_weights.items())
        
        # Base risk from violations (0-70 points)
        base_risk = min(70, weighted_violations * 2)
        
        # Additional risk from unfixed issues (0-30 points)
        if total_fixes > 0:
            unfixed_ratio = (total_fixes - fixed_automatically) / total_fixes
            unfixed_risk = unfixed_ratio * 30
        else:
            unfixed_risk = 0
        
        total_risk = int(base_risk + unfixed_risk)
        return min(100, total_risk)

    def _violation_to_dict(self, violation: Violation) -> Dict[str, Any]:
        """Convert violation to dictionary format."""
        return {
            "id": violation.id,
            "severity": violation.severity,
            "category": violation.category,
            "rule_id": violation.rule_id,
            "rule_name": violation.rule_name,
            "file_path": violation.file_path,
            "line_number": violation.line_number,
            "column": violation.column,
            "code_snippet": violation.code_snippet,
            "description": violation.description,
            "recommendation": violation.recommendation,
            "cwe_id": violation.cwe_id,
            "cvss_score": violation.cvss_score
        }

    def _build_remediations_data(self) -> List[Dict[str, Any]]:
        """Build remediations data with diffs."""
        remediations_data = []
        
        for remediation in self.remediations:
            for fix in remediation.fixes:
                # Generate unified diff
                diff_html = self._generate_colored_diff(fix.original_code, fix.fixed_code, fix.file_path)
                
                remediations_data.append({
                    "violation_id": fix.violation_id,
                    "file_path": fix.file_path,
                    "applied": fix.applied,
                    "confidence": fix.confidence,
                    "explanation": fix.explanation,
                    "diff": diff_html
                })
        
        return remediations_data

    def _build_tests_data(self) -> Dict[str, Any]:
        """Build tests data."""
        if not self.test_results:
            return {"total": 0, "passed": 0, "failed": 0}
        
        return {
            "total": self.test_results.total,
            "passed": self.test_results.passed,
            "failed": self.test_results.failed,
            "skipped": self.test_results.skipped
        }

    def _generate_colored_diff(self, original: str, fixed: str, file_path: str) -> str:
        """Generate HTML colored diff (red for deletions, green for additions)."""
        original_lines = original.splitlines(keepends=True)
        fixed_lines = fixed.splitlines(keepends=True)
        
        diff = difflib.unified_diff(
            original_lines,
            fixed_lines,
            fromfile=f"{file_path} (original)",
            tofile=f"{file_path} (fixed)",
            lineterm=''
        )
        
        html_lines = []
        for line in diff:
            if line.startswith('---') or line.startswith('+++'):
                html_lines.append(f'<div class="diff-header">{self._escape_html(line)}</div>')
            elif line.startswith('-'):
                html_lines.append(f'<div class="diff-removed">{self._escape_html(line)}</div>')
            elif line.startswith('+'):
                html_lines.append(f'<div class="diff-added">{self._escape_html(line)}</div>')
            elif line.startswith('@@'):
                html_lines.append(f'<div class="diff-info">{self._escape_html(line)}</div>')
            else:
                html_lines.append(f'<div class="diff-context">{self._escape_html(line)}</div>')
        
        return ''.join(html_lines)

    def _escape_html(self, text: str) -> str:
        """Escape HTML special characters."""
        return (text.replace('&', '&amp;')
                   .replace('<', '&lt;')
                   .replace('>', '&gt;')
                   .replace('"', '&quot;')
                   .replace("'", '&#39;'))

    def _generate_executive_summary(self) -> str:
        """Generate executive summary using IBM Bob."""
        # Prepare context for Bob (initialize outside try block)
        summary = self._build_summary()
        
        # Get top 3 critical violations
        top_violations = sorted(
            self.violations,
            key=lambda v: {'CRITICAL': 4, 'HIGH': 3, 'MEDIUM': 2, 'LOW': 1}.get(v.severity.upper(), 0),
            reverse=True
        )[:3]
        
        top_violations_text = "\n".join([
            f"  - {v.severity.upper()}: {v.rule_name} in {Path(v.file_path).name} (Line {v.line_number})"
            for v in top_violations
        ])
        
        # Count files scanned
        files_scanned = len(set(v.file_path for v in self.violations))
        
        try:
            prompt = f"""Write a professional executive summary in English for a code compliance and security report intended for decision-makers.

CONTEXT:
- Repository Analyzed: {Path(self.repo_path).name}
- Total Files Scanned: {files_scanned}
- Scan Date: {datetime.now().strftime('%B %d, %Y')}

VIOLATIONS FOUND:
- Total: {summary['total_violations']}
- By Severity:
  • CRITICAL: {summary['by_severity']['CRITICAL']}
  • HIGH: {summary['by_severity']['HIGH']}
  • MEDIUM: {summary['by_severity']['MEDIUM']}
  • LOW: {summary['by_severity']['LOW']}
- By Category: {', '.join(f"{k}: {v}" for k, v in summary['by_category'].items())}

TOP 3 MOST CRITICAL VIOLATIONS:
{top_violations_text}

REMEDIATION ACTIONS:
- Automatically Fixed: {summary['fixed_automatically']} violations
- Require Manual Review: {summary['require_manual_review']} violations
- Overall Risk Score: {summary['risk_score']}/100

INSTRUCTIONS:
Write a professional executive summary structured in exactly 4 paragraphs:

§1 - Analysis Context: Briefly describe the repository analyzed, the scope of the scan (number of files), and when it was performed.

§2 - Main Findings: Highlight the most critical violations found, their severity distribution, and the primary security/compliance concerns identified. Focus on business impact.

§3 - Remediation Actions: Summarize the automated fixes that were successfully applied by Bob-Guard, emphasizing the efficiency of AI-powered remediation.

§4 - Recommendations: Provide clear next steps for violations requiring manual review, prioritizing critical and high-severity issues. Include timeline suggestions.

REQUIREMENTS:
- Tone: Professional, factual, suitable for decision-makers
- Length: 200-250 words maximum (approximately 50-60 words per paragraph)
- Avoid excessive technical jargon
- Focus on business value and risk mitigation
- Be specific with numbers and metrics
- Make it convincing for a hackathon demo

Return ONLY the 4-paragraph summary without any additional formatting or explanations."""

            result = self.bob_client.chat(
                message=prompt,
                context={
                    'action': 'generate_executive_summary',
                    'summary': summary
                }
            )
            
            return result.get('response', self._generate_fallback_summary(summary))
            
        except BobAPIError as e:
            logger.warning(f"Bob API error generating executive summary: {e}")
            return self._generate_fallback_summary(summary)
        except Exception as e:
            logger.error(f"Error generating executive summary: {e}")
            return self._generate_fallback_summary(summary)

    def _generate_fallback_summary(self, summary: Dict[str, Any]) -> str:
        """Generate a fallback executive summary when Bob API is unavailable."""
        risk_level = "HIGH" if summary['risk_score'] > 70 else "MEDIUM" if summary['risk_score'] > 40 else "LOW"
        
        return f"""
<p>This security compliance scan of <strong>{self.repo_path}</strong> identified <strong>{summary['total_violations']} violations</strong> 
across the codebase, with a risk score of <strong>{summary['risk_score']}/100 ({risk_level} RISK)</strong>. 
The analysis revealed {summary['by_severity']['CRITICAL']} critical and {summary['by_severity']['HIGH']} high-severity issues 
that require immediate attention.</p>

<p>The automated remediation system successfully addressed <strong>{summary['fixed_automatically']} violations</strong>, 
demonstrating the effectiveness of AI-powered security fixes. However, <strong>{summary['require_manual_review']} issues</strong> 
require manual review and intervention by the development team.</p>

<p>The violations span multiple compliance categories including {', '.join(summary['by_category'].keys())}, 
indicating the need for a comprehensive security review. Priority should be given to addressing critical and high-severity 
issues to reduce the overall risk exposure.</p>

<p><strong>Recommended Actions:</strong> (1) Review and validate all automated fixes, (2) Prioritize manual remediation 
of critical issues, (3) Implement security testing for all changes, and (4) Establish ongoing compliance monitoring 
to prevent future violations.</p>
"""

    def _build_html_report(self, executive_summary: str, summary: Dict[str, Any],
                          scan_duration: float, files_scanned: int) -> str:
        """Build complete HTML report with professional styling."""
        
        # Get risk level and color
        risk_score = summary['risk_score']
        if risk_score > 70:
            risk_class = "risk-high"
            risk_label = "HIGH RISK"
        elif risk_score > 40:
            risk_class = "risk-medium"
            risk_label = "MEDIUM RISK"
        else:
            risk_class = "risk-low"
            risk_label = "LOW RISK"
        
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bob-Guard Compliance Report</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
            color: #333;
        }}
        .container {{ 
            max-width: 1400px; 
            margin: 0 auto; 
            background: white; 
            border-radius: 12px; 
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            overflow: hidden;
        }}
        .header {{ 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white; 
            padding: 40px; 
            text-align: center;
        }}
        .header h1 {{ font-size: 2.5em; margin-bottom: 10px; }}
        .header p {{ font-size: 1.1em; opacity: 0.9; }}
        .content {{ padding: 40px; }}
        
        .summary-grid {{ 
            display: grid; 
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); 
            gap: 20px; 
            margin: 30px 0;
        }}
        .summary-card {{ 
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
            padding: 25px; 
            border-radius: 10px; 
            text-align: center;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            transition: transform 0.2s;
        }}
        .summary-card:hover {{ transform: translateY(-5px); }}
        .summary-card h3 {{ color: #555; font-size: 0.9em; margin-bottom: 10px; text-transform: uppercase; }}
        .summary-card .value {{ font-size: 2.5em; font-weight: bold; color: #667eea; }}
        
        .risk-score {{ 
            background: white;
            border: 3px solid #ddd;
            border-radius: 10px;
            padding: 30px;
            margin: 30px 0;
            text-align: center;
        }}
        .risk-score.risk-high {{ border-color: #dc3545; }}
        .risk-score.risk-medium {{ border-color: #ffc107; }}
        .risk-score.risk-low {{ border-color: #28a745; }}
        .risk-score h2 {{ margin-bottom: 15px; }}
        .risk-score .score {{ font-size: 4em; font-weight: bold; margin: 20px 0; }}
        .risk-score.risk-high .score {{ color: #dc3545; }}
        .risk-score.risk-medium .score {{ color: #ffc107; }}
        .risk-score.risk-low .score {{ color: #28a745; }}
        
        .executive-summary {{ 
            background: #f8f9fa; 
            padding: 30px; 
            border-radius: 10px; 
            margin: 30px 0;
            border-left: 5px solid #667eea;
        }}
        .executive-summary h2 {{ color: #667eea; margin-bottom: 20px; }}
        .executive-summary p {{ line-height: 1.8; margin-bottom: 15px; }}
        
        .section {{ margin: 40px 0; }}
        .section h2 {{ 
            color: #667eea; 
            margin-bottom: 20px; 
            padding-bottom: 10px; 
            border-bottom: 3px solid #667eea;
        }}
        
        .violations-table {{ 
            width: 100%; 
            border-collapse: collapse; 
            margin: 20px 0;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .violations-table th {{ 
            background: #667eea; 
            color: white; 
            padding: 15px; 
            text-align: left;
            font-weight: 600;
        }}
        .violations-table td {{ 
            padding: 15px; 
            border-bottom: 1px solid #ddd;
        }}
        .violations-table tr:hover {{ background: #f8f9fa; }}
        
        .badge {{ 
            display: inline-block; 
            padding: 5px 12px; 
            border-radius: 20px; 
            font-size: 0.85em; 
            font-weight: bold;
            text-transform: uppercase;
        }}
        .badge-critical {{ background: #dc3545; color: white; }}
        .badge-high {{ background: #fd7e14; color: white; }}
        .badge-medium {{ background: #ffc107; color: #333; }}
        .badge-low {{ background: #28a745; color: white; }}
        
        .fix-item {{ 
            background: white; 
            border: 1px solid #ddd; 
            border-radius: 8px; 
            padding: 20px; 
            margin: 15px 0;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        }}
        .fix-item.applied {{ border-left: 5px solid #28a745; }}
        .fix-item.pending {{ border-left: 5px solid #ffc107; }}
        .fix-item h3 {{ color: #333; margin-bottom: 10px; }}
        .fix-item .meta {{ color: #666; font-size: 0.9em; margin-bottom: 15px; }}
        
        .diff-container {{ 
            background: #f8f9fa; 
            border-radius: 5px; 
            padding: 15px; 
            margin: 15px 0;
            font-family: 'Courier New', monospace;
            font-size: 0.9em;
            overflow-x: auto;
        }}
        .diff-header {{ color: #666; font-weight: bold; }}
        .diff-removed {{ background: #ffebee; color: #c62828; padding: 2px 5px; }}
        .diff-added {{ background: #e8f5e9; color: #2e7d32; padding: 2px 5px; }}
        .diff-info {{ color: #1976d2; font-weight: bold; margin: 10px 0; }}
        .diff-context {{ color: #666; padding: 2px 5px; }}
        
        .footer {{ 
            background: #f8f9fa; 
            padding: 20px; 
            text-align: center; 
            color: #666;
            border-top: 1px solid #ddd;
        }}
        
        @media print {{
            body {{ background: white; padding: 0; }}
            .container {{ box-shadow: none; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🛡️ Bob-Guard Compliance Report</h1>
            <p>Generated on {datetime.now().strftime('%B %d, %Y at %H:%M:%S')}</p>
            <p>Repository: {self.repo_path}</p>
        </div>
        
        <div class="content">
            <!-- Risk Score -->
            <div class="risk-score {risk_class}">
                <h2>Overall Risk Assessment</h2>
                <div class="score">{risk_score}/100</div>
                <div style="font-size: 1.2em; font-weight: bold;">{risk_label}</div>
            </div>
            
            <!-- Summary Grid -->
            <div class="summary-grid">
                <div class="summary-card">
                    <h3>Files Scanned</h3>
                    <div class="value">{files_scanned}</div>
                </div>
                <div class="summary-card">
                    <h3>Total Violations</h3>
                    <div class="value">{summary['total_violations']}</div>
                </div>
                <div class="summary-card">
                    <h3>Auto-Fixed</h3>
                    <div class="value" style="color: #28a745;">{summary['fixed_automatically']}</div>
                </div>
                <div class="summary-card">
                    <h3>Manual Review</h3>
                    <div class="value" style="color: #ffc107;">{summary['require_manual_review']}</div>
                </div>
                <div class="summary-card">
                    <h3>Scan Duration</h3>
                    <div class="value" style="font-size: 1.8em;">{scan_duration:.1f}s</div>
                </div>
            </div>
            
            <!-- Executive Summary -->
            <div class="executive-summary">
                <h2>📊 Executive Summary</h2>
                {executive_summary}
            </div>
            
            <!-- Severity Breakdown -->
            <div class="section">
                <h2>🔍 Violations by Severity</h2>
                <div class="summary-grid">
                    <div class="summary-card">
                        <h3>Critical</h3>
                        <div class="value" style="color: #dc3545;">{summary['by_severity']['CRITICAL']}</div>
                    </div>
                    <div class="summary-card">
                        <h3>High</h3>
                        <div class="value" style="color: #fd7e14;">{summary['by_severity']['HIGH']}</div>
                    </div>
                    <div class="summary-card">
                        <h3>Medium</h3>
                        <div class="value" style="color: #ffc107;">{summary['by_severity']['MEDIUM']}</div>
                    </div>
                    <div class="summary-card">
                        <h3>Low</h3>
                        <div class="value" style="color: #28a745;">{summary['by_severity']['LOW']}</div>
                    </div>
                </div>
            </div>
            
            <!-- Violations Table -->
            <div class="section">
                <h2>📋 Detailed Violations</h2>
                <table class="violations-table">
                    <thead>
                        <tr>
                            <th>Severity</th>
                            <th>Category</th>
                            <th>Rule</th>
                            <th>File</th>
                            <th>Line</th>
                            <th>Description</th>
                        </tr>
                    </thead>
                    <tbody>
"""
        
        # Add violations
        for v in self.violations:
            severity_class = f"badge-{v.severity.lower()}"
            html += f"""
                        <tr>
                            <td><span class="badge {severity_class}">{v.severity}</span></td>
                            <td>{v.category}</td>
                            <td>{v.rule_name}</td>
                            <td>{Path(v.file_path).name}</td>
                            <td>{v.line_number}</td>
                            <td>{self._escape_html(v.description[:100])}...</td>
                        </tr>
"""
        
        html += """
                    </tbody>
                </table>
            </div>
            
            <!-- Remediations -->
            <div class="section">
                <h2>🔧 Applied Remediations</h2>
"""
        
        # Add remediations
        for remediation in self.remediations:
            for fix in remediation.fixes:
                status_class = "applied" if fix.applied else "pending"
                status_icon = "✅" if fix.applied else "⏳"
                diff_html = self._generate_colored_diff(fix.original_code, fix.fixed_code, fix.file_path)
                
                html += f"""
                <div class="fix-item {status_class}">
                    <h3>{status_icon} {Path(fix.file_path).name}</h3>
                    <div class="meta">
                        <strong>Confidence:</strong> {fix.confidence:.1%} | 
                        <strong>Status:</strong> {'Applied' if fix.applied else 'Pending'}
                    </div>
                    <p>{self._escape_html(fix.explanation)}</p>
                    <div class="diff-container">
                        {diff_html}
                    </div>
                </div>
"""
        
        # Add test results
        tests_data = self._build_tests_data()
        html += f"""
            </div>
            
            <!-- Test Results -->
            <div class="section">
                <h2>🧪 Test Results</h2>
                <div class="summary-grid">
                    <div class="summary-card">
                        <h3>Total Tests</h3>
                        <div class="value">{tests_data['total']}</div>
                    </div>
                    <div class="summary-card">
                        <h3>Passed</h3>
                        <div class="value" style="color: #28a745;">{tests_data['passed']}</div>
                    </div>
                    <div class="summary-card">
                        <h3>Failed</h3>
                        <div class="value" style="color: #dc3545;">{tests_data['failed']}</div>
                    </div>
                </div>
            </div>
        </div>
        
        <div class="footer">
            <p>Generated by <strong>Bob-Guard</strong> - AI-Powered Security Compliance Tool</p>
            <p>Powered by IBM Bob | © 2026</p>
        </div>
    </div>
</body>
</html>
"""
        
        return html

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if hasattr(self.bob_client, 'close'):
            self.bob_client.close()


# Made with Bob
