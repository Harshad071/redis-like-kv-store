"""
Issue #4: Accurate Memory Accounting

Tracks actual memory usage with sys.getsizeof() recursion.
Ensures maxmemory limits are enforced reliably.
"""

import sys
import logging
from typing import Any, Dict
from collections import abc

logger = logging.getLogger(__name__)


class MemoryTracker:
    """
    Tracks accurate memory usage of keys in RedisLite.
    
    Uses sys.getsizeof() with recursive measurement for:
    - String values
    - Numeric values
    - Complex objects (dicts, lists, etc.)
    
    Allows reliable enforcement of maxmemory limits.
    """
    
    PYTHON_OVERHEAD = 50  # Approximate overhead per object
    
    @staticmethod
    def get_size(obj: Any) -> int:
        """
        Get accurate size in bytes of a Python object.
        
        Recursively measures container types (dict, list, set, tuple).
        For strings, includes actual string data.
        For numbers, base size only.
        
        Args:
            obj: Python object to measure
            
        Returns:
            Size in bytes
        """
        size = sys.getsizeof(obj)
        
        if isinstance(obj, str):
            # String size includes the actual string data
            return size + len(obj.encode('utf-8'))
        elif isinstance(obj, dict):
            # Add size of all keys and values
            for key, value in obj.items():
                size += MemoryTracker.get_size(key)
                size += MemoryTracker.get_size(value)
        elif isinstance(obj, (list, tuple)):
            # Add size of all elements
            for item in obj:
                size += MemoryTracker.get_size(item)
        elif isinstance(obj, set):
            # Add size of all elements
            for item in obj:
                size += MemoryTracker.get_size(item)
        elif isinstance(obj, (int, float, bool)):
            # Numbers have fixed size, already counted by sys.getsizeof
            pass
        elif hasattr(obj, '__dict__'):
            # Object with attributes - recursively measure
            size += MemoryTracker.get_size(obj.__dict__)
        
        return size
    
    @staticmethod
    def get_key_memory(key: str, value: Any, ttl: Any = None) -> int:
        """
        Get total memory used by a key-value pair.
        
        Includes key, value, and TTL metadata.
        
        Args:
            key: Key name
            value: Value object
            ttl: TTL data (heap node, expiry, etc.)
            
        Returns:
            Total bytes used by this key-value pair
        """
        total = 0
        
        # Key size
        total += MemoryTracker.get_size(key)
        
        # Value size
        total += MemoryTracker.get_size(value)
        
        # TTL metadata (if present)
        if ttl is not None:
            total += MemoryTracker.get_size(ttl)
        
        # Overhead for dictionary entry, hash table, etc.
        total += MemoryTracker.PYTHON_OVERHEAD
        
        return total
    
    @staticmethod
    def calculate_total_memory(store: Dict[str, Dict[str, Any]]) -> int:
        """
        Calculate total memory used by all keys.
        
        Args:
            store: RedisLite store dictionary
            
        Returns:
            Total bytes used
        """
        total = 0
        for key, entry in store.items():
            value = entry.get('value')
            ttl_info = entry.get('ttl_info')
            total += MemoryTracker.get_key_memory(key, value, ttl_info)
        return total
    
    @staticmethod
    def memory_usage_stats(store: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """
        Get detailed memory statistics.
        
        Returns:
            Dict with memory stats in bytes and MB
        """
        total_bytes = MemoryTracker.calculate_total_memory(store)
        total_mb = total_bytes / (1024 * 1024)
        
        return {
            "total_bytes": total_bytes,
            "total_mb": round(total_mb, 2),
            "avg_per_key_bytes": int(total_bytes / len(store)) if store else 0,
            "keys_count": len(store),
        }


class HotKeyDetector:
    """
    Issue #9: Hot Key Detection
    
    Detects keys with high access frequency that become bottlenecks
    due to single-shard lock contention in lock striping.
    
    Tracks per-key access counts and suggests keys that exceed threshold.
    """
    
    def __init__(self, threshold_percentile: float = 99.0):
        """
        Initialize hot key detector.
        
        Args:
            threshold_percentile: Which percentile counts as "hot" (default 99th)
        """
        self.access_counts: Dict[str, int] = {}
        self.threshold_percentile = threshold_percentile
    
    def record_access(self, key: str) -> None:
        """Record an access to a key."""
        self.access_counts[key] = self.access_counts.get(key, 0) + 1
    
    def get_hot_keys(self, limit: int = 10) -> list:
        """
        Get the hottest keys by access count.
        
        Args:
            limit: Return top N keys
            
        Returns:
            List of (key, access_count) tuples
        """
        if not self.access_counts:
            return []
        
        sorted_keys = sorted(
            self.access_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )
        
        return sorted_keys[:limit]
    
    def get_percentile_threshold(self) -> int:
        """
        Get the access count threshold for the configured percentile.
        
        Example: if 99th percentile threshold is 10, keys with
        10+ accesses are considered "hot".
        
        Returns:
            Access count threshold
        """
        if not self.access_counts:
            return 0
        
        sorted_counts = sorted(self.access_counts.values())
        idx = int(len(sorted_counts) * (self.threshold_percentile / 100.0))
        return sorted_counts[min(idx, len(sorted_counts) - 1)]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get hot key detection statistics."""
        if not self.access_counts:
            return {"status": "no_data"}
        
        counts = list(self.access_counts.values())
        threshold = self.get_percentile_threshold()
        hot_keys = len([c for c in counts if c >= threshold])
        
        return {
            "total_unique_keys": len(self.access_counts),
            "total_accesses": sum(counts),
            f"percentile_{int(self.threshold_percentile)}_threshold": threshold,
            "hot_keys_detected": hot_keys,
            "top_10_hot_keys": self.get_hot_keys(10),
        }
    
    def reset(self) -> None:
        """Reset all counters."""
        self.access_counts.clear()
