"""
Code Analyzer Module
Scans legacy codebases for compliance violations and security vulnerabilities.

This module implements a two-phase detection strategy:
1. Fast regex-based pattern matching for initial detection
2. IBM Bob API confirmation for deep analysis and context-aware validation
"""

import re
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Set, Callable
from dataclasses import dataclass, asdict, field
from datetime import datetime

from src.bob_client import BobClient, BobAPIError

# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class Violation:
    """
    Represents a detected compliance or security violation.
    
    Attributes:
        id: Unique identifier for this violation instance
        rule_id: ID of the rule that was violated (e.g., 'SEC-001')
        rule_name: Human-readable name of the rule
        category: Category of violation (SECURITY, GDPR, HIPAA, QUALITY)
        severity: Severity level (CRITICAL, HIGH, MEDIUM, LOW)
        file_path: Path to the file containing the violation
        line_number: Line number where violation occurs
        column: Column number (optional)
        code_snippet: The actual code that violates the rule
        context_before: Lines of code before the violation (for context)
        context_after: Lines of code after the violation (for context)
        description: Detailed description of the violation
        explanation: IBM Bob's explanation of why this is a violation
        recommendation: How to fix the violation
        confidence: Confidence score from Bob (0.0 to 1.0)
        detected_at: Timestamp when violation was detected
    """
    id: str
    rule_id: str
    rule_name: str
    category: str
    severity: str
    file_path: str
    line_number: int
    column: Optional[int]
    code_snippet: str
    context_before: List[str]
    context_after: List[str]
    description: str
    explanation: str
    recommendation: str
    confidence: float
    detected_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert violation to dictionary for serialization."""
        return asdict(self)


class Analyzer:
    """
    Main analyzer class for detecting compliance and security violations.
    
    Uses a two-phase approach:
    1. Fast regex pattern matching for initial detection
    2. IBM Bob API for deep analysis and confirmation
    """
    
    # Supported file extensions and their language mappings
    SUPPORTED_EXTENSIONS = {
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
    
    # Directories to ignore during scanning
    IGNORED_DIRECTORIES = {
        'node_modules',
        '.git',
        '__pycache__',
        'venv',
        'env',
        'dist',
        'build',
        '.vscode',
        '.idea',
        'target',
        'bin',
        'obj',
        '.pytest_cache',
        'coverage',
        '.next',
        'out'
    }
    
    # Number of context lines to include around violations
    CONTEXT_LINES = 10
    
    def __init__(
        self,
        repo_path: str,
        rules: List[Dict[str, Any]],
        bob_client: Optional[BobClient] = None,
        progress_callback: Optional[Callable[[int, int, Optional[str], int], None]] = None,
    ):
        """
        Initialize the Analyzer.
        
        Args:
            repo_path: Path to the repository to analyze
            rules: List of rule dictionaries from rules.json
            bob_client: Instance of BobClient for deep analysis (optional)
            
        Raises:
            ValueError: If repo_path doesn't exist or is not a directory
        """
        self.repo_path = Path(repo_path)
        
        if not self.repo_path.exists():
            raise ValueError(f"Repository path does not exist: {repo_path}")
        
        if not self.repo_path.is_dir():
            raise ValueError(f"Repository path is not a directory: {repo_path}")
        
        self.rules = rules
        self.bob_client = bob_client
        self.progress_callback = progress_callback
        self.violations: List[Violation] = []
        self.files_scanned = 0
        self.files_with_violations = 0
        
        # Compile regex patterns for faster matching
        self._compile_patterns()
    
    def _compile_patterns(self):
        """
        Pre-compile all regex patterns from rules for better performance.
        """
        for rule in self.rules:
            try:
                # Compile pattern with case-insensitive flag
                rule['_compiled_pattern'] = re.compile(
                    rule['pattern'],
                    re.IGNORECASE | re.MULTILINE
                )
            except re.error as e:
                print(f"Warning: Invalid regex pattern in rule {rule['id']}: {e}")
                rule['_compiled_pattern'] = None
    
    def scan_repository(self) -> List[Violation]:
        """
        Recursively scan the entire repository for violations.
        
        This method:
        1. Traverses all files in the repository
        2. Filters by supported extensions
        3. Ignores specified directories
        4. Analyzes each file for violations
        
        Returns:
            List of all detected violations
        """
        print(f"Starting repository scan: {self.repo_path}")
        
        # Reset counters
        self.violations = []
        self.files_scanned = 0
        self.files_with_violations = 0
        
        # Collect all files to analyze
        files_to_analyze = self._collect_files()
        total_files = len(files_to_analyze)
        
        print(f"Found {total_files} files to analyze")

        self._emit_progress(0, total_files, None)
        
        # Analyze each file
        for index, file_path in enumerate(files_to_analyze, start=1):
            try:
                file_violations = self.analyze_file(file_path)
                
                if file_violations:
                    self.violations.extend(file_violations)
                    self.files_with_violations += 1
                
                self.files_scanned += 1

                self._emit_progress(index, total_files, str(file_path), len(file_violations))
                
            except Exception as e:
                print(f"Error analyzing {file_path}: {e}")
                self.files_scanned += 1
                self._emit_progress(index, total_files, str(file_path), 0)
                continue
        
        print(f"Scan complete: {self.files_scanned} files scanned, "
              f"{len(self.violations)} violations found in {self.files_with_violations} files")

        self._emit_progress(total_files, total_files, None)
        
        return self.violations

    def _emit_progress(self, processed_files: int, total_files: int, current_file: Optional[str], violations_found: int = 0):
        """Send a progress update to the caller, if one was provided."""
        if self.progress_callback is None:
            return

        try:
            self.progress_callback(processed_files, total_files, current_file, violations_found)
        except Exception as e:
            logger.debug(f"Progress callback failed: {e}")
    
    def _collect_files(self) -> List[Path]:
        """
        Collect all files in the repository that should be analyzed.
        
        Returns:
            List of Path objects for files to analyze
        """
        files_to_analyze = []
        
        for file_path in self.repo_path.rglob('*'):
            # Skip if it's a directory
            if file_path.is_dir():
                continue
            
            # Skip if in ignored directory
            if any(ignored in file_path.parts for ignored in self.IGNORED_DIRECTORIES):
                continue
            
            # Skip if extension not supported
            if file_path.suffix not in self.SUPPORTED_EXTENSIONS:
                continue
            
            files_to_analyze.append(file_path)
        
        return files_to_analyze
    
    def analyze_file(self, file_path: Path) -> List[Violation]:
        """
        Analyze a single file for violations.
        
        Process:
        1. Read file content
        2. Apply fast regex pattern matching
        3. For matches, extract context and send to IBM Bob for confirmation
        4. Return confirmed violations with Bob's analysis
        
        Args:
            file_path: Path to the file to analyze
            
        Returns:
            List of violations found in this file
        """
        violations = []
        
        try:
            # Read file content
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                lines = content.splitlines()
            
            # Get language for this file
            language = self.SUPPORTED_EXTENSIONS.get(file_path.suffix, 'unknown')
            
            # Apply each rule to the file
            for rule in self.rules:
                # Skip if rule doesn't apply to this language
                if language not in rule.get('languages', []):
                    continue
                
                # Skip if pattern didn't compile
                if rule.get('_compiled_pattern') is None:
                    continue
                
                # Find all matches using regex
                pattern = rule['_compiled_pattern']
                matches = list(pattern.finditer(content))
                
                if matches:
                    # Process each match
                    for match in matches:
                        # Get line number of the match
                        line_number = content[:match.start()].count('\n') + 1
                        
                        # Extract context around the match
                        context = self._extract_context(lines, line_number)
                        
                        # Confirm with IBM Bob for deep analysis
                        confirmed_violation = self._confirm_with_bob(
                            file_path=file_path,
                            rule=rule,
                            line_number=line_number,
                            match_text=match.group(0),
                            context=context,
                            language=language
                        )
                        
                        if confirmed_violation:
                            violations.append(confirmed_violation)
        
        except UnicodeDecodeError:
            print(f"Warning: Could not decode file {file_path} (binary file?)")
        except PermissionError:
            print(f"Warning: Permission denied reading {file_path}")
        except Exception as e:
            print(f"Warning: Error reading {file_path}: {e}")
        
        return violations
    
    def _extract_context(self, lines: List[str], line_number: int) -> Dict[str, Any]:
        """
        Extract context lines around a violation.
        
        Args:
            lines: All lines in the file
            line_number: Line number of the violation (1-based)
            
        Returns:
            Dictionary with context information
        """
        # Convert to 0-based index
        line_index = line_number - 1
        
        # Calculate context range
        start_index = max(0, line_index - self.CONTEXT_LINES)
        end_index = min(len(lines), line_index + self.CONTEXT_LINES + 1)
        
        # Extract lines
        context_before = lines[start_index:line_index]
        violation_line = lines[line_index] if line_index < len(lines) else ""
        context_after = lines[line_index + 1:end_index]
        
        return {
            'before': context_before,
            'line': violation_line,
            'after': context_after,
            'start_line': start_index + 1,
            'end_line': end_index
        }
    
    def _confirm_with_bob(
        self,
        file_path: Path,
        rule: Dict[str, Any],
        line_number: int,
        match_text: str,
        context: Dict[str, Any],
        language: str
    ) -> Optional[Violation]:
        """
        Confirm a potential violation with IBM Bob for deep analysis.
        
        Args:
            file_path: Path to the file
            rule: Rule that was matched
            line_number: Line number of the match
            match_text: The text that matched the pattern
            context: Context lines around the match
            language: Programming language
            
        Returns:
            Violation object if confirmed, None if false positive
        """
        # If Bob client is not available, create violation based on regex match
        if self.bob_client is None:
            violation_id = f"{rule['id']}-{file_path.name}-{line_number}"
            
            violation = Violation(
                id=violation_id,
                rule_id=rule['id'],
                rule_name=rule['name'],
                category=rule['category'],
                severity=rule['severity'],
                file_path=str(file_path),
                line_number=line_number,
                column=None,
                code_snippet=match_text,
                context_before=context['before'],
                context_after=context['after'],
                description=rule['description'],
                explanation=rule['description'],
                recommendation=rule['remediation_hint'],
                confidence=0.6  # Lower confidence without Bob confirmation
            )
            
            return violation
        
        try:
            # Prepare context for Bob
            context_code = '\n'.join(
                context['before'] +
                [context['line']] +
                context['after']
            )
            
            # Build the analysis prompt for Bob
            prompt = self._build_bob_analysis_prompt(
                file_path=file_path,
                rule=rule,
                line_number=line_number,
                match_text=match_text,
                context_code=context_code,
                language=language
            )
            
            # Ask Bob to analyze with the detailed prompt
            bob_response = self.bob_client.explain_violation(
                code_snippet=prompt,
                rule=rule['id']
            )
            
            # Normalize Bob response: some endpoints may return a JSON
            # encoded string. Ensure we have a dict-like object.
            if isinstance(bob_response, str):
                try:
                    bob_response = json.loads(bob_response)
                except Exception:
                    logger.warning(f"Bob response is a string and could not be parsed as JSON for {file_path}:{line_number}")
                    return None

            # Check if Bob confirms this is a real violation
            # Bob's response may include a numeric confidence (0.0-1.0)
            # or a textual level like "high"/"medium"/"low".
            raw_conf = bob_response.get('confidence', 0.0)

            if isinstance(raw_conf, str):
                level = raw_conf.strip().lower()
                level_map = {'high': 0.95, 'medium': 0.75, 'low': 0.45}
                confidence = level_map.get(level, 0.0)
            else:
                try:
                    confidence = float(raw_conf)
                except Exception:
                    confidence = 0.0

            # Only create violation if confidence is above threshold
            if confidence < 0.5:
                return None
            
            # Generate unique violation ID
            violation_id = f"{rule['id']}-{file_path.name}-{line_number}"
            
            # Create violation object
            violation = Violation(
                id=violation_id,
                rule_id=rule['id'],
                rule_name=rule['name'],
                category=rule['category'],
                severity=rule['severity'],
                file_path=str(file_path),
                line_number=line_number,
                column=None,  # Could be enhanced to find exact column
                code_snippet=match_text,
                context_before=context['before'],
                context_after=context['after'],
                description=rule['description'],
                explanation=bob_response.get('explanation', rule['description']),
                recommendation=bob_response.get('recommendation', rule['remediation_hint']),
                confidence=confidence
            )
            
            return violation
            
        except BobAPIError as e:
            # If Bob API fails, create violation based on regex match alone
            # but with lower confidence
            print(f"Warning: Bob API error for {file_path}:{line_number}: {e}")
            
            violation_id = f"{rule['id']}-{file_path.name}-{line_number}"
            
            violation = Violation(
                id=violation_id,
                rule_id=rule['id'],
                rule_name=rule['name'],
                category=rule['category'],
                severity=rule['severity'],
                file_path=str(file_path),
                line_number=line_number,
                column=None,
                code_snippet=match_text,
                context_before=context['before'],
                context_after=context['after'],
                description=rule['description'],
                explanation=rule['description'],
                recommendation=rule['remediation_hint'],
                confidence=0.6  # Lower confidence without Bob confirmation
            )
            
            return violation
        
        except Exception as e:
            print(f"Error confirming violation with Bob: {e}")
            return None
    
    def _build_bob_analysis_prompt(
        self,
        file_path: Path,
        rule: Dict[str, Any],
        line_number: int,
        match_text: str,
        context_code: str,
        language: str
    ) -> str:
        """
        Build a precise prompt for IBM Bob to analyze a suspicious code section.
        
        Args:
            file_path: Path to the file being analyzed
            rule: The rule that was triggered
            line_number: Line number of the suspicious code
            match_text: The text that matched the regex pattern
            context_code: Full code excerpt (up to 15 lines) around the suspicious line
            language: Programming language
            
        Returns:
            Formatted prompt string optimized for Bob API
        """
        prompt = f"""You are a security and compliance expert analyzing code for potential violations.

