"""
Bob-Guard CLI Orchestrator
Command-line interface for running analysis, remediation, and test generation.
"""

import os
import sys
import logging
import click
from pathlib import Path
from typing import Optional

from src.analyzer import CodeAnalyzer
from src.remediator import CodeRemediator
from src.test_generator import TestGenerator
from src.reporter import ReportGenerator
from src.bob_client import BobClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@click.group()
@click.version_option(version='1.0.0')
def cli():
    """
    Bob-Guard: Automated Compliance & Security Analysis Agent
    
    Analyze legacy codebases for compliance violations and security issues,
    then automatically propose and apply fixes.
    """
    pass


@cli.command()
@click.option('--repo', '-r', required=True, help='Path to repository to analyze')
@click.option('--config', '-c', default='config/rules.json', help='Path to rules configuration')
@click.option('--output', '-o', default='output', help='Output directory for reports')
@click.option('--format', '-f', type=click.Choice(['html', 'json', 'markdown']), 
              default='html', help='Report format')
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose output')
def analyze(repo: str, config: str, output: str, format: str, verbose: bool):
    """Analyze a repository for compliance and security issues."""
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    click.echo(f"🔍 Analyzing repository: {repo}")
    
    try:
        # Initialize analyzer
        analyzer = CodeAnalyzer(config_path=config)
        
        # Run analysis
        result = analyzer.analyze_repository(repo)
        
        # Generate report
        reporter = ReportGenerator(output_dir=output)
        report_path = reporter.generate_analysis_report(result, format=format)
        
        # Display summary
        click.echo(f"\n✅ Analysis complete!")
        click.echo(f"📊 Total violations: {len(result.violations)}")
        click.echo(f"📁 Analyzed files: {result.analyzed_files}/{result.total_files}")
        click.echo(f"📄 Report generated: {report_path}")
        
        # Display severity breakdown
        click.echo("\n📈 Violations by severity:")
        for severity, count in result.summary['by_severity'].items():
            click.echo(f"  {severity.capitalize()}: {count}")
        
        # Exit with error code if critical violations found
        if result.summary['by_severity'].get('critical', 0) > 0:
            sys.exit(1)
            
    except Exception as e:
        click.echo(f"❌ Error during analysis: {e}", err=True)
        if verbose:
            raise
        sys.exit(1)


@cli.command()
@click.option('--repo', '-r', required=True, help='Path to repository to remediate')
@click.option('--config', '-c', default='config/rules.json', help='Path to rules configuration')
@click.option('--output', '-o', default='output', help='Output directory')
@click.option('--auto-apply', is_flag=True, help='Automatically apply fixes without confirmation')
@click.option('--min-confidence', type=float, default=0.7, 
              help='Minimum confidence threshold for applying fixes (0.0-1.0)')
@click.option('--backup/--no-backup', default=True, help='Create backups before applying fixes')
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose output')
def remediate(repo: str, config: str, output: str, auto_apply: bool, 
              min_confidence: float, backup: bool, verbose: bool):
    """Generate and apply fixes for detected violations."""
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    click.echo(f"🔧 Remediating repository: {repo}")
    
    try:
        # First, analyze the repository
        click.echo("Step 1: Analyzing repository...")
        analyzer = CodeAnalyzer(config_path=config)
        analysis_result = analyzer.analyze_repository(repo)
        
        if not analysis_result.violations:
            click.echo("✅ No violations found. Nothing to remediate.")
            return
        
        click.echo(f"Found {len(analysis_result.violations)} violations")
        
        # Generate fixes
        click.echo("\nStep 2: Generating fixes...")
        remediator = CodeRemediator(backup_dir=f"{output}/backups")
        fixes = remediator.generate_fixes(analysis_result.violations, min_confidence)
        
        click.echo(f"Generated {len(fixes)} fixes")
        
        if not fixes:
            click.echo("⚠️  No fixes could be generated.")
            return
        
        # Apply fixes
        click.echo("\nStep 3: Applying fixes...")
        if not auto_apply:
            if not click.confirm(f"Apply {len(fixes)} fixes?"):
                click.echo("Remediation cancelled.")
                return
        
        remediation_result = remediator.apply_fixes(
            fixes=fixes,
            auto_apply=auto_apply,
            create_backup=backup
        )
        
        # Generate report
        reporter = ReportGenerator(output_dir=output)
        report_path = reporter.generate_remediation_report(remediation_result, format='html')
        
        # Display summary
        click.echo(f"\n✅ Remediation complete!")
        click.echo(f"✓ Fixes applied: {remediation_result.fixes_applied}")
        click.echo(f"✗ Fixes failed: {remediation_result.fixes_failed}")
        click.echo(f"📄 Report generated: {report_path}")
        
    except Exception as e:
        click.echo(f"❌ Error during remediation: {e}", err=True)
        if verbose:
            raise
        sys.exit(1)


@cli.command()
@click.option('--repo', '-r', required=True, help='Path to repository')
@click.option('--output', '-o', default='tests', help='Output directory for tests')
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose output')
def generate_tests(repo: str, output: str, verbose: bool):
    """Generate unit tests for code in repository."""
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    click.echo(f"🧪 Generating tests for: {repo}")
    
    try:
        # Collect source files
        repo_path = Path(repo)
        source_files = list(repo_path.rglob('*.py'))  # Example: Python files
        
        if not source_files:
            click.echo("⚠️  No source files found.")
            return
        
        click.echo(f"Found {len(source_files)} source files")
        
        # Generate tests
        test_generator = TestGenerator(test_dir=output)
        
        for file_path in source_files:
            click.echo(f"Generating tests for {file_path.name}...")
            test_generator.generate_tests_for_file(str(file_path))
        
        # Export results
        test_generator.export_results(f"{output}/test_generation_report.json")
        
        click.echo(f"\n✅ Test generation complete!")
        click.echo(f"📁 Tests written to: {output}")
        
    except Exception as e:
        click.echo(f"❌ Error generating tests: {e}", err=True)
        if verbose:
            raise
        sys.exit(1)


