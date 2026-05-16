"""
Report Generator Module
Generates detailed HTML and JSON reports for analysis results.
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
from jinja2 import Environment, FileSystemLoader, select_autoescape

from src.analyzer import AnalysisResult, Violation
from src.remediator import RemediationResult, Fix
from src.test_generator import TestGenerationResult

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
