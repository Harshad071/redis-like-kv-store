"""
RedisLite Observability & Metrics

Comprehensive metrics collection and Prometheus export for production monitoring:
- Command-level latency tracking
- Real-time throughput measurement
- Memory usage tracking
- Eviction and expiration stats
- Structured JSON logging
"""

import time
import threading
import logging
import json
from typing import Dict, Any, List, Optional
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime

# Setup structured logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


@dataclass
class CommandMetrics:
    """Metrics for a specific command type."""
    name: str
    count: int = 0
    total_latency_ms: float = 0.0
    min_latency_ms: float = float('inf')
    max_latency_ms: float = 0.0
    error_count: int = 0
    
    @property
    def avg_latency_ms(self) -> float:
        """Average latency in milliseconds."""
        if self.count == 0:
            return 0.0
        return self.total_latency_ms / self.count
    
    def record(self, latency_ms: float, error: bool = False):
        """Record a command execution."""
        self.count += 1
        self.total_latency_ms += latency_ms
        self.min_latency_ms = min(self.min_latency_ms, latency_ms)
        self.max_latency_ms = max(self.max_latency_ms, latency_ms)
        if error:
            self.error_count += 1
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON export."""
        return {
            "name": self.name,
            "count": self.count,
            "error_count": self.error_count,
            "avg_latency_ms": round(self.avg_latency_ms, 3),
            "min_latency_ms": round(self.min_latency_ms, 3) if self.min_latency_ms != float('inf') else 0,
            "max_latency_ms": round(self.max_latency_ms, 3),
        }


class MetricsCollector:
    """
    Centralized metrics collection and aggregation.
    
    Tracks:
    - Per-command latency (SET, GET, DEL, etc.)
    - Throughput (ops/sec)
    - Memory usage
    - Evictions and expirations
    - Error rates
    """
    
    def __init__(self):
        self.command_metrics: Dict[str, CommandMetrics] = {}
        self.metrics_lock = threading.RLock()
        
        # Time window for throughput calculation (last 60 seconds)
        self.throughput_window_secs = 60
        self.operation_timestamps: deque = deque()
        
        # System metrics
        self.start_time = time.time()
        self.total_connections = 0
        self.current_connections = 0
    
    def record_command(
        self,
        command_name: str,
        latency_ms: float,
        error: bool = False
    ) -> None:
        """
        Record a command execution.
        
        Args:
            command_name: Command name (SET, GET, DEL, etc.)
            latency_ms: Execution time in milliseconds
            error: Whether command resulted in error
        """
        with self.metrics_lock:
            if command_name not in self.command_metrics:
                self.command_metrics[command_name] = CommandMetrics(command_name)
            
            self.command_metrics[command_name].record(latency_ms, error)
            self.operation_timestamps.append(time.time())
            
            # Trim old timestamps
            current_time = time.time()
            while self.operation_timestamps and \
                  (current_time - self.operation_timestamps[0]) > self.throughput_window_secs:
                self.operation_timestamps.popleft()
    
    def get_throughput_ops_sec(self) -> float:
        """Get current throughput in operations per second."""
        with self.metrics_lock:
            if self.operation_timestamps:
                oldest_ts = self.operation_timestamps[0]
                newest_ts = self.operation_timestamps[-1] if self.operation_timestamps else time.time()
                time_diff = newest_ts - oldest_ts
                
                if time_diff > 0:
                    return len(self.operation_timestamps) / time_diff
        
        return 0.0
    
    def get_command_metrics(self, command: str = None) -> Dict[str, Any]:
        """
        Get metrics for a specific command or all commands.
        
        Args:
            command: Command name, or None for all
        
        Returns:
            Dictionary of command metrics
        """
        with self.metrics_lock:
            if command:
                if command in self.command_metrics:
                    return self.command_metrics[command].to_dict()
                return {}
            
            return {
                cmd: metrics.to_dict()
                for cmd, metrics in self.command_metrics.items()
            }
    
    def export_prometheus(self, redislite_store: Any) -> str:
        """
        Export metrics in Prometheus format.
        
        Args:
            redislite_store: RedisLite instance for current state
        
        Returns:
            Prometheus-format metrics string
        """
        info = redislite_store.info()
        throughput = self.get_throughput_ops_sec()
        uptime = time.time() - self.start_time
        
        prometheus_lines = [
            "# HELP redislite_info General server info",
            "# TYPE redislite_info gauge",
            f"redislite_info{{role=\"master\",version=\"1.0\"}} 1",
            "",
            "# HELP redislite_uptime_seconds Server uptime in seconds",
            "# TYPE redislite_uptime_seconds counter",
            f"redislite_uptime_seconds {uptime}",
            "",
            "# HELP redislite_keys_total Current number of keys",
            "# TYPE redislite_keys_total gauge",
            f"redislite_keys_total {info.get('keys', 0)}",
            "",
            "# HELP redislite_memory_bytes Memory usage in bytes",
            "# TYPE redislite_memory_bytes gauge",
            f"redislite_memory_bytes {info.get('memory_bytes', 0)}",
            "",
            "# HELP redislite_memory_max_bytes Maximum memory allowed",
            "# TYPE redislite_memory_max_bytes gauge",
            f"redislite_memory_max_bytes {info.get('max_memory_bytes', 0)}",
            "",
            "# HELP redislite_operations_total Total commands processed",
            "# TYPE redislite_operations_total counter",
            f"redislite_operations_total {info.get('operations_total', 0)}",
            "",
            "# HELP redislite_operations_per_sec Current throughput",
            "# TYPE redislite_operations_per_sec gauge",
            f"redislite_operations_per_sec {throughput:.2f}",
            "",
            "# HELP redislite_sets_total Total SET commands",
            "# TYPE redislite_sets_total counter",
            f"redislite_sets_total {info.get('sets_total', 0)}",
            "",
            "# HELP redislite_gets_total Total GET commands",
            "# TYPE redislite_gets_total counter",
            f"redislite_gets_total {info.get('gets_total', 0)}",
            "",
            "# HELP redislite_deletes_total Total DELETE commands",
            "# TYPE redislite_deletes_total counter",
            f"redislite_deletes_total {info.get('deletes_total', 0)}",
            "",
            "# HELP redislite_evictions_total Total keys evicted by LRU",
            "# TYPE redislite_evictions_total counter",
            f"redislite_evictions_total {info.get('evictions_total', 0)}",
            "",
            "# HELP redislite_expirations_total Total keys expired",
            "# TYPE redislite_expirations_total counter",
            f"redislite_expirations_total {info.get('expirations_total', 0)}",
            "",
        ]
        
        # Command-specific metrics
        with self.metrics_lock:
            for cmd_name, cmd_metrics in self.command_metrics.items():
                cmd_lower = cmd_name.lower()
                prometheus_lines.extend([
                    f"# HELP redislite_cmd_{cmd_lower}_count Total executions",
                    f"# TYPE redislite_cmd_{cmd_lower}_count counter",
                    f"redislite_cmd_{cmd_lower}_count {cmd_metrics.count}",
                    "",
                    f"# HELP redislite_cmd_{cmd_lower}_latency_ms Average latency",
                    f"# TYPE redislite_cmd_{cmd_lower}_latency_ms gauge",
                    f"redislite_cmd_{cmd_lower}_latency_ms {cmd_metrics.avg_latency_ms:.3f}",
                    "",
                ])
        
        return "\n".join(prometheus_lines)
    
    def export_json(self, redislite_store: Any) -> str:
        """
        Export metrics as JSON.
        
        Args:
            redislite_store: RedisLite instance
        
        Returns:
            JSON-formatted metrics
        """
        info = redislite_store.info()
        
        metrics_dict = {
            "timestamp": datetime.now().isoformat(),
            "uptime_seconds": time.time() - self.start_time,
            "store": info,
            "throughput": {
                "ops_per_sec": self.get_throughput_ops_sec(),
                "window_secs": self.throughput_window_secs,
            },
            "commands": self.get_command_metrics(),
        }
        
        return json.dumps(metrics_dict, indent=2)
    
    def reset_stats(self) -> None:
        """Reset all metrics."""
        with self.metrics_lock:
            self.command_metrics.clear()
            self.operation_timestamps.clear()


class StructuredLogger:
    """
    Structured JSON logging for production observability.
    
    Logs important events in JSON format for easy parsing by log aggregation.
    """
    
    def __init__(self, name: str = "redislite"):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)
    
    def log_command(
        self,
        command: str,
        key: str,
        status: str,
        latency_ms: float,
        details: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log a command execution.
        
        Args:
            command: Command name
            key: Key involved
            status: "success" or "error"
            latency_ms: Execution time
            details: Optional additional details
        """
        log_entry = {
            "event": "command_executed",
            "command": command,
            "key": key,
            "status": status,
            "latency_ms": round(latency_ms, 3),
            "timestamp": datetime.now().isoformat(),
        }
        
        if details:
            log_entry.update(details)
        
        self.logger.info(json.dumps(log_entry))
    
    def log_eviction(
        self,
        key: str,
        reason: str,
        memory_before_bytes: int,
        memory_after_bytes: int
    ) -> None:
        """Log a key eviction event."""
        log_entry = {
            "event": "key_evicted",
            "key": key,
            "reason": reason,
            "memory_before_bytes": memory_before_bytes,
            "memory_after_bytes": memory_after_bytes,
            "freed_bytes": memory_before_bytes - memory_after_bytes,
            "timestamp": datetime.now().isoformat(),
        }
        self.logger.warning(json.dumps(log_entry))
    
    def log_expiration(self, key_count: int) -> None:
        """Log batch expiration event."""
        log_entry = {
            "event": "keys_expired",
            "count": key_count,
            "timestamp": datetime.now().isoformat(),
        }
        self.logger.info(json.dumps(log_entry))
    
    def log_startup(self, config: Dict[str, Any]) -> None:
        """Log startup event."""
        log_entry = {
            "event": "server_started",
            "config": config,
            "timestamp": datetime.now().isoformat(),
        }
        self.logger.info(json.dumps(log_entry))
    
    def log_shutdown(self, reason: str, final_stats: Dict[str, Any]) -> None:
        """Log shutdown event."""
        log_entry = {
            "event": "server_shutdown",
            "reason": reason,
            "final_stats": final_stats,
            "timestamp": datetime.now().isoformat(),
        }
        self.logger.info(json.dumps(log_entry))
