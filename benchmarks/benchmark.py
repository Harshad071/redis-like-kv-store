"""
RedisLite Comprehensive Benchmarking Suite

Measures performance across multiple scenarios:
- Sequential operations (SET, GET)
- Concurrent client connections
- Large value handling
- TTL expiration under load
- Memory efficiency

Generates detailed performance reports for production validation.
"""

import sys
import time
import threading
import json
import statistics
from typing import List, Dict, Any, Callable
from dataclasses import dataclass, field, asdict
from pathlib import Path
import asyncio

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.redislite import RedisLite


@dataclass
class BenchmarkResult:
    """Single benchmark operation result."""
    name: str
    operation_count: int = 0
    total_time_ms: float = 0.0
    latencies_ms: List[float] = field(default_factory=list)
    throughput_ops_sec: float = 0.0
    error_count: int = 0
    
    @property
    def avg_latency_ms(self) -> float:
        return statistics.mean(self.latencies_ms) if self.latencies_ms else 0.0
    
    @property
    def p50_latency_ms(self) -> float:
        if len(self.latencies_ms) < 2:
            return 0.0
        return statistics.quantiles(self.latencies_ms, n=2)[0]
    
    @property
    def p95_latency_ms(self) -> float:
        if len(self.latencies_ms) < 20:
            return max(self.latencies_ms) if self.latencies_ms else 0.0
        return statistics.quantiles(self.latencies_ms, n=20)[18]
    
    @property
    def p99_latency_ms(self) -> float:
        if len(self.latencies_ms) < 100:
            return max(self.latencies_ms) if self.latencies_ms else 0.0
        return statistics.quantiles(self.latencies_ms, n=100)[98]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "operation_count": self.operation_count,
            "total_time_ms": round(self.total_time_ms, 2),
            "throughput_ops_sec": round(self.throughput_ops_sec, 2),
            "error_count": self.error_count,
            "latency_ms": {
                "avg": round(self.avg_latency_ms, 3),
                "p50": round(self.p50_latency_ms, 3),
                "p95": round(self.p95_latency_ms, 3),
                "p99": round(self.p99_latency_ms, 3),
                "min": round(min(self.latencies_ms), 3) if self.latencies_ms else 0,
                "max": round(max(self.latencies_ms), 3) if self.latencies_ms else 0,
            }
        }


