#!/usr/bin/env python3
"""
Bob-Guard CLI - Main Entry Point
Automated Compliance & Security Analysis Agent for Legacy Codebases

This script orchestrates the complete analysis pipeline:
1. Code Analysis (detect violations)
2. Automated Remediation (generate and apply fixes)
3. Test Generation (create validation tests)
4. Report Generation (produce final report)

Usage:
    python main.py --repo /path/to/repository --output ./output
"""

import sys
import argparse
import json
import shutil
import subprocess
import uuid
from pathlib import Path
from datetime import datetime
from typing import Dict, Any
from urllib.parse import urlparse

# Progress bar for visual feedback
try:
    from tqdm import tqdm
    tqdm_lib = tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False
    # Fallback if tqdm not available
    class TqdmFallback:
        def __init__(self, *args, **kwargs):
            self.total = kwargs.get('total', 100)
            self.desc = kwargs.get('desc', '')
            self.current = 0
        
        def update(self, n=1):
            self.current += n
            print(f"\r{self.desc}: {self.current}/{self.total}", end='', flush=True)
        
        def close(self):
            print()
        
        def __enter__(self):
            return self
        
        def __exit__(self, *args):
            self.close()
    
    tqdm_lib = TqdmFallback

# Import Bob-Guard modules
from src.analyzer import Analyzer, Violation
from src.remediator import CodeRemediator
from src.test_generator import TestGenerator
from src.reporter import ReportGenerator
from src.bob_client import BobClient, BobAPIError


# ANSI color codes for terminal output
class Colors:
    """Terminal color codes for pretty output"""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'


def print_header():
    """Print Bob-Guard ASCII art header"""
    header = f"""
{Colors.CYAN}{Colors.BOLD}
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║   ██████╗  ██████╗ ██████╗        ██████╗ ██╗   ██╗ █████╗  ║
║   ██╔══██╗██╔═══██╗██╔══██╗      ██╔════╝ ██║   ██║██╔══██╗ ║
║   ██████╔╝██║   ██║██████╔╝█████╗██║  ███╗██║   ██║███████║ ║
║   ██╔══██╗██║   ██║██╔══██╗╚════╝██║   ██║██║   ██║██╔══██║ ║
║   ██████╔╝╚██████╔╝██████╔╝      ╚██████╔╝╚██████╔╝██║  ██║ ║
║   ╚═════╝  ╚═════╝ ╚═════╝        ╚═════╝  ╚═════╝ ╚═╝  ╚═╝ ║
║                                                              ║
║        Automated Compliance & Security Analysis Agent       ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
{Colors.END}
    """
    print(header)


def print_step(step_num: int, total_steps: int, message: str):
    """Print current step with formatting"""
    print(f"\n{Colors.BOLD}{Colors.BLUE}[Step {step_num}/{total_steps}]{Colors.END} {message}")
    print("─" * 60)


def print_success(message: str):
    """Print success message"""
    print(f"{Colors.GREEN}✓{Colors.END} {message}")


def print_error(message: str):
    """Print error message"""
    print(f"{Colors.RED}✗{Colors.END} {message}")


def print_warning(message: str):
    """Print warning message"""
    print(f"{Colors.YELLOW}⚠{Colors.END} {message}")


def print_info(message: str):
    """Print info message"""
    print(f"{Colors.CYAN}ℹ{Colors.END} {message}")


def load_rules(config_path: str = "config/rules.json") -> Dict[str, Any]:
    """
    Load compliance rules from configuration file.
    
    Args:
        config_path: Path to rules configuration file
        
    Returns:
        Dictionary containing rules configuration
        
    Raises:
        FileNotFoundError: If config file doesn't exist
        json.JSONDecodeError: If config file is invalid JSON
    """
    config_file = Path(config_path)
    
    if not config_file.exists():
        raise FileNotFoundError(f"Rules configuration not found: {config_path}")
    
    with open(config_file, 'r') as f:
        return json.load(f)


