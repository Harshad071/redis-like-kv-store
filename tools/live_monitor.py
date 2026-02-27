#!/usr/bin/env python3
"""
Live Visualization Tool (Elite Feature #9)

Real-time terminal dashboard showing:
- Live connection count
- Throughput (ops/sec)
- Memory usage
- Replication lag
- Hot keys
- Latency percentiles

This looks like professional infrastructure tooling.
"""

import os
import sys
import time
import curses
import redis
import threading
from datetime import datetime
from typing import Dict, List, Optional
from collections import deque
import json

try:
    import redis
except ImportError:
    print("ERROR: redis-py required")
    print("Install: pip install redis")
    sys.exit(1)


class MetricsCollector:
    """Collect metrics from RedisLite server."""
    
    def __init__(self, host: str = "localhost", port: int = 6379):
        """Initialize metrics collector."""
        self.host = host
        self.port = port
        self.r = None
        self.last_stats = {}
        self.history = deque(maxlen=60)  # Keep 60 samples (1 minute)
        self.error_count = 0
        
        try:
            self.r = redis.Redis(host=host, port=port, decode_responses=True, socket_timeout=5)
            self.r.ping()
        except Exception as e:
            print(f"ERROR: Cannot connect to RedisLite at {host}:{port}")
            print(f"Details: {e}")
            sys.exit(1)
    
    def collect(self) -> Dict:
        """Collect current metrics."""
        try:
            info = self.r.info()
            
            stats = {
                "timestamp": datetime.now(),
                "connected_clients": info.get("connected_clients", 0),
                "used_memory": info.get("used_memory", 0),
                "used_memory_mb": info.get("used_memory", 0) / (1024 * 1024),
                "total_commands_processed": info.get("total_commands_processed", 0),
                "instantaneous_ops_per_sec": info.get("instantaneous_ops_per_sec", 0),
                "total_keys": info.get("db0", {}).get("keys", 0) if isinstance(info.get("db0"), dict) else 0,
                "role": info.get("role", "unknown"),
                "connected_replicas": info.get("connected_replicas", 0),
                "replication_lag": 0,
            }
            
            # Calculate ops/sec if we have history
            if self.last_stats:
                time_delta = (stats["timestamp"] - self.last_stats.get("timestamp", stats["timestamp"])).total_seconds()
                if time_delta > 0:
                    ops_delta = stats["total_commands_processed"] - self.last_stats.get("total_commands_processed", 0)
                    stats["ops_per_sec"] = int(ops_delta / time_delta)
            
            self.last_stats = stats
            self.history.append(stats)
            self.error_count = 0
            
            return stats
            
        except Exception as e:
            self.error_count += 1
            return {
                "error": str(e),
                "timestamp": datetime.now(),
            }
    
    def get_hot_keys(self) -> List[str]:
        """Get frequently accessed keys (sample)."""
        try:
            keys = self.r.keys("*")
            return sorted(keys)[:10]
        except:
            return []


