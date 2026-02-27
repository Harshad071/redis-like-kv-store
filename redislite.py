"""
RedisLite - A Redis-like in-memory key-value store with TTL support.

This module provides backwards compatibility for the original single-file
implementation. New code should use the 'redislite' package instead:

    from redislite import RedisLite

This module imports from the redislite package to maintain backwards
compatibility with existing code.
"""

# Backwards compatibility - import from the new package
from redislite import RedisLite

# Export exception classes for backwards compatibility
from redislite import (
    RedisLiteError,
    KeyNotFoundError,
    InvalidKeyError,
    InvalidTTLError,
    StoreClosedError,
)

__version__ = "1.0.0"

__all__ = [
    "RedisLite",
    "RedisLiteError",
    "KeyNotFoundError",
    "InvalidKeyError", 
    "InvalidTTLError",
    "StoreClosedError",
]
