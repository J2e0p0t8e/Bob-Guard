"""
Remediation Module
Automatically generates and applies fixes for detected code violations.

This module receives detected violations and intelligently generates fixes using IBM Bob,
then applies them with proper validation, backup, and conflict resolution.
"""

import os
import shutil
import logging
import difflib
import ast
import re
import json
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime
from collections import defaultdict

from src.bob_client import BobClient, BobAPIError
from src.analyzer import Violation

# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class RemediationResult:
    """
    Represents the result of a single remediation operation.
    
    Attributes:
        violation_id: ID of the violation that was remediated
        file_path: Path to the file that was fixed
        original_code: Original code snippet before fix
        fixed_code: Code after applying the fix
        diff: Unified diff showing the changes
        status: Status of remediation (SUCCESS, FAILED, SKIPPED, DRY_RUN)
        error_message: Error message if remediation failed
        confidence: Confidence score from Bob (0.0 to 1.0)
        backup_path: Path to backup file created
        applied_at: Timestamp when fix was applied
    """
    violation_id: str
    file_path: str
    original_code: str
    fixed_code: str
    diff: str
    status: str  # SUCCESS, FAILED, SKIPPED, DRY_RUN
    error_message: Optional[str] = None
    confidence: float = 0.0
    backup_path: Optional[str] = None
    applied_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary for serialization."""
        return asdict(self)


@dataclass
class RemediationReport:
    """
    Comprehensive report of all remediation operations.
    
    Attributes:
        total_violations: Total number of violations processed
        successful_fixes: Number of successfully applied fixes
        failed_fixes: Number of failed fix attempts
        skipped_fixes: Number of skipped violations
        dry_run: Whether this was a dry run (no actual changes)
        results: List of individual remediation results
        files_modified: Set of file paths that were modified
        execution_time: Time taken to complete remediation
        generated_at: Timestamp when report was generated
    """
    total_violations: int
    successful_fixes: int
    failed_fixes: int
    skipped_fixes: int
    dry_run: bool
    results: List[RemediationResult]
    files_modified: List[str]
    execution_time: float = 0.0
    generated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert report to dictionary for serialization."""
        data = asdict(self)
        data['results'] = [r.to_dict() for r in self.results]
        return data


