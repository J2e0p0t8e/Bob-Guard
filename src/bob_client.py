"""
IBM Bob API Client
Handles communication with IBM Bob API for intelligent code analysis and remediation.
"""

import os
import requests
import json
from typing import Dict, List, Optional, Any
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class BobAPIError(Exception):
    """Custom exception for Bob API errors"""
    pass


class BobClient:
    """
    Client for interacting with IBM Bob API.
    Provides methods for code analysis, fix generation, and test creation.
    """

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        """
        Initialize Bob API client.
        
        Args:
            api_key: IBM Bob API key (defaults to BOB_API_KEY env var)
            base_url: API base URL (defaults to BOB_API_URL env var)
        """
        self.api_key = api_key or os.getenv('BOB_API_KEY')
        self.base_url = base_url or os.getenv('BOB_API_URL', 'https://api.ibm.com/bob/v1')
        
        if not self.api_key:
            raise BobAPIError("Bob API key not provided. Set BOB_API_KEY environment variable.")
        
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })

    def analyze_code(self, code: str, language: str, rules: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Analyze code for compliance and security issues.
        
        Args:
            code: Source code to analyze
            language: Programming language (e.g., 'python', 'javascript')
            rules: List of rule IDs to apply (optional)
            
        Returns:
            Dictionary containing analysis results with violations and suggestions
            
        Raises:
            BobAPIError: If API request fails
        """
        endpoint = f"{self.base_url}/analyze"
        payload = {
            'code': code,
            'language': language,
            'rules': rules or []
        }
        
        try:
            response = self.session.post(endpoint, json=payload, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            raise BobAPIError(f"Failed to analyze code: {str(e)}")

    def generate_fix(self, code: str, violation: Dict[str, Any], language: str) -> Dict[str, Any]:
        """
        Generate a fix for a specific code violation.
        
        Args:
            code: Original source code
            violation: Violation details from analysis
            language: Programming language
            
        Returns:
            Dictionary containing fixed code and explanation
            
        Raises:
            BobAPIError: If API request fails
        """
        endpoint = f"{self.base_url}/remediate"
        payload = {
            'code': code,
            'violation': violation,
            'language': language
        }
        
        try:
            response = self.session.post(endpoint, json=payload, timeout=60)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            raise BobAPIError(f"Failed to generate fix: {str(e)}")

    def generate_tests(self, code: str, language: str, test_framework: Optional[str] = None) -> Dict[str, Any]:
        """
        Generate unit tests for given code.
        
        Args:
            code: Source code to generate tests for
            language: Programming language
            test_framework: Testing framework to use (e.g., 'pytest', 'jest')
            
        Returns:
            Dictionary containing generated test code
            
        Raises:
            BobAPIError: If API request fails
        """
        endpoint = f"{self.base_url}/generate-tests"
        payload = {
            'code': code,
            'language': language,
            'test_framework': test_framework
        }
        
        try:
            response = self.session.post(endpoint, json=payload, timeout=60)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            raise BobAPIError(f"Failed to generate tests: {str(e)}")

    def chat(self, message: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Interactive chat with Bob for code-related questions.
        
        Args:
            message: User message/question
            context: Optional context (code, previous messages, etc.)
            
        Returns:
            Dictionary containing Bob's response
            
        Raises:
            BobAPIError: If API request fails
        """
        endpoint = f"{self.base_url}/chat"
        payload = {
            'message': message,
            'context': context or {}
        }
        
        try:
            response = self.session.post(endpoint, json=payload, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            raise BobAPIError(f"Failed to chat with Bob: {str(e)}")

    def batch_analyze(self, files: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        Analyze multiple files in a single request.
        
        Args:
            files: List of dictionaries with 'path', 'code', and 'language' keys
            
        Returns:
            Dictionary containing analysis results for all files
            
        Raises:
            BobAPIError: If API request fails
        """
        endpoint = f"{self.base_url}/batch-analyze"
        payload = {'files': files}
        
        try:
            response = self.session.post(endpoint, json=payload, timeout=120)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            raise BobAPIError(f"Failed to batch analyze: {str(e)}")

    def get_supported_languages(self) -> List[str]:
        """
        Get list of supported programming languages.
        
        Returns:
            List of supported language identifiers
            
        Raises:
            BobAPIError: If API request fails
        """
        endpoint = f"{self.base_url}/languages"
        
        try:
            response = self.session.get(endpoint, timeout=10)
            response.raise_for_status()
            return response.json().get('languages', [])
        except requests.exceptions.RequestException as e:
            raise BobAPIError(f"Failed to get supported languages: {str(e)}")

    def get_available_rules(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get available compliance and security rules.
        
        Args:
            category: Optional category filter (e.g., 'gdpr', 'hipaa', 'security')
            
        Returns:
            List of rule definitions
            
        Raises:
            BobAPIError: If API request fails
        """
        endpoint = f"{self.base_url}/rules"
        params = {'category': category} if category else {}
        
        try:
            response = self.session.get(endpoint, params=params, timeout=10)
            response.raise_for_status()
            return response.json().get('rules', [])
        except requests.exceptions.RequestException as e:
            raise BobAPIError(f"Failed to get available rules: {str(e)}")

    def close(self):
        """Close the HTTP session."""
        self.session.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


# Convenience function for quick analysis
def quick_analyze(code: str, language: str, api_key: Optional[str] = None) -> Dict[str, Any]:
    """
    Quick code analysis without managing client instance.
    
    Args:
        code: Source code to analyze
        language: Programming language
        api_key: Optional API key (uses env var if not provided)
        
    Returns:
        Analysis results
    """
    with BobClient(api_key=api_key) as client:
        return client.analyze_code(code, language)

# Made with Bob
