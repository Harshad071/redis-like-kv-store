"""
RedisLite Replication - Master-Replica Architecture

Implements one-way replication from master to replicas:
- Master streams SET/DEL commands to all connected replicas
- Replicas apply commands in order, stay synchronized
- Read-only mode on replicas
- Automatic reconnection on network failure

Enables high availability and read scaling.
"""

import asyncio
import json
import logging
import time
import threading
from typing import Optional, List, Set
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class ReplicationCommand:
    """A command to be replicated to replicas."""
    id: int
    command: str  # "SET", "DEL"
    key: str
    value: Optional[str] = None
    ttl: Optional[int] = None
    timestamp: float = 0.0
    
    def to_json(self) -> str:
        """Serialize to JSON for transmission."""
        return json.dumps({
            "id": self.id,
            "command": self.command,
            "key": self.key,
            "value": self.value,
            "ttl": self.ttl,
            "timestamp": self.timestamp,
        })


class ReplicationMaster:
    """
    Master side of replication - streams commands to replicas.
    
    Responsibilities:
    - Accept replica connections
    - Stream SET/DEL commands to all connected replicas
    - Track replication offset
    - Handle replica disconnections
    """
    
    def __init__(self, redislite_store, listen_port: int = 6380):
        """
        Initialize replication master.
        
        Args:
            redislite_store: RedisLite instance
            listen_port: Port for replicas to connect to (default 6380)
        """
        self.store = redislite_store
        self.listen_port = listen_port
        
        # Replication state
        self.replication_id = "master_" + str(int(time.time() * 1000000))
        self.replication_offset = 0
        self.connected_replicas: Set[str] = set()
        self.replica_connections: Dict = {}
        
        # Command queue for replicas
        self.command_queue: List[ReplicationCommand] = []
        self.command_queue_lock = threading.RLock()
        self.command_id_counter = 0
        
        # Server
        self.server = None
        self._running = False
    
    async def handle_replica_connection(self, reader, writer):
        """
        Handle a replica connection.
        
        Replicas connect and receive all subsequent commands.
        """
        addr = writer.get_extra_info("peername")
        replica_id = f"replica_{addr[0]}_{addr[1]}"
        
        logger.info(f"Replica connected: {replica_id}")
        
        with self.command_queue_lock:
            self.connected_replicas.add(replica_id)
        
        try:
            while self._running:
                # Wait for next command in queue
                await asyncio.sleep(0.1)
                
                with self.command_queue_lock:
                    if self.command_queue:
                        for cmd in self.command_queue:
                            # Send command to this replica
                            try:
                                writer.write((cmd.to_json() + "\n").encode())
                                await writer.drain()
                                self.replication_offset += 1
                            except Exception as e:
                                logger.error(f"Error sending to {replica_id}: {e}")
                                raise
                        
                        # Commands sent, clear queue
                        self.command_queue.clear()
        
        except Exception as e:
            logger.error(f"Replica {replica_id} disconnected: {e}")
        finally:
            with self.command_queue_lock:
                self.connected_replicas.discard(replica_id)
            writer.close()
            await writer.wait_closed()
    
    async def start_server(self):
        """Start the replication server."""
        self._running = True
        self.server = await asyncio.start_server(
            self.handle_replica_connection,
            "0.0.0.0",
            self.listen_port
        )
        
        logger.info(f"Replication master listening on 0.0.0.0:{self.listen_port}")
        
        async with self.server:
            await self.server.serve_forever()
    
    def queue_command(self, command: str, key: str, value: Optional[str] = None, ttl: Optional[int] = None):
        """
        Queue a command for replication to replicas.
        
        Called on every SET/DEL operation.
        """
        with self.command_queue_lock:
            self.command_id_counter += 1
            cmd = ReplicationCommand(
                id=self.command_id_counter,
                command=command,
                key=key,
                value=value,
                ttl=ttl,
                timestamp=time.time()
            )
            self.command_queue.append(cmd)
    
    def get_info(self) -> dict:
        """Get replication info."""
        return {
            "role": "master",
            "replication_id": self.replication_id,
            "replication_offset": self.replication_offset,
            "connected_replicas": len(self.connected_replicas),
            "replica_ids": list(self.connected_replicas),
        }
    
    def stop(self):
        """Stop replication server."""
        self._running = False
        if self.server:
            self.server.close()


