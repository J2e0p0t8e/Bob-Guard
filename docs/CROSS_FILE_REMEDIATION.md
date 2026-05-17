# Cross-File Remediation

This document explains how Bob-Guard handles code violations that require changes across multiple files.

## Overview

Some security fixes impact multiple files. For example:
- Renaming a function for security requires updating all call sites
- Changing an API interface requires updating all consumers
- Modifying imports requires updating all dependent files
- Refactoring shared utilities affects all users

The `handle_cross_file_remediation()` method intelligently identifies, plans, and applies changes across the entire codebase.

## Process Flow

```
1. Detect Cross-File Need
   ↓
2. Find Dependent Files
   ↓
3. Generate Comprehensive Prompt
   ↓
4. Get Modification Plan from Bob
   ↓
5. Validate Plan
   ↓
6. Determine Dependency Order
   ↓
7. Apply Changes (Dependencies First)
```

## Method Signature

```python
def handle_cross_file_remediation(
    self, 
    violation: Violation, 
    repo_path: str
) -> Dict[str, Any]
```

### Parameters
- **violation**: The violation that requires fixing
- **repo_path**: Path to the repository root

### Returns
Dictionary containing:
- `requires_cross_file`: Boolean indicating if multiple files need changes
- `affected_files`: List of file paths that need modification
- `modification_plan`: Detailed plan for each file from Bob
- `dependency_order`: Order in which files should be modified
- `results`: List of RemediationResult objects for each file
- `error`: Error message if something went wrong (optional)

## Step-by-Step Breakdown

### Step 1: Detect Cross-File Need

The `_requires_cross_file_changes()` method analyzes the violation to determine if it affects multiple files.

**Indicators of cross-file impact:**
- Keywords: "rename", "refactor", "interface", "api", "import", "global", "export", "public", "shared"
- Function or class definitions (might be used elsewhere)
- API/interface modifications
- Configuration changes

**Example:**
```python
# This violation requires cross-file changes
violation.recommendation = "Rename function to use secure naming convention"
# Result: requires_cross_file = True
```

### Step 2: Find Dependent Files

The `_find_dependent_files()` method scans the repository to find all files that depend on the code being fixed.

**Search Strategy:**
1. Extract identifiers (function names, class names) from the violation
2. Search for import statements referencing the file
3. Search for usage of extracted identifiers
4. Return list of dependent files

**Example:**
```python
# Original file: src/auth.py
# Function: authenticate_user()

# Dependent files found:
# - src/api/routes.py (imports and calls authenticate_user)
# - src/middleware/auth.py (imports authenticate_user)
# - tests/test_auth.py (tests authenticate_user)
```

### Step 3: Generate Comprehensive Prompt

The `_generate_cross_file_prompt()` method creates a detailed prompt for IBM Bob.

**Prompt Structure:**

#### Section 1: Primary Violation
- File path, line number, violation details
- Complete file content (not just snippet)
- Problematic code and recommendation

#### Section 2: Potentially Affected Files
- Complete content of each dependent file (up to 20 files)
- Relative paths from repository root
- Full context for analysis

#### Section 3: Task Requirements
Bob must:
1. **Be Exhaustive**: Check EVERY file for impacts
2. **Maintain Consistency**: Same naming, same patterns
3. **Preserve Functionality**: No breaking changes
4. **Determine Dependency Order**: Fix dependencies first

#### Section 4: Required Response Format
Strict JSON structure with:
- Impact analysis summary
- Complete list of files to modify
- Exact changes for each file
- Complete patched content for each file
- Dependency levels and modification order
- Validation checklist
- Confidence and warnings

**Example Prompt Excerpt:**
```
## YOUR TASK

You must provide a COMPREHENSIVE modification plan that:

1. **Identifies ALL files that need changes** - Be exhaustive
2. **Specifies exact changes for each file** - Complete patched content
3. **Determines the correct modification order** - Dependencies first
4. **Ensures consistency across all files** - Same naming, patterns
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
...
```

### Step 4: Get Modification Plan from Bob

Send the prompt to Bob via the chat endpoint and parse the JSON response.