def validate_repository(repo_path: str) -> Path:
    """
    Validate that repository path exists and is accessible.
    
    Args:
        repo_path: Path to repository
        
    Returns:
        Path object for the repository
        
    Raises:
        ValueError: If path doesn't exist or is not a directory
    """
    repo = Path(repo_path)
    
    if not repo.exists():
        raise ValueError(f"Repository path does not exist: {repo_path}")
    
    if not repo.is_dir():
        raise ValueError(f"Repository path is not a directory: {repo_path}")
    
    return repo


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


def clone_github_repository(repo_source: str, work_dir: Path) -> Path:
    """Clone a GitHub repository into a local work directory and return the path."""
    clone_url = normalize_github_clone_url(repo_source)
    target_dir = work_dir / f"github_clone_{uuid.uuid4().hex}"

    try:
        subprocess.run(
            ['git', 'clone', '--depth', '1', clone_url, str(target_dir)],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as e:
        raise RuntimeError("Git is not installed or not available in PATH") from e
    except subprocess.CalledProcessError as e:
        error_output = (e.stderr or e.stdout or str(e)).strip()
        raise RuntimeError(f"Failed to clone GitHub repository: {error_output}") from e

    if not target_dir.exists():
        raise RuntimeError("Git clone completed but the repository directory was not created")

    return target_dir


def resolve_repository_source(repo_source: str, work_dir: Path) -> tuple[Path, bool]:
    """Resolve a repository source into a local path ready for analysis.

    Returns:
        A tuple of (local repository path, cleanup_required).
    """
    source = repo_source.strip()

    if is_github_repository_source(source):
        return clone_github_repository(source, work_dir), True

    return validate_repository(source), False


def create_output_directory(output_path: str) -> Path:
    """
    Create output directory if it doesn't exist.
    
    Args:
        output_path: Path to output directory
        
    Returns:
        Path object for the output directory
    """
    output_dir = Path(output_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def print_summary(violations, remediation_result, test_result, report_path: str):
    """
    Print final summary of the analysis pipeline.
    
    Args:
        violations: List of violations from analysis
        remediation_result: Results from remediation
        test_result: Results from test generation
        report_path: Path to generated report
    """
    print(f"\n{Colors.BOLD}{Colors.GREEN}{'═' * 60}")
    print("                    FINAL SUMMARY")
    print(f"{'═' * 60}{Colors.END}\n")
    
    # Violations detected
    print(f"{Colors.BOLD}🔍 Violations Detected:{Colors.END}")
    print(f"   Total violations: {len(violations)}")
    
    # Count by severity
    severity_counts = {}
    for v in violations:
        severity_counts[v.severity] = severity_counts.get(v.severity, 0) + 1
    
    if severity_counts:
        print(f"\n   By Severity:")
        severity_colors = {
            'CRITICAL': Colors.RED,
            'HIGH': Colors.YELLOW,
            'MEDIUM': Colors.CYAN,
            'LOW': Colors.GREEN
        }
        for severity in ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']:
            if severity in severity_counts:
                color = severity_colors.get(severity, '')
                print(f"      • {color}{severity}: {severity_counts[severity]}{Colors.END}")
    
    # Fixes applied
    if remediation_result:
        print(f"\n{Colors.BOLD}🔧 Remediation:{Colors.END}")
        print(f"   Fixes generated: {remediation_result.fixes_generated}")
        print(f"   Fixes applied: {remediation_result.fixes_applied}")
        if remediation_result.fixes_failed > 0:
            print(f"   {Colors.YELLOW}Fixes failed: {remediation_result.fixes_failed}{Colors.END}")
    
    # Tests generated
    if test_result:
        print(f"\n{Colors.BOLD}🧪 Test Generation:{Colors.END}")
        print(f"   Test suites created: {len(test_result.test_suites)}")
        print(f"   Total tests: {test_result.tests_generated}")
    
    # Report location
    print(f"\n{Colors.BOLD}📄 Report:{Colors.END}")
    print(f"   {report_path}")
    
    print(f"\n{Colors.GREEN}{'═' * 60}{Colors.END}")
    print(f"{Colors.BOLD}Analysis complete! 🎉{Colors.END}\n")


def main():
    """
    Main entry point for Bob-Guard CLI.
    Orchestrates the complete analysis pipeline.
    """
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description="Bob-Guard: Automated Compliance & Security Analysis Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --repo ./my-project --output ./reports
  python main.py --repo /path/to/legacy/code --output ./analysis-results
    python main.py --repo https://github.com/user/repository --output ./analysis-results
        """
    )
    
    parser.add_argument(
        '--repo',
        required=True,
        help='Path to the repository to analyze or a GitHub repository URL'
    )
    
    parser.add_argument(
        '--output',
        default='./output',
        help='Output directory for reports and results (default: ./output)'
    )
    
    parser.add_argument(
        '--config',
        default='config/rules.json',
        help='Path to rules configuration file (default: config/rules.json)'
    )
    
    parser.add_argument(
        '--auto-fix',
        action='store_true',
        help='Automatically apply fixes (default: False)'
    )
    
    parser.add_argument(
        '--skip-tests',
        action='store_true',
        help='Skip test generation (default: False)'
    )
    
    args = parser.parse_args()
    cleanup_repo_path = None
    repo_path = None
    
    # Print header
    print_header()
    
    # Start timestamp
    start_time = datetime.now()
    print_info(f"Started at: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        # ============================================================
        # INITIALIZATION
        # ============================================================
        print_step(0, 4, "Initializing Bob-Guard")
        
        # Create output directory early so temporary clones can live beside the run artifacts.
        print_info(f"Creating output directory: {args.output}")
        output_dir = create_output_directory(args.output)
        print_success(f"Output directory ready: {output_dir}")
        
        # Validate or clone repository source
        print_info(f"Resolving repository source: {args.repo}")
        repo_path, cleanup_repo_path = resolve_repository_source(args.repo, output_dir)
        print_success(f"Repository ready: {repo_path}")
        
        # Load rules configuration
        print_info(f"Loading rules from: {args.config}")
        rules_config = load_rules(args.config)
        rules = rules_config.get('rules', [])
        total_rules = len(rules)
        print_success(f"Loaded {total_rules} compliance rules")
        
        # Initialize Bob API client
        print_info("Connecting to IBM Bob API...")
        try:
            bob_client = BobClient()
            if bob_client.health_check():
                print_success("IBM Bob API connection established")
            else:
                print_warning("IBM Bob API health check failed, continuing anyway...")
        except BobAPIError as e:
            print_warning(f"IBM Bob API not available: {e}")
            print_info("Continuing with local analysis only...")
            bob_client = None
        
        # ============================================================
        # STEP 1: CODE ANALYSIS
        # ============================================================
        print_step(1, 4, "Analyzing Code for Violations")
        
        print_info("Initializing code analyzer...")
        analyzer = Analyzer(
            repo_path=str(repo_path),
            rules=rules,
            bob_client=bob_client
        )
        
        print_info(f"Scanning repository: {repo_path}")
        with tqdm_lib(total=100, desc="Analyzing", ncols=80) as pbar:
            pbar.update(20)
            violations = analyzer.scan_repository()
            pbar.update(80)
        
        print_success(f"Analysis complete: {len(violations)} violations found")
        print_info(f"Files scanned: {analyzer.files_scanned}")
        
        # ============================================================
        # STEP 2: AUTOMATED REMEDIATION
        # ============================================================
        print_step(2, 4, "Generating and Applying Fixes")
        
        remediation_result = None
        
        if violations:
            print_info("Initializing remediator...")
            remediator = CodeRemediator(
                bob_client=bob_client,
                backup_dir=str(output_dir / 'backups')
            )
            
            print_info("Generating fixes for violations...")
            with tqdm_lib(total=len(violations), desc="Generating fixes", ncols=80) as pbar:
                fixes = remediator.generate_fixes(violations, min_confidence=0.7)
                pbar.update(len(violations))
            
            print_success(f"Generated {len(fixes)} fixes")
            
            if fixes and args.auto_fix:
                print_info("Applying fixes automatically...")
                with tqdm_lib(total=len(fixes), desc="Applying fixes", ncols=80) as pbar:
                    remediation_result = remediator.apply_fixes(
                        fixes=fixes,
                        auto_apply=True,
                        create_backup=True
                    )
                    pbar.update(len(fixes))
                
                print_success(f"Applied {remediation_result.fixes_applied} fixes")
                if remediation_result.fixes_failed > 0:
                    print_warning(f"{remediation_result.fixes_failed} fixes failed")
            else:
                print_info("Skipping fix application (use --auto-fix to apply)")
        else:
            print_success("No violations found - repository is compliant! 🎉")
        
        # ============================================================
        # STEP 3: TEST GENERATION
        # ============================================================
        print_step(3, 4, "Generating Validation Tests")
        
        test_result = None
        
        if not args.skip_tests and remediation_result and remediation_result.fixes_applied > 0:
            print_info("Initializing test generator...")
            test_generator = TestGenerator(
                bob_client=bob_client
            )
            
            print_info("Generating unit tests for fixed code...")
            with tqdm_lib(total=len(remediation_result.fixes), desc="Generating tests", ncols=80) as pbar:
                test_result = test_generator.generate_tests_for_fixes(remediation_result.fixes)
                pbar.update(len(remediation_result.fixes))
            
            print_success(f"Generated {test_result.tests_generated} tests in {len(test_result.test_suites)} test suites")
        else:
            if args.skip_tests:
                print_info("Test generation skipped (--skip-tests flag)")
            else:
                print_info("No fixes applied - skipping test generation")
        
        # ============================================================
        # STEP 4: REPORT GENERATION
        # ============================================================
        print_step(4, 4, "Generating Final Report")
        
        print_info("Initializing report generator...")
        reporter = ReportGenerator(
            template_dir='templates',
            output_dir=str(output_dir)
        )
        
        print_info("Creating comprehensive report...")
        # Create a simple summary for the report
        summary = analyzer.get_summary()
        
        with tqdm_lib(total=100, desc="Generating report", ncols=80) as pbar:
            pbar.update(30)
            # Export violations to JSON for the report
            violations_file = output_dir / 'violations.json'
            analyzer.export_violations(str(violations_file), format='json')
            pbar.update(40)
            report_path = str(violations_file)
            pbar.update(30)
        
        print_success(f"Report generated: {report_path}")
        
        # ============================================================
        # FINAL SUMMARY
        # ============================================================
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        print_summary(violations, remediation_result, test_result, report_path)
        
        print_info(f"Total execution time: {duration:.2f} seconds")
        
        # Exit with appropriate code
        critical_count = sum(1 for v in violations if v.severity == 'CRITICAL')
        if critical_count > 0:
            print_warning("Critical violations found - review required!")
            sys.exit(1)
        else:
            sys.exit(0)
    
    except FileNotFoundError as e:
        print_error(f"File not found: {e}")
        sys.exit(1)
    
    except ValueError as e:
        print_error(f"Invalid input: {e}")
        sys.exit(1)
    
    except BobAPIError as e:
        print_error(f"IBM Bob API error: {e}")
        print_info("Check your API credentials in .env file")
        sys.exit(1)
    
    except KeyboardInterrupt:
        print_warning("\n\nAnalysis interrupted by user")
        sys.exit(130)
    
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        print_info("Please report this issue with the full error message")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        if cleanup_repo_path and repo_path and repo_path.exists():
            shutil.rmtree(repo_path, ignore_errors=True)
            print_info("Cleaned up temporary cloned repository")


if __name__ == '__main__':
    main()

# Made with Bob