**CONTEXT:**
- File: {file_path.name}
- Language: {language}
- Line Number: {line_number}
- Rule Triggered: {rule['id']} - {rule['name']}
- Rule Description: {rule['description']}

**CODE EXCERPT (max 15 lines around suspicious line):**
```{language.lower()}
{context_code}
```

**SUSPICIOUS LINE:**
Line {line_number}: {match_text}

**YOUR TASK:**
Analyze this code carefully and determine if this is a REAL violation or a FALSE POSITIVE.

Consider:
1. Is the detected pattern actually problematic in this context?
2. Are there mitigating factors (e.g., input validation, sanitization, proper escaping)?
3. Is this a common false positive pattern (e.g., test code, comments, string literals)?
4. Does the surrounding code provide adequate security controls?

**EXAMPLES OF FALSE POSITIVES TO AVOID:**
- SQL queries in comments or documentation
- Hardcoded credentials in test files or example code  
- Sanitized user input that's properly validated
- Framework-provided safe methods that look unsafe
- Code in try-except blocks with proper error handling

**EXAMPLES OF REAL VIOLATIONS:**
- Direct string concatenation in SQL queries with user input
- Unvalidated user input used in system commands
- Hardcoded credentials in production code
- Missing encryption for sensitive data transmission
- Exposed PII without proper access controls