**Expected Response Structure:**
```json
{
  "requires_cross_file": true,
  "primary_fix_description": "Rename authenticate_user to verify_user_credentials",
  "impact_analysis": {
    "total_files_affected": 4,
    "types_of_changes": ["function_rename", "import_update", "call_site_update"],
    "risk_level": "medium",
    "breaking_changes": false
  },
  "files_to_modify": [
    {
      "file_path": "src/auth.py",
      "reason": "Contains the function being renamed",
      "changes_needed": [
        "Rename function from authenticate_user to verify_user_credentials",
        "Update docstring"
      ],
      "patched_content": "COMPLETE FILE CONTENT...",
      "dependency_level": 0
    },
    {
      "file_path": "src/api/routes.py",
      "reason": "Imports and calls authenticate_user",
      "changes_needed": [
        "Update import statement",
        "Update function call on line 45"
      ],
      "patched_content": "COMPLETE FILE CONTENT...",
      "dependency_level": 1
    }
  ],
  "modification_order": [
    "src/auth.py",
    "src/api/routes.py",
    "src/middleware/auth.py",
    "tests/test_auth.py"
  ],
  "validation_checklist": [
    "All imports updated",
    "All function calls updated",
    "All tests updated"
  ],
  "confidence": 0.95,
  "requires_manual_review": false,
  "warnings": []
}
```

### Step 5: Validate Plan

The `_validate_modification_plan()` method ensures the plan is complete and correct.

**Validation Checks:**
- All required fields present
- `files_to_modify` is a list
- Each file has: `file_path`, `patched_content`, `dependency_level`
- `modification_order` matches `files_to_modify`

**Example:**
```python
validation_result = {
    'valid': True,
    'errors': []
}
# or
validation_result = {
    'valid': False,
    'errors': [
        'File 2 missing patched_content',
        'modification_order doesn\'t match files_to_modify'
    ]
}
```

### Step 6: Determine Dependency Order

The `_determine_dependency_order()` method sorts files by dependency level.

**Dependency Levels:**
- **Level 0**: No dependencies (base files, utilities)
- **Level 1**: Depends on level 0 files
- **Level 2**: Depends on level 1 files
- And so on...

**Example:**
```python
# Files sorted by dependency_level
dependency_order = [
    "src/auth.py",           # Level 0 - base module
    "src/api/routes.py",     # Level 1 - imports auth
    "src/middleware/auth.py", # Level 1 - imports auth
    "tests/test_auth.py"     # Level 2 - imports routes
]
```

### Step 7: Apply Changes

The `_apply_cross_file_modifications()` method applies changes in dependency order.

**Process for each file:**
1. Read original content
2. Get patched content from plan
3. Generate diff
4. Apply patch (creates backup)
5. Create RemediationResult
6. Log success/failure

**Safety Features:**
- Automatic backups (.backup extension)
- Syntax validation before writing
- Rollback on failure
- Comprehensive error logging

## Usage Example

```python
from src.remediator import Remediator
from src.bob_client import BobClient
from src.analyzer import Violation

# Initialize
bob_client = BobClient()
remediator = Remediator([], bob_client, dry_run=False)

# Create violation that requires cross-file changes
violation = Violation(
    id="V001",
    rule_id="SEC-001",
    rule_name="Insecure Function Name",
    category="SECURITY",
    severity="HIGH",
    file_path="src/auth.py",
    line_number=45,
    column=0,
    code_snippet="def authenticate_user(username, password):",
    context_before=[],
    context_after=[],
    description="Function name reveals authentication mechanism",
    explanation="Exposing authentication details in function names",
    recommendation="Rename to generic name like verify_credentials",
    confidence=0.95
)

# Handle cross-file remediation
result = remediator.handle_cross_file_remediation(
    violation=violation,
    repo_path="/path/to/repo"
)

# Check results
if result['requires_cross_file']:
    print(f"Affected files: {len(result['affected_files'])}")
    print(f"Modification order: {result['dependency_order']}")
    
    for remediation_result in result['results']:
        print(f"  {remediation_result.file_path}: {remediation_result.status}")
```

