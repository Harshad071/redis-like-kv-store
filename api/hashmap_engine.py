"""
HashMapEngine - Default Storage Backend

Implements the StorageEngine interface with high-performance HashMap.
This is the current production engine for RedisLite.
"""

import heapq
import sys
import threading
import time
from collections import OrderedDict
from typing import Any, Optional, Tuple, Dict, List
import fnmatch

from api.storage_engine import StorageEngine, LatencyBreakdown, LatencyCollector


class HashMapEngine(StorageEngine):
    """
    High-performance HashMap storage engine with:
    - Lock striping (16 independent locks)
    - Min-heap TTL expiration (O(log n))
    - LRU eviction with OrderedDict
    - Fine-grained latency measurement
    """
    
    LOCK_STRIPE_COUNT = 16
    
    def __init__(
        self,
        max_memory_mb: int = 100,
        eviction_policy: str = "lru",
        ttl_check_interval_ms: int = 100
    ):
        """Initialize HashMap engine with memory limits."""
        self.max_memory_bytes = max_memory_mb * 1024 * 1024
        self.eviction_policy = eviction_policy
        self.ttl_check_interval_ms = ttl_check_interval_ms / 1000.0
        
        # Sharded data storage
        self._data: List[Dict[str, Any]] = [{} for _ in range(self.LOCK_STRIPE_COUNT)]
        self._expiry: List[Dict[str, float]] = [{} for _ in range(self.LOCK_STRIPE_COUNT)]
        self._access_times: List[OrderedDict] = [
            OrderedDict() for _ in range(self.LOCK_STRIPE_COUNT)
        ]
        
        # Lock striping
        self._locks: List[threading.RLock] = [
            threading.RLock() for _ in range(self.LOCK_STRIPE_COUNT)
        ]
        
        # Min-heap for TTL expiration
        self._expiry_heap: List[Tuple[float, str, int]] = []
        self._heap_lock = threading.RLock()
        
        # Monotonic clock baseline
        self._monotonic_base = time.monotonic()
        self._system_time_base = time.time()
        
        # Statistics
        self._stats = {
            "sets": 0,
            "gets": 0,
            "deletes": 0,
            "evictions": 0,
            "expirations": 0,
            "memory_bytes": 0,
        }
        self._stats_lock = threading.RLock()
        
        # Latency collector
        self._latency_collector = LatencyCollector()
        
        # Background threads
        self._running = False
        self._ttl_daemon: Optional[threading.Thread] = None
        self._start_daemon()
    
    def _get_shard(self, key: str) -> int:
        """Get shard ID for key using hash."""
        return hash(key) % self.LOCK_STRIPE_COUNT
    
    def _measure_time_us(self, start: float) -> float:
        """Convert time difference to microseconds."""
        return (time.monotonic() - start) * 1_000_000
    
    def _get_monotonic_ttl(self, ttl_sec: Optional[float]) -> Optional[float]:
        """Convert TTL to monotonic clock timestamp."""
        if ttl_sec is None:
            return None
        return time.monotonic() + ttl_sec
    
    def set(self, key: str, value: Any, ttl_sec: Optional[float] = None) -> LatencyBreakdown:
        """Set key with optional TTL."""
        breakdown = LatencyBreakdown()
        start_total = time.monotonic()
        
        shard_id = self._get_shard(key)
        lock = self._locks[shard_id]
        
        # Measure lock wait time
        lock_start = time.monotonic()
        with lock:
            breakdown.lock_wait_us = self._measure_time_us(lock_start)
            
            # Measure memory update
            mem_start = time.monotonic()
            
            # LRU tracking
            self._access_times[shard_id][key] = time.monotonic()
            self._access_times[shard_id].move_to_end(key)
            
            # Store data
            self._data[shard_id][key] = value
            
            breakdown.memory_update_us = self._measure_time_us(mem_start)
            
            # Handle TTL
            if ttl_sec is not None:
                ttl_monotonic = self._get_monotonic_ttl(ttl_sec)
                self._expiry[shard_id][key] = ttl_monotonic
                
                with self._heap_lock:
                    heapq.heappush(self._expiry_heap, (ttl_monotonic, key, shard_id))
            else:
                self._expiry[shard_id].pop(key, None)
            
            # Check if eviction needed
            if self._stats["memory_bytes"] > self.max_memory_bytes and self.eviction_policy == "lru":
                evict_start = time.monotonic()
                self._evict_lru()
                breakdown.eviction_us = self._measure_time_us(evict_start)
            
            with self._stats_lock:
                self._stats["sets"] += 1
                self._stats["memory_bytes"] = sum(
                    sys.getsizeof(v) for shard in self._data for v in shard.values()
                )
        
        breakdown.total_us = self._measure_time_us(start_total)
        self._latency_collector.record("set", breakdown.total_us)
        return breakdown
    
    def get(self, key: str) -> Tuple[Optional[Any], LatencyBreakdown]:
        """Get key value."""
        breakdown = LatencyBreakdown()
        start_total = time.monotonic()
        
        shard_id = self._get_shard(key)
        lock = self._locks[shard_id]
        
        lock_start = time.monotonic()
        with lock:
            breakdown.lock_wait_us = self._measure_time_us(lock_start)
            
            mem_start = time.monotonic()
            
            # Check expiration
            if key in self._expiry[shard_id]:
                if time.monotonic() >= self._expiry[shard_id][key]:
                    # Expired
                    self._data[shard_id].pop(key, None)
                    self._expiry[shard_id].pop(key, None)
                    self._access_times[shard_id].pop(key, None)
                    
                    with self._stats_lock:
                        self._stats["expirations"] += 1
                    
                    breakdown.memory_update_us = self._measure_time_us(mem_start)
                    breakdown.total_us = self._measure_time_us(start_total)
                    self._latency_collector.record("get", breakdown.total_us)
                    return None, breakdown
            
            # Update LRU
            if key in self._access_times[shard_id]:
                self._access_times[shard_id].move_to_end(key)
            
            value = self._data[shard_id].get(key)
            
            breakdown.memory_update_us = self._measure_time_us(mem_start)
            
            with self._stats_lock:
                self._stats["gets"] += 1
        
        breakdown.total_us = self._measure_time_us(start_total)
        self._latency_collector.record("get", breakdown.total_us)
        return value, breakdown
    
    def delete(self, key: str) -> Tuple[bool, LatencyBreakdown]:
        """Delete key."""
        breakdown = LatencyBreakdown()
        start_total = time.monotonic()
        
        shard_id = self._get_shard(key)
        lock = self._locks[shard_id]
        
        lock_start = time.monotonic()
        with lock:
            breakdown.lock_wait_us = self._measure_time_us(lock_start)
            
            mem_start = time.monotonic()
            
            existed = key in self._data[shard_id]
            self._data[shard_id].pop(key, None)
            self._expiry[shard_id].pop(key, None)
            self._access_times[shard_id].pop(key, None)
            
            breakdown.memory_update_us = self._measure_time_us(mem_start)
            
            with self._stats_lock:
                self._stats["deletes"] += 1
        
        breakdown.total_us = self._measure_time_us(start_total)
        self._latency_collector.record("delete", breakdown.total_us)
        return existed, breakdown
    
    def exists(self, key: str) -> Tuple[bool, LatencyBreakdown]:
        """Check if key exists."""
        breakdown = LatencyBreakdown()
        start_total = time.monotonic()
        
        shard_id = self._get_shard(key)
        lock = self._locks[shard_id]
        
        lock_start = time.monotonic()
        with lock:
            breakdown.lock_wait_us = self._measure_time_us(lock_start)
            
            mem_start = time.monotonic()
            
            exists = key in self._data[shard_id]
            
            # Check expiration
            if exists and key in self._expiry[shard_id]:
                if time.monotonic() >= self._expiry[shard_id][key]:
                    self._data[shard_id].pop(key, None)
                    self._expiry[shard_id].pop(key, None)
                    exists = False
            
            breakdown.memory_update_us = self._measure_time_us(mem_start)
        
        breakdown.total_us = self._measure_time_us(start_total)
        self._latency_collector.record("exists", breakdown.total_us)
        return exists, breakdown
    
    def expire(self, key: str, ttl_sec: float) -> Tuple[bool, LatencyBreakdown]:
        """Set expiration on key."""
        breakdown = LatencyBreakdown()
        start_total = time.monotonic()
        
        shard_id = self._get_shard(key)
        lock = self._locks[shard_id]
        
        lock_start = time.monotonic()
        with lock:
            breakdown.lock_wait_us = self._measure_time_us(lock_start)
            
            mem_start = time.monotonic()
            
            if key not in self._data[shard_id]:
                breakdown.memory_update_us = self._measure_time_us(mem_start)
                breakdown.total_us = self._measure_time_us(start_total)
                self._latency_collector.record("expire", breakdown.total_us)
                return False, breakdown
            
            ttl_monotonic = self._get_monotonic_ttl(ttl_sec)
            self._expiry[shard_id][key] = ttl_monotonic
            
            with self._heap_lock:
                heapq.heappush(self._expiry_heap, (ttl_monotonic, key, shard_id))
            
            breakdown.memory_update_us = self._measure_time_us(mem_start)
        
        breakdown.total_us = self._measure_time_us(start_total)
        self._latency_collector.record("expire", breakdown.total_us)
        return True, breakdown
    
    def ttl(self, key: str) -> Tuple[Optional[float], LatencyBreakdown]:
        """Get TTL in seconds."""
        breakdown = LatencyBreakdown()
        start_total = time.monotonic()
        
        shard_id = self._get_shard(key)
        lock = self._locks[shard_id]
        
        lock_start = time.monotonic()
        with lock:
            breakdown.lock_wait_us = self._measure_time_us(lock_start)
            
            mem_start = time.monotonic()
            
            if key not in self._data[shard_id]:
                result = None  # -2 = key doesn't exist
            elif key not in self._expiry[shard_id]:
                result = -1.0  # No TTL
            else:
                ttl_remaining = self._expiry[shard_id][key] - time.monotonic()
                result = max(0.0, ttl_remaining)
            
            breakdown.memory_update_us = self._measure_time_us(mem_start)
        
        breakdown.total_us = self._measure_time_us(start_total)
        self._latency_collector.record("ttl", breakdown.total_us)
        return result, breakdown
    
    def keys(self, pattern: str = "*") -> Tuple[List[str], LatencyBreakdown]:
        """Scan keys matching pattern."""
        breakdown = LatencyBreakdown()
        start_total = time.monotonic()
        
        mem_start = time.monotonic()
        
        result = []
        current_time = time.monotonic()
        
        for shard_id in range(self.LOCK_STRIPE_COUNT):
            with self._locks[shard_id]:
                for key in list(self._data[shard_id].keys()):
                    # Skip expired keys
                    if key in self._expiry[shard_id]:
                        if current_time >= self._expiry[shard_id][key]:
                            continue
                    
                    if fnmatch.fnmatch(key, pattern):
                        result.append(key)
        
        breakdown.memory_update_us = self._measure_time_us(mem_start)
        breakdown.total_us = self._measure_time_us(start_total)
        self._latency_collector.record("keys", breakdown.total_us)
        return result, breakdown
    
    def dbsize(self) -> Tuple[int, LatencyBreakdown]:
        """Get total keys."""
        breakdown = LatencyBreakdown()
        start_total = time.monotonic()
        
        mem_start = time.monotonic()
        
        count = 0
        for shard_id in range(self.LOCK_STRIPE_COUNT):
            with self._locks[shard_id]:
                count += len(self._data[shard_id])
        
        breakdown.memory_update_us = self._measure_time_us(mem_start)
        breakdown.total_us = self._measure_time_us(start_total)
        self._latency_collector.record("dbsize", breakdown.total_us)
        return count, breakdown
    
    def flush(self) -> LatencyBreakdown:
        """Clear all data."""
        breakdown = LatencyBreakdown()
        start_total = time.monotonic()
        
        mem_start = time.monotonic()
        
        for shard_id in range(self.LOCK_STRIPE_COUNT):
            with self._locks[shard_id]:
                self._data[shard_id].clear()
                self._expiry[shard_id].clear()
                self._access_times[shard_id].clear()
        
        with self._heap_lock:
            self._expiry_heap.clear()
        
        breakdown.memory_update_us = self._measure_time_us(mem_start)
        breakdown.total_us = self._measure_time_us(start_total)
        return breakdown
    
    def memory_usage(self) -> int:
        """Get estimated memory usage."""
        total = 0
        for shard_id in range(self.LOCK_STRIPE_COUNT):
            with self._locks[shard_id]:
                for value in self._data[shard_id].values():
                    total += sys.getsizeof(value)
        return total
    
    def get_stats(self) -> Dict[str, Any]:
        """Get engine statistics."""
        with self._stats_lock:
            return {
                **self._stats,
                "memory_mb": self._stats["memory_bytes"] / (1024 * 1024),
            }
    
    def get_latency_stats(self) -> Dict[str, Dict[str, float]]:
        """Get latency percentiles."""
        return self._latency_collector.get_stats()
    
    def _evict_lru(self) -> None:
        """Evict least recently used key."""
        for shard_id in range(self.LOCK_STRIPE_COUNT):
            if self._access_times[shard_id]:
                # Get oldest key
                oldest_key = next(iter(self._access_times[shard_id]))
                self._data[shard_id].pop(oldest_key, None)
                self._expiry[shard_id].pop(oldest_key, None)
                self._access_times[shard_id].pop(oldest_key, None)
                
                with self._stats_lock:
                    self._stats["evictions"] += 1
                break
    
    def _cleanup_expired(self) -> None:
        """Background daemon to clean up expired keys."""
        current_time = time.monotonic()
        cleaned = 0
        
        with self._heap_lock:
            while self._expiry_heap and self._expiry_heap[0][0] <= current_time:
                exp_time, key, shard_id = heapq.heappop(self._expiry_heap)
                
                # Verify in shard (might have been deleted)
                with self._locks[shard_id]:
                    if key in self._data[shard_id] and self._expiry[shard_id].get(key) == exp_time:
                        self._data[shard_id].pop(key, None)
                        self._expiry[shard_id].pop(key, None)
                        cleaned += 1
        
        return cleaned
    
    def _ttl_daemon_loop(self) -> None:
        """Background thread for TTL expiration."""
        while self._running:
            self._cleanup_expired()
            time.sleep(self.ttl_check_interval_ms)
    
    def _start_daemon(self) -> None:
        """Start background daemon threads."""
        self._running = True
        self._ttl_daemon = threading.Thread(target=self._ttl_daemon_loop, daemon=True)
        self._ttl_daemon.start()
    
    def shutdown(self) -> None:
        """Gracefully shutdown engine."""
        self._running = False
        if self._ttl_daemon:
            self._ttl_daemon.join(timeout=5)
