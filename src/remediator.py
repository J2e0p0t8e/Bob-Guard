"""
Code Remediator Module
Automatically generates and applies fixes for compliance violations and security issues.
"""

import os
import logging
import difflib
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
import shutil
from datetime import datetime

from src.bob_client import BobClient, BobAPIError
from src.analyzer import Violation

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class Fix:
    """Represents a code fix for a violation."""
    violation_id: str
    file_path: str
    original_code: str
    fixed_code: str
    explanation: str
    confidence: float  # 0.0 to 1.0
    applied: bool = False
    backup_path: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert fix to dictionary."""
        return asdict(self)


@dataclass
class RemediationResult:
    """Contains the results of remediation process."""
    total_violations: int
    fixes_generated: int
    fixes_applied: int
    fixes_failed: int
    fixes: List[Fix]
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert remediation result to dictionary."""
        return {
            'total_violations': self.total_violations,
            'fixes_generated': self.fixes_generated,
            'fixes_applied': self.fixes_applied,
            'fixes_failed': self.fixes_failed,
            'fixes': [f.to_dict() for f in self.fixes],
            'timestamp': self.timestamp
        }


class CodeRemediator:
    """
    Main remediator class for generating and applying code fixes.
    Uses IBM Bob API for intelligent fix generation.
    """

    def __init__(self, bob_client: Optional[BobClient] = None, backup_dir: str = 'output/backups'):
        """
        Initialize the code remediator.
        
        Args:
            bob_client: Optional BobClient instance (creates new if not provided)
            backup_dir: Directory to store file backups
        """
        self.bob_client = bob_client or BobClient()
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.fixes: List[Fix] = []

    def generate_fixes(self, violations: List[Violation], min_confidence: float = 0.7) -> List[Fix]:
        """
        Generate fixes for a list of violations.
        
        Args:
            violations: List of violations to fix
            min_confidence: Minimum confidence threshold for applying fixes
            
        Returns:
            List of generated fixes
        """
        logger.info(f"Generating fixes for {len(violations)} violations")
        self.fixes = []

        for violation in violations:
            try:
                fix = self._generate_fix_for_violation(violation)
                if fix and fix.confidence >= min_confidence:
                    self.fixes.append(fix)
                    logger.info(f"Generated fix for violation {violation.id} (confidence: {fix.confidence:.2f})")
                else:
                    logger.warning(f"Fix confidence too low for violation {violation.id}")
            except Exception as e:
                logger.error(f"Error generating fix for violation {violation.id}: {e}")

        logger.info(f"Generated {len(self.fixes)} fixes")
        return self.fixes

    def _generate_fix_for_violation(self, violation: Violation) -> Optional[Fix]:
        """Generate a fix for a single violation using Bob API."""
        try:
            # Read the file content
            with open(violation.file_path, 'r', encoding='utf-8') as f:
                code = f.read()

            # Determine language from file extension
            file_path = Path(violation.file_path)
            language = self._get_language_from_extension(file_path.suffix)

            # Use Bob API to generate fix
            violation_data = violation.to_dict()
            result = self.bob_client.generate_fix(code, violation_data, language)

            # Extract fix information
            fixed_code = result.get('fixed_code', '')
            explanation = result.get('explanation', '')
            confidence = result.get('confidence', 0.5)

            if not fixed_code:
                logger.warning(f"No fix generated for violation {violation.id}")
                return None

            fix = Fix(
                violation_id=violation.id,
                file_path=violation.file_path,
                original_code=code,
                fixed_code=fixed_code,
                explanation=explanation,
                confidence=confidence
            )

            return fix

        except BobAPIError as e:
            logger.error(f"Bob API error generating fix: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error generating fix: {e}")
            return None

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

    def apply_fixes(self, fixes: Optional[List[Fix]] = None, auto_apply: bool = False,
                   create_backup: bool = True) -> RemediationResult:
        """
        Apply generated fixes to files.
        
        Args:
            fixes: List of fixes to apply (uses self.fixes if None)
            auto_apply: If True, apply all fixes without confirmation
            create_backup: If True, create backup before applying fixes
            
        Returns:
            RemediationResult with application statistics
        """
        fixes_to_apply = fixes or self.fixes
        logger.info(f"Applying {len(fixes_to_apply)} fixes")

        applied_count = 0
        failed_count = 0

        for fix in fixes_to_apply:
            try:
                if not auto_apply:
                    # In interactive mode, would prompt user here
                    # For now, we'll apply if confidence is high enough
                    if fix.confidence < 0.8:
                        logger.info(f"Skipping fix for {fix.file_path} (low confidence)")
                        continue

                # Create backup if requested
                if create_backup:
                    backup_path = self._create_backup(fix.file_path)
                    fix.backup_path = str(backup_path)

                # Apply the fix
                self._apply_fix(fix)
                fix.applied = True
                applied_count += 1
                logger.info(f"Applied fix to {fix.file_path}")

            except Exception as e:
                logger.error(f"Error applying fix to {fix.file_path}: {e}")
                failed_count += 1

        result = RemediationResult(
            total_violations=len(fixes_to_apply),
            fixes_generated=len(fixes_to_apply),
            fixes_applied=applied_count,
            fixes_failed=failed_count,
            fixes=fixes_to_apply,
            timestamp=datetime.utcnow().isoformat()
        )

        logger.info(f"Remediation complete: {applied_count} applied, {failed_count} failed")
        return result

    def _create_backup(self, file_path: str) -> Path:
        """Create a backup of the file before modification."""
        source = Path(file_path)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_name = f"{source.stem}_{timestamp}{source.suffix}.bak"
        backup_path = self.backup_dir / backup_name

        shutil.copy2(source, backup_path)
        logger.debug(f"Created backup: {backup_path}")
        return backup_path

    def _apply_fix(self, fix: Fix):
        """Apply a fix to the file."""
        with open(fix.file_path, 'w', encoding='utf-8') as f:
            f.write(fix.fixed_code)

    def preview_fix(self, fix: Fix) -> str:
        """
        Generate a unified diff preview of the fix.
        
        Args:
            fix: Fix to preview
            
        Returns:
            Unified diff string
        """
        original_lines = fix.original_code.splitlines(keepends=True)
        fixed_lines = fix.fixed_code.splitlines(keepends=True)

        diff = difflib.unified_diff(
            original_lines,
            fixed_lines,
            fromfile=f"{fix.file_path} (original)",
            tofile=f"{fix.file_path} (fixed)",
            lineterm=''
        )

        return ''.join(diff)

    def rollback_fix(self, fix: Fix) -> bool:
        """
        Rollback a fix using its backup.
        
        Args:
            fix: Fix to rollback
            
        Returns:
            True if rollback successful, False otherwise
        """
        if not fix.backup_path or not Path(fix.backup_path).exists():
            logger.error(f"No backup found for {fix.file_path}")
            return False

        try:
            shutil.copy2(fix.backup_path, fix.file_path)
            fix.applied = False
            logger.info(f"Rolled back fix for {fix.file_path}")
            return True
        except Exception as e:
            logger.error(f"Error rolling back fix: {e}")
            return False

    def get_fixes_by_confidence(self, min_confidence: float, max_confidence: float = 1.0) -> List[Fix]:
        """Get fixes within a confidence range."""
        return [f for f in self.fixes 
                if min_confidence <= f.confidence <= max_confidence]

    def get_applied_fixes(self) -> List[Fix]:
        """Get all applied fixes."""
        return [f for f in self.fixes if f.applied]

    def get_pending_fixes(self) -> List[Fix]:
        """Get all pending (not applied) fixes."""
        return [f for f in self.fixes if not f.applied]

    def export_fixes(self, output_path: str, format: str = 'json'):
        """
        Export fixes to file.
        
        Args:
            output_path: Path to output file
            format: Output format ('json' or 'diff')
        """
        import json

        if format == 'json':
            with open(output_path, 'w') as f:
                json.dump([fix.to_dict() for fix in self.fixes], f, indent=2)
        elif format == 'diff':
            with open(output_path, 'w') as f:
                for fix in self.fixes:
                    f.write(self.preview_fix(fix))
                    f.write('\n\n' + '='*80 + '\n\n')

    def validate_fix(self, fix: Fix) -> Tuple[bool, str]:
        """
        Validate that a fix doesn't introduce syntax errors.
        
        Args:
            fix: Fix to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        file_path = Path(fix.file_path)
        language = self._get_language_from_extension(file_path.suffix)

        # For Python, we can do basic syntax checking
        if language == 'python':
            try:
                compile(fix.fixed_code, fix.file_path, 'exec')
                return True, "Valid Python syntax"
            except SyntaxError as e:
                return False, f"Syntax error: {str(e)}"

        # For other languages, would need language-specific validators
        return True, "Validation not implemented for this language"

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if hasattr(self.bob_client, 'close'):
            self.bob_client.close()

# Made with Bob