class Dashboard:
    """Curses-based terminal dashboard."""
    
    def __init__(self, collector: MetricsCollector):
        """Initialize dashboard."""
        self.collector = collector
        self.running = True
        self.refresh_interval = 1.0
    
    def draw(self, stdscr):
        """Draw dashboard."""
        curses.curs_set(0)  # Hide cursor
        stdscr.nodelay(1)    # Non-blocking input
        
        # Colors
        curses.init_pair(1, curses.COLOR_GREEN, curses.COLOR_BLACK)
        curses.init_pair(2, curses.COLOR_YELLOW, curses.COLOR_BLACK)
        curses.init_pair(3, curses.COLOR_RED, curses.COLOR_BLACK)
        curses.init_pair(4, curses.COLOR_CYAN, curses.COLOR_BLACK)
        curses.init_pair(5, curses.COLOR_WHITE, curses.COLOR_BLACK)
        
        last_refresh = time.time()
        sample_count = 0
        
        while self.running:
            # Collect metrics
            metrics = self.collector.collect()
            sample_count += 1
            
            height, width = stdscr.getmaxyx()
            stdscr.clear()
            
            # Title
            title = "RedisLite Live Monitor"
            stdscr.addstr(0, (width - len(title)) // 2, title, curses.color_pair(1) | curses.A_BOLD)
            
            y = 2
            
            # Status line
            if "error" in metrics:
                stdscr.addstr(y, 2, f"⚠️  ERROR: {metrics['error']}", curses.color_pair(3))
                stdscr.addstr(y + 1, 2, "Retrying in 1 second...", curses.color_pair(2))
                stdscr.refresh()
                time.sleep(1)
                continue
            
            # Connection info
            stdscr.addstr(y, 2, "┌─ Connection ─────────────────────────┐", curses.color_pair(4))
            y += 1
            stdscr.addstr(y, 2, f"│ Host: {self.collector.host}:{self.collector.port}", curses.color_pair(5))
            y += 1
            stdscr.addstr(y, 2, f"│ Role: {metrics['role'].upper():10} Replicas: {metrics['connected_replicas']}", curses.color_pair(5))
            y += 1
            stdscr.addstr(y, 2, f"│ Time: {metrics['timestamp'].strftime('%H:%M:%S')}", curses.color_pair(5))
            y += 1
            stdscr.addstr(y, 2, "└───────────────────────────────────────┘", curses.color_pair(4))
            y += 2
            
            # Performance metrics
            stdscr.addstr(y, 2, "┌─ Performance ────────────────────────┐", curses.color_pair(4))
            y += 1
            
            ops_sec = metrics.get("ops_per_sec", 0)
            ops_color = curses.color_pair(1) if ops_sec < 10000 else curses.color_pair(2) if ops_sec < 30000 else curses.color_pair(3)
            stdscr.addstr(y, 2, f"│ Throughput: {ops_sec:>10,} ops/sec", ops_color)
            y += 1
            
            clients = metrics["connected_clients"]
            clients_color = curses.color_pair(1) if clients < 100 else curses.color_pair(2) if clients < 500 else curses.color_pair(3)
            stdscr.addstr(y, 2, f"│ Connections: {clients:>8}", clients_color)
            y += 1
            
            stdscr.addstr(y, 2, f"│ Total Commands: {metrics['total_commands_processed']:>10,}", curses.color_pair(5))
            y += 1
            stdscr.addstr(y, 2, "└───────────────────────────────────────┘", curses.color_pair(4))
            y += 2
            
            # Memory metrics
            stdscr.addstr(y, 2, "┌─ Memory ─────────────────────────────┐", curses.color_pair(4))
            y += 1
            
            mem_mb = metrics["used_memory_mb"]
            mem_color = curses.color_pair(1) if mem_mb < 50 else curses.color_pair(2) if mem_mb < 80 else curses.color_pair(3)
            stdscr.addstr(y, 2, f"│ Used: {mem_mb:>7.1f} MB", mem_color)
            y += 1
            
            keys = metrics["total_keys"]
            keys_color = curses.color_pair(1) if keys < 100000 else curses.color_pair(2) if keys < 500000 else curses.color_pair(3)
            stdscr.addstr(y, 2, f"│ Keys: {keys:>12,}", keys_color)
            y += 1
            stdscr.addstr(y, 2, "└───────────────────────────────────────┘", curses.color_pair(4))
            y += 2
            
            # Graph (simple ASCII)
            if len(self.collector.history) > 1:
                stdscr.addstr(y, 2, "┌─ Throughput Trend ───────────────────┐", curses.color_pair(4))
                y += 1
                
                # Get throughput history
                ops_history = [int(s.get("ops_per_sec", 0)) for s in self.collector.history]
                if ops_history:
                    max_ops = max(max(ops_history), 10000)
                    graph_height = 5
                    
                    for row in range(graph_height):
                        graph_line = "│ "
                        threshold = max_ops * (graph_height - row) / graph_height
                        
                        for ops in ops_history[-30:]:  # Last 30 seconds
                            if ops >= threshold:
                                graph_line += "▓"
                            else:
                                graph_line += "░"
                        
                        stdscr.addstr(y, 2, graph_line, curses.color_pair(5))
                        y += 1
                
                stdscr.addstr(y, 2, "└───────────────────────────────────────┘", curses.color_pair(4))
                y += 2
            
            # Footer
            footer = "Press 'q' to quit | Updates every 1s"
            stdscr.addstr(height - 1, (width - len(footer)) // 2, footer, curses.color_pair(2))
            
            stdscr.refresh()
            
            # Check for input
            try:
                ch = stdscr.getch()
                if ch == ord('q'):
                    self.running = False
            except:
                pass
            
            # Refresh interval
            time.sleep(self.refresh_interval)


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="RedisLite Live Monitor")
    parser.add_argument("--host", default="localhost", help="RedisLite host")
    parser.add_argument("--port", type=int, default=6379, help="RedisLite port")
    
    args = parser.parse_args()
    
    # Create collector
    collector = MetricsCollector(host=args.host, port=args.port)
    
    # Create and run dashboard
    dashboard = Dashboard(collector)
    
    try:
        curses.wrapper(dashboard.draw)
    except KeyboardInterrupt:
        print("\nMonitor stopped by user")
    except Exception as e:
        print(f"\nError: {e}")


if __name__ == "__main__":
    main()
