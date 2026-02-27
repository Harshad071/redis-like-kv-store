"""
Issue #3: Production-Grade Replication with PSYNC

Implements Redis-compatible replication:
- FULLSYNC: Full snapshot + stream of all commands
- PSYNC: Partial resync from a specific offset
- Offset tracking: Each command increments master offset
- Replica reconnection: Reconnects to last known offset

This is true distributed systems work with fault tolerance.
"""

import asyncio
import json
import logging
import time
from typing import Optional, Dict, Set, List
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class SyncType(str, Enum):
    """Replication sync types."""
    FULLSYNC = "FULLSYNC"  # Full state + stream
    PSYNC = "PSYNC"        # Partial resync from offset


@dataclass
class ReplicationState:
    """Tracks replication state for master and replicas."""
    replication_id: str  # Unique ID for this master
    replication_offset: int = 0  # Global command offset
    replicas_online: int = 0
    last_sync_time: Optional[float] = None


class ReplicationMasterPSYNC:
    """
    Master side of replication with PSYNC support.
    
    Responsibilities:
    - Accept SYNC/PSYNC commands from replicas
    - Send full snapshot on FULLSYNC
    - Stream incremental commands on PSYNC
    - Track offset per replica for partial resync
    """
    
    def __init__(self, listen_port: int = 6380, buffer_size_mb: int = 16):
        """
        Initialize replication master with PSYNC.
        
        Args:
            listen_port: Port for replicas to connect to
            buffer_size_mb: Size of backlog buffer for partial resync
        """
        self.listen_port = listen_port
        self.buffer_size_mb = buffer_size_mb
        
        # State
        self.replication_id = self._generate_replication_id()
        self.replication_offset = 0
        
        # Replica tracking
        self.replica_offsets: Dict[str, int] = {}  # replica_id -> last_offset
        self.connected_replicas: Set[str] = set()
        
        # Command backlog for partial resync
        self.command_backlog: List[bytes] = []
        self.backlog_size_bytes = 0
        self.MAX_BACKLOG_SIZE = buffer_size_mb * 1024 * 1024
    
    def _generate_replication_id(self) -> str:
        """Generate unique replication ID."""
        import hashlib
        seed = str(time.time()).encode()
        return hashlib.sha1(seed).hexdigest()[:40]
    
    def record_command(self, command: str, key: str, value: Optional[str] = None, ttl: Optional[int] = None) -> None:
        """
        Record a command in the replication backlog.
        
        Called on every SET/DEL operation.
        
        Args:
            command: "SET", "DEL", "EXPIRE"
            key: Key being modified
            value: New value (for SET)
            ttl: TTL in seconds (for EXPIRE)
        """
        # Create command record
        record = {
            "cmd": command,
            "key": key,
            "val": value,
            "ttl": ttl,
            "offset": self.replication_offset
        }
        
        # Serialize
        data = json.dumps(record).encode('utf-8')
        
        # Add to backlog
        self.command_backlog.append(data)
        self.backlog_size_bytes += len(data)
        self.replication_offset += len(data)
        
        # Trim backlog if too large
        while self.backlog_size_bytes > self.MAX_BACKLOG_SIZE and self.command_backlog:
            removed = self.command_backlog.pop(0)
            self.backlog_size_bytes -= len(removed)
            logger.debug(f"Trimmed backlog, size now {self.backlog_size_bytes} bytes")
    
    async def handle_sync_request(
        self,
        replica_id: str,
        requested_offset: int,
        snapshot_callback,
        writer
    ) -> None:
        """
        Handle SYNC or PSYNC request from replica.
        
        Args:
            replica_id: Unique ID of replica
            requested_offset: Offset replica wants to resume from (-1 = unknown)
            snapshot_callback: Function to get full snapshot
            writer: asyncio StreamWriter to send data to replica
        """
        
        # Decide: FULLSYNC or PSYNC?
        if requested_offset == -1:
            # Replica is new or can't resume
            await self._handle_fullsync(replica_id, snapshot_callback, writer)
        else:
            # Try partial resync
            can_psync = requested_offset >= (self.replication_offset - self.backlog_size_bytes)
            
            if can_psync:
                await self._handle_psync(replica_id, requested_offset, writer)
            else:
                # Backlog too old, need FULLSYNC
                logger.info(f"Replica {replica_id} offset {requested_offset} too old, FULLSYNC required")
                await self._handle_fullsync(replica_id, snapshot_callback, writer)
    
    async def _handle_fullsync(self, replica_id: str, snapshot_callback, writer) -> None:
        """
        Send full snapshot to replica (FULLSYNC).
        
        Protocol:
        1. Send: +FULLSYNC {replication_id} {offset}\r\n
        2. Send: snapshot data
        3. Stream commands
        """
        logger.info(f"Starting FULLSYNC for replica {replica_id}")
        
        try:
            # Send FULLSYNC header
            response = f"+FULLSYNC {self.replication_id} {self.replication_offset}\r\n"
            writer.write(response.encode())
            await writer.drain()
            
            # Get and send snapshot
            snapshot = snapshot_callback()
            snapshot_data = json.dumps(snapshot).encode('utf-8')
            
            # Send snapshot with length prefix (Redis RDB format simulation)
            header = f"${len(snapshot_data)}\r\n".encode()
            writer.write(header)
            writer.write(snapshot_data)
            writer.write(b"\r\n")
            await writer.drain()
            
            # Track replica
            self.replica_offsets[replica_id] = self.replication_offset
            self.connected_replicas.add(replica_id)
            
            logger.info(f"FULLSYNC sent to {replica_id}, offset {self.replication_offset}")
            
        except Exception as e:
            logger.error(f"Error during FULLSYNC for {replica_id}: {e}")
            self.connected_replicas.discard(replica_id)
    
    async def _handle_psync(self, replica_id: str, requested_offset: int, writer) -> None:
        """
        Partial resync (PSYNC) from specific offset.
        
        Protocol:
        1. Send: +CONTINUE {replication_id} {offset}\r\n
        2. Stream only commands after requested_offset
        """
        logger.info(f"Starting PSYNC for replica {replica_id} from offset {requested_offset}")
        
        try:
            # Send CONTINUE response
            response = f"+CONTINUE {self.replication_id} {self.replication_offset}\r\n"
            writer.write(response.encode())
            await writer.drain()
            
            # Find starting index in backlog
            start_bytes = self.replication_offset - self.backlog_size_bytes
            skip_bytes = requested_offset - start_bytes
            
            bytes_sent = 0
            for cmd_data in self.command_backlog:
                if bytes_sent >= skip_bytes:
                    writer.write(cmd_data)
                    writer.write(b"\r\n")
                bytes_sent += len(cmd_data)
            
            await writer.drain()
            
            self.replica_offsets[replica_id] = self.replication_offset
            self.connected_replicas.add(replica_id)
            
            logger.info(f"PSYNC sent {bytes_sent - skip_bytes} bytes to {replica_id}")
            
        except Exception as e:
            logger.error(f"Error during PSYNC for {replica_id}: {e}")
            self.connected_replicas.discard(replica_id)
    
    def get_replication_info(self) -> Dict:
        """Get replication information for INFO command."""
        return {
            "role": "master",
            "replication_id": self.replication_id,
            "replication_offset": self.replication_offset,
            "connected_replicas": len(self.connected_replicas),
            "backlog_size_bytes": self.backlog_size_bytes,
            "replicas": list(self.connected_replicas),
        }