**REQUIRED RESPONSE FORMAT (JSON ONLY):**
{{
  "is_violation": true,
  "confidence": "high",
  "explanation": "Direct SQL string concatenation with user input detected. The variable 'user_id' is concatenated directly into the query without parameterization, creating a SQL injection vulnerability.",
  "affected_lines": [12, 13]
}}

**CONFIDENCE LEVELS:**
- "high": 90-100% certain this is a real violation
- "medium": 60-89% certain, some ambiguity exists
- "low": 40-59% certain, likely a false positive but worth reviewing

**IMPORTANT:**
- Respond ONLY with valid JSON, no additional text
- Keep explanation to 2-3 sentences maximum
- Be precise about which lines are affected
- If uncertain, use "medium" or "low" confidence
- Consider the full context, not just the suspicious line

Analyze the code now and respond with JSON only:"""
        
        return prompt
    
    def get_violations_by_severity(self, severity: str) -> List[Violation]:
        """
        Filter violations by severity level.
        
        Args:
            severity: Severity level (CRITICAL, HIGH, MEDIUM, LOW)
            
        Returns:
            List of violations matching the severity
        """
        return [v for v in self.violations if v.severity.upper() == severity.upper()]
    
    def cross_file_analysis(
        self,
        violations_list: List[Violation],
        repo_path: str
    ) -> Dict[str, Any]:
        """
        Perform cross-file analysis to detect violations that span multiple files.
        
        This method analyzes data flow across files to identify hidden compliance
        violations that are only visible when examining multiple files together.
        For example: personal data defined in models.py but used without masking in api.py.
        
        Args:
            violations_list: List of violations already detected
            repo_path: Path to the repository root
            
        Returns:
            Dictionary containing:
                - additional_violations: List of new violations found through cross-file analysis
                - risk_score: Global risk score (0-100) for the repository
                - data_flow_issues: List of problematic data flows
                - affected_file_groups: Groups of related files with issues
        """
        if self.bob_client is None:
            logger.warning("Bob client not available for cross-file analysis")
            return {
                'additional_violations': [],
                'risk_score': 0,
                'data_flow_issues': [],
                'affected_file_groups': []
            }
        
        logger.info("Starting cross-file analysis for data flow violations...")
        
        # Step 1: Group violations by type/category
        grouped_violations = self._group_violations_by_category(violations_list)
        
        # Step 2: Focus on GDPR and HIPAA violations (data privacy concerns)
        privacy_violations = []
        for category in ['GDPR', 'HIPAA']:
            if category in grouped_violations:
                privacy_violations.extend(grouped_violations[category])
        
        if not privacy_violations:
            logger.info("No privacy violations found, skipping cross-file analysis")
            return {
                'additional_violations': [],
                'risk_score': 0,
                'data_flow_issues': [],
                'affected_file_groups': []
            }
        
        # Step 3: Collect related files for each violation
        file_dependencies = self._build_file_dependency_graph(
            privacy_violations,
            repo_path
        )
        
        # Step 4: Build prompt for IBM Bob
        prompt = self._build_cross_file_analysis_prompt(
            privacy_violations,
            file_dependencies,
            repo_path
        )
        
        # Step 5: Send to IBM Bob for analysis
        try:
            logger.info("Sending cross-file analysis request to IBM Bob...")
            bob_response = self.bob_client.analyze_code(
                file_path=repo_path,
                rule='CROSS_FILE_ANALYSIS'
            )

            # Normalize bob_response: sometimes the API returns a JSON
            # encoded string. Ensure we have a dict/list before using .get()
            if isinstance(bob_response, str):
                try:
                    bob_response = json.loads(bob_response)
                except Exception:
                    logger.warning("Bob analyze_code returned a string that could not be parsed as JSON")
                    bob_response = {}
            
            # Parse Bob's response
            additional_violations = self._parse_cross_file_violations(
                bob_response,
                repo_path
            )
            
            risk_score = bob_response.get('risk_score', 0)
            data_flow_issues = bob_response.get('data_flow_issues', [])
            affected_file_groups = bob_response.get('affected_file_groups', [])
            
            logger.info(f"Cross-file analysis complete. Found {len(additional_violations)} additional violations. Risk score: {risk_score}")
            
            return {
                'additional_violations': additional_violations,
                'risk_score': risk_score,
                'data_flow_issues': data_flow_issues,
                'affected_file_groups': affected_file_groups
            }
            
        except Exception as e:
            logger.error(f"Cross-file analysis failed: {e}")
            return {
                'additional_violations': [],
                'risk_score': 0,
                'data_flow_issues': [],
                'affected_file_groups': []
            }
    
    def _group_violations_by_category(
        self,
        violations: List[Violation]
    ) -> Dict[str, List[Violation]]:
        """Group violations by their category."""
        grouped = {}
        for violation in violations:
            category = violation.category.upper()
            if category not in grouped:
                grouped[category] = []
            grouped[category].append(violation)
        return grouped
    
    def _build_file_dependency_graph(
        self,
        violations: List[Violation],
        repo_path: str
    ) -> Dict[str, Any]:
        """
        Build a simplified dependency graph for files involved in violations.
        
        Analyzes imports, function calls, and data model usage to understand
        how data flows between files.
        """
        repo_root = Path(repo_path)
        file_graph = {}
        
        # Get unique files from violations
        violation_files = set(v.file_path for v in violations)
        
        for file_path in violation_files:
            full_path = Path(file_path)
            if not full_path.is_absolute():
                full_path = repo_root / file_path
            
            if not full_path.exists():
                continue
            
            try:
                with open(full_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Extract imports
                imports = self._extract_imports(content, full_path.suffix)
                
                # Extract function/class definitions
                definitions = self._extract_definitions(content, full_path.suffix)
                
                # Extract data model references (common patterns)
                data_models = self._extract_data_model_references(content)
                
                file_graph[str(file_path)] = {
                    'imports': imports,
                    'definitions': definitions,
                    'data_models': data_models,
                    'violations': [v for v in violations if v.file_path == file_path]
                }
                
            except Exception as e:
                logger.warning(f"Could not analyze {file_path}: {e}")
                continue
        
        return file_graph
    
    def _extract_imports(self, content: str, file_ext: str) -> List[str]:
        """Extract import statements from code."""
        imports = []
        
        if file_ext == '.py':
            # Python imports
            import_patterns = [
                r'^\s*import\s+([a-zA-Z0-9_.]+)',
                r'^\s*from\s+([a-zA-Z0-9_.]+)\s+import'
            ]
            for pattern in import_patterns:
                matches = re.finditer(pattern, content, re.MULTILINE)
                imports.extend([m.group(1) for m in matches])
        
        elif file_ext in ['.js', '.ts']:
            # JavaScript/TypeScript imports
            import_patterns = [
                r'import\s+.*\s+from\s+[\'"]([^\'"]+)[\'"]',
                r'require\([\'"]([^\'"]+)[\'"]\)'
            ]
            for pattern in import_patterns:
                matches = re.finditer(pattern, content)
                imports.extend([m.group(1) for m in matches])
        
        return list(set(imports))
    
    def _extract_definitions(self, content: str, file_ext: str) -> List[str]:
        """Extract function and class definitions."""
        definitions = []
        
        if file_ext == '.py':
            # Python definitions
            patterns = [
                r'^\s*def\s+([a-zA-Z0-9_]+)',
                r'^\s*class\s+([a-zA-Z0-9_]+)'
            ]
            for pattern in patterns:
                matches = re.finditer(pattern, content, re.MULTILINE)
                definitions.extend([m.group(1) for m in matches])
        
        elif file_ext in ['.js', '.ts']:
            # JavaScript/TypeScript definitions
            patterns = [
                r'function\s+([a-zA-Z0-9_]+)',
                r'class\s+([a-zA-Z0-9_]+)',
                r'const\s+([a-zA-Z0-9_]+)\s*=\s*\('
            ]
            for pattern in patterns:
                matches = re.finditer(pattern, content)
                definitions.extend([m.group(1) for m in matches])
        
        return list(set(definitions))
    
    def _extract_data_model_references(self, content: str) -> List[str]:
        """Extract references to data models (common patterns)."""
        models = []
        
        # Common data model patterns
        patterns = [
            r'class\s+([A-Z][a-zA-Z0-9]*Model)',
            r'@dataclass\s+class\s+([A-Z][a-zA-Z0-9]*)',
            r'interface\s+([A-Z][a-zA-Z0-9]*)',
            r'type\s+([A-Z][a-zA-Z0-9]*)\s*=',
            r'models\.([A-Z][a-zA-Z0-9]*)',
            r'Schema\([\'"]([a-zA-Z0-9_]+)[\'"]'
        ]
        
        for pattern in patterns:
            matches = re.finditer(pattern, content)
            models.extend([m.group(1) for m in matches])
        
        return list(set(models))
    
    def _build_cross_file_analysis_prompt(
        self,
        violations: List[Violation],
        file_dependencies: Dict[str, Any],
        repo_path: str
    ) -> str:
        """
        Build a comprehensive prompt for IBM Bob to analyze data flow across files.
        """
        # Build dependency graph visualization
        dependency_graph = self._format_dependency_graph(file_dependencies)
        
        # Group violations by file
        violations_by_file = {}
        for v in violations:
            if v.file_path not in violations_by_file:
                violations_by_file[v.file_path] = []
            violations_by_file[v.file_path].append(v)
        
        # Format violations summary
        violations_summary = self._format_violations_summary(violations_by_file)
        
        prompt = f"""You are a security and compliance expert performing CROSS-FILE DATA FLOW ANALYSIS.