class BenchmarkSuite:
    """
    Comprehensive benchmark suite for RedisLite.
    
    Tests various scenarios to validate production readiness:
    - Sequential performance
    - Concurrent performance
    - Memory efficiency
    - TTL under load
    """
    
    def __init__(self, output_file: str = "benchmark_results.json"):
        self.store = None
        self.results: List[BenchmarkResult] = []
        self.output_file = output_file
    
    def setup(self) -> None:
        """Setup store for benchmarking."""
        self.store = RedisLite(max_memory_mb=500, eviction_policy="lru")
        self.store.flushdb()
    
    def teardown(self) -> None:
        """Cleanup after benchmarking."""
        if self.store:
            self.store.shutdown()
    
    def _time_operation(self, operation: Callable[[], Any]) -> float:
        """Time a single operation in milliseconds."""
        start = time.perf_counter()
        operation()
        end = time.perf_counter()
        return (end - start) * 1000.0
    
    def benchmark_sequential_set(self, count: int = 100_000) -> BenchmarkResult:
        """Benchmark sequential SET operations."""
        print(f"Benchmarking sequential SET ({count} ops)...")
        
        result = BenchmarkResult(name="Sequential SET")
        start = time.perf_counter()
        
        for i in range(count):
            try:
                latency = self._time_operation(
                    lambda i=i: self.store.set(f"key_{i}", f"value_{i}")
                )
                result.latencies_ms.append(latency)
                result.operation_count += 1
            except Exception as e:
                result.error_count += 1
        
        end = time.perf_counter()
        result.total_time_ms = (end - start) * 1000
        result.throughput_ops_sec = count / (end - start) if (end - start) > 0 else 0
        
        return result
    
    def benchmark_sequential_get(self, count: int = 100_000) -> BenchmarkResult:
        """Benchmark sequential GET operations."""
        print(f"Benchmarking sequential GET ({count} ops)...")
        
        # Populate with keys first
        for i in range(min(count, 10_000)):
            self.store.set(f"key_{i}", f"value_{i}")
        
        result = BenchmarkResult(name="Sequential GET")
        start = time.perf_counter()
        
        for i in range(count):
            try:
                key_idx = i % min(count, 10_000)
                latency = self._time_operation(
                    lambda: self.store.get(f"key_{key_idx}")
                )
                result.latencies_ms.append(latency)
                result.operation_count += 1
            except Exception as e:
                result.error_count += 1
        
        end = time.perf_counter()
        result.total_time_ms = (end - start) * 1000
        result.throughput_ops_sec = count / (end - start) if (end - start) > 0 else 0
        
        return result
    
    def benchmark_mixed_workload(self, count: int = 100_000) -> BenchmarkResult:
        """Benchmark mixed SET/GET/DEL workload (50% SET, 30% GET, 20% DEL)."""
        print(f"Benchmarking mixed workload ({count} ops)...")
        
        result = BenchmarkResult(name="Mixed Workload (50% SET, 30% GET, 20% DEL)")
        start = time.perf_counter()
        
        for i in range(count):
            try:
                rand_op = (i * 7) % 100  # Pseudo-random
                
                if rand_op < 50:  # SET
                    latency = self._time_operation(
                        lambda i=i: self.store.set(f"key_{i}", f"value_{i}")
                    )
                elif rand_op < 80:  # GET
                    latency = self._time_operation(
                        lambda i=i: self.store.get(f"key_{i}")
                    )
                else:  # DEL
                    latency = self._time_operation(
                        lambda i=i: self.store.delete(f"key_{max(0, i-1000)}")
                    )
                
                result.latencies_ms.append(latency)
                result.operation_count += 1
            except Exception as e:
                result.error_count += 1
        
        end = time.perf_counter()
        result.total_time_ms = (end - start) * 1000
        result.throughput_ops_sec = count / (end - start) if (end - start) > 0 else 0
        
        return result
    
    def benchmark_concurrent_clients(self, num_clients: int = 100, ops_per_client: int = 1_000) -> BenchmarkResult:
        """Benchmark concurrent client connections."""
        print(f"Benchmarking {num_clients} concurrent clients ({ops_per_client} ops each)...")
        
        result = BenchmarkResult(name=f"Concurrent Clients ({num_clients})")
        
        client_results = []
        client_lock = threading.Lock()
        
        def client_worker(client_id: int):
            for i in range(ops_per_client):
                try:
                    latency = self._time_operation(
                        lambda: self.store.set(
                            f"client_{client_id}_key_{i}",
                            f"value_{i}"
                        )
                    )
                    with client_lock:
                        client_results.append(latency)
                except:
                    pass
        
        start = time.perf_counter()
        
        threads = []
        for client_id in range(num_clients):
            t = threading.Thread(target=client_worker, args=(client_id,))
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()
        
        end = time.perf_counter()
        
        result.latencies_ms = client_results
        result.operation_count = len(client_results)
        result.total_time_ms = (end - start) * 1000
        result.throughput_ops_sec = (num_clients * ops_per_client) / (end - start) if (end - start) > 0 else 0
        
        return result
    
    def benchmark_large_values(self, value_size_kb: int = 100, count: int = 1_000) -> BenchmarkResult:
        """Benchmark handling of large values."""
        print(f"Benchmarking large values ({value_size_kb}KB, {count} ops)...")
        
        large_value = "x" * (value_size_kb * 1024)
        result = BenchmarkResult(name=f"Large Values ({value_size_kb}KB)")
        
        start = time.perf_counter()
        
        for i in range(count):
            try:
                latency = self._time_operation(
                    lambda i=i: self.store.set(f"large_key_{i}", large_value)
                )
                result.latencies_ms.append(latency)
                result.operation_count += 1
            except Exception as e:
                result.error_count += 1
        
        end = time.perf_counter()
        result.total_time_ms = (end - start) * 1000
        result.throughput_ops_sec = count / (end - start) if (end - start) > 0 else 0
        
        return result
    
    def benchmark_ttl_expiration(self, count: int = 10_000) -> BenchmarkResult:
        """Benchmark TTL expiration under load."""
        print(f"Benchmarking TTL expiration ({count} ops)...")
        
        result = BenchmarkResult(name="TTL Expiration")
        
        start = time.perf_counter()
        
        # Set keys with TTL
        for i in range(count):
            try:
                latency = self._time_operation(
                    lambda i=i: self.store.set(f"ttl_key_{i}", f"value_{i}", ttl=5)
                )
                result.latencies_ms.append(latency)
                result.operation_count += 1
            except Exception as e:
                result.error_count += 1
        
        # Wait for expiration
        print("Waiting for keys to expire...")
        time.sleep(6)
        
        # Verify expiration
        remaining = self.store.dbsize()
        end = time.perf_counter()
        
        result.total_time_ms = (end - start) * 1000
        result.throughput_ops_sec = count / (end - start) if (end - start) > 0 else 0
        
        print(f"  Keys remaining after expiration: {remaining} (should be near 0)")
        
        return result
    
    def benchmark_memory_efficiency(self, num_keys: int = 100_000) -> BenchmarkResult:
        """Benchmark memory usage efficiency."""
        print(f"Benchmarking memory efficiency ({num_keys} keys)...")
        
        result = BenchmarkResult(name="Memory Efficiency")
        
        start = time.perf_counter()
        
        for i in range(num_keys):
            self.store.set(f"mem_key_{i}", f"value_{i}" * 10)
        
        end = time.perf_counter()
        
        info = self.store.info()
        memory_bytes = info.get("memory_bytes", 0)
        memory_per_key = memory_bytes / num_keys if num_keys > 0 else 0
        
        result.operation_count = num_keys
        result.total_time_ms = (end - start) * 1000
        result.throughput_ops_sec = num_keys / (end - start) if (end - start) > 0 else 0
        
        print(f"  Total memory: {memory_bytes / (1024*1024):.2f}MB")
        print(f"  Per-key average: {memory_per_key:.1f} bytes")
        
        return result
    
    def run_all(self) -> None:
        """Run complete benchmark suite."""
        print("=" * 60)
        print("RedisLite Comprehensive Benchmark Suite")
        print("=" * 60)
        print()
        
        self.setup()
        
        try:
            # Run benchmarks
            self.results.append(self.benchmark_sequential_set(100_000))
            print()
            
            self.store.flushdb()
            self.results.append(self.benchmark_sequential_get(100_000))
            print()
            
            self.store.flushdb()
            self.results.append(self.benchmark_mixed_workload(100_000))
            print()
            
            self.store.flushdb()
            self.results.append(self.benchmark_concurrent_clients(100, 1_000))
            print()
            
            self.store.flushdb()
            self.results.append(self.benchmark_large_values(100, 1_000))
            print()
            
            self.store.flushdb()
            self.results.append(self.benchmark_ttl_expiration(10_000))
            print()
            
            self.store.flushdb()
            self.results.append(self.benchmark_memory_efficiency(100_000))
            print()
            
        finally:
            self.teardown()
        
        # Print summary
        self._print_summary()
        self._save_results()
    
    def _print_summary(self) -> None:
        """Print benchmark summary."""
        print()
        print("=" * 60)
        print("Benchmark Results Summary")
        print("=" * 60)
        print()
        
        for result in self.results:
            print(f"Test: {result.name}")
            print(f"  Operations: {result.operation_count:,}")
            print(f"  Total Time: {result.total_time_ms:.2f}ms")
            print(f"  Throughput: {result.throughput_ops_sec:,.0f} ops/sec")
            print(f"  Latency (avg): {result.avg_latency_ms:.3f}ms")
            print(f"  Latency (p50): {result.p50_latency_ms:.3f}ms")
            print(f"  Latency (p95): {result.p95_latency_ms:.3f}ms")
            print(f"  Latency (p99): {result.p99_latency_ms:.3f}ms")
            if result.error_count > 0:
                print(f"  Errors: {result.error_count}")
            print()
    
    def _save_results(self) -> None:
        """Save results to JSON file."""
        output_data = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "results": [r.to_dict() for r in self.results],
            "summary": {
                "total_tests": len(self.results),
                "total_operations": sum(r.operation_count for r in self.results),
                "average_throughput_ops_sec": statistics.mean(
                    [r.throughput_ops_sec for r in self.results if r.throughput_ops_sec > 0]
                ) if any(r.throughput_ops_sec > 0 for r in self.results) else 0,
            }
        }
        
        with open(self.output_file, "w") as f:
            json.dump(output_data, f, indent=2)
        
        print(f"Results saved to {self.output_file}")


if __name__ == "__main__":
    suite = BenchmarkSuite()
    suite.run_all()