class Remediator:
    """
    Main remediation class for generating and applying fixes to code violations.
    
    Handles:
    - Intelligent fix generation via IBM Bob
    - Conflict resolution when multiple violations affect the same file
    - Automatic backup creation before modifications
    - Syntax validation of generated fixes
    - Dry-run mode for safe testing
    """
    
    # Severity order for prioritization (highest to lowest)
    SEVERITY_ORDER = {
        'CRITICAL': 0,
        'HIGH': 1,
        'MEDIUM': 2,
        'LOW': 3
    }
    
    # Language-specific syntax validators
    SYNTAX_VALIDATORS = {
        'python': '_validate_python_syntax',
        'javascript': '_validate_javascript_syntax',
        'typescript': '_validate_javascript_syntax',
        'java': '_validate_java_syntax',
    }
    
    def __init__(self, violations: List[Violation], bob_client: BobClient, dry_run: bool = True):
        """
        Initialize the Remediator.
        
        Args:
            violations: List of detected violations to remediate
            bob_client: Initialized BobClient instance for fix generation
            dry_run: If True, generate fixes but don't apply them (default: True)
        """
        self.violations = violations
        self.bob_client = bob_client
        self.dry_run = dry_run
        self.results: List[RemediationResult] = []
        self.start_time = datetime.utcnow()
        
        logger.info(f"Remediator initialized with {len(violations)} violations (dry_run={dry_run})")
    
    def remediate_all(self) -> RemediationReport:
        """
        Remediate all violations intelligently.
        
        Process:
        1. Sort violations by severity (CRITICAL first)
        2. Group violations by file to avoid conflicts
        3. For each file, remediate all violations together
        4. Generate comprehensive report
        
        Returns:
            RemediationReport with results of all remediation operations
        """
        logger.info("Starting remediation process...")
        
        # Sort violations by severity
        sorted_violations = self._sort_by_severity(self.violations)
        
        # Group violations by file
        violations_by_file = self._group_by_file(sorted_violations)
        
        logger.info(f"Processing {len(violations_by_file)} files with violations")
        
        # Remediate each file
        for file_path, file_violations in violations_by_file.items():
            try:
                logger.info(f"Remediating {len(file_violations)} violations in {file_path}")
                file_results = self.remediate_file(file_path, file_violations)
                self.results.extend(file_results)
            except Exception as e:
                logger.error(f"Error remediating file {file_path}: {str(e)}")
                # Create failed results for all violations in this file
                for violation in file_violations:
                    self.results.append(RemediationResult(
                        violation_id=violation.id,
                        file_path=file_path,
                        original_code=violation.code_snippet,
                        fixed_code="",
                        diff="",
                        status="FAILED",
                        error_message=str(e)
                    ))
        
        # Generate report
        report = self._generate_report()
        
        execution_time = (datetime.utcnow() - self.start_time).total_seconds()
        report.execution_time = execution_time
        
        logger.info(f"Remediation complete: {report.successful_fixes} successful, "
                   f"{report.failed_fixes} failed, {report.skipped_fixes} skipped")
        
        return report
    
    def _generate_fix_prompt(self, file_path: str, file_content: str,
                            violation: Violation, language: str) -> str:
        """
        Generate a comprehensive prompt for IBM Bob to fix a violation.
        
        The prompt provides full context and clear instructions for generating
        a complete corrected file while respecting existing code style.
        
        Args:
            file_path: Path to the file being fixed
            file_content: Complete content of the file
            violation: The violation to fix
            language: Programming language of the file
            
        Returns:
            Formatted prompt string for IBM Bob
        """
        # Detect language version if possible
        language_version = self._detect_language_version(file_content, language)
        
        prompt = f"""You are an expert code remediation assistant. Your task is to fix a specific code violation while preserving the existing code structure and logic.

# SECTION 1: CONTEXT

**File Information:**
- File Path: `{file_path}`
- Programming Language: {language}{f' ({language_version})' if language_version else ''}
- Affected Line(s): {violation.line_number}
- Total Lines: {len(file_content.splitlines())}

**Complete File Content:**
```{language}
{file_content}
```

**Violation Details:**
- Violation ID: {violation.id}
- Rule: {violation.rule_id} - {violation.rule_name}
- Category: {violation.category}
- Severity: {violation.severity}
- Description: {violation.description}
- Explanation: {violation.explanation}
- Recommendation: {violation.recommendation}

**Problematic Code (Line {violation.line_number}):**
```{language}
{violation.code_snippet}
```

# SECTION 2: FIX CONSTRAINTS

You MUST follow these constraints when generating the fix:

1. **Preserve Code Style:**
   - Maintain the existing naming conventions (camelCase, snake_case, etc.)
   - Keep the same indentation style (spaces/tabs, indent size)
   - Follow the existing code formatting patterns
   - Preserve existing comments and docstrings

2. **Minimize Changes:**
   - Apply the PRINCIPLE OF LEAST CHANGE
   - Only modify what is necessary to fix the violation
   - Do NOT refactor unrelated code
   - Do NOT change variable/function names unless required for the fix
   - Do NOT modify the business logic or functionality

3. **Preserve Functionality:**
   - The fixed code MUST maintain the same behavior as the original
   - Do NOT alter the program's logic or control flow
   - Ensure all existing function signatures remain compatible
   - Keep all imports and dependencies intact unless they're part of the violation

4. **Language-Specific Requirements:**
   - Use {language}{f' {language_version}' if language_version else ''} syntax and best practices
   - Follow language-specific security and compliance standards
   - Ensure the fix is compatible with the language version

# SECTION 3: REQUIRED RESPONSE FORMAT

You MUST respond with ONLY a valid JSON object. Do NOT include any text before or after the JSON.
Do NOT use markdown code blocks. Return ONLY the raw JSON.

The JSON must have this exact structure:

{{
  "can_fix": true or false,
  "fix_description": "Brief description of what was changed and why (1-2 sentences)",
  "patched_code": "THE COMPLETE CORRECTED FILE CONTENT - EVERY SINGLE LINE FROM START TO END",
  "changes_summary": [
    "Specific change 1",
    "Specific change 2"
  ],
  "risk_level": "low" or "medium" or "high",
  "requires_manual_review": true or false,
  "confidence": 0.0 to 1.0
}}

**CRITICAL:** The "patched_code" field MUST contain the ENTIRE file with the fix applied, not just the modified lines or a snippet. Include every line from the beginning to the end of the file.

**If you cannot fix the violation safely:**
- Set "can_fix" to false
- Provide a brief explanation in "fix_description"
- Set "patched_code" to an empty string
- Explain why in "changes_summary"

Now, generate the fix following all constraints above. Return ONLY the JSON response."""

        return prompt
    
    def _detect_language_version(self, file_content: str, language: str) -> Optional[str]:
        """
        Attempt to detect the language version from file content.
        
        Args:
            file_content: Content of the file
            language: Programming language
            
        Returns:
            Version string if detected, None otherwise
        """
        if language == 'python':
            # Look for version hints in shebang or comments
            if '#!/usr/bin/env python3' in file_content or '# -*- coding: utf-8 -*-' in file_content:
                return '3.x'
            if 'from __future__ import' in file_content:
                return '2.7+'
        
        return None
    
    def remediate_file(self, file_path: str, violations: List[Violation]) -> List[RemediationResult]:
        """
        Remediate all violations in a single file.
        
        Process:
        1. Read the entire file content
        2. Generate fixes for each violation via Bob with comprehensive prompts
        3. Apply all fixes in one operation (to avoid conflicts)
        4. Create backup before modification
        5. Validate syntax of fixed code
        6. Write fixed content or return dry-run results
        
        Args:
            file_path: Path to the file to remediate
            violations: List of violations in this file
            
        Returns:
            List of RemediationResult objects for each violation
        """
        results = []
        
        try:
            # Read original file content
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"File not found: {file_path}")
            
            with open(file_path, 'r', encoding='utf-8') as f:
                original_content = f.read()
            
            # Detect language
            file_ext = Path(file_path).suffix.lower()
            language = self._get_language_from_extension(file_ext) or 'unknown'
            
            # Track the current content as we apply fixes
            current_content = original_content
            
            # Process each violation
            for violation in violations:
                try:
                    logger.debug(f"Generating fix for violation {violation.id}")
                    
                    # Generate comprehensive prompt for Bob
                    prompt = self._generate_fix_prompt(
                        file_path=file_path,
                        file_content=current_content,
                        violation=violation,
                        language=language
                    )
                    
                    # Prefer `generate_fix` when available (tests and some clients)
                    fix_data = None
                    try:
                        if hasattr(self.bob_client, 'generate_fix'):
                            resp = self.bob_client.generate_fix(code_snippet=prompt, violation_type=violation.rule_id)
                            # Normalize string responses
                            if isinstance(resp, str):
                                try:
                                    resp = json.loads(resp)
                                except Exception:
                                    resp = {'fixed_code': str(resp)}

                            # If the client returned a dict with 'fixed_code', convert to expected structure
                            if isinstance(resp, dict) and 'fixed_code' in resp:
                                fix_data = {
                                    'can_fix': True,
                                    'patched_code': resp.get('fixed_code', ''),
                                    'fix_description': resp.get('explanation', ''),
                                    'changes_summary': [resp.get('diff', '')],
                                    'requires_manual_review': False,
                                    'confidence': resp.get('confidence', 0.0),
                                    'risk_level': 'unknown'
                                }
                            elif isinstance(resp, dict):
                                fix_data = resp
                            else:
                                fix_data = {'can_fix': False, 'patched_code': ''}
                        else:
                            # Fallback to chat interface
                            fix_response = self.bob_client.chat(
                                message=prompt,
                                context={
                                    'file_path': file_path,
                                    'violation_id': violation.id,
                                    'action': 'remediate'
                                }
                            )

                            # Normalize chat response
                            if isinstance(fix_response, dict) and 'response' in fix_response:
                                response_text = fix_response.get('response', '')
                            else:
                                response_text = str(fix_response)

                            # Try to extract JSON from response_text
                            try:
                                if isinstance(response_text, str):
                                    # Remove markdown code blocks if present
                                    if '```json' in response_text:
                                        response_text = response_text.split('```json')[1].split('```')[0].strip()
                                    elif '```' in response_text:
                                        response_text = response_text.split('```')[1].split('```')[0].strip()
                                    fix_data = json.loads(response_text)
                                else:
                                    fix_data = {}
                            except Exception:
                                logger.error(f"Failed to parse Bob's response as JSON for violation {violation.id}")
                                results.append(RemediationResult(
                                    violation_id=violation.id,
                                    file_path=file_path,
                                    original_code=violation.code_snippet,
                                    fixed_code="",
                                    diff="",
                                    status="FAILED",
                                    error_message="Invalid JSON response from Bob"
                                ))
                                continue
                    except BobAPIError as e:
                        logger.error(f"Bob API error for violation {violation.id}: {str(e)}")
                        results.append(RemediationResult(
                            violation_id=violation.id,
                            file_path=file_path,
                            original_code=violation.code_snippet,
                            fixed_code="",
                            diff="",
                            status="FAILED",
                            error_message=f"Bob API error: {str(e)}"
                        ))
                        continue
                    
                    # Check if Bob can fix the violation
                    if not fix_data.get('can_fix', False):
                        logger.warning(f"Bob cannot fix violation {violation.id}: {fix_data.get('fix_description', 'Unknown reason')}")
                        results.append(RemediationResult(
                            violation_id=violation.id,
                            file_path=file_path,
                            original_code=violation.code_snippet,
                            fixed_code="",
                            diff="",
                            status="SKIPPED",
                            error_message=fix_data.get('fix_description', 'Cannot fix safely')
                        ))
                        continue
                    
                    patched_code = fix_data.get('patched_code', '')
                    confidence = fix_data.get('confidence', 0.0)
                    fix_description = fix_data.get('fix_description', '')
                    changes_summary = fix_data.get('changes_summary', [])
                    risk_level = fix_data.get('risk_level', 'unknown')
                    requires_review = fix_data.get('requires_manual_review', False)
                    
                    if not patched_code:
                        logger.error(f"Bob returned empty patched code for violation {violation.id}")
                        results.append(RemediationResult(
                            violation_id=violation.id,
                            file_path=file_path,
                            original_code=violation.code_snippet,
                            fixed_code="",
                            diff="",
                            status="FAILED",
                            error_message="Bob did not generate patched code",
                            confidence=confidence
                        ))
                        continue
                    
                    # Validate the patched code syntax
                    if not self._validate_syntax(patched_code, language):
                        logger.error(f"Patched code has invalid syntax for violation {violation.id}")
                        results.append(RemediationResult(
                            violation_id=violation.id,
                            file_path=file_path,
                            original_code=violation.code_snippet,
                            fixed_code=patched_code,
                            diff="",
                            status="FAILED",
                            error_message="Generated code has invalid syntax",
                            confidence=confidence
                        ))
                        continue
                    
                    # Generate diff between current and patched content
                    diff = self._generate_diff(
                        current_content,
                        patched_code,
                        file_path
                    )
                    
                    # Update current content for next iteration (use the complete patched file)
                    current_content = patched_code
                    
                    # Create result with additional metadata
                    status = "DRY_RUN" if self.dry_run else "SUCCESS"
                    result = RemediationResult(
                        violation_id=violation.id,
                        file_path=file_path,
                        original_code=violation.code_snippet,
                        fixed_code=patched_code,
                        diff=diff,
                        status=status,
                        confidence=confidence
                    )
                    results.append(result)
                    
                    logger.info(f"Fix generated for violation {violation.id} "
                               f"(confidence: {confidence:.2f}, risk: {risk_level}, "
                               f"requires_review: {requires_review})")
                    logger.debug(f"Changes: {', '.join(changes_summary)}")
                
                except BobAPIError as e:
                    logger.error(f"Bob API error for violation {violation.id}: {str(e)}")
                    results.append(RemediationResult(
                        violation_id=violation.id,
                        file_path=file_path,
                        original_code=violation.code_snippet,
                        fixed_code="",
                        diff="",
                        status="FAILED",
                        error_message=f"Bob API error: {str(e)}"
                    ))
                
                except Exception as e:
                    logger.error(f"Error processing violation {violation.id}: {str(e)}")
                    results.append(RemediationResult(
                        violation_id=violation.id,
                        file_path=file_path,
                        original_code=violation.code_snippet,
                        fixed_code="",
                        diff="",
                        status="FAILED",
                        error_message=str(e)
                    ))
            
            # If we have successful fixes and not in dry-run mode, apply the patch
            if not self.dry_run and current_content != original_content:
                backup_path = self.apply_patch(file_path, original_content, current_content)
                # Update all successful results with backup path
                for result in results:
                    if result.status == "SUCCESS":
                        result.backup_path = backup_path
        
        except Exception as e:
            logger.error(f"Error reading file {file_path}: {str(e)}")
            # Create failed results for all violations
            for violation in violations:
                results.append(RemediationResult(
                    violation_id=violation.id,
                    file_path=file_path,
                    original_code=violation.code_snippet,
                    fixed_code="",
                    diff="",
                    status="FAILED",
                    error_message=f"File error: {str(e)}"
                ))
        
        return results
    
    def apply_patch(self, file_path: str, original_content: str, 
                   patched_content: str) -> Optional[str]:
        """
        Apply a patch to a file with validation and backup.
        
        Process:
        1. Validate syntax of patched content
        2. Create backup of original file
        3. Write patched content
        4. Log the operation
        
        Args:
            file_path: Path to the file to patch
            original_content: Original file content
            patched_content: Content after applying fixes
            
        Returns:
            Path to backup file, or None if backup failed
            
        Raises:
            ValueError: If syntax validation fails
            IOError: If file operations fail
        """
        logger.info(f"Applying patch to {file_path}")
        
        # Validate syntax
        file_ext = Path(file_path).suffix.lower()
        language = self._get_language_from_extension(file_ext)
        
        if language and not self._validate_syntax(patched_content, language):
            raise ValueError(f"Patched content has invalid {language} syntax")
        
        # Create backup
        backup_path = f"{file_path}.backup"
        try:
            shutil.copy2(file_path, backup_path)
            logger.info(f"Created backup at {backup_path}")
        except Exception as e:
            logger.error(f"Failed to create backup: {str(e)}")
            backup_path = None
        
        # Generate and log diff
        diff = self._generate_diff(original_content, patched_content, file_path)
        logger.debug(f"Diff for {file_path}:\n{diff}")
        
        # Write patched content
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(patched_content)
            logger.info(f"Successfully wrote patched content to {file_path}")
        except Exception as e:
            # Restore from backup if write fails
            if backup_path and os.path.exists(backup_path):
                shutil.copy2(backup_path, file_path)
                logger.info(f"Restored original file from backup")
            raise IOError(f"Failed to write patched file: {str(e)}")
        
        return backup_path
    
    def _sort_by_severity(self, violations: List[Violation]) -> List[Violation]:
        """
        Sort violations by severity (CRITICAL first).
        
        Args:
            violations: List of violations to sort
            
        Returns:
            Sorted list of violations
        """
        return sorted(
            violations,
            key=lambda v: self.SEVERITY_ORDER.get(v.severity, 999)
        )
    
    def _group_by_file(self, violations: List[Violation]) -> Dict[str, List[Violation]]:
        """
        Group violations by file path.
        
        Args:
            violations: List of violations to group
            
        Returns:
            Dictionary mapping file paths to lists of violations
        """
        grouped = defaultdict(list)
        for violation in violations:
            grouped[violation.file_path].append(violation)
        return dict(grouped)
    
    def _generate_diff(self, original: str, fixed: str, file_path: str) -> str:
        """
        Generate a unified diff between original and fixed content.
        
        Args:
            original: Original content
            fixed: Fixed content
            file_path: Path to the file (for diff header)
            
        Returns:
            Unified diff as string
        """
        original_lines = original.splitlines(keepends=True)
        fixed_lines = fixed.splitlines(keepends=True)
        
        diff = difflib.unified_diff(
            original_lines,
            fixed_lines,
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}",
            lineterm=''
        )
        
        return ''.join(diff)
    
    def _validate_syntax(self, code: str, language: str) -> bool:
        """
        Validate syntax of code for a given language.
        
        Args:
            code: Code to validate
            language: Programming language
            
        Returns:
            True if syntax is valid, False otherwise
        """
        validator_method = self.SYNTAX_VALIDATORS.get(language)
        if not validator_method:
            logger.warning(f"No syntax validator for {language}, skipping validation")
            return True
        
        try:
            method = getattr(self, validator_method)
            return method(code)
        except Exception as e:
            logger.error(f"Syntax validation error: {str(e)}")
            return False
    
    def _validate_python_syntax(self, code: str) -> bool:
        """
        Validate Python syntax using AST.
        
        Args:
            code: Python code to validate
            
        Returns:
            True if syntax is valid, False otherwise
        """
        try:
            ast.parse(code)
            return True
        except SyntaxError as e:
            logger.error(f"Python syntax error: {str(e)}")
            return False
    
    def _validate_javascript_syntax(self, code: str) -> bool:
        """
        Basic JavaScript/TypeScript syntax validation.
        
        Note: This is a simple check. For production, consider using a proper JS parser.
        
        Args:
            code: JavaScript/TypeScript code to validate
            
        Returns:
            True if basic syntax checks pass
        """
        # Basic checks for common syntax errors
        # Count braces, brackets, parentheses
        if code.count('{') != code.count('}'):
            logger.error("Mismatched curly braces")
            return False
        if code.count('[') != code.count(']'):
            logger.error("Mismatched square brackets")
            return False
        if code.count('(') != code.count(')'):
            logger.error("Mismatched parentheses")
            return False
        
        return True
    
    def _validate_java_syntax(self, code: str) -> bool:
        """
        Basic Java syntax validation.
        
        Note: This is a simple check. For production, consider using a proper Java parser.
        
        Args:
            code: Java code to validate
            
        Returns:
            True if basic syntax checks pass
        """
        # Basic checks similar to JavaScript
        if code.count('{') != code.count('}'):
            logger.error("Mismatched curly braces")
            return False
        if code.count('[') != code.count(']'):
            logger.error("Mismatched square brackets")
            return False
        if code.count('(') != code.count(')'):
            logger.error("Mismatched parentheses")
            return False
        
        return True
    
    def validate_patch(self, file_path: str, original_code: str,
                      patched_code: str, language: str, 
                      violation_type: str = "unknown") -> Dict[str, Any]:
        """
        Validate that a patched file is syntactically correct and doesn't introduce new issues.
        
        This method performs multi-level validation:
        1. Syntax validation by language
        2. Semantic validation via IBM Bob
        3. Business logic preservation check
        
        Args:
            file_path: Path to the file being validated
            original_code: Original code before patching
            patched_code: Code after applying the patch
            language: Programming language of the file
            violation_type: Type of violation that was fixed
            
        Returns:
            Dictionary containing:
                - valid: Boolean indicating if patch is valid
                - syntax_valid: Boolean for syntax check result
                - semantic_valid: Boolean for semantic check result
                - issues: List of issues found
                - bob_analysis: Bob's detailed analysis
        """
        logger.info(f"Validating patch for {file_path}")
        
        validation_result = {
            'valid': False,
            'syntax_valid': False,
            'semantic_valid': False,
            'issues': [],
            'bob_analysis': {}
        }
        
        # Step 1: Syntax Validation
        syntax_result = self._validate_syntax_comprehensive(patched_code, language)
        validation_result['syntax_valid'] = syntax_result['valid']
        
        if not syntax_result['valid']:
            validation_result['issues'].extend(syntax_result['errors'])
            logger.error(f"Syntax validation failed for {file_path}: {syntax_result['errors']}")
            return validation_result
        
        logger.info(f"Syntax validation passed for {file_path}")
        
        # Step 2: Semantic Validation via Bob
        try:
            semantic_result = self._validate_patch_with_bob(
                original_code=original_code,
                patched_code=patched_code,
                violation_type=violation_type,
                language=language,
                file_path=file_path
            )
            
            validation_result['semantic_valid'] = semantic_result.get('valid', False)
            validation_result['bob_analysis'] = semantic_result
            
            if not semantic_result.get('valid', False):
                issues = semantic_result.get('issues', [])
                validation_result['issues'].extend(issues)
                logger.warning(f"Semantic validation failed for {file_path}: {issues}")
            else:
                logger.info(f"Semantic validation passed for {file_path}")
            
        except Exception as e:
            logger.error(f"Error during semantic validation: {e}")
            validation_result['issues'].append(f"Semantic validation error: {str(e)}")
            validation_result['semantic_valid'] = False
        
        # Overall validation result
        validation_result['valid'] = (
            validation_result['syntax_valid'] and 
            validation_result['semantic_valid']
        )
        
        # Log final result
        if validation_result['valid']:
            logger.info(f"✓ Patch validation successful for {file_path}")
        else:
            logger.error(f"✗ Patch validation failed for {file_path}")
            logger.error(f"  Issues: {', '.join(validation_result['issues'])}")
        
        return validation_result
    
    def _validate_syntax_comprehensive(self, code: str, language: str) -> Dict[str, Any]:
        """
        Comprehensive syntax validation by language.
        
        Args:
            code: Code to validate
            language: Programming language
            
        Returns:
            Dictionary with 'valid' boolean and 'errors' list
        """
        result = {
            'valid': True,
            'errors': []
        }
        
        # Check if code is empty
        if not code or not code.strip():
            result['valid'] = False
            result['errors'].append("Code is empty")
            return result
        
        # Language-specific validation
        if language == 'python':
            try:
                ast.parse(code)
                logger.debug("Python syntax validation passed")
            except SyntaxError as e:
                result['valid'] = False
                result['errors'].append(f"Python syntax error at line {e.lineno}: {e.msg}")
            except Exception as e:
                result['valid'] = False
                result['errors'].append(f"Python parsing error: {str(e)}")
        
        elif language in ['javascript', 'typescript']:
            # Basic JavaScript/TypeScript validation
            errors = []
            
            if code.count('{') != code.count('}'):
                errors.append("Mismatched curly braces")
            if code.count('[') != code.count(']'):
                errors.append("Mismatched square brackets")
            if code.count('(') != code.count(')'):
                errors.append("Mismatched parentheses")
            
            # Check for common syntax errors
            if code.count('"') % 2 != 0 and code.count("'") % 2 != 0:
                errors.append("Unclosed string literal")
            
            if errors:
                result['valid'] = False
                result['errors'].extend(errors)
            else:
                logger.debug(f"{language} syntax validation passed")
        
        elif language == 'java':
            # Basic Java validation
            errors = []
            
            if code.count('{') != code.count('}'):
                errors.append("Mismatched curly braces")
            if code.count('[') != code.count(']'):
                errors.append("Mismatched square brackets")
            if code.count('(') != code.count(')'):
                errors.append("Mismatched parentheses")
            
            # Check for class definition
            if 'class ' not in code and 'interface ' not in code:
                errors.append("No class or interface definition found")
            
            if errors:
                result['valid'] = False
                result['errors'].extend(errors)
            else:
                logger.debug("Java syntax validation passed")
        
        else:
            # Generic validation for other languages
            logger.debug(f"Generic validation for {language}")
            
            # Check for basic coherence
            if len(code.strip()) < 10:
                result['valid'] = False
                result['errors'].append("Code appears too short to be valid")
            
            # Check for balanced braces (common in many languages)
            if code.count('{') != code.count('}'):
                result['errors'].append("Warning: Mismatched curly braces")
        
        return result
    
    def _validate_patch_with_bob(self, original_code: str, patched_code: str,
                                 violation_type: str, language: str,
                                 file_path: str) -> Dict[str, Any]:
        """
        Use IBM Bob to validate that the patch correctly fixes the violation
        without introducing new issues.
        
        Args:
            original_code: Original code before fix
            patched_code: Code after applying fix
            violation_type: Type of violation that was fixed
            language: Programming language
            file_path: Path to the file
            
        Returns:
            Dictionary with validation results from Bob
        """
        prompt = f"""You are a code security and quality validator. Your task is to analyze two versions of a code file and determine if the correction is valid.

# FILE INFORMATION
- File: `{file_path}`
- Language: {language}
- Violation Type: {violation_type}

# ORIGINAL CODE (Before Fix)
```{language}
{original_code}
```

# CORRECTED CODE (After Fix)
```{language}
{patched_code}
```

# YOUR TASK

Analyze ONLY the following aspects:

1. **Violation Resolution**: Does the corrected version effectively resolve the {violation_type} violation?
   - Check if the specific security/quality issue has been addressed
   - Verify the fix is appropriate for the violation type

2. **No New Vulnerabilities**: Has the correction introduced any obvious new security vulnerabilities or quality issues?
   - Look for new SQL injection risks
   - Check for new XSS vulnerabilities
   - Identify potential new security holes
   - Check for logic errors

3. **Business Logic Preservation**: Does the corrected code appear to maintain the same business logic and functionality?
   - Same inputs and outputs
   - Same control flow (unless required by the fix)
   - Same side effects
   - No unintended behavior changes

# IMPORTANT CONSTRAINTS

- Focus ONLY on the three aspects above
- Do NOT critique code style or formatting
- Do NOT suggest additional improvements
- Do NOT analyze performance unless it's a critical regression
- Be objective and specific in identifying issues

# REQUIRED RESPONSE FORMAT

Respond with ONLY a valid JSON object. No markdown, no extra text.

```json
{{
  "valid": true or false,
  "violation_resolved": true or false,
  "new_vulnerabilities": [],
  "logic_preserved": true or false,
  "issues": [
    "Specific issue 1 if any",
    "Specific issue 2 if any"
  ],
  "analysis": {{
    "violation_resolution": "Brief explanation of how/if the violation was resolved",
    "security_assessment": "Brief security assessment of the corrected code",
    "logic_assessment": "Brief assessment of business logic preservation"
  }},
  "confidence": 0.0 to 1.0,
  "recommendation": "approve" or "reject" or "manual_review"
}}
```

**Field Descriptions:**
- `valid`: Overall validation result (true if all checks pass)
- `violation_resolved`: Whether the original violation is fixed
- `new_vulnerabilities`: List of any new security issues introduced
- `logic_preserved`: Whether business logic appears intact
- `issues`: List of specific problems found (empty if none)
- `analysis`: Detailed breakdown of each aspect
- `confidence`: Your confidence in this assessment (0.0-1.0)
- `recommendation`: "approve" (safe to apply), "reject" (do not apply), or "manual_review" (human review needed)

Now analyze the code and provide your validation. Return ONLY the JSON response.
"""
        
        try:
            # Send to Bob via chat endpoint
            response = self.bob_client.chat(
                message=prompt,
                context={
                    'action': 'validate_patch',
                    'file_path': file_path,
                    'violation_type': violation_type
                }
            )
            
            # Parse Bob's response
            response_text = response.get('response', '')
            
            # Extract JSON from response
            if '```json' in response_text:
                response_text = response_text.split('```json')[1].split('```')[0].strip()
            elif '```' in response_text:
                response_text = response_text.split('```')[1].split('```')[0].strip()
            
            validation_data = json.loads(response_text)
            
            logger.debug(f"Bob validation result: {validation_data.get('recommendation', 'unknown')}")
            
            return validation_data
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Bob's validation response: {e}")
            return {
                'valid': False,
                'issues': ['Failed to parse validation response from Bob'],
                'confidence': 0.0,
                'recommendation': 'manual_review'
            }
        except BobAPIError as e:
            logger.error(f"Bob API error during validation: {e}")
            return {
                'valid': False,
                'issues': [f'Bob API error: {str(e)}'],
                'confidence': 0.0,
                'recommendation': 'manual_review'
            }
    
    def rollback(self, file_path: str) -> bool:
        """
        Restore a file from its backup if validation fails.
        
        This method looks for a .backup file and restores it to the original location.
        
        Args:
            file_path: Path to the file to rollback
            
        Returns:
            True if rollback successful, False otherwise
        """
        backup_path = f"{file_path}.backup"
        
        if not os.path.exists(backup_path):
            logger.error(f"Backup file not found: {backup_path}")
            return False
        
        try:
            # Restore from backup
            shutil.copy2(backup_path, file_path)
            logger.info(f"✓ Successfully rolled back {file_path} from backup")
            
            # Optionally keep the backup or remove it
            # For safety, we'll keep it with a timestamp
            timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
            archived_backup = f"{backup_path}.{timestamp}"
            shutil.move(backup_path, archived_backup)
            logger.info(f"  Backup archived as {archived_backup}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to rollback {file_path}: {e}")
            return False
    
    def validate_and_apply_patch(self, file_path: str, original_content: str,
                                 patched_content: str, violation_type: str = "unknown") -> Dict[str, Any]:
        """
        Validate a patch and apply it only if validation passes, with automatic rollback on failure.
        
        This is a high-level method that combines validation and application with safety checks.
        
        Args:
            file_path: Path to the file to patch
            original_content: Original file content
            patched_content: Patched file content
            violation_type: Type of violation being fixed
            
        Returns:
            Dictionary containing:
                - applied: Boolean indicating if patch was applied
                - validation_result: Full validation results
                - backup_path: Path to backup file if created
                - rolled_back: Boolean indicating if rollback occurred
        """
        result = {
            'applied': False,
            'validation_result': {},
            'backup_path': None,
            'rolled_back': False
        }
        
        # Detect language
        file_ext = Path(file_path).suffix.lower()
        language = self._get_language_from_extension(file_ext) or 'unknown'
        
        # Validate the patch
        validation_result = self.validate_patch(
            file_path=file_path,
            original_code=original_content,
            patched_code=patched_content,
            language=language,
            violation_type=violation_type
        )
        
        result['validation_result'] = validation_result
        
        # If validation fails, don't apply
        if not validation_result['valid']:
            logger.error(f"Patch validation failed for {file_path}, not applying")
            logger.error(f"Issues: {', '.join(validation_result['issues'])}")
            return result
        
        # Validation passed, apply the patch
        try:
            backup_path = self.apply_patch(file_path, original_content, patched_content)
            result['backup_path'] = backup_path
            result['applied'] = True
            logger.info(f"✓ Patch successfully applied to {file_path}")
            
            # Post-application validation (optional but recommended)
            # Read the file back and verify it matches what we wrote
            with open(file_path, 'r', encoding='utf-8') as f:
                written_content = f.read()
            
            if written_content != patched_content:
                logger.error(f"Post-write verification failed for {file_path}")
                logger.error("File content doesn't match expected patched content")
                
                # Rollback
                if self.rollback(file_path):
                    result['rolled_back'] = True
                    result['applied'] = False
                    logger.info(f"✓ Rolled back {file_path} due to verification failure")
                else:
                    logger.error(f"✗ Rollback failed for {file_path}")
            
        except Exception as e:
            logger.error(f"Error applying patch to {file_path}: {e}")
            
            # Attempt rollback
            if self.rollback(file_path):
                result['rolled_back'] = True
                logger.info(f"✓ Rolled back {file_path} after application error")
            else:
                logger.error(f"✗ Rollback failed for {file_path}")
        
        return result

        """
        Handle remediation that requires changes across multiple files.
        
        This method identifies when a fix impacts multiple files (e.g., function renaming,
        interface changes, import modifications) and generates a comprehensive modification
        plan that ensures all dependent files are updated correctly.
        
        Process:
        1. Analyze the violation to determine if cross-file changes are needed
        2. Scan repository to find all files that depend on the modified element
        3. Generate a comprehensive prompt for Bob with full context
        4. Parse Bob's modification plan (which files to change and how)
        5. Validate the plan for completeness and correctness
        6. Apply modifications in dependency order
        
        Args:
            violation: The violation that requires fixing
            repo_path: Path to the repository root
            
        Returns:
            Dictionary containing:
                - requires_cross_file: Boolean indicating if multiple files need changes
                - affected_files: List of file paths that need modification
                - modification_plan: Detailed plan for each file
                - dependency_order: Order in which files should be modified
                - results: List of RemediationResult objects for each file
        """
        logger.info(f"Analyzing cross-file impact for violation {violation.id}")
        
        # Step 1: Identify if cross-file changes are needed
        cross_file_needed = self._requires_cross_file_changes(violation)
        
        if not cross_file_needed:
            logger.info(f"Violation {violation.id} does not require cross-file changes")
            return {
                'requires_cross_file': False,
                'affected_files': [violation.file_path],
                'modification_plan': {},
                'dependency_order': [violation.file_path],
                'results': []
            }
        
        logger.info(f"Violation {violation.id} requires cross-file remediation")
        
        # Step 2: Find all dependent files
        dependent_files = self._find_dependent_files(violation, repo_path)
        logger.info(f"Found {len(dependent_files)} dependent files")
        
        # Step 3: Generate comprehensive prompt for Bob
        prompt = self._generate_cross_file_prompt(
            violation=violation,
            repo_path=repo_path,
            dependent_files=dependent_files
        )
        
        # Step 4: Get modification plan from Bob
        try:
            response = self.bob_client.chat(
                message=prompt,
                context={
                    'violation_id': violation.id,
                    'action': 'cross_file_remediation',
                    'repo_path': repo_path
                }
            )
            
            # Parse Bob's response
            import json
            response_text = response.get('response', '')
            
            # Extract JSON from response
            if '```json' in response_text:
                response_text = response_text.split('```json')[1].split('```')[0].strip()
            elif '```' in response_text:
                response_text = response_text.split('```')[1].split('```')[0].strip()
            
            modification_plan = json.loads(response_text)
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Bob's cross-file modification plan: {e}")
            return {
                'requires_cross_file': True,
                'affected_files': dependent_files,
                'modification_plan': {},
                'dependency_order': [],
                'results': [],
                'error': 'Failed to parse modification plan'
            }
        except BobAPIError as e:
            logger.error(f"Bob API error during cross-file analysis: {e}")
            return {
                'requires_cross_file': True,
                'affected_files': dependent_files,
                'modification_plan': {},
                'dependency_order': [],
                'results': [],
                'error': str(e)
            }
        
        # Step 5: Validate the modification plan
        validation_result = self._validate_modification_plan(modification_plan, dependent_files)
        
        if not validation_result['valid']:
            logger.error(f"Modification plan validation failed: {validation_result['errors']}")
            return {
                'requires_cross_file': True,
                'affected_files': dependent_files,
                'modification_plan': modification_plan,
                'dependency_order': [],
                'results': [],
                'error': f"Invalid plan: {', '.join(validation_result['errors'])}"
            }
        
        # Step 6: Determine dependency order
        dependency_order = self._determine_dependency_order(
            modification_plan.get('files_to_modify', []),
            repo_path
        )
        
        logger.info(f"Dependency order: {' -> '.join(dependency_order)}")
        
        # Step 7: Apply modifications in order (if not dry-run)
        results = []
        if not self.dry_run:
            results = self._apply_cross_file_modifications(
                modification_plan,
                dependency_order,
                violation
            )
        else:
            logger.info("Dry-run mode: modifications not applied")
            # Create dry-run results
            for file_info in modification_plan.get('files_to_modify', []):
                results.append(RemediationResult(
                    violation_id=violation.id,
                    file_path=file_info['file_path'],
                    original_code="",
                    fixed_code=file_info.get('patched_content', ''),
                    diff="",
                    status="DRY_RUN",
                    confidence=modification_plan.get('confidence', 0.0)
                ))
        
        return {
            'requires_cross_file': True,
            'affected_files': [f['file_path'] for f in modification_plan.get('files_to_modify', [])],
            'modification_plan': modification_plan,
            'dependency_order': dependency_order,
            'results': results
        }
    
    def _requires_cross_file_changes(self, violation: Violation) -> bool:
        """
        Determine if a violation requires changes across multiple files.
        
        Indicators of cross-file changes:
        - Function/class renaming for security
        - API/interface modifications
        - Import path changes
        - Global variable renaming
        - Configuration changes affecting multiple modules
        
        Args:
            violation: The violation to analyze
            
        Returns:
            True if cross-file changes are likely needed
        """
        # Keywords that suggest cross-file impact
        cross_file_indicators = [
            'rename', 'refactor', 'interface', 'api', 'import',
            'global', 'export', 'public', 'shared', 'common',
            'function signature', 'method signature', 'class name'
        ]
        
        # Check violation description and recommendation
        text_to_check = (
            violation.description.lower() + ' ' +
            violation.recommendation.lower() + ' ' +
            violation.explanation.lower()
        )
        
        for indicator in cross_file_indicators:
            if indicator in text_to_check:
                logger.debug(f"Cross-file indicator found: '{indicator}'")
                return True
        
        # Check if the code snippet contains function/class definitions
        if 'def ' in violation.code_snippet or 'class ' in violation.code_snippet:
            # These might be used elsewhere
            return True
        
        return False
    
    def _find_dependent_files(self, violation: Violation, repo_path: str) -> List[str]:
        """
        Find all files in the repository that might depend on the violated code.
        
        Searches for:
        - Import statements referencing the file
        - Function/class usage
        - Variable references
        
        Args:
            violation: The violation being fixed
            repo_path: Path to repository root
            
        Returns:
            List of file paths that depend on the violated code
        """
        dependent_files = []
        
        # Extract potential identifiers from the violation
        identifiers = self._extract_identifiers(violation.code_snippet)
        
        if not identifiers:
            return dependent_files
        
        # Get the module name from file path
        file_path = Path(violation.file_path)
        module_name = file_path.stem
        
        # Search patterns
        search_patterns = []
        
        # Import patterns
        search_patterns.append(f"from .* import .*{module_name}")
        search_patterns.append(f"import .*{module_name}")
        
        # Identifier usage patterns
        for identifier in identifiers:
            search_patterns.append(f"\\b{identifier}\\b")
        
        # Scan repository files
        for root, dirs, files in os.walk(repo_path):
            # Skip common directories
            dirs[:] = [d for d in dirs if d not in {
                '.git', '__pycache__', 'node_modules', 'venv', 'env',
                '.venv', 'dist', 'build', '.pytest_cache'
            }]
            
            for file in files:
                # Only check source files
                if not any(file.endswith(ext) for ext in ['.py', '.js', '.ts', '.java', '.go']):
                    continue
                
                file_path_str = os.path.join(root, file)
                
                # Skip the file with the violation
                if os.path.abspath(file_path_str) == os.path.abspath(violation.file_path):
                    continue
                
                try:
                    with open(file_path_str, 'r', encoding='utf-8') as f:
                        content = f.read()
                        
                        # Check if any pattern matches
                        for pattern in search_patterns:
                            if re.search(pattern, content):
                                dependent_files.append(file_path_str)
                                logger.debug(f"Found dependency: {file_path_str}")
                                break
                
                except Exception as e:
                    logger.warning(f"Error reading {file_path_str}: {e}")
                    continue
        
        return dependent_files
    
    def _extract_identifiers(self, code_snippet: str) -> List[str]:
        """
        Extract function names, class names, and variable names from code.
        
        Args:
            code_snippet: Code to analyze
            
        Returns:
            List of identifier names
        """
        identifiers = []
        
        # Python patterns
        func_pattern = r'def\s+(\w+)\s*\('
        class_pattern = r'class\s+(\w+)\s*[:\(]'
        
        identifiers.extend(re.findall(func_pattern, code_snippet))
        identifiers.extend(re.findall(class_pattern, code_snippet))
        
        # JavaScript/TypeScript patterns
        js_func_pattern = r'function\s+(\w+)\s*\('
        js_const_pattern = r'const\s+(\w+)\s*='
        
        identifiers.extend(re.findall(js_func_pattern, code_snippet))
        identifiers.extend(re.findall(js_const_pattern, code_snippet))
        
        return list(set(identifiers))  # Remove duplicates
    
    def _generate_cross_file_prompt(self, violation: Violation, repo_path: str,
                                    dependent_files: List[str]) -> str:
        """
        Generate a comprehensive prompt for IBM Bob to analyze cross-file impacts.
        
        The prompt provides complete context about the violation, the proposed fix,
        and all potentially affected files, asking Bob to identify ALL necessary
        changes across the codebase.
        
        Args:
            violation: The violation requiring a fix
            repo_path: Path to repository root
            dependent_files: List of files that might be affected
            
        Returns:
            Formatted prompt string for IBM Bob
        """
        # Read content of dependent files
        dependent_files_content = {}
        for file_path in dependent_files[:20]:  # Limit to 20 files to avoid token limits
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    dependent_files_content[file_path] = f.read()
            except Exception as e:
                logger.warning(f"Could not read {file_path}: {e}")
        
        # Read the main file
        try:
            with open(violation.file_path, 'r', encoding='utf-8') as f:
                main_file_content = f.read()
        except Exception as e:
            logger.error(f"Could not read main file {violation.file_path}: {e}")
            main_file_content = violation.code_snippet
        
        prompt = f"""You are an expert code remediation assistant specializing in cross-file dependency analysis and refactoring.

# TASK: CROSS-FILE IMPACT ANALYSIS AND REMEDIATION

Your task is to analyze a code violation that requires changes across multiple files and provide a COMPLETE modification plan.

## PRIMARY VIOLATION

**File:** `{violation.file_path}`
**Line:** {violation.line_number}
**Violation ID:** {violation.id}
**Rule:** {violation.rule_id} - {violation.rule_name}
**Category:** {violation.category}
**Severity:** {violation.severity}

**Description:** {violation.description}
**Explanation:** {violation.explanation}
**Recommendation:** {violation.recommendation}

**Problematic Code:**
```
{violation.code_snippet}
```

**Complete File Content:**
```
{main_file_content}
```

## POTENTIALLY AFFECTED FILES

The following files have been identified as potentially depending on the code being fixed.
You MUST analyze each file to determine if it needs modification.

"""
        
        # Add dependent files
        for idx, (file_path, content) in enumerate(dependent_files_content.items(), 1):
            rel_path = os.path.relpath(file_path, repo_path)
            prompt += f"""
### File {idx}: `{rel_path}`

```
{content}
```

"""
        
        prompt += f"""

## YOUR TASK

You must provide a COMPREHENSIVE modification plan that:

1. **Identifies ALL files that need changes** - Be exhaustive, not just the obvious ones
2. **Specifies exact changes for each file** - Complete patched content for each
3. **Determines the correct modification order** - Dependencies first
4. **Ensures consistency across all files** - Same naming, same patterns
5. **Validates that the fix is complete** - No broken references

## CRITICAL REQUIREMENTS

1. **Be Exhaustive**: Check EVERY file for:
   - Direct imports of the modified element
   - Indirect usage through other imports
   - Function/method calls
   - Class instantiations
   - Variable references
   - Type annotations
   - Documentation references
   - Test files that test the modified code

2. **Maintain Consistency**:
   - Use the same naming conventions across all files
   - Keep the same code style in each file
   - Preserve existing patterns and structures
   - Update comments and docstrings

3. **Preserve Functionality**:
   - The changes must maintain the same behavior
   - Do not break any existing functionality
   - Ensure all references are updated
   - Keep backward compatibility where possible

4. **Dependency Order**:
   - Identify which files depend on which
   - Specify the order of modifications
   - Ensure dependencies are fixed before dependents

## REQUIRED RESPONSE FORMAT

You MUST respond with ONLY a valid JSON object. No markdown, no extra text.

```json
{{
  "requires_cross_file": true,
  "primary_fix_description": "Brief description of the main fix",
  "impact_analysis": {{
    "total_files_affected": 5,
    "types_of_changes": ["function_rename", "import_update", "call_site_update"],
    "risk_level": "medium",
    "breaking_changes": false
  }},
  "files_to_modify": [
    {{
      "file_path": "relative/path/to/file1.py",
      "reason": "Contains import of renamed function",
      "changes_needed": [
        "Update import statement",
        "Update function call on line 45"
      ],
      "patched_content": "COMPLETE FILE CONTENT WITH ALL FIXES APPLIED",
      "dependency_level": 0
    }},
    {{
      "file_path": "relative/path/to/file2.py",
      "reason": "Calls the function being renamed",
      "changes_needed": [
        "Update function call on line 23",
        "Update function call on line 67"
      ],
      "patched_content": "COMPLETE FILE CONTENT WITH ALL FIXES APPLIED",
      "dependency_level": 1
    }}
  ],
  "modification_order": [
    "relative/path/to/file1.py",
    "relative/path/to/file2.py"
  ],
  "validation_checklist": [
    "All imports updated",
    "All function calls updated",
    "All tests updated",
    "Documentation updated"
  ],
  "confidence": 0.95,
  "requires_manual_review": false,
  "warnings": [
    "File X has complex logic that should be manually reviewed"
  ]
}}
```

## FIELD DESCRIPTIONS

- **requires_cross_file**: Always true for this analysis
- **primary_fix_description**: What is being fixed in the main file
- **impact_analysis**: Summary of the scope of changes
- **files_to_modify**: Array of ALL files that need changes
  - **file_path**: Relative path from repo root
  - **reason**: Why this file needs modification
  - **changes_needed**: List of specific changes
  - **patched_content**: COMPLETE file with ALL fixes applied
  - **dependency_level**: 0 = no dependencies, higher = depends on lower levels
- **modification_order**: Order to apply changes (dependencies first)
- **validation_checklist**: Things to verify after applying changes
- **confidence**: Your confidence in the completeness of this plan (0.0-1.0)
- **requires_manual_review**: Whether human review is recommended
- **warnings**: Any concerns or edge cases

## IMPORTANT NOTES

- If you cannot determine all impacts with high confidence, set requires_manual_review to true
- If the change is too complex or risky, explain in warnings
- Always include test files if they exist
- Check for indirect dependencies (A imports B, B imports C, C uses the modified code)
- Consider configuration files, documentation, and examples

Now, analyze the violation and provide the COMPLETE cross-file modification plan.
Return ONLY the JSON response, nothing else.
"""
        
        return prompt
    
    def _validate_modification_plan(self, plan: Dict[str, Any], 
                                   expected_files: List[str]) -> Dict[str, Any]:
        """
        Validate that the modification plan is complete and correct.
        
        Args:
            plan: The modification plan from Bob
            expected_files: Files we expect might need changes
            
        Returns:
            Dictionary with 'valid' boolean and 'errors' list
        """
        errors = []
        
        # Check required fields
        required_fields = ['requires_cross_file', 'files_to_modify', 'modification_order']
        for field in required_fields:
            if field not in plan:
                errors.append(f"Missing required field: {field}")
        
        if errors:
            return {'valid': False, 'errors': errors}
        
        # Validate files_to_modify structure
        files_to_modify = plan.get('files_to_modify', [])
        if not isinstance(files_to_modify, list):
            errors.append("files_to_modify must be a list")
            return {'valid': False, 'errors': errors}
        
        for idx, file_info in enumerate(files_to_modify):
            if not isinstance(file_info, dict):
                errors.append(f"File {idx} is not a dictionary")
                continue
            
            # Check required fields for each file
            if 'file_path' not in file_info:
                errors.append(f"File {idx} missing file_path")
            if 'patched_content' not in file_info:
                errors.append(f"File {idx} missing patched_content")
            if 'dependency_level' not in file_info:
                errors.append(f"File {idx} missing dependency_level")
        
        # Validate modification order
        modification_order = plan.get('modification_order', [])
        file_paths = [f['file_path'] for f in files_to_modify]
        
        if set(modification_order) != set(file_paths):
            errors.append("modification_order doesn't match files_to_modify")
        
        return {
            'valid': len(errors) == 0,
            'errors': errors
        }
    
    def _determine_dependency_order(self, files_to_modify: List[Dict[str, Any]],
                                   repo_path: str) -> List[str]:
        """
        Determine the correct order to apply modifications based on dependencies.
        
        Files with lower dependency_level should be modified first.
        
        Args:
            files_to_modify: List of file modification info
            repo_path: Repository root path
            
        Returns:
            Ordered list of file paths
        """
        # Sort by dependency_level (lower first)
        sorted_files = sorted(
            files_to_modify,
            key=lambda f: f.get('dependency_level', 999)
        )
        
        return [f['file_path'] for f in sorted_files]
    
    def _apply_cross_file_modifications(self, plan: Dict[str, Any],
                                       dependency_order: List[str],
                                       violation: Violation) -> List[RemediationResult]:
        """
        Apply modifications to multiple files in the correct order.
        
        Args:
            plan: The modification plan
            dependency_order: Order to apply changes
            violation: The original violation
            
        Returns:
            List of RemediationResult objects
        """
        results = []
        files_to_modify = {f['file_path']: f for f in plan.get('files_to_modify', [])}
        
        for file_path in dependency_order:
            if file_path not in files_to_modify:
                continue
            
            file_info = files_to_modify[file_path]
            
            try:
                # Read original content
                if not os.path.exists(file_path):
                    logger.error(f"File not found: {file_path}")
                    results.append(RemediationResult(
                        violation_id=violation.id,
                        file_path=file_path,
                        original_code="",
                        fixed_code="",
                        diff="",
                        status="FAILED",
                        error_message="File not found"
                    ))
                    continue
                
                with open(file_path, 'r', encoding='utf-8') as f:
                    original_content = f.read()
                
                patched_content = file_info['patched_content']
                
                # Generate diff
                diff = self._generate_diff(original_content, patched_content, file_path)
                
                # Apply patch
                backup_path = self.apply_patch(file_path, original_content, patched_content)
                
                results.append(RemediationResult(
                    violation_id=violation.id,
                    file_path=file_path,
                    original_code=original_content[:500],  # Truncate for storage
                    fixed_code=patched_content[:500],
                    diff=diff,
                    status="SUCCESS",
                    backup_path=backup_path,
                    confidence=plan.get('confidence', 0.0)
                ))
                
                logger.info(f"Successfully modified {file_path}")
                
            except Exception as e:
                logger.error(f"Error modifying {file_path}: {e}")
                results.append(RemediationResult(
                    violation_id=violation.id,
                    file_path=file_path,
                    original_code="",
                    fixed_code="",
                    diff="",
                    status="FAILED",
                    error_message=str(e)
                ))
        
        return results

        # Count braces, brackets, parentheses
        if code.count('{') != code.count('}'):
            logger.error("Mismatched curly braces")
            return False
        if code.count('[') != code.count(']'):
            logger.error("Mismatched square brackets")
            return False
        if code.count('(') != code.count(')'):
            logger.error("Mismatched parentheses")
            return False
        
        return True
    
    def _get_language_from_extension(self, extension: str) -> Optional[str]:
        """
        Get language name from file extension.
        
        Args:
            extension: File extension (e.g., '.py')
            
        Returns:
            Language name or None
        """
        language_map = {
            '.py': 'python',
            '.js': 'javascript',
            '.ts': 'typescript',
            '.java': 'java',
            '.php': 'php',
            '.rb': 'ruby',
            '.go': 'go',
            '.cpp': 'cpp',
            '.c': 'c',
            '.cs': 'csharp'
        }
        return language_map.get(extension.lower())
    
    def _generate_report(self) -> RemediationReport:
        """
        Generate comprehensive remediation report.
        
        Returns:
            RemediationReport with statistics and results
        """
        total = len(self.results)
        successful = sum(1 for r in self.results if r.status in ["SUCCESS", "DRY_RUN"])
        failed = sum(1 for r in self.results if r.status == "FAILED")
        skipped = sum(1 for r in self.results if r.status == "SKIPPED")
        
        # Get unique files that were modified
        files_modified = list(set(
            r.file_path for r in self.results 
            if r.status in ["SUCCESS", "DRY_RUN"]
        ))
        
        return RemediationReport(
            total_violations=total,
            successful_fixes=successful,
            failed_fixes=failed,
            skipped_fixes=skipped,
            dry_run=self.dry_run,
            results=self.results,
            files_modified=files_modified
        )