## Dry-Run Mode

In dry-run mode, the method:
1. Analyzes the violation
2. Finds dependent files
3. Gets modification plan from Bob
4. Validates the plan
5. **Does NOT apply changes**
6. Returns DRY_RUN results

This allows you to review the plan before applying it.

```python
# Dry-run mode (safe)
remediator = Remediator([], bob_client, dry_run=True)
result = remediator.handle_cross_file_remediation(violation, repo_path)

# Review the plan
print(f"Would modify {len(result['affected_files'])} files")
for file_info in result['modification_plan']['files_to_modify']:
    print(f"  {file_info['file_path']}: {file_info['reason']}")

# If satisfied, apply for real
remediator.dry_run = False
result = remediator.handle_cross_file_remediation(violation, repo_path)
```

## Error Handling

The method handles various error scenarios:

### JSON Parse Error
```python
{
    'requires_cross_file': True,
    'affected_files': [...],
    'modification_plan': {},
    'dependency_order': [],
    'results': [],
    'error': 'Failed to parse modification plan'
}
```

### Bob API Error
```python
{
    'requires_cross_file': True,
    'affected_files': [...],
    'modification_plan': {},
    'dependency_order': [],
    'results': [],
    'error': 'Bob API error: Rate limit exceeded'
}
```

### Validation Error
```python
{
    'requires_cross_file': True,
    'affected_files': [...],
    'modification_plan': {...},
    'dependency_order': [],
    'results': [],
    'error': 'Invalid plan: Missing required field: patched_content'
}
```

### File Not Found
Individual file errors are captured in RemediationResult:
```python
RemediationResult(
    violation_id="V001",
    file_path="missing_file.py",
    status="FAILED",
    error_message="File not found"
)
```

## Best Practices

### 1. Always Use Dry-Run First
```python
# Test the plan
remediator.dry_run = True
result = remediator.handle_cross_file_remediation(violation, repo_path)

# Review and apply
if result['modification_plan'].get('confidence', 0) > 0.9:
    remediator.dry_run = False
    result = remediator.handle_cross_file_remediation(violation, repo_path)
```

### 2. Check Confidence Scores
```python
plan = result['modification_plan']
if plan.get('confidence', 0) < 0.8:
    print("Low confidence - manual review recommended")
if plan.get('requires_manual_review', False):
    print("Bob recommends manual review")
```

### 3. Review Warnings
```python
warnings = result['modification_plan'].get('warnings', [])
for warning in warnings:
    print(f"Warning: {warning}")
```

### 4. Validate Backups
```python
for remediation_result in result['results']:
    if remediation_result.backup_path:
        print(f"Backup: {remediation_result.backup_path}")
```

### 5. Test After Application
```python
# After applying changes, run tests
import subprocess
subprocess.run(['pytest', 'tests/'], check=True)
```

## Limitations

1. **Token Limits**: Only analyzes up to 20 dependent files to avoid token limits
2. **Language Support**: Best results with Python, JavaScript, TypeScript, Java
3. **Complex Dependencies**: Very complex dependency chains may require manual review
4. **Indirect Dependencies**: May miss very indirect dependencies (A→B→C→D)

## Future Enhancements

- **Incremental Analysis**: Analyze files in batches for large codebases
- **Dependency Graph**: Build and visualize complete dependency graph
- **Test Generation**: Automatically generate tests for modified code
- **Rollback Support**: Easy rollback of entire cross-file changes
- **Interactive Mode**: Ask user for confirmation at each step
- **Impact Prediction**: Predict impact before analyzing all files

## Integration with Bob-Guard

Cross-file remediation integrates with:
- **Analyzer**: Receives Violation objects
- **BobClient**: Uses chat endpoint for complex prompts
- **Reporter**: Logs all changes across files
- **Test Generator**: Can generate tests for all modified files

## Conclusion

Cross-file remediation ensures that security fixes are applied comprehensively across the entire codebase, maintaining consistency and preventing broken references. The exhaustive prompt template guides IBM Bob to identify all impacts and generate a complete, validated modification plan.