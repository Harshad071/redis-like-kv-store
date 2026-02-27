"""
RedisLite API Client Example
A simple Python client for interacting with the RedisLite Microservice API.
"""

import requests
import json
from typing import Any, Optional
from urllib.parse import urljoin


class RedisLiteClient:
    """
    Simple HTTP client for the RedisLite Microservice.
    
    Example:
        >>> client = RedisLiteClient("http://localhost:8000")
        >>> client.set("mykey", "myvalue", ttl=60)
        >>> client.get("mykey")
        {"key": "mykey", "value": "myvalue", "exists": True}
    """
    
    def __init__(self, base_url: str = "http://localhost:8000", timeout: int = 5):
        """
        Initialize the client.
        
        Args:
            base_url: The base URL of the RedisLite API
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
    
    def _request(self, method: str, endpoint: str, **kwargs) -> dict:
        """
        Make an HTTP request to the API.
        
        Args:
            method: HTTP method (GET, POST, DELETE, etc.)
            endpoint: API endpoint path
            **kwargs: Additional arguments to pass to requests
        
        Returns:
            Response JSON as dictionary
        
        Raises:
            requests.exceptions.RequestException: If request fails
        """
        url = urljoin(self.base_url, endpoint)
        kwargs.setdefault("timeout", self.timeout)
        
        response = self.session.request(method, url, **kwargs)
        response.raise_for_status()
        
        return response.json()
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> dict:
        """
        Set a key-value pair in the store.
        
        Args:
            key: The key to store
            value: The value to store (any JSON-serializable type)
            ttl: Time-to-live in seconds (optional)
        
        Returns:
            Response dictionary with success status
        """
        return self._request(
            "POST",
            "/api/set",
            json={"key": key, "value": value, "ttl": ttl}
        )
    
    def get(self, key: str) -> dict:
        """
        Retrieve a value by key.
        
        Args:
            key: The key to retrieve
        
        Returns:
            Response dictionary with the value and existence status
        """
        return self._request("GET", "/api/get", params={"key": key})
    
    def delete(self, key: str) -> dict:
        """
        Delete a key from the store.
        
        Args:
            key: The key to delete
        
        Returns:
            Response dictionary with deletion status
        """
        return self._request("DELETE", "/api/delete", params={"key": key})
    
    def exists(self, key: str) -> dict:
        """
        Check if a key exists and hasn't expired.
        
        Args:
            key: The key to check
        
        Returns:
            Response dictionary with existence status
        """
        return self._request("GET", "/api/exists", params={"key": key})
    
    def health(self) -> dict:
        """
        Check the health of the service.
        
        Returns:
            Response dictionary with service status
        """
        return self._request("GET", "/health")
    
    def close(self):
        """Close the session."""
        self.session.close()
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


# Example usage
if __name__ == "__main__":
    # Initialize client
    with RedisLiteClient("http://localhost:8000") as client:
        # Check health
        print("Health Check:")
        print(client.health())
        print()
        
        # Set some values
        print("Setting values:")
        print(client.set("user:1", {"name": "Alice", "role": "admin"}, ttl=3600))
        print(client.set("session:xyz", "active_session", ttl=1800))
        print()
        
        # Get values
        print("Getting values:")
        print(client.get("user:1"))
        print(client.get("session:xyz"))
        print()
        
        # Check existence
        print("Checking existence:")
        print(client.exists("user:1"))
        print(client.exists("nonexistent"))
        print()
        
        # Delete
        print("Deleting:")
        print(client.delete("session:xyz"))
        print(client.exists("session:xyz"))
