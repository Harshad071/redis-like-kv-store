"""
Storage Engine Abstraction - Elite Database Architecture

This separates protocol handling from storage implementation, allowing:
- Multiple storage backends (HashMap, BTree, LSM)
- Storage engine substitution for testing
- Clear interface contracts
- Future-proof extensibility

This is how real databases are structured.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional, Dict, List, Tuple
import threading
import time


@dataclass
class LatencyBreakdown:
    """Measure latency at each stage of write path (Elite profiling)."""
    parse_us: float = 0.0        # RESP parsing
    lock_wait_us: float = 0.0    # Waiting for lock
    memory_update_us: float = 0.0  # Actual data structure update
    eviction_us: float = 0.0     # LRU eviction if needed
    wal_write_us: float = 0.0    # WAL append
    fsync_us: float = 0.0        # fsync operation
    replication_us: float = 0.0  # Replication queue
    total_us: float = 0.0        # Total wall-clock time
    
    def to_dict(self) -> Dict[str, float]:
        """Export latency breakdown for monitoring."""
        return {
            "parse_µs": self.parse_us,
            "lock_wait_µs": self.lock_wait_us,
            "memory_update_µs": self.memory_update_us,
            "eviction_µs": self.eviction_us,
            "wal_write_µs": self.wal_write_us,
            "fsync_µs": self.fsync_us,
            "replication_µs": self.replication_us,
            "total_µs": self.total_us,
        }


class StorageEngine(ABC):
    """
    Abstract storage engine interface.
    
    Implementations can be:
    - HashMapEngine (current, fastest, no ordering)
    - BTreeEngine (future, ordered iteration)
    - LSMEngine (future, better write performance)
    
    This is the boundary between protocol and storage.
    """
    
    @abstractmethod
    def set(self, key: str, value: Any, ttl_sec: Optional[float] = None) -> LatencyBreakdown:
        """Set key with optional TTL. Returns latency breakdown."""
        pass
    
    @abstractmethod
    def get(self, key: str) -> Tuple[Optional[Any], LatencyBreakdown]:
        """Get key value. Returns (value, latency_breakdown)."""
        pass
    
    @abstractmethod
    def delete(self, key: str) -> Tuple[bool, LatencyBreakdown]:
        """Delete key. Returns (existed, latency_breakdown)."""
        pass
    
    @abstractmethod
    def exists(self, key: str) -> Tuple[bool, LatencyBreakdown]:
        """Check if key exists. Returns (exists, latency_breakdown)."""
        pass
    
    @abstractmethod
    def expire(self, key: str, ttl_sec: float) -> Tuple[bool, LatencyBreakdown]:
        """Set expiration on key. Returns (existed, latency_breakdown)."""
        pass
    
    @abstractmethod
    def ttl(self, key: str) -> Tuple[Optional[float], LatencyBreakdown]:
        """Get TTL in seconds. Returns (-1=no ttl, -2=not exists, latency_breakdown)."""
        pass
    
    @abstractmethod
    def keys(self, pattern: str = "*") -> Tuple[List[str], LatencyBreakdown]:
        """Scan keys matching pattern. Returns (keys, latency_breakdown)."""
        pass
    
    @abstractmethod
    def dbsize(self) -> Tuple[int, LatencyBreakdown]:
        """Get total keys. Returns (count, latency_breakdown)."""
        pass
    
    @abstractmethod
    def flush(self) -> LatencyBreakdown:
        """Clear all data. Returns latency_breakdown."""
        pass
    
    @abstractmethod
    def memory_usage(self) -> int:
        """Get estimated memory usage in bytes."""
        pass
    
    @abstractmethod
    def get_stats(self) -> Dict[str, Any]:
        """Get engine statistics."""
        pass
    
    @abstractmethod
    def get_latency_stats(self) -> Dict[str, Dict[str, float]]:
        """Get P50/P95/P99 latency for each operation."""
        pass


class LatencyCollector:
    """Thread-safe latency statistics collector (elite monitoring)."""
    
    def __init__(self, window_size: int = 1000):
        """Track last N operations per command type."""
        self.window_size = window_size
        self._latencies: Dict[str, List[float]] = {
            "set": [],
            "get": [],
            "delete": [],
            "exists": [],
            "expire": [],
            "ttl": [],
            "keys": [],
            "dbsize": [],
        }
        self._lock = threading.Lock()
    
    def record(self, operation: str, latency_us: float) -> None:
        """Record operation latency in microseconds."""
        with self._lock:
            if operation not in self._latencies:
                self._latencies[operation] = []
            
            self._latencies[operation].append(latency_us)
            
            # Keep only last window_size entries
            if len(self._latencies[operation]) > self.window_size:
                self._latencies[operation].pop(0)
    
    def get_stats(self) -> Dict[str, Dict[str, float]]:
        """Get P50/P95/P99 percentiles for each operation."""
        with self._lock:
            result = {}
            for op, latencies in self._latencies.items():
                if not latencies:
                    continue
                
                sorted_latencies = sorted(latencies)
                count = len(sorted_latencies)
                
                result[op] = {
                    "count": count,
                    "min": sorted_latencies[0],
                    "p50": sorted_latencies[count // 2],
                    "p95": sorted_latencies[int(count * 0.95)],
                    "p99": sorted_latencies[int(count * 0.99)],
                    "max": sorted_latencies[-1],
                    "avg": sum(latencies) / count,
                }
            
            return result