**REPOSITORY:** {repo_path}

**OBJECTIVE:**
Analyze data flow across multiple files to identify hidden compliance violations that are only visible when examining the complete system. Focus on GDPR and HIPAA violations related to personal data handling.

**CURRENT VIOLATIONS DETECTED:**
{violations_summary}

**FILE DEPENDENCY GRAPH:**
{dependency_graph}

**YOUR TASK - DATA FLOW ANALYSIS:**

1. **Trace Data Flow:**
   - Identify where sensitive data (PII, PHI) is defined (models, schemas, databases)
   - Track how this data flows through the system (APIs, functions, services)
   - Find where data is exposed, logged, transmitted, or stored

2. **Cross-File Violations to Look For:**
   
   **GDPR Violations:**
   - Personal data collected in one file but used without consent tracking in another
   - PII stored in one file but transmitted unencrypted in another
   - User data defined in models but exposed in API responses without masking
   - Data retention: collected in one place but never deleted elsewhere
   - Missing data access controls across file boundaries
   
   **HIPAA Violations:**
   - PHI defined in models but logged in plaintext elsewhere
   - Medical records accessed without audit logging in other files
   - Health data transmitted without encryption between components
   - Missing access controls for PHI across the system
   - PHI in one file shared with unauthorized services in another
   
   **Common Cross-File Patterns:**
   - Data model in models.py → API endpoint in api.py (check masking)
   - User input in controller.py → Database query in repository.py (check sanitization)
   - Sensitive data in service.py → Logging in utils.py (check redaction)
   - Authentication in auth.py → Data access in handlers.py (check authorization)

