#!/usr/bin/env python3
"""
RedisLite API Test Suite
Simple test script to verify all API endpoints are working correctly.
"""

import sys
import json
import time
from api.client import RedisLiteClient


def print_section(title: str):
    """Print a formatted section header."""
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}\n")


def print_test(name: str, passed: bool, details: str = ""):
    """Print test result."""
    status = "✓ PASS" if passed else "✗ FAIL"
    print(f"  {status}: {name}")
    if details:
        print(f"         {details}")


def test_health_check(client: RedisLiteClient):
    """Test health check endpoint."""
    try:
        response = client.health()
        passed = response.get("status") == "healthy"
        print_test("Health Check", passed, f"Status: {response.get('status')}")
        return passed
    except Exception as e:
        print_test("Health Check", False, str(e))
        return False


def test_set_get(client: RedisLiteClient):
    """Test set and get operations."""
    try:
        # Set a simple value
        set_response = client.set("test_key", "test_value")
        set_ok = set_response.get("success", False)
        print_test("Set Key (Simple)", set_ok)
        
        # Get the value
        get_response = client.get("test_key")
        get_ok = (
            get_response.get("value") == "test_value" and
            get_response.get("exists") is True
        )
        print_test("Get Key (Simple)", get_ok, f"Value: {get_response.get('value')}")
        
        return set_ok and get_ok
    except Exception as e:
        print_test("Set/Get Key", False, str(e))
        return False


def test_set_get_complex(client: RedisLiteClient):
    """Test set and get with complex JSON data."""
    try:
        # Set complex data
        data = {
            "user_id": 123,
            "username": "john_doe",
            "email": "john@example.com",
            "roles": ["admin", "user"],
            "metadata": {"created": "2024-01-01", "last_login": "2024-01-15"}
        }
        set_response = client.set("user:123", data)
        set_ok = set_response.get("success", False)
        print_test("Set Key (Complex JSON)", set_ok)
        
        # Get the value
        get_response = client.get("user:123")
        get_ok = (
            get_response.get("value") == data and
            get_response.get("exists") is True
        )
        print_test("Get Key (Complex JSON)", get_ok)
        
        return set_ok and get_ok
    except Exception as e:
        print_test("Set/Get Complex", False, str(e))
        return False


def test_ttl_expiration(client: RedisLiteClient):
    """Test TTL expiration."""
    try:
        # Set key with 2 second TTL
        set_response = client.set("temp_key", "temporary_value", ttl=2)
        set_ok = set_response.get("success", False)
        print_test("Set Key with TTL (2 seconds)", set_ok)
        
        # Check it exists immediately
        exists1 = client.exists("temp_key").get("exists", False)
        print_test("Key Exists (Immediately)", exists1)
        
        # Wait for expiration
        print("  → Waiting 3 seconds for TTL expiration...")
        time.sleep(3)
        
        # Check it doesn't exist anymore
        exists2 = client.exists("temp_key").get("exists", False)
        expiration_ok = not exists2
        print_test("Key Expired (After TTL)", expiration_ok)
        
        return set_ok and exists1 and expiration_ok
    except Exception as e:
        print_test("TTL Expiration", False, str(e))
        return False


def test_delete(client: RedisLiteClient):
    """Test delete operation."""
    try:
        # Set a key
        client.set("delete_test", "value")
        
        # Delete it
        delete_response = client.delete("delete_test")
        deleted = delete_response.get("deleted", False)
        print_test("Delete Key", deleted)
        
        # Verify it's gone
        exists_response = client.exists("delete_test")
        not_exists = not exists_response.get("exists", True)
        print_test("Verify Key Deleted", not_exists)
        
        return deleted and not_exists
    except Exception as e:
        print_test("Delete", False, str(e))
        return False


def test_exists(client: RedisLiteClient):
    """Test exists operation."""
    try:
        # Set a key
        client.set("exists_test", "value")
        
        # Check it exists
        exists_response = client.exists("exists_test")
        exists = exists_response.get("exists", False)
        print_test("Exists (Key Present)", exists)
        
        # Check non-existent key
        not_exists_response = client.exists("nonexistent_key")
        not_exists = not not_exists_response.get("exists", True)
        print_test("Not Exists (Key Missing)", not_exists)
        
        return exists and not_exists
    except Exception as e:
        print_test("Exists", False, str(e))
        return False


def test_overwrite(client: RedisLiteClient):
    """Test overwriting a key."""
    try:
        # Set initial value
        client.set("overwrite_test", "value1")
        get1 = client.get("overwrite_test").get("value")
        
        # Overwrite with new value
        client.set("overwrite_test", "value2")
        get2 = client.get("overwrite_test").get("value")
        
        ok = get1 == "value1" and get2 == "value2"
        print_test("Overwrite Key", ok, f"{get1} → {get2}")
        
        return ok
    except Exception as e:
        print_test("Overwrite", False, str(e))
        return False


def test_nonexistent_get(client: RedisLiteClient):
    """Test getting a non-existent key."""
    try:
        response = client.get("nonexistent_key_12345")
        value_is_none = response.get("value") is None
        exists_is_false = response.get("exists") is False
        ok = value_is_none and exists_is_false
        print_test("Get Non-existent Key", ok)
        return ok
    except Exception as e:
        print_test("Get Non-existent", False, str(e))
        return False


def test_delete_nonexistent(client: RedisLiteClient):
    """Test deleting a non-existent key."""
    try:
        response = client.delete("nonexistent_key_67890")
        deleted = response.get("deleted", False)
        ok = not deleted  # Should be False since key didn't exist
        print_test("Delete Non-existent Key", ok, "Correctly returned False")
        return ok
    except Exception as e:
        print_test("Delete Non-existent", False, str(e))
        return False


def run_tests(base_url: str = "http://localhost:8000"):
    """Run all tests."""
    print_section("RedisLite API Test Suite")
    print(f"Testing: {base_url}\n")
    
    try:
        client = RedisLiteClient(base_url)
    except Exception as e:
        print(f"✗ FATAL: Could not connect to API at {base_url}")
        print(f"  Error: {e}")
        print(f"\n  Make sure the API is running:")
        print(f"  $ uvicorn api.index:app --reload")
        return False
    
    results = []
    
    print_section("Basic Operations")
    results.append(test_health_check(client))
    results.append(test_set_get(client))
    results.append(test_set_get_complex(client))
    
    print_section("Key Management")
    results.append(test_exists(client))
    results.append(test_delete(client))
    results.append(test_overwrite(client))
    
    print_section("Edge Cases")
    results.append(test_nonexistent_get(client))
    results.append(test_delete_nonexistent(client))
    
    print_section("TTL Features")
    results.append(test_ttl_expiration(client))
    
    # Summary
    passed = sum(results)
    total = len(results)
    success_rate = (passed / total * 100) if total > 0 else 0
    
    print_section("Test Summary")
    print(f"  Total Tests: {total}")
    print(f"  Passed: {passed}")
    print(f"  Failed: {total - passed}")
    print(f"  Success Rate: {success_rate:.1f}%\n")
    
    if passed == total:
        print("  ✓ All tests passed! API is working correctly.\n")
        return True
    else:
        print(f"  ✗ {total - passed} test(s) failed. Please check the output above.\n")
        return False


if __name__ == "__main__":
    # Get base URL from command line argument or use default
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
    
    success = run_tests(base_url)
    sys.exit(0 if success else 1)