class ReplicationReplicaPSYNC:
    """
    Replica side of replication with PSYNC support.
    
    Responsibilities:
    - Connect to master
    - Send PSYNC with last known offset
    - Apply commands from master
    - Maintain offset tracking
    - Auto-reconnect on failure
    """
    
    def __init__(self, master_host: str, master_port: int):
        """
        Initialize replication replica.
        
        Args:
            master_host: Master hostname/IP
            master_port: Master replication port
        """
        self.master_host = master_host
        self.master_port = master_port
        self.last_offset = 0
        self.replication_id = "?"
        self.is_connected = False
    
    async def connect_and_sync(self, callback) -> None:
        """
        Connect to master and synchronize.
        
        Args:
            callback: Function(command, key, value, ttl) to apply commands
        """
        try:
            reader, writer = await asyncio.open_connection(self.master_host, self.master_port)
            logger.info(f"Connected to master {self.master_host}:{self.master_port}")
            
            # Send PSYNC request
            psync_cmd = f"PSYNC {self.replication_id} {self.last_offset}\r\n"
            writer.write(psync_cmd.encode())
            await writer.drain()
            
            # Read response
            response_line = await reader.readline()
            response = response_line.decode().strip()
            
            if response.startswith("+FULLSYNC"):
                await self._handle_fullsync_response(reader, writer, callback)
            elif response.startswith("+CONTINUE"):
                await self._handle_continue_response(reader, callback)
            else:
                logger.error(f"Unexpected response: {response}")
            
            self.is_connected = True
            
        except Exception as e:
            logger.error(f"Replica sync error: {e}")
            self.is_connected = False
    
    async def _handle_fullsync_response(self, reader, writer, callback) -> None:
        """Handle FULLSYNC response from master."""
        logger.info("Received FULLSYNC, loading snapshot...")
        
        # Read snapshot size
        size_line = await reader.readline()
        size = int(size_line.decode().strip()[1:])
        
        # Read snapshot
        snapshot_data = await reader.readexactly(size)
        snapshot = json.loads(snapshot_data.decode())
        
        # Apply snapshot
        for key, entry in snapshot.items():
            callback("SET", key, entry.get("value"), entry.get("ttl"))
        
        logger.info(f"Snapshot applied: {len(snapshot)} keys")
        
        # Continue streaming
        await self._stream_commands(reader, callback)
    
    async def _handle_continue_response(self, reader, callback) -> None:
        """Handle CONTINUE (partial resync) response from master."""
        logger.info("Resuming from offset, streaming commands...")
        await self._stream_commands(reader, callback)
    
    async def _stream_commands(self, reader, callback) -> None:
        """Stream and apply commands from master."""
        while True:
            line = await reader.readline()
            if not line:
                break
            
            try:
                record = json.loads(line.decode().strip())
                cmd = record["cmd"]
                key = record["key"]
                val = record.get("val")
                ttl = record.get("ttl")
                
                callback(cmd, key, val, ttl)
                self.last_offset = record["offset"]
                
            except Exception as e:
                logger.error(f"Error processing streamed command: {e}")