3. **Data Flow Examples to Analyze:**

   **Example 1 - Missing Masking:**
   ```
   File: models.py
   class User:
       email: str
       ssn: str  # Sensitive!
   
   File: api.py
   def get_user(id):
       user = User.get(id)
       return jsonify(user)  # ❌ SSN exposed in API response!
   ```

   **Example 2 - Missing Encryption:**
   ```
   File: models.py
   class Patient:
       medical_record: str  # PHI
   
   File: sync.py
   def sync_to_external():
       patients = Patient.all()
       requests.post(url, json=patients)  # ❌ PHI sent unencrypted!
   ```

   **Example 3 - Missing Audit:**
   ```
   File: models.py
   class MedicalRecord:
       diagnosis: str  # PHI
   
   File: views.py
   def view_record(id):
       record = MedicalRecord.get(id)  # ❌ No audit log of PHI access!
       return render(record)
   ```

4. **Calculate Global Risk Score (0-100):**
   - 0-20: Low risk - Minor issues, good security practices
   - 21-40: Moderate risk - Some violations, needs improvement
   - 41-60: High risk - Multiple violations, significant gaps
   - 61-80: Critical risk - Severe violations, major compliance issues
   - 81-100: Extreme risk - Systemic failures, immediate action required

   Consider:
   - Number and severity of cross-file violations
   - Sensitivity of data being mishandled
   - Scope of exposure (internal vs external)
   - Presence of compensating controls
   - Regulatory compliance requirements