# Convenience function for quick remediation
def quick_remediate(violations: List[Violation], api_key: Optional[str] = None, 
                   dry_run: bool = True) -> RemediationReport:
    """
    Quick remediation without managing client instance.
    
    Args:
        violations: List of violations to remediate
        api_key: Optional API key (uses env var if not provided)
        dry_run: If True, don't apply fixes (default: True)
        
    Returns:
        RemediationReport with results
    """
    with BobClient(api_key=api_key) as client:
        remediator = Remediator(violations, client, dry_run=dry_run)
        return remediator.remediate_all()


class CodeRemediator:
    """
    Simplified wrapper around Remediator for easier API usage.
    Provides a stateless interface for generating and applying fixes.
    """
    
    def __init__(self, bob_client: Optional[BobClient] = None, backup_dir: str = 'backups'):
        """
        Initialize CodeRemediator.
        
        Args:
            bob_client: Optional BobClient instance
            backup_dir: Directory for backups
        """
        self.bob_client = bob_client
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
    
    def generate_fixes(self, violations: List[Violation], min_confidence: float = 0.7) -> List['Fix']:
        """
        Generate fixes for violations.
        
        Args:
            violations: List of violations to fix
            min_confidence: Minimum confidence threshold
            
        Returns:
            List of Fix objects
        """
        if not violations:
            return []
        
        # Filter by confidence if violations have confidence scores
        filtered_violations = [
            v for v in violations 
            if getattr(v, 'confidence', 1.0) >= min_confidence
        ]
        
        if not filtered_violations:
            return []
        
        # Use Remediator to generate fixes
        if self.bob_client:
            remediator = Remediator(filtered_violations, self.bob_client, dry_run=True)
            report = remediator.remediate_all()
            
            # Convert RemediationResults to Fix objects
            fixes = []
            for result in report.results:
                if result.status in ['SUCCESS', 'DRY_RUN']:
                    fix = Fix(
                        violation_id=result.violation_id,
                        file_path=result.file_path,
                        original_code=result.original_code,
                        fixed_code=result.fixed_code,
                        explanation=result.diff,
                        confidence=result.confidence,
                        applied=False,
                        backup_path=result.backup_path
                    )
                    fixes.append(fix)
            
            return fixes
        
        return []
    
    def apply_fixes(self, fixes: List['Fix'], auto_apply: bool = False, 
                   create_backup: bool = True) -> 'RemediationSummary':
        """
        Apply generated fixes to files.
        
        Args:
            fixes: List of Fix objects to apply
            auto_apply: Whether to apply automatically
            create_backup: Whether to create backups
            
        Returns:
            RemediationSummary with results
        """
        applied = 0
        failed = 0
        
        if not auto_apply:
            return RemediationSummary(
                fixes_generated=len(fixes),
                fixes_applied=0,
                fixes_failed=0,
                fixes=fixes
            )
        
        for fix in fixes:
            try:
                file_path = Path(fix.file_path)
                
                if not file_path.exists():
                    logger.warning(f"File not found: {file_path}")
                    failed += 1
                    continue
                
                # Create backup if requested
                if create_backup:
                    backup_path = self.backup_dir / f"{file_path.name}.backup"
                    shutil.copy2(file_path, backup_path)
                    fix.backup_path = str(backup_path)
                
                # Apply fix
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(fix.fixed_code)
                
                fix.applied = True
                applied += 1
                logger.info(f"Applied fix to {file_path}")
            
            except Exception as e:
                logger.error(f"Failed to apply fix to {fix.file_path}: {e}")
                failed += 1
        
        return RemediationSummary(
            fixes_generated=len(fixes),
            fixes_applied=applied,
            fixes_failed=failed,
            fixes=fixes
        )


@dataclass
class Fix:
    """Represents a code fix."""
    violation_id: str
    file_path: str
    original_code: str
    fixed_code: str
    explanation: str
    confidence: float
    applied: bool = False
    backup_path: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class RemediationSummary:
    """Summary of remediation operations."""
    fixes_generated: int
    fixes_applied: int
    fixes_failed: int
    fixes: List[Fix]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'fixes_generated': self.fixes_generated,
            'fixes_applied': self.fixes_applied,
            'fixes_failed': self.fixes_failed,
            'fixes': [f.to_dict() for f in self.fixes]
        }


# Made with Bob
