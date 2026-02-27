"""
Issue #10: SlowLog Implementation

Redis-compatible slowlog that records operations exceeding latency threshold.
Enables profiling and performance debugging in production.
"""

import time
import logging
from typing import Any, Dict, List, Optional
from collections import deque
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class CommandType(str, Enum):
    """Types of commands that can be logged."""
    GET = "get"
    SET = "set"
    DEL = "del"
    EXPIRE = "expire"
    KEYS = "keys"
    FLUSHDB = "flushdb"
    OTHER = "other"


@dataclass
class SlowLogEntry:
    """A single entry in the slowlog."""
    id: int
    timestamp: float  # Unix timestamp
    duration_us: int  # Duration in microseconds
    command: str  # "GET", "SET", etc.
    key: Optional[str]  # Key being operated on
    client_addr: str = "internal"  # Client IP:port
    args: Optional[Dict[str, Any]] = None  # Additional arguments
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "duration_us": self.duration_us,
            "duration_ms": round(self.duration_us / 1000, 3),
            "command": self.command,
            "key": self.key,
            "client": self.client_addr,
            "args": self.args,
        }


class SlowLog:
    """
    Records operations that exceed slowlog_microseconds threshold.
    
    Similar to Redis SLOWLOG, helps identify performance bottlenecks
    and slow queries in production.
    """
    
    def __init__(self, max_entries: int = 128, threshold_us: int = 10000):
        """
        Initialize slowlog.
        
        Args:
            max_entries: Maximum slowlog entries to keep (default 128)
            threshold_us: Log operations taking > this many microseconds (default 10ms)
        """
        self.max_entries = max_entries
        self.threshold_us = threshold_us
        self.entries: deque = deque(maxlen=max_entries)
        self.entry_id_counter = 0
        self.stats = {
            "total_slow_operations": 0,
            "threshold_us": threshold_us,
        }
    
    def record(
        self,
        command: str,
        key: Optional[str],
        duration_us: int,
        client_addr: str = "internal",
        args: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Record an operation if it exceeds slowlog threshold.
        
        Args:
            command: Command name ("GET", "SET", "DEL", etc.)
            key: Key being operated on (if applicable)
            duration_us: Operation duration in microseconds
            client_addr: Client IP:port
            args: Optional additional arguments
        """
        if duration_us < self.threshold_us:
            return  # Don't log fast operations
        
        self.entry_id_counter += 1
        entry = SlowLogEntry(
            id=self.entry_id_counter,
            timestamp=time.time(),
            duration_us=duration_us,
            command=command,
            key=key,
            client_addr=client_addr,
            args=args,
        )
        
        self.entries.append(entry)
        self.stats["total_slow_operations"] += 1
        
        # Log to stderr for monitoring systems to pick up
        logger.warning(
            f"SlowLog: {command} {key or ''} took {duration_us/1000:.2f}ms "
            f"(threshold: {self.threshold_us/1000:.2f}ms)"
        )
    
    def get_entries(self, count: int = 10) -> List[Dict[str, Any]]:
        """
        Get recent slowlog entries.
        
        Args:
            count: Number of most recent entries to return
            
        Returns:
            List of slowlog entries as dicts
        """
        # Return most recent entries (deque is FIFO, so reverse to get newest first)
        return [
            entry.to_dict()
            for entry in list(self.entries)[-count:][::-1]
        ]
    
    def clear(self) -> None:
        """Clear all slowlog entries."""
        self.entries.clear()
        logger.info("Slowlog cleared")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get slowlog statistics."""
        if not self.entries:
            return {
                **self.stats,
                "entries_count": 0,
                "slowest_operation_us": 0,
                "average_duration_us": 0,
            }
        
        durations = [e.duration_us for e in self.entries]
        return {
            **self.stats,
            "entries_count": len(self.entries),
            "slowest_operation_us": max(durations),
            "average_duration_us": int(sum(durations) / len(durations)),
            "slowest_command": max(self.entries, key=lambda e: e.duration_us).command,
        }
    
    def set_threshold(self, threshold_us: int) -> None:
        """Dynamically update the slowlog threshold."""
        self.threshold_us = threshold_us
        self.stats["threshold_us"] = threshold_us
        logger.info(f"SlowLog threshold updated to {threshold_us}us ({threshold_us/1000:.2f}ms)")


class OperationTimer:
    """
    Context manager for timing operations to slowlog.
    
    Usage:
        with OperationTimer(slowlog, "GET", "mykey") as timer:
            # do operation
            pass
    """
    
    def __init__(
        self,
        slowlog: Optional[SlowLog],
        command: str,
        key: Optional[str] = None,
        client_addr: str = "internal"
    ):
        self.slowlog = slowlog
        self.command = command
        self.key = key
        self.client_addr = client_addr
        self.start_time = None
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time is None:
            return
        
        duration_us = int((time.time() - self.start_time) * 1_000_000)
        
        if self.slowlog:
            self.slowlog.record(
                self.command,
                self.key,
                duration_us,
                self.client_addr
            )
