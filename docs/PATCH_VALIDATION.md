# Patch Validation and Rollback

This document explains how Bob-Guard validates patches after applying fixes to ensure code correctness and safety.

## Overview

After generating and applying a fix, it's critical to validate that:
1. The code is syntactically correct
2. The violation is actually resolved
3. No new vulnerabilities were introduced
4. Business logic is preserved

The validation system provides multi-level checks with automatic rollback on failure.

## Core Methods

### 1. validate_patch()

Comprehensive validation of a patched file.

```python
def validate_patch(
    self, 
    file_path: str, 
    original_code: str,
    patched_code: str, 
    language: str, 
    violation_type: str = "unknown"
) -> Dict[str, Any]
```

**Process:**
1. **Syntax Validation**: Language-specific syntax checking
2. **Semantic Validation**: IBM Bob analyzes the fix
3. **Combined Result**: Both must pass for overall validation

**Returns:**
```python
{
    'valid': True/False,              # Overall result
    'syntax_valid': True/False,       # Syntax check result
    'semantic_valid': True/False,     # Semantic check result
    'issues': [],                     # List of problems found
    'bob_analysis': {                 # Detailed analysis from Bob
        'violation_resolved': True/False,
        'new_vulnerabilities': [],
        'logic_preserved': True/False,
        'recommendation': 'approve/reject/manual_review'
    }
}
```

### 2. rollback()

Restore a file from backup if validation fails.

```python
def rollback(self, file_path: str) -> bool
```

**Process:**
1. Looks for `.backup` file
2. Restores original content
3. Archives backup with timestamp
4. Returns success/failure

**Returns:** `True` if rollback successful, `False` otherwise

### 3. validate_and_apply_patch()

High-level method combining validation and application with automatic rollback.

```python
def validate_and_apply_patch(
    self,
    file_path: str,
    original_content: str,
    patched_content: str,
    violation_type: str = "unknown"
) -> Dict[str, Any]
```

**Process:**
1. Validate the patch
2. If valid, apply it
3. Verify written content
4. Rollback automatically if anything fails

**Returns:**
```python
{
    'applied': True/False,           # Whether patch was applied
    'validation_result': {...},      # Full validation results
    'backup_path': 'path/to/backup', # Backup file location
    'rolled_back': True/False        # Whether rollback occurred
}
```

## Validation Levels

### Level 1: Syntax Validation

Language-specific syntax checking to ensure the code can be parsed.

#### Python
- Uses `ast.parse()` for comprehensive syntax checking
- Detects syntax errors with line numbers
- Validates Python-specific constructs

```python
# Valid Python
def hello():
    return "world"

# Invalid Python (caught by validation)
def hello()
    return "world"  # Missing colon
```

#### JavaScript/TypeScript
- Checks balanced braces `{}`
- Checks balanced brackets `[]`
- Checks balanced parentheses `()`
- Detects unclosed string literals

```javascript
// Valid JavaScript
function hello() {
    return "world";
}

// Invalid JavaScript (caught by validation)
function hello() {
    return "world";
// Missing closing brace
```

#### Java
- Checks balanced braces, brackets, parentheses
- Verifies class or interface definition exists
- Basic structure validation

```java
// Valid Java
public class Hello {
    public String greet() {
        return "world";
    }
}

// Invalid Java (caught by validation)
public class Hello {
    public String greet() {
        return "world";
    }
// Missing closing brace
```

#### Other Languages
- Generic validation for coherence
- Checks minimum code length
- Warns about unbalanced braces
- Ensures file is not empty

### Level 2: Semantic Validation

IBM Bob analyzes the fix to ensure it's correct and safe.

#### Validation Prompt

Bob receives both versions of the code and analyzes:

1. **Violation Resolution**
   - Is the specific violation fixed?
   - Is the fix appropriate for the violation type?

2. **No New Vulnerabilities**
   - SQL injection risks
   - XSS vulnerabilities
   - Security holes
   - Logic errors

3. **Business Logic Preservation**
   - Same inputs/outputs
   - Same control flow (unless required by fix)
   - Same side effects
   - No unintended behavior changes

#### Bob's Response Format

```json
{
  "valid": true,
  "violation_resolved": true,
  "new_vulnerabilities": [],
  "logic_preserved": true,
  "issues": [],
  "analysis": {
    "violation_resolution": "SQL injection fixed by using parameterized queries",
    "security_assessment": "No new vulnerabilities introduced",
    "logic_assessment": "Business logic preserved, same functionality"
  },
  "confidence": 0.95,
  "recommendation": "approve"
}
```

**Recommendations:**
- `approve`: Safe to apply the patch
- `reject`: Do not apply, issues found
- `manual_review`: Human review recommended

## Usage Examples

### Example 1: Basic Validation

```python
from src.remediator import Remediator
from src.bob_client import BobClient

# Initialize
bob_client = BobClient()
remediator = Remediator([], bob_client)

# Read files
with open('app.py', 'r') as f:
    original = f.read()

with open('app_fixed.py', 'r') as f:
    patched = f.read()

# Validate
result = remediator.validate_patch(
    file_path='app.py',
    original_code=original,
    patched_code=patched,
    language='python',
    violation_type='SQL_INJECTION'
)

if result['valid']:
    print("✓ Patch is valid")
else:
    print("✗ Patch validation failed")
    print(f"Issues: {result['issues']}")
```

### Example 2: Validate and Apply with Auto-Rollback