class ReplicationReplica:
    """
    Replica side of replication - receives commands from master.
    
    Responsibilities:
    - Connect to master
    - Receive and apply commands in order
    - Maintain read-only state
    - Automatic reconnection
    """
    
    def __init__(self, redislite_store, master_host: str, master_port: int = 6380):
        """
        Initialize replication replica.
        
        Args:
            redislite_store: RedisLite instance
            master_host: Master server hostname
            master_port: Master replication port
        """
        self.store = redislite_store
        self.master_host = master_host
        self.master_port = master_port
        
        # Replica state
        self.replication_offset = 0
        self.master_replication_id = None
        self.connected = False
        
        # Connection
        self.reader = None
        self.writer = None
        
        self._running = False
        self._connection_thread = None
    
    async def connect_to_master(self):
        """Connect to master and start receiving commands."""
        self._running = True
        
        while self._running:
            try:
                logger.info(f"Connecting to master at {self.master_host}:{self.master_port}")
                
                self.reader, self.writer = await asyncio.open_connection(
                    self.master_host,
                    self.master_port
                )
                
                self.connected = True
                logger.info("Connected to master, receiving commands...")
                
                await self._receive_commands()
                
            except Exception as e:
                logger.error(f"Connection error: {e}")
                self.connected = False
                
                # Exponential backoff
                await asyncio.sleep(5)
    
    async def _receive_commands(self):
        """Receive and apply commands from master."""
        try:
            while self._running and self.connected:
                # Read line from master
                data = await asyncio.wait_for(
                    self.reader.readuntil(b'\n'),
                    timeout=30.0
                )
                
                if not data:
                    break
                
                # Parse command
                try:
                    cmd_data = json.loads(data.decode().strip())
                    await self._apply_command(cmd_data)
                    self.replication_offset += 1
                except json.JSONDecodeError:
                    logger.warning(f"Invalid command from master: {data}")
        
        except asyncio.TimeoutError:
            logger.warning("Master connection timeout")
        except Exception as e:
            logger.error(f"Error receiving commands: {e}")
        finally:
            self.connected = False
            if self.writer:
                self.writer.close()
                await self.writer.wait_closed()
    
    async def _apply_command(self, cmd_data: dict):
        """
        Apply a replicated command.
        
        Executes command on local store.
        """
        command = cmd_data.get("command")
        key = cmd_data.get("key")
        value = cmd_data.get("value")
        ttl = cmd_data.get("ttl")
        
        try:
            if command == "SET":
                self.store.set(key, value, ttl=ttl)
            elif command == "DEL":
                self.store.delete(key)
            else:
                logger.warning(f"Unknown command: {command}")
        except Exception as e:
            logger.error(f"Error applying command {command} {key}: {e}")
    
    def get_info(self) -> dict:
        """Get replica info."""
        return {
            "role": "replica",
            "master_host": self.master_host,
            "master_port": self.master_port,
            "master_replication_id": self.master_replication_id,
            "replication_offset": self.replication_offset,
            "connected": self.connected,
        }
    
    def run(self):
        """Run replica in current event loop."""
        try:
            asyncio.run(self.connect_to_master())
        except KeyboardInterrupt:
            self._running = False
    
    def stop(self):
        """Stop replica."""
        self._running = False
        if self.writer:
            self.writer.close()


class ReplicationManager:
    """
    Manages replication for the cluster.
    
    Handles both master and replica roles.
    """
    
    def __init__(self, redislite_store, config):
        """
        Initialize replication manager.
        
        Args:
            redislite_store: RedisLite instance
            config: Configuration with replica_mode, replica_host, etc.
        """
        self.store = redislite_store
        self.config = config
        
        self.master = None
        self.replica = None
        
        if config.replica_mode == "master":
            self.master = ReplicationMaster(redislite_store)
        elif config.replica_mode == "replica":
            self.replica = ReplicationReplica(
                redislite_store,
                config.replica_host,
                config.replica_port
            )
    
    def log_command(self, command: str, key: str, value=None, ttl=None):
        """Log a command for replication."""
        if self.master:
            self.master.queue_command(command, key, value, ttl)
    
    def get_info(self) -> dict:
        """Get replication info."""
        if self.master:
            return self.master.get_info()
        elif self.replica:
            return self.replica.get_info()
        else:
            return {"role": "standalone"}
    
    def start(self):
        """Start replication services."""
        if self.master:
            # Run in background thread
            import threading
            self.master_thread = threading.Thread(
                target=lambda: asyncio.run(self.master.start_server()),
                daemon=True
            )
            self.master_thread.start()
        elif self.replica:
            # Run in background thread
            import threading
            self.replica_thread = threading.Thread(
                target=self.replica.run,
                daemon=True
            )
            self.replica_thread.start()
    
    def stop(self):
        """Stop replication services."""
        if self.master:
            self.master.stop()
        elif self.replica:
            self.replica.stop()
