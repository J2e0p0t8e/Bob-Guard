"""
Test Generator Module
Automatically generates unit tests for remediated code.
"""

import os
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime

from src.bob_client import BobClient, BobAPIError
from src.remediator import Fix

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class TestCase:
    """Represents a generated test case."""
    test_name: str
    test_code: str
    description: str
    target_function: str
    file_path: str
    framework: str  # e.g., 'pytest', 'unittest', 'jest'

    def to_dict(self) -> Dict[str, Any]:
        """Convert test case to dictionary."""
        return asdict(self)


@dataclass
class TestSuite:
    """Contains a collection of test cases for a file."""
    source_file: str
    test_file: str
    test_cases: List[TestCase]
    framework: str
    coverage_estimate: float  # Estimated code coverage percentage

    def to_dict(self) -> Dict[str, Any]:
        """Convert test suite to dictionary."""
        return {
            'source_file': self.source_file,
            'test_file': self.test_file,
            'test_cases': [tc.to_dict() for tc in self.test_cases],
            'framework': self.framework,
            'coverage_estimate': self.coverage_estimate
        }


@dataclass
class TestGenerationResult:
    """Contains the results of test generation process."""
    total_files: int
    tests_generated: int
    test_suites: List[TestSuite]
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert test generation result to dictionary."""
        return {
            'total_files': self.total_files,
            'tests_generated': self.tests_generated,
            'test_suites': [ts.to_dict() for ts in self.test_suites],
            'timestamp': self.timestamp
        }


class TestGenerator:
    """
    Main test generator class for creating unit tests.
    Uses IBM Bob API for intelligent test generation.
    """

    FRAMEWORK_MAP = {
        'python': 'pytest',
        'javascript': 'jest',
        'typescript': 'jest',
        'java': 'junit',
        'csharp': 'nunit',
        'go': 'testing',
        'ruby': 'rspec',
        'php': 'phpunit'
    }

    def __init__(self, bob_client: Optional[BobClient] = None, test_dir: str = 'tests'):
        """
        Initialize the test generator.
        
        Args:
            bob_client: Optional BobClient instance (creates new if not provided)
            test_dir: Directory to store generated tests
        """
        self.bob_client = bob_client or BobClient()
        self.test_dir = Path(test_dir)
        self.test_dir.mkdir(parents=True, exist_ok=True)
        self.test_suites: List[TestSuite] = []

    def generate_tests_for_fixes(self, fixes: List[Fix]) -> TestGenerationResult:
        """
        Generate tests for a list of fixes.
        
        Args:
            fixes: List of fixes to generate tests for
            
        Returns:
            TestGenerationResult with generated test suites
        """
        logger.info(f"Generating tests for {len(fixes)} fixes")
        self.test_suites = []

        # Group fixes by file
        fixes_by_file = self._group_fixes_by_file(fixes)

        for file_path, file_fixes in fixes_by_file.items():
            try:
                test_suite = self._generate_test_suite_for_file(file_path, file_fixes)
                if test_suite:
                    self.test_suites.append(test_suite)
                    logger.info(f"Generated {len(test_suite.test_cases)} tests for {file_path}")
            except Exception as e:
                logger.error(f"Error generating tests for {file_path}: {e}")

        total_tests = sum(len(suite.test_cases) for suite in self.test_suites)
        
        result = TestGenerationResult(
            total_files=len(fixes_by_file),
            tests_generated=total_tests,
            test_suites=self.test_suites,
            timestamp=datetime.utcnow().isoformat()
        )

        logger.info(f"Test generation complete: {total_tests} tests for {len(self.test_suites)} files")
        return result

    def _group_fixes_by_file(self, fixes: List[Fix]) -> Dict[str, List[Fix]]:
        """Group fixes by their file path."""
        fixes_by_file = {}
        for fix in fixes:
            if fix.file_path not in fixes_by_file:
                fixes_by_file[fix.file_path] = []
            fixes_by_file[fix.file_path].append(fix)
        return fixes_by_file

    def _generate_test_suite_for_file(self, file_path: str, fixes: List[Fix]) -> Optional[TestSuite]:
        """Generate a test suite for a specific file."""
        try:
            # Read the fixed code
            with open(file_path, 'r', encoding='utf-8') as f:
                code = f.read()

            # Determine language and framework
            language = self._get_language_from_extension(Path(file_path).suffix)
            framework = self.FRAMEWORK_MAP.get(language, 'pytest')

            # Use Bob API to generate tests
            result = self.bob_client.generate_tests(code, language, framework)

            # Parse test cases from result
            test_cases = self._parse_test_cases(result, file_path, framework)

            if not test_cases:
                logger.warning(f"No test cases generated for {file_path}")
                return None

            # Determine test file path
            test_file_path = self._get_test_file_path(file_path, language)

            # Create test suite
            test_suite = TestSuite(
                source_file=file_path,
                test_file=str(test_file_path),
                test_cases=test_cases,
                framework=framework,
                coverage_estimate=result.get('coverage_estimate', 0.0)
            )

            # Write test file
            self._write_test_file(test_suite)

            return test_suite

        except BobAPIError as e:
            logger.error(f"Bob API error generating tests: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error generating tests: {e}")
            return None

    def _parse_test_cases(self, result: Dict[str, Any], file_path: str, 
                         framework: str) -> List[TestCase]:
        """Parse test cases from Bob API result."""
        test_cases = []
        
        for tc_data in result.get('test_cases', []):
            test_case = TestCase(
                test_name=tc_data.get('name', 'test_unknown'),
                test_code=tc_data.get('code', ''),
                description=tc_data.get('description', ''),
                target_function=tc_data.get('target_function', ''),
                file_path=file_path,
                framework=framework
            )
            test_cases.append(test_case)

        return test_cases

    def _get_language_from_extension(self, extension: str) -> str:
        """Map file extension to language identifier."""
        extension_map = {
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
        return extension_map.get(extension.lower(), 'unknown')

    def _get_test_file_path(self, source_file: str, language: str) -> Path:
        """Determine the test file path for a source file."""
        source_path = Path(source_file)
        
        if language == 'python':
            # Python convention: test_filename.py
            test_name = f"test_{source_path.stem}.py"
        elif language in ['javascript', 'typescript']:
            # JS/TS convention: filename.test.js or filename.spec.ts
            test_name = f"{source_path.stem}.test{source_path.suffix}"
        elif language == 'java':
            # Java convention: FilenameTest.java
            test_name = f"{source_path.stem}Test{source_path.suffix}"
        else:
            # Generic convention
            test_name = f"test_{source_path.name}"

        return self.test_dir / test_name

    def _write_test_file(self, test_suite: TestSuite):
        """Write test suite to file."""
        test_file_path = Path(test_suite.test_file)
        
        # Generate test file content
        content = self._generate_test_file_content(test_suite)
        
        # Write to file
        with open(test_file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        logger.info(f"Wrote test file: {test_file_path}")

    def _generate_test_file_content(self, test_suite: TestSuite) -> str:
        """Generate the complete test file content."""
        if test_suite.framework == 'pytest':
            return self._generate_pytest_content(test_suite)
        elif test_suite.framework == 'jest':
            return self._generate_jest_content(test_suite)
        elif test_suite.framework == 'junit':
            return self._generate_junit_content(test_suite)
        else:
            return self._generate_generic_content(test_suite)

    def _generate_pytest_content(self, test_suite: TestSuite) -> str:
        """Generate pytest test file content."""
        lines = [
            '"""',
            f'Unit tests for {test_suite.source_file}',
            'Auto-generated by Bob-Guard Test Generator',
            '"""',
            '',
            'import pytest',
            f'from {Path(test_suite.source_file).stem} import *',
            '',
            ''
        ]

        for test_case in test_suite.test_cases:
            lines.append(f'def {test_case.test_name}():')
            lines.append(f'    """')
            lines.append(f'    {test_case.description}')
            lines.append(f'    """')
            # Add the test code with proper indentation
            for line in test_case.test_code.split('\n'):
                lines.append(f'    {line}' if line.strip() else '')
            lines.append('')
            lines.append('')

        return '\n'.join(lines)

    def _generate_jest_content(self, test_suite: TestSuite) -> str:
        """Generate Jest test file content."""
        lines = [
            '/**',
            f' * Unit tests for {test_suite.source_file}',
            ' * Auto-generated by Bob-Guard Test Generator',
            ' */',
            '',
            f"const module = require('./{Path(test_suite.source_file).stem}');",
            '',
            f"describe('{Path(test_suite.source_file).stem}', () => {{",
            ''
        ]

        for test_case in test_suite.test_cases:
            lines.append(f"  test('{test_case.test_name}', () => {{")
            lines.append(f"    // {test_case.description}")
            # Add the test code with proper indentation
            for line in test_case.test_code.split('\n'):
                lines.append(f'    {line}' if line.strip() else '')
            lines.append('  });')
            lines.append('')

        lines.append('});')
        return '\n'.join(lines)

    def _generate_junit_content(self, test_suite: TestSuite) -> str:
        """Generate JUnit test file content."""
        class_name = Path(test_suite.source_file).stem + 'Test'
        
        lines = [
            'import org.junit.Test;',
            'import static org.junit.Assert.*;',
            '',
            f'public class {class_name} {{',
            ''
        ]

        for test_case in test_suite.test_cases:
            lines.append('    @Test')
            lines.append(f'    public void {test_case.test_name}() {{')
            lines.append(f'        // {test_case.description}')
            # Add the test code with proper indentation
            for line in test_case.test_code.split('\n'):
                lines.append(f'        {line}' if line.strip() else '')
            lines.append('    }')
            lines.append('')

        lines.append('}')
        return '\n'.join(lines)

    def _generate_generic_content(self, test_suite: TestSuite) -> str:
        """Generate generic test file content."""
        lines = [
            f'# Unit tests for {test_suite.source_file}',
            '# Auto-generated by Bob-Guard Test Generator',
            '',
            ''
        ]

        for test_case in test_suite.test_cases:
            lines.append(f'# Test: {test_case.test_name}')
            lines.append(f'# {test_case.description}')
            lines.append(test_case.test_code)
            lines.append('')
            lines.append('')

        return '\n'.join(lines)

    def generate_tests_for_file(self, file_path: str, language: Optional[str] = None) -> Optional[TestSuite]:
        """
        Generate tests for a single file.
        
        Args:
            file_path: Path to the source file
            language: Optional language override
            
        Returns:
            TestSuite if successful, None otherwise
        """
        if not language:
            language = self._get_language_from_extension(Path(file_path).suffix)

        # Create a dummy fix to use existing logic
        from src.remediator import Fix
        dummy_fix = Fix(
            violation_id='manual',
            file_path=file_path,
            original_code='',
            fixed_code='',
            explanation='Manual test generation',
            confidence=1.0
        )

        return self._generate_test_suite_for_file(file_path, [dummy_fix])

    def export_results(self, output_path: str):
        """
        Export test generation results to JSON file.
        
        Args:
            output_path: Path to output file
        """
        import json
        
        result = TestGenerationResult(
            total_files=len(self.test_suites),
            tests_generated=sum(len(suite.test_cases) for suite in self.test_suites),
            test_suites=self.test_suites,
            timestamp=datetime.utcnow().isoformat()
        )

        with open(output_path, 'w') as f:
            json.dump(result.to_dict(), f, indent=2)

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if hasattr(self.bob_client, 'close'):
            self.bob_client.close()

# Made with Bob
