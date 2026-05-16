"""
IBM Bob API Client
Handles communication with IBM Bob API for intelligent code analysis and remediation.
IBM Bob is an AI agent capable of understanding and transforming entire codebases.
"""

import os
import time
from typing import Dict, List, Optional, Any
from dotenv import load_dotenv
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Load environment variables
load_dotenv()


class BobAPIError(Exception):
    """Custom exception for Bob API errors"""
    pass


class BobRateLimitError(BobAPIError):
    """Exception for rate limit errors"""
    pass


class BobTimeoutError(BobAPIError):
    """Exception for timeout errors"""
    pass


class BobClient:
    """
    Client for interacting with IBM Bob API.
    Provides methods for code analysis, fix generation, and test creation.
    """

    def __init__(self, api_key: Optional[str] = None, endpoint: Optional[str] = None):
        """
        Initialize Bob API client.
        
        Args:
            api_key: IBM Bob API key (defaults to IBM_BOB_API_KEY env var)
            endpoint: API endpoint URL (defaults to IBM_BOB_ENDPOINT env var)
        
        Raises:
            BobAPIError: If API key is not provided
        """
        self.api_key = api_key or os.getenv('IBM_BOB_API_KEY')
        self.endpoint = endpoint or os.getenv('IBM_BOB_ENDPOINT', 'https://api.ibm.com/bob/v1')
        
        if not self.api_key:
            raise BobAPIError(
                "IBM Bob API key not provided. Set IBM_BOB_API_KEY environment variable "
                "or pass api_key parameter."
            )
        
        # Configure session with retry strategy
        self.session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # Set default headers
        self.session.headers.update({
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'User-Agent': 'Bob-Guard/1.0'
        })
        
        # Request timeout in seconds
        self.timeout = 60

    def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None, 
                     max_retries: int = 3) -> Dict[str, Any]:
        """
        Make HTTP request to Bob API with retry logic.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            data: Request payload
            max_retries: Maximum number of retry attempts
            
        Returns:
            Response data as dictionary
            
        Raises:
            BobAPIError: For general API errors
            BobRateLimitError: When rate limit is exceeded
            BobTimeoutError: When request times out
        """
        url = f"{self.endpoint}/{endpoint.lstrip('/')}"
        
        for attempt in range(max_retries):
            try:
                if method.upper() == 'GET':
                    response = self.session.get(url, params=data, timeout=self.timeout)
                elif method.upper() == 'POST':
                    response = self.session.post(url, json=data, timeout=self.timeout)
                else:
                    raise BobAPIError(f"Unsupported HTTP method: {method}")
                
                # Handle rate limiting
                if response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', 60))
                    if attempt < max_retries - 1:
                        time.sleep(retry_after)
                        continue
                    raise BobRateLimitError(
                        f"Rate limit exceeded. Retry after {retry_after} seconds."
                    )
                
                # Raise for other HTTP errors
                response.raise_for_status()
                
                return response.json()
                
            except requests.exceptions.Timeout:
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
                    continue
                raise BobTimeoutError(f"Request timed out after {self.timeout} seconds")
                
            except requests.exceptions.ConnectionError as e:
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise BobAPIError(f"Connection error: {str(e)}")
                
            except requests.exceptions.HTTPError as e:
                error_msg = f"HTTP error: {e.response.status_code}"
                try:
                    error_data = e.response.json()
                    error_msg += f" - {error_data.get('error', error_data.get('message', ''))}"
                except:
                    pass
                raise BobAPIError(error_msg)
                
            except requests.exceptions.RequestException as e:
                raise BobAPIError(f"Request failed: {str(e)}")
        
        raise BobAPIError(f"Max retries ({max_retries}) exceeded")

    def analyze_code(self, file_path: str, rule: str) -> Dict[str, Any]:
        """
        Send a file to Bob for analysis against a specific rule.
        
        Args:
            file_path: Path to the file to analyze
            rule: Compliance rule to check against (e.g., 'gdpr-001', 'hipaa-002')
            
        Returns:
            Dictionary containing analysis results with violations and recommendations
            
        Raises:
            BobAPIError: If analysis fails
            FileNotFoundError: If file doesn't exist
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        
        with open(file_path, 'r', encoding='utf-8') as f:
            code_content = f.read()
        
        payload = {
            'file_path': file_path,
            'code': code_content,
            'rule': rule,
            'action': 'analyze'
        }
        
        return self._make_request('POST', 'analyze', payload)

    def explain_violation(self, code_snippet: str, rule: str) -> Dict[str, Any]:
        """
        Ask Bob to explain why code is non-compliant with a specific rule.
        
        Args:
            code_snippet: The code that violates the rule
            rule: The compliance rule being violated
            
        Returns:
            Dictionary with explanation, severity, and recommendations
            
        Raises:
            BobAPIError: If explanation request fails
        """
        payload = {
            'code_snippet': code_snippet,
            'rule': rule,
            'action': 'explain'
        }
        
        return self._make_request('POST', 'explain', payload)

    def generate_fix(self, code_snippet: str, violation_type: str) -> Dict[str, Any]:
        """
        Ask Bob to generate a fix for a code violation.
        
        Args:
            code_snippet: The code containing the violation
            violation_type: Type of violation (e.g., 'sql_injection', 'gdpr_violation')
            
        Returns:
            Dictionary containing:
                - fixed_code: The corrected code
                - explanation: Description of changes made
                - confidence: Confidence score (0.0 to 1.0)
                - diff: Unified diff of changes
            
        Raises:
            BobAPIError: If fix generation fails
        """
        payload = {
            'code_snippet': code_snippet,
            'violation_type': violation_type,
            'action': 'fix'
        }
        
        return self._make_request('POST', 'fix', payload)

    def generate_tests(self, original_code: str, fixed_code: str) -> Dict[str, Any]:
        """
        Ask Bob to generate unit tests for the fixed code.
        
        Args:
            original_code: The original code before fixes
            fixed_code: The code after applying fixes
            
        Returns:
            Dictionary containing:
                - test_code: Generated unit test code
                - test_framework: Framework used (e.g., 'pytest', 'unittest')
                - test_cases: List of test case descriptions
                - coverage_estimate: Estimated code coverage percentage
            
        Raises:
            BobAPIError: If test generation fails
        """
        payload = {
            'original_code': original_code,
            'fixed_code': fixed_code,
            'action': 'generate_tests'
        }
        
        return self._make_request('POST', 'tests', payload)

    def generate_report(self, violations_list: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Ask Bob to generate a compliance report summary.
        
        Args:
            violations_list: List of violation dictionaries with details
            
        Returns:
            Dictionary containing:
                - summary: Executive summary of findings
                - risk_assessment: Overall risk level and analysis
                - recommendations: Prioritized list of actions
                - compliance_score: Overall compliance score (0-100)
            
        Raises:
            BobAPIError: If report generation fails
        """
        payload = {
            'violations': violations_list,
            'action': 'generate_report'
        }
        
        return self._make_request('POST', 'report', payload)

    def chat(self, message: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Send a free-form message to Bob with optional context.
        Used for interactive chat in the web interface.
        
        Args:
            message: User's question or message
            context: Optional context dictionary containing:
                - code: Code snippet for context
                - file_path: File being discussed
                - violations: Related violations
                - previous_messages: Chat history
            
        Returns:
            Dictionary containing:
                - response: Bob's response message
                - suggestions: List of suggested follow-up questions
                - code_examples: Any code examples in the response
            
        Raises:
            BobAPIError: If chat request fails
        """
        payload = {
            'message': message,
            'context': context or {},
            'action': 'chat'
        }
        
        return self._make_request('POST', 'chat', payload)

    def health_check(self) -> bool:
        """
        Check if Bob API is accessible and responding.
        
        Returns:
            True if API is healthy, False otherwise
        """
        try:
            response = self._make_request('GET', 'health', max_retries=1)
            return response.get('status') == 'healthy'
        except:
            return False

    def get_supported_rules(self) -> List[Dict[str, Any]]:
        """
        Get list of supported compliance rules from Bob.
        
        Returns:
            List of rule dictionaries with id, name, category, and description
            
        Raises:
            BobAPIError: If request fails
        """
        return self._make_request('GET', 'rules')

    def close(self):
        """Close the HTTP session."""
        self.session.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


# Convenience functions for quick operations
def quick_analyze(file_path: str, rule: str, api_key: Optional[str] = None) -> Dict[str, Any]:
    """
    Quick code analysis without managing client instance.
    
    Args:
        file_path: Path to file to analyze
        rule: Compliance rule to check
        api_key: Optional API key (uses env var if not provided)
        
    Returns:
        Analysis results
    """
    with BobClient(api_key=api_key) as client:
        return client.analyze_code(file_path, rule)


def quick_fix(code_snippet: str, violation_type: str, api_key: Optional[str] = None) -> Dict[str, Any]:
    """
    Quick fix generation without managing client instance.
    
    Args:
        code_snippet: Code to fix
        violation_type: Type of violation
        api_key: Optional API key (uses env var if not provided)
        
    Returns:
        Fix results with corrected code
    """
    with BobClient(api_key=api_key) as client:
        return client.generate_fix(code_snippet, violation_type)


def quick_chat(message: str, context: Optional[Dict] = None, api_key: Optional[str] = None) -> str:
    """
    Quick chat with Bob without managing client instance.
    
    Args:
        message: Message to send
        context: Optional context
        api_key: Optional API key (uses env var if not provided)
        
    Returns:
        Bob's response message
    """
    with BobClient(api_key=api_key) as client:
        result = client.chat(message, context)
        return result.get('response', '')

# Made with Bob