**REQUIRED RESPONSE FORMAT (JSON ONLY):**
{{
  "additional_violations": [
    {{
      "id": "CROSS-001",
      "type": "GDPR_DATA_EXPOSURE",
      "severity": "CRITICAL",
      "description": "Personal data (SSN) defined in models.py is exposed without masking in api.py endpoint /users/<id>",
      "affected_files": ["models.py", "api.py"],
      "data_flow": "User.ssn (models.py:15) → get_user() (api.py:42) → JSON response (api.py:45)",
      "recommendation": "Implement field-level masking for SSN in API serializer. Add @mask_sensitive decorator to get_user endpoint.",
      "confidence": "high"
    }}
  ],
  "risk_score": 75,
  "risk_level": "critical",
  "risk_explanation": "Multiple GDPR violations with PII exposure. PHI transmitted without encryption. Missing audit logs for sensitive data access.",
  "data_flow_issues": [
    {{
      "flow": "User.email → logging.info() → application.log",
      "issue": "PII logged in plaintext",
      "severity": "HIGH"
    }}
  ],
  "affected_file_groups": [
    {{
      "files": ["models.py", "api.py", "serializers.py"],
      "issue": "PII exposure chain",
      "risk": "CRITICAL"
    }}
  ],
  "recommendations": [
    "Implement data masking layer between models and API responses",
    "Add encryption for all PHI transmissions",
    "Implement comprehensive audit logging for sensitive data access"
  ]
}}