```python
# Safer approach - validates before applying
result = remediator.validate_and_apply_patch(
    file_path='app.py',
    original_content=original,
    patched_content=patched,
    violation_type='SQL_INJECTION'
)

if result['applied']:
    print(f"✓ Patch applied successfully")
    print(f"  Backup: {result['backup_path']}")
else:
    print("✗ Patch not applied")
    if result['rolled_back']:
        print("  File rolled back to original")
```

### Example 3: Manual Rollback

```python
# If something goes wrong after applying
if remediator.rollback('app.py'):
    print("✓ Successfully rolled back app.py")
else:
    print("✗ Rollback failed")
```

### Example 4: Integration with Remediation

```python
# In remediate_file method
for violation in violations:
    # Generate fix
    fix_response = bob_client.generate_fix(...)
    patched_code = fix_response['fixed_code']
    
    # Validate before applying
    validation = remediator.validate_patch(
        file_path=file_path,
        original_code=current_content,
        patched_code=patched_code,
        language=language,
        violation_type=violation.rule_id
    )
    
    if validation['valid']:
        # Apply the fix
        backup_path = remediator.apply_patch(
            file_path, current_content, patched_code
        )
        logger.info(f"✓ Fix applied and validated")
    else:
        logger.error(f"✗ Validation failed: {validation['issues']}")
        # Don't apply the fix
```

## Validation Workflow

```
┌─────────────────────┐
│  Generate Fix       │
│  (via Bob)          │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Syntax Validation  │
│  (Language-specific)│
└──────────┬──────────┘
           │
           ├─── FAIL ──► Don't Apply
           │
           ▼ PASS
┌─────────────────────┐
│ Semantic Validation │
│ (Bob Analysis)      │
└──────────┬──────────┘
           │
           ├─── FAIL ──► Don't Apply
           │
           ▼ PASS
┌─────────────────────┐
│  Apply Patch        │
│  (Create Backup)    │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ Post-Write Verify   │
└──────────┬──────────┘
           │
           ├─── FAIL ──► Automatic Rollback
           │
           ▼ PASS
┌─────────────────────┐
│  Success!           │
└─────────────────────┘
```

## Error Handling

### Syntax Validation Errors

```python
{
    'valid': False,
    'syntax_valid': False,
    'semantic_valid': False,
    'issues': [
        'Python syntax error at line 45: invalid syntax'
    ],
    'bob_analysis': {}
}
```

### Semantic Validation Errors

```python
{
    'valid': False,
    'syntax_valid': True,
    'semantic_valid': False,
    'issues': [
        'New SQL injection vulnerability introduced',
        'Business logic altered unexpectedly'
    ],
    'bob_analysis': {
        'valid': False,
        'violation_resolved': True,
        'new_vulnerabilities': ['SQL_INJECTION'],
        'logic_preserved': False,
        'recommendation': 'reject'
    }
}
```

### Bob API Errors

```python
{
    'valid': False,
    'syntax_valid': True,
    'semantic_valid': False,
    'issues': [
        'Bob API error: Rate limit exceeded'
    ],
    'bob_analysis': {
        'valid': False,
        'issues': ['Bob API error: Rate limit exceeded'],
        'confidence': 0.0,
        'recommendation': 'manual_review'
    }
}
```

## Best Practices

### 1. Always Validate Before Applying

```python
# Good
validation = remediator.validate_patch(...)
if validation['valid']:
    remediator.apply_patch(...)

# Better
result = remediator.validate_and_apply_patch(...)
```

### 2. Check Confidence Scores

```python
bob_analysis = validation['bob_analysis']
if bob_analysis.get('confidence', 0) < 0.8:
    print("Low confidence - manual review recommended")
```

### 3. Handle Recommendations

```python
recommendation = bob_analysis.get('recommendation')
if recommendation == 'reject':
    print("Bob recommends rejecting this patch")
elif recommendation == 'manual_review':
    print("Bob recommends manual review")
elif recommendation == 'approve':
    print("Bob approves this patch")
```

### 4. Keep Backups

```python
# Backups are automatically created
# They're archived with timestamps on rollback
# Keep them for audit trails
```

### 5. Log Everything

```python
# All validation steps are logged
# Check logs for detailed information
logger.info("Validation results logged")
```

## Limitations

1. **Syntax Validation**
   - JavaScript/TypeScript validation is basic
   - Complex language features may not be fully validated
   - Consider using language-specific linters for production

2. **Semantic Validation**
   - Depends on Bob's analysis capabilities
   - May miss subtle logic errors
   - Complex business logic may require manual review

3. **Performance**
   - Semantic validation requires API call to Bob
   - May be slow for large files
   - Consider batching for multiple files

## Future Enhancements

- **Static Analysis Integration**: Use tools like pylint, ESLint
- **Unit Test Execution**: Run tests after applying patches
- **Diff-based Validation**: Validate only changed lines
- **Caching**: Cache validation results for similar patches
- **Parallel Validation**: Validate multiple files concurrently

## Integration with Bob-Guard

Validation integrates seamlessly with:
- **Remediator**: Validates all applied fixes
- **Reporter**: Logs validation results
- **Test Generator**: Can trigger test generation for validated fixes
- **Cross-File Remediation**: Validates all modified files

## Conclusion

The validation system ensures that fixes are safe, correct, and don't introduce new issues. With multi-level validation and automatic rollback, Bob-Guard provides a robust safety net for automated code remediation.