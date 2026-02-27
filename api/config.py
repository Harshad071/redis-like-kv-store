"""
RedisLite Configuration Management

Environment-based configuration with validation and type checking.
Loads from .env file and environment variables.
"""

import os
from dataclasses import dataclass
from typing import Optional
from enum import Enum
from pathlib import Path


class EvictionPolicy(str, Enum):
    """Memory eviction policy options."""
    LRU = "lru"
    NONE = "none"


class LogLevel(str, Enum):
    """Logging level options."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class FsyncPolicy(str, Enum):
    """AOF fsync policy (Redis-compatible)."""
    ALWAYS = "always"      # fsync after every write (safest)
    EVERYSEC = "everysec"  # fsync every 1 second (default)
    NO = "no"              # let OS decide (fastest)


@dataclass
class RedisLiteConfig:
    """
    Complete RedisLite configuration.
    
    All values come from environment variables with sensible defaults.
    """
    
    # Server configuration
    tcp_port: int = 6379
    http_port: int = 8000
    host: str = "0.0.0.0"
    
    # Memory configuration
    max_memory_mb: int = 100
    max_keys: int = 1_000_000
    eviction_policy: EvictionPolicy = EvictionPolicy.LRU
    
    # TTL configuration
    ttl_check_interval_ms: int = 100  # How often to check expiration heap
    
    # Persistence configuration (crash-safe)
    persistence_enabled: bool = True
    data_dir: str = "./data"
    aof_fsync_policy: FsyncPolicy = FsyncPolicy.EVERYSEC  # "always", "everysec", "no"
    aof_fsync_interval_secs: float = 1.0
    snapshot_interval_secs: float = 30.0
    
    # Replication configuration
    replica_enabled: bool = False
    replica_mode: str = "master"  # "master" or "replica"
    replica_host: Optional[str] = None
    replica_port: int = 6379
    
    # Observability configuration
    log_level: LogLevel = LogLevel.INFO
    metrics_enabled: bool = True
    
    # Network & Backpressure (Issue #5 - prevent resource exhaustion)
    max_clients: int = 1000  # Max concurrent TCP connections
    max_client_buffer_mb: int = 10  # Max size per client buffer
    socket_keepalive: bool = True
    socket_keepalive_interval_sec: int = 300  # 5 minutes
    
    # Performance tuning
    lock_stripe_count: int = 16
    
    @classmethod
    def from_env(cls) -> "RedisLiteConfig":
        """
        Load configuration from environment variables.
        
        Environment variable names:
        - REDISLITE_TCP_PORT
        - REDISLITE_HTTP_PORT
        - REDISLITE_HOST
        - REDISLITE_MAX_MEMORY_MB
        - REDISLITE_MAX_KEYS
        - REDISLITE_EVICTION_POLICY
        - REDISLITE_TTL_CHECK_INTERVAL_MS
        - REDISLITE_PERSISTENCE_ENABLED
        - REDISLITE_DATA_DIR
        - REDISLITE_AOF_FSYNC_INTERVAL_SECS
        - REDISLITE_SNAPSHOT_INTERVAL_SECS
        - REDISLITE_REPLICA_ENABLED
        - REDISLITE_REPLICA_MODE
        - REDISLITE_REPLICA_HOST
        - REDISLITE_REPLICA_PORT
        - REDISLITE_LOG_LEVEL
        - REDISLITE_METRICS_ENABLED
        """
        
        def get_int(key: str, default: int) -> int:
            try:
                return int(os.getenv(f"REDISLITE_{key}", default))
            except ValueError:
                return default
        
        def get_float(key: str, default: float) -> float:
            try:
                return float(os.getenv(f"REDISLITE_{key}", default))
            except ValueError:
                return default
        
        def get_bool(key: str, default: bool) -> bool:
            value = os.getenv(f"REDISLITE_{key}", str(default)).lower()
            return value in ("true", "1", "yes", "on")
        
        def get_str(key: str, default: str) -> str:
            return os.getenv(f"REDISLITE_{key}", default)
        
        def get_enum(key: str, enum_cls, default):
            value = get_str(key, default.value)
            try:
                return enum_cls(value)
            except ValueError:
                return default
        
        return cls(
            tcp_port=get_int("TCP_PORT", 6379),
            http_port=get_int("HTTP_PORT", 8000),
            host=get_str("HOST", "0.0.0.0"),
            max_memory_mb=get_int("MAX_MEMORY_MB", 100),
            max_keys=get_int("MAX_KEYS", 1_000_000),
            eviction_policy=get_enum("EVICTION_POLICY", EvictionPolicy, EvictionPolicy.LRU),
            ttl_check_interval_ms=get_int("TTL_CHECK_INTERVAL_MS", 100),
            persistence_enabled=get_bool("PERSISTENCE_ENABLED", True),
            data_dir=get_str("DATA_DIR", "./data"),
            aof_fsync_policy=get_enum("AOF_FSYNC_POLICY", FsyncPolicy, FsyncPolicy.EVERYSEC),
            aof_fsync_interval_secs=get_float("AOF_FSYNC_INTERVAL_SECS", 1.0),
            snapshot_interval_secs=get_float("SNAPSHOT_INTERVAL_SECS", 30.0),
            replica_enabled=get_bool("REPLICA_ENABLED", False),
            replica_mode=get_str("REPLICA_MODE", "master"),
            replica_host=get_str("REPLICA_HOST", None) if get_str("REPLICA_HOST", "") else None,
            replica_port=get_int("REPLICA_PORT", 6379),
            log_level=get_enum("LOG_LEVEL", LogLevel, LogLevel.INFO),
            metrics_enabled=get_bool("METRICS_ENABLED", True),
            max_clients=get_int("MAX_CLIENTS", 1000),
            max_client_buffer_mb=get_int("MAX_CLIENT_BUFFER_MB", 10),
            socket_keepalive=get_bool("SOCKET_KEEPALIVE", True),
            socket_keepalive_interval_sec=get_int("SOCKET_KEEPALIVE_INTERVAL_SEC", 300),
            lock_stripe_count=get_int("LOCK_STRIPE_COUNT", 16),
        )
    
    def validate(self) -> bool:
        """
        Validate configuration values.
        
        Returns:
            True if valid, raises ValueError if invalid
        """
        if self.tcp_port < 1024 or self.tcp_port > 65535:
            raise ValueError(f"Invalid tcp_port: {self.tcp_port}")
        
        if self.http_port < 1024 or self.http_port > 65535:
            raise ValueError(f"Invalid http_port: {self.http_port}")
        
        if self.tcp_port == self.http_port:
            raise ValueError("tcp_port and http_port cannot be the same")
        
        if self.max_memory_mb < 10:
            raise ValueError(f"max_memory_mb too small: {self.max_memory_mb}")
        
        if self.max_keys < 1000:
            raise ValueError(f"max_keys too small: {self.max_keys}")
        
        if self.ttl_check_interval_ms < 10:
            raise ValueError(f"ttl_check_interval_ms too small: {self.ttl_check_interval_ms}")
        
        if self.aof_fsync_interval_secs < 0.1:
            raise ValueError(f"aof_fsync_interval_secs too small: {self.aof_fsync_interval_secs}")
        
        if self.snapshot_interval_secs < 1:
            raise ValueError(f"snapshot_interval_secs too small: {self.snapshot_interval_secs}")
        
        if self.replica_mode not in ("master", "replica"):
            raise ValueError(f"Invalid replica_mode: {self.replica_mode}")
        
        return True
    
    def to_dict(self) -> dict:
        """Convert configuration to dictionary."""
        return {
            "tcp_port": self.tcp_port,
            "http_port": self.http_port,
            "host": self.host,
            "max_memory_mb": self.max_memory_mb,
            "max_keys": self.max_keys,
            "eviction_policy": self.eviction_policy.value,
            "ttl_check_interval_ms": self.ttl_check_interval_ms,
            "persistence_enabled": self.persistence_enabled,
            "data_dir": self.data_dir,
            "aof_fsync_interval_secs": self.aof_fsync_interval_secs,
            "snapshot_interval_secs": self.snapshot_interval_secs,
            "replica_enabled": self.replica_enabled,
            "replica_mode": self.replica_mode,
            "replica_host": self.replica_host,
            "replica_port": self.replica_port,
            "log_level": self.log_level.value,
            "metrics_enabled": self.metrics_enabled,
            "lock_stripe_count": self.lock_stripe_count,
        }
    
    def __str__(self) -> str:
        """Pretty print configuration."""
        lines = ["RedisLite Configuration:"]
        for key, value in self.to_dict().items():
            lines.append(f"  {key}: {value}")
        return "\n".join(lines)


# Load default configuration
DEFAULT_CONFIG = RedisLiteConfig.from_env()