**IMPORTANT:**
- Focus on violations that span MULTIPLE files
- Think in terms of DATA FLOW, not individual files
- Be specific about which files and lines are involved
- Provide actionable recommendations
- Consider the complete system context
- Respond ONLY with valid JSON

Analyze the repository now and respond with JSON only:"""
        
        return prompt
    
    def _format_dependency_graph(self, file_dependencies: Dict[str, Any]) -> str:
        """Format the dependency graph for the prompt."""
        lines = []
        for file_path, data in file_dependencies.items():
            lines.append(f"\n**{file_path}:**")
            
            if data['imports']:
                lines.append(f"  Imports: {', '.join(data['imports'][:5])}")
            
            if data['definitions']:
                lines.append(f"  Defines: {', '.join(data['definitions'][:5])}")
            
            if data['data_models']:
                lines.append(f"  Data Models: {', '.join(data['data_models'][:5])}")
            
            if data['violations']:
                lines.append(f"  Violations: {len(data['violations'])} detected")
        
        return '\n'.join(lines)
    
    def _format_violations_summary(self, violations_by_file: Dict[str, List[Violation]]) -> str:
        """Format violations summary for the prompt."""
        lines = []
        for file_path, violations in violations_by_file.items():
            lines.append(f"\n**{file_path}:** {len(violations)} violation(s)")
            for v in violations[:3]:  # Show first 3
                lines.append(f"  - [{v.severity}] {v.rule_name} (line {v.line_number})")
        return '\n'.join(lines)
    
    def _parse_cross_file_violations(
        self,
        bob_response: Dict[str, Any],
        repo_path: str
    ) -> List[Violation]:
        """Parse Bob's response and create Violation objects."""
        violations = []
        # Defensive: allow bob_response to be a JSON string
        if isinstance(bob_response, str):
            try:
                bob_response = json.loads(bob_response)
            except Exception:
                logger.warning("_parse_cross_file_violations received unparseable string response")
                bob_response = {}

        additional_violations = bob_response.get('additional_violations', [])
        
        for i, v_data in enumerate(additional_violations):
            violation_id = f"CROSS-{i+1:03d}"
            
            # Use first affected file as primary file
            affected_files = v_data.get('affected_files', [])
            primary_file = affected_files[0] if affected_files else 'unknown'
            
            violation = Violation(
                id=violation_id,
                rule_id='CROSS_FILE_ANALYSIS',
                rule_name=v_data.get('type', 'Cross-File Violation'),
                category='GDPR' if 'GDPR' in v_data.get('type', '') else 'HIPAA',
                severity=v_data.get('severity', 'HIGH'),
                file_path=primary_file,
                line_number=0,  # Cross-file violations don't have single line
                column=None,
                code_snippet=v_data.get('data_flow', ''),
                context_before=[],
                context_after=[],
                description=v_data.get('description', ''),
                explanation=v_data.get('description', ''),
                recommendation=v_data.get('recommendation', ''),
                confidence=0.9 if v_data.get('confidence') == 'high' else 0.7
            )
            
            violations.append(violation)
        
        return violations
    
    def get_violations_by_category(self, category: str) -> List[Violation]:
        """
        Filter violations by category.
        
        Args:
            category: Category (SECURITY, GDPR, HIPAA, QUALITY)
            
        Returns:
            List of violations matching the category
        """
        return [v for v in self.violations if v.category.upper() == category.upper()]
    
    def get_violations_by_file(self, file_path: str) -> List[Violation]:
        """
        Get all violations for a specific file.
        
        Args:
            file_path: Path to the file
            
        Returns:
            List of violations in that file
        """
        return [v for v in self.violations if v.file_path == file_path]
    
    def get_summary(self) -> Dict[str, Any]:
        """
        Generate a summary of the analysis results.
        
        Returns:
            Dictionary with summary statistics
        """
        summary = {
            'total_violations': len(self.violations),
            'files_scanned': self.files_scanned,
            'files_with_violations': self.files_with_violations,
            'by_severity': {},
            'by_category': {},
            'by_file': {},
            'high_confidence_violations': 0
        }
        
        # Count by severity
        for severity in ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']:
            summary['by_severity'][severity.lower()] = len(
                self.get_violations_by_severity(severity)
            )
        
        # Count by category
        categories = set(v.category for v in self.violations)
        for category in categories:
            summary['by_category'][category.lower()] = len(
                self.get_violations_by_category(category)
            )
        
        # Count by file
        files = set(v.file_path for v in self.violations)
        for file_path in files:
            summary['by_file'][file_path] = len(
                self.get_violations_by_file(file_path)
            )
        
        # Count high confidence violations (>= 0.8)
        summary['high_confidence_violations'] = len(
            [v for v in self.violations if v.confidence >= 0.8]
        )
        
        return summary
    
    def export_violations(self, output_path: str, format: str = 'json'):
        """
        Export violations to a file.
        
        Args:
            output_path: Path to output file
            format: Output format ('json' or 'csv')
        """
        if format == 'json':
            with open(output_path, 'w') as f:
                json.dump(
                    [v.to_dict() for v in self.violations],
                    f,
                    indent=2
                )
        elif format == 'csv':
            import csv
            with open(output_path, 'w', newline='') as f:
                if self.violations:
                    fieldnames = self.violations[0].to_dict().keys()
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    for violation in self.violations:
                        writer.writerow(violation.to_dict())

# Made with Bob
