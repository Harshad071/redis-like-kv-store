"""
RedisLite - A Redis-like in-memory key-value store with TTL support.

This module provides a thread-safe in-memory key-value store with support
for time-to-live (TTL) expiration and a background daemon for automatic
key expiration.
"""

import threading
import time
from typing import Any, Optional


class RedisLite:
    """
    A Redis-like in-memory key-value store with TTL and background expiration.
    
    This class implements a thread-safe key-value store supporting basic
    operations (set, get, delete, exists) with optional TTL (time-to-live)
    support. A background daemon thread runs every second to automatically
    remove expired keys.
    
    Attributes:
        _data: Internal dictionary storing key-value pairs.
        _expiry: Internal dictionary storing expiration times for keys with TTL.
        _lock: Threading lock for ensuring thread-safe operations.
        _daemon_thread: Background thread for expiration checking.
        _running: Flag to control the daemon thread lifecycle.
    
    Example:
        >>> store = RedisLite()
        >>> store.set("key", "value")
        >>> store.get("key")
        'value'
        >>> store.set("temp", "data", ttl=5)
        >>> store.exists("temp")
        True
    """
    
    def __init__(self) -> None:
        """Initialize the RedisLite store with empty data structures and start daemon."""
        self._data: dict[str, Any] = {}
        self._expiry: dict[str, float] = {}
        self._lock = threading.Lock()
        self._running = False
        self._daemon_thread: Optional[threading.Thread] = None
        self._start_daemon()
    
    def _start_daemon(self) -> None:
        """Start the background daemon thread for key expiration."""
        self._running = True
        self._daemon_thread = threading.Thread(
            target=self._expiration_loop,
            name="RedisLite-Daemon",
            daemon=True
        )
        self._daemon_thread.start()
    
    def _expiration_loop(self) -> None:
        """
        Background loop that runs every second to remove expired keys.
        
        This method runs in a separate daemon thread and continuously checks
        for keys that have exceeded their TTL, removing them from the store.
        """
        while self._running:
            self._remove_expired_keys()
            time.sleep(1.0)
    
    def _remove_expired_keys(self) -> None:
        """Remove all keys that have expired based on their TTL."""
        current_time = time.time()
        with self._lock:
            expired_keys = [
                key for key, expiry_time in self._expiry.items()
                if expiry_time <= current_time
            ]
            for key in expired_keys:
                del self._data[key]
                del self._expiry[key]
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """
        Set a key-value pair in the store with optional TTL.
        
        Args:
            key: The key to store. Must be a string.
            value: The value to store. Can be any serializable Python object.
            ttl: Optional time-to-live in seconds. If provided, the key will
                 automatically expire after this many seconds.
        
        Example:
            >>> store.set("username", "john")
            >>> store.set("session", "data", ttl=3600)
        """
        with self._lock:
            self._data[key] = value
            if ttl is not None:
                self._expiry[key] = time.time() + ttl
            elif key in self._expiry:
                del self._expiry[key]
    
    def get(self, key: str) -> Optional[Any]:
        """
        Retrieve a value by key.
        
        If the key has expired, it will be removed and None will be returned.
        
        Args:
            key: The key to retrieve.
        
        Returns:
            The stored value if key exists and hasn't expired, None otherwise.
        
        Example:
            >>> store.get("username")
            'john'
            >>> store.get("nonexistent")
            None
        """
        with self._lock:
            if key not in self._data:
                return None
            
            if key in self._expiry:
                if time.time() >= self._expiry[key]:
                    del self._data[key]
                    del self._expiry[key]
                    return None
            
            return self._data[key]
    
    def delete(self, key: str) -> bool:
        """
        Delete a key from the store.
        
        Args:
            key: The key to delete.
        
        Returns:
            True if the key was deleted, False if the key didn't exist.
        
        Example:
            >>> store.delete("username")
            True
            >>> store.delete("nonexistent")
            False
        """
        with self._lock:
            if key in self._data:
                del self._data[key]
                if key in self._expiry:
                    del self._expiry[key]
                return True
            return False
    
    def exists(self, key: str) -> bool:
        """
        Check if a key exists and hasn't expired.
        
        Args:
            key: The key to check.
        
        Returns:
            True if the key exists and hasn't expired, False otherwise.
        
        Example:
            >>> store.exists("username")
            True
            >>> store.exists("nonexistent")
            False
        """
        with self._lock:
            if key not in self._data:
                return False
            
            if key in self._expiry:
                if time.time() >= self._expiry[key]:
                    del self._data[key]
                    del self._expiry[key]
                    return False
            
            return True
    
    def shutdown(self) -> None:
        """
        Shutdown the background daemon thread.
        
        This method stops the expiration daemon and waits for it to finish.
        Should be called when the store is no longer needed.
        
        Example:
            >>> store.shutdown()
        """
        self._running = False
        if self._daemon_thread is not None:
            self._daemon_thread.join(timeout=2.0)
    
    def __enter__(self) -> "RedisLite":
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - ensures daemon is shutdown."""
        self.shutdown()
    
    def __del__(self) -> None:
        """Destructor - ensures daemon is shutdown."""
        try:
            self.shutdown()
        except Exception:
            pass