@cli.command()
@click.option('--repo', '-r', required=True, help='Path to repository')
@click.option('--config', '-c', default='config/rules.json', help='Path to rules configuration')
@click.option('--output', '-o', default='output', help='Output directory')
@click.option('--auto-fix', is_flag=True, help='Automatically apply fixes')
@click.option('--generate-tests', is_flag=True, help='Generate unit tests after remediation')
@click.option('--min-confidence', type=float, default=0.7, help='Minimum fix confidence')
@click.option('--format', '-f', type=click.Choice(['html', 'json', 'markdown']), 
              default='html', help='Report format')
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose output')
def run(repo: str, config: str, output: str, auto_fix: bool, generate_tests: bool,
        min_confidence: float, format: str, verbose: bool):
    """Run complete pipeline: analyze, remediate, and generate tests."""
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    click.echo("🚀 Starting Bob-Guard full pipeline")
    click.echo(f"📁 Repository: {repo}\n")
    
    try:
        # Step 1: Analysis
        click.echo("=" * 60)
        click.echo("STEP 1: ANALYSIS")
        click.echo("=" * 60)
        
        analyzer = CodeAnalyzer(config_path=config)
        analysis_result = analyzer.analyze_repository(repo)
        
        click.echo(f"✓ Found {len(analysis_result.violations)} violations")
        
        # Step 2: Remediation
        if analysis_result.violations:
            click.echo("\n" + "=" * 60)
            click.echo("STEP 2: REMEDIATION")
            click.echo("=" * 60)
            
            remediator = CodeRemediator(backup_dir=f"{output}/backups")
            fixes = remediator.generate_fixes(analysis_result.violations, min_confidence)
            
            click.echo(f"✓ Generated {len(fixes)} fixes")
            
            if fixes:
                if not auto_fix:
                    if not click.confirm(f"Apply {len(fixes)} fixes?"):
                        click.echo("Skipping remediation.")
                        remediation_result = None
                    else:
                        remediation_result = remediator.apply_fixes(fixes, auto_apply=True)
                else:
                    remediation_result = remediator.apply_fixes(fixes, auto_apply=True)
                
                if remediation_result:
                    click.echo(f"✓ Applied {remediation_result.fixes_applied} fixes")
            else:
                remediation_result = None
        else:
            remediation_result = None
            click.echo("✓ No violations to remediate")
        
        # Step 3: Test Generation
        test_result = None
        if generate_tests and remediation_result and remediation_result.fixes_applied > 0:
            click.echo("\n" + "=" * 60)
            click.echo("STEP 3: TEST GENERATION")
            click.echo("=" * 60)
            
            test_generator = TestGenerator(test_dir='tests')
            test_result = test_generator.generate_tests_for_fixes(remediation_result.fixes)
            
            click.echo(f"✓ Generated {test_result.tests_generated} tests")
        
        # Step 4: Report Generation
        click.echo("\n" + "=" * 60)
        click.echo("STEP 4: REPORT GENERATION")
        click.echo("=" * 60)
        
        reporter = ReportGenerator(output_dir=output)
        report_path = reporter.generate_combined_report(
            analysis_result,
            remediation_result,
            test_result,
            format=format
        )
        
        click.echo(f"✓ Report generated: {report_path}")
        
        # Final summary
        click.echo("\n" + "=" * 60)
        click.echo("PIPELINE COMPLETE")
        click.echo("=" * 60)
        click.echo(f"📊 Violations found: {len(analysis_result.violations)}")
        if remediation_result:
            click.echo(f"🔧 Fixes applied: {remediation_result.fixes_applied}")
        if test_result:
            click.echo(f"🧪 Tests generated: {test_result.tests_generated}")
        click.echo(f"📄 Report: {report_path}")
        
    except Exception as e:
        click.echo(f"\n❌ Pipeline error: {e}", err=True)
        if verbose:
            raise
        sys.exit(1)


@cli.command()
@click.option('--port', '-p', default=5000, help='Port to run web server on')
def serve(port: int):
    """Start the Bob-Guard web interface."""
    click.echo(f"🌐 Starting Bob-Guard web server on port {port}...")
    click.echo(f"📱 Open http://localhost:{port} in your browser")
    
    try:
        # Import and run Flask app
        from app import app
        app.run(host='0.0.0.0', port=port, debug=True)
    except ImportError:
        click.echo("❌ Flask app not found. Make sure app.py exists.", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"❌ Error starting server: {e}", err=True)
        sys.exit(1)


@cli.command()
def version():
    """Display version information."""
    click.echo("Bob-Guard v1.0.0")
    click.echo("Automated Compliance & Security Analysis Agent")
    click.echo("\nComponents:")
    click.echo("  - Code Analyzer")
    click.echo("  - Automated Remediator")
    click.echo("  - Test Generator")
    click.echo("  - Report Generator")
    click.echo("  - IBM Bob API Integration")


if __name__ == '__main__':
    cli()

# Made with Bob
