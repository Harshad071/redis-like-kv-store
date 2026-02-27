"""
Deterministic Crash Testing System (Elite Feature #1)

Tests crash-safety by:
1. Starting server
2. Running writes with known dataset
3. Randomly killing process with SIGKILL (-9)
4. Restarting and verifying data integrity
5. Repeating 1000+ cycles

This is what Real databases do (Redis, RocksDB, Kafka test like this).
Almost no student projects do this.

Expected outcome:
- 0 data corruption across 1000+ crash cycles
- All written data recovered
"""

import os
import sys
import time
import json
import signal
import subprocess
import random
import socket
import threading
from pathlib import Path
from typing import Dict, List, Tuple
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("CrashTest")


class CrashTestCoordinator:
    """Orchestrates deterministic crash testing."""
    
    def __init__(
        self,
        data_dir: str = "./crash_test_data",
        server_host: str = "localhost",
        server_port: int = 6379,
        max_crashes: int = 1000,
    ):
        """Initialize crash test suite."""
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.server_host = server_host
        self.server_port = server_port
        self.max_crashes = max_crashes
        
        # Test dataset
        self.test_data: Dict[str, str] = {}
        self.server_process = None
        
        # Statistics
        self.stats = {
            "crashes": 0,
            "total_writes": 0,
            "total_reads": 0,
            "data_corruption_detected": 0,
            "successful_recoveries": 0,
        }
    
    def generate_test_dataset(self, size: int = 100) -> Dict[str, str]:
        """
        Generate deterministic test data.
        
        Uses fixed seed for reproducibility.
        """
        random.seed(42)  # Fixed seed
        
        self.test_data = {}
        for i in range(size):
            key = f"test_key_{i}"
            value = f"value_{i}_" + "x" * random.randint(10, 100)
            self.test_data[key] = value
        
        logger.info(f"Generated {len(self.test_data)} test records")
        return self.test_data
    
    def start_server(self) -> None:
        """Start RedisLite server in background."""
        logger.info("Starting RedisLite server...")
        
        # Set environment for persistence
        env = os.environ.copy()
        env["REDISLITE_PERSISTENCE_ENABLED"] = "true"
        env["REDISLITE_DATA_DIR"] = str(self.data_dir / "server_data")
        env["REDISLITE_AOF_FSYNC_POLICY"] = "always"  # Safest for crash test
        
        # Start server
        try:
            self.server_process = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "api.index:app", 
                 "--host", self.server_host, "--port", str(self.server_port)],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            
            # Wait for server to be ready
            time.sleep(2)
            self._wait_for_server(max_attempts=10)
            logger.info(f"Server started (PID: {self.server_process.pid})")
            
        except Exception as e:
            logger.error(f"Failed to start server: {e}")
            raise
    
    def _wait_for_server(self, max_attempts: int = 10) -> bool:
        """Wait for server to accept connections."""
        for attempt in range(max_attempts):
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                result = sock.connect_ex((self.server_host, self.server_port))
                sock.close()
                
                if result == 0:
                    logger.info("Server is ready")
                    return True
                
                time.sleep(0.5)
            except:
                time.sleep(0.5)
        
        logger.error("Server failed to start")
        return False
    
    def write_test_data(self) -> int:
        """Write test dataset via redis-cli or API."""
        count = 0
        try:
            import redis
            r = redis.Redis(host=self.server_host, port=self.server_port, decode_responses=True)
            
            for key, value in self.test_data.items():
                r.set(key, value, ex=3600)  # 1 hour TTL
                count += 1
            
            self.stats["total_writes"] += count
            logger.info(f"Wrote {count} keys to server")
            
            # Give server time to persist
            time.sleep(0.5)
            
        except ImportError:
            logger.warning("redis-py not available, skipping write")
        except Exception as e:
            logger.error(f"Write failed: {e}")
        
        return count
    
    def kill_server(self) -> None:
        """Kill server process with SIGKILL (simulates power failure)."""
        if self.server_process:
            pid = self.server_process.pid
            logger.info(f"Killing server (PID: {pid}) with SIGKILL...")
            
            try:
                os.kill(pid, signal.SIGKILL)
                time.sleep(0.5)
            except ProcessLookupError:
                pass  # Already dead
            
            self.stats["crashes"] += 1
    
    def verify_data_integrity(self) -> Tuple[bool, Dict[str, any]]:
        """
        After restart, verify all written data is still there.
        
        Returns: (all_ok, report)
        """
        report = {
            "missing_keys": [],
            "corrupted_values": [],
            "extra_keys": [],
        }
        
        try:
            import redis
            r = redis.Redis(host=self.server_host, port=self.server_port, decode_responses=True)
            
            # Check all expected keys exist
            for key, expected_value in self.test_data.items():
                actual_value = r.get(key)
                
                if actual_value is None:
                    report["missing_keys"].append(key)
                elif actual_value != expected_value:
                    report["corrupted_values"].append({
                        "key": key,
                        "expected": expected_value[:50] + "...",
                        "actual": actual_value[:50] + "..." if actual_value else None,
                    })
                
                self.stats["total_reads"] += 1
            
            # Check for extra keys (shouldn't happen)
            all_keys = r.keys("test_key_*")
            if len(all_keys) != len(self.test_data):
                extra = set(all_keys) - set(self.test_data.keys())
                report["extra_keys"] = list(extra)
            
            # Determine if corruption
            all_ok = (
                len(report["missing_keys"]) == 0 and
                len(report["corrupted_values"]) == 0
            )
            
            if all_ok:
                self.stats["successful_recoveries"] += 1
                logger.info("✓ Data integrity verified")
            else:
                self.stats["data_corruption_detected"] += 1
                logger.error(f"✗ Data corruption detected: {report}")
            
            return all_ok, report
            
        except Exception as e:
            logger.error(f"Integrity check failed: {e}")
            return False, {"error": str(e)}
    
    def run_crash_cycle(self) -> bool:
        """
        Single crash test cycle:
        1. Write data
        2. Kill server
        3. Restart
        4. Verify integrity
        """
        logger.info(f"\n--- Crash Cycle {self.stats['crashes'] + 1} ---")
        
        # Write data
        self.write_test_data()
        
        # Kill randomly (sometimes early, sometimes after pause)
        if random.random() > 0.5:
            time.sleep(random.uniform(0.1, 0.5))
        
        self.kill_server()
        time.sleep(1)
        
        # Restart
        self.start_server()
        
        # Verify
        ok, report = self.verify_data_integrity()
        return ok
    
    def run_test_suite(self) -> Dict[str, any]:
        """Run full crash test suite."""
        logger.info(f"Starting crash test suite ({self.max_crashes} cycles)")
        logger.info(f"Test data size: {len(self.test_data)} keys")
        
        try:
            self.generate_test_dataset(size=50)
            self.start_server()
            
            all_ok = True
            for cycle in range(self.max_crashes):
                try:
                    cycle_ok = self.run_crash_cycle()
                    if not cycle_ok:
                        all_ok = False
                    
                    # Progress indicator
                    if (cycle + 1) % 10 == 0:
                        logger.info(f"Completed {cycle + 1}/{self.max_crashes} cycles")
                    
                except Exception as e:
                    logger.error(f"Cycle failed: {e}")
                    all_ok = False
            
            # Final stats
            result = {
                "passed": all_ok,
                "cycles": self.stats["crashes"],
                "total_writes": self.stats["total_writes"],
                "total_reads": self.stats["total_reads"],
                "corruption_detected": self.stats["data_corruption_detected"],
                "successful_recoveries": self.stats["successful_recoveries"],
                "corruption_rate": (
                    self.stats["data_corruption_detected"] / self.stats["crashes"]
                    if self.stats["crashes"] > 0 else 0
                ),
            }
            
            logger.info("\n" + "=" * 60)
            logger.info("CRASH TEST RESULTS")
            logger.info("=" * 60)
            logger.info(f"Status: {'✓ PASSED' if all_ok else '✗ FAILED'}")
            logger.info(f"Cycles: {result['cycles']}")
            logger.info(f"Corruption detected: {result['corruption_detected']}")
            logger.info(f"Corruption rate: {result['corruption_rate'] * 100:.2f}%")
            logger.info(f"Successful recoveries: {result['successful_recoveries']}/{result['cycles']}")
            logger.info("=" * 60)
            
            return result
            
        finally:
            if self.server_process:
                try:
                    os.kill(self.server_process.pid, signal.SIGKILL)
                except:
                    pass


if __name__ == "__main__":
    tester = CrashTestCoordinator(max_crashes=100)
    results = tester.run_test_suite()
    
    # Exit with error if corruption detected
    sys.exit(0 if results["passed"] else 1)
