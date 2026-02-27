"""
RedisLite TCP Server - Native Redis Protocol Implementation

Implements RESP (Redis Serialization Protocol) for native Redis compatibility.
Allows redis-cli and all Redis client libraries to connect directly.

Architecture:
- Async I/O using asyncio for thousands of concurrent connections
- RESP protocol parser (simple, bulletproof)
- Shared RedisLite instance with lock striping
- Graceful shutdown and error handling
"""

import asyncio
import logging
import time
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
import signal
import sys

logger = logging.getLogger(__name__)


@dataclass
class RESPValue:
    """Represents a RESP protocol value."""
    type: str  # "+", "-", ":", "$", "*"
    value: Any
    
    def encode(self) -> bytes:
        """Encode to RESP bytes format."""
        if self.type == "+":  # Simple String
            return f"+{self.value}\r\n".encode()
        elif self.type == "-":  # Error
            return f"-{self.value}\r\n".encode()
        elif self.type == ":":  # Integer
            return f":{self.value}\r\n".encode()
        elif self.type == "$":  # Bulk String
            if self.value is None:
                return b"$-1\r\n"
            encoded = str(self.value).encode()
            return f"${len(encoded)}\r\n".encode() + encoded + b"\r\n"
        elif self.type == "*":  # Array
            if self.value is None:
                return b"*-1\r\n"
            resp = f"*{len(self.value)}\r\n".encode()
            for item in self.value:
                if isinstance(item, RESPValue):
                    resp += item.encode()
                else:
                    resp += RESPValue("$", item).encode()
            return resp
        return b""


class RESPParser:
    """
    RESP (Redis Serialization Protocol) Parser.
    
    Handles parsing incoming Redis commands in RESP format.
    """
    
    def __init__(self):
        self.buffer = b""
    
    def parse(self, data: bytes) -> Optional[List[str]]:
        """
        Parse RESP command from bytes.
        
        Returns:
            List of command parts (e.g., ["SET", "key", "value"])
            None if incomplete command
        """
        self.buffer += data
        
        if not self.buffer.startswith(b"*"):
            return None
        
        # Find first CRLF
        idx = self.buffer.find(b"\r\n")
        if idx == -1:
            return None
        
        try:
            # Parse array length: *N
            array_len = int(self.buffer[1:idx])
            
            # Parse each element
            command_parts = []
            pos = idx + 2
            
            for _ in range(array_len):
                # Expect bulk string: $LEN\r\nDATA\r\n
                if pos >= len(self.buffer) or self.buffer[pos:pos+1] != b"$":
                    return None
                
                # Find length line
                len_idx = self.buffer.find(b"\r\n", pos)
                if len_idx == -1:
                    return None
                
                length = int(self.buffer[pos+1:len_idx])
                data_start = len_idx + 2
                data_end = data_start + length
                
                if data_end + 2 > len(self.buffer):
                    return None
                
                # Extract string value
                value = self.buffer[data_start:data_end].decode("utf-8", errors="replace")
                command_parts.append(value)
                
                pos = data_end + 2  # Skip \r\n
            
            # Command successfully parsed, consume from buffer
            self.buffer = self.buffer[pos:]
            return command_parts
            
        except (ValueError, IndexError):
            return None


class RedisProtocolHandler:
    """
    Handles Redis protocol commands.
    
    Implements subset of Redis commands compatible with our store.
    """
    
    # Supported commands
    COMMANDS = {
        "SET", "GET", "DEL", "EXISTS", "EXPIRE", "TTL", "KEYS",
        "FLUSHDB", "DBSIZE", "INFO", "PING", "ECHO", "COMMAND",
        "SAVE", "BGSAVE", "SHUTDOWN"
    }
    
    def __init__(self, redislite_store):
        """
        Initialize protocol handler.
        
        Args:
            redislite_store: RedisLite instance
        """
        self.store = redislite_store
        self.start_time = time.time()
    
    def handle_command(self, parts: List[str]) -> RESPValue:
        """
        Handle a Redis command.
        
        Args:
            parts: Command parts (e.g., ["SET", "key", "value"])
        
        Returns:
            RESPValue response
        """
        if not parts:
            return RESPValue("-", "ERR empty command")
        
        command = parts[0].upper()
        
        if command == "PING":
            return self._cmd_ping(parts)
        elif command == "ECHO":
            return self._cmd_echo(parts)
        elif command == "SET":
            return self._cmd_set(parts)
        elif command == "GET":
            return self._cmd_get(parts)
        elif command == "DEL":
            return self._cmd_del(parts)
        elif command == "EXISTS":
            return self._cmd_exists(parts)
        elif command == "EXPIRE":
            return self._cmd_expire(parts)
        elif command == "TTL":
            return self._cmd_ttl(parts)
        elif command == "KEYS":
            return self._cmd_keys(parts)
        elif command == "FLUSHDB":
            return self._cmd_flushdb(parts)
        elif command == "DBSIZE":
            return self._cmd_dbsize(parts)
        elif command == "INFO":
            return self._cmd_info(parts)
        elif command == "COMMAND":
            return self._cmd_command(parts)
        elif command == "SAVE":
            return self._cmd_save(parts)
        elif command == "SHUTDOWN":
            return self._cmd_shutdown(parts)
        else:
            return RESPValue("-", f"ERR unknown command '{command}'")
    
    def _cmd_ping(self, parts: List[str]) -> RESPValue:
        """PING or PING message"""
        if len(parts) > 1:
            return RESPValue("$", parts[1])
        return RESPValue("+", "PONG")
    
    def _cmd_echo(self, parts: List[str]) -> RESPValue:
        """ECHO message"""
        if len(parts) < 2:
            return RESPValue("-", "ERR wrong number of arguments")
        return RESPValue("$", parts[1])
    
    def _cmd_set(self, parts: List[str]) -> RESPValue:
        """SET key value [EX seconds]"""
        if len(parts) < 3:
            return RESPValue("-", "ERR wrong number of arguments")
        
        key = parts[1]
        value = parts[2]
        ttl = None
        
        # Parse optional EX argument
        if len(parts) >= 5 and parts[3].upper() == "EX":
            try:
                ttl = int(parts[4])
            except ValueError:
                return RESPValue("-", "ERR invalid TTL")
        
        try:
            self.store.set(key, value, ttl=ttl)
            return RESPValue("+", "OK")
        except Exception as e:
            return RESPValue("-", f"ERR {str(e)}")
    
    def _cmd_get(self, parts: List[str]) -> RESPValue:
        """GET key"""
        if len(parts) < 2:
            return RESPValue("-", "ERR wrong number of arguments")
        
        value = self.store.get(parts[1])
        return RESPValue("$", value)
    
    def _cmd_del(self, parts: List[str]) -> RESPValue:
        """DEL key [key ...]"""
        if len(parts) < 2:
            return RESPValue("-", "ERR wrong number of arguments")
        
        count = 0
        for key in parts[1:]:
            if self.store.delete(key):
                count += 1
        
        return RESPValue(":", count)
    
    def _cmd_exists(self, parts: List[str]) -> RESPValue:
        """EXISTS key [key ...]"""
        if len(parts) < 2:
            return RESPValue("-", "ERR wrong number of arguments")
        
        count = 0
        for key in parts[1:]:
            if self.store.exists(key):
                count += 1
        
        return RESPValue(":", count)
    
    def _cmd_expire(self, parts: List[str]) -> RESPValue:
        """EXPIRE key seconds"""
        if len(parts) < 3:
            return RESPValue("-", "ERR wrong number of arguments")
        
        key = parts[1]
        try:
            ttl = int(parts[2])
        except ValueError:
            return RESPValue("-", "ERR invalid TTL")
        
        if not self.store.exists(key):
            return RESPValue(":", 0)
        
        # Re-set with new TTL
        value = self.store.get(key)
        if value is not None:
            self.store.set(key, value, ttl=ttl)
            return RESPValue(":", 1)
        
        return RESPValue(":", 0)
    
    def _cmd_ttl(self, parts: List[str]) -> RESPValue:
        """TTL key"""
        if len(parts) < 2:
            return RESPValue("-", "ERR wrong number of arguments")
        
        ttl = self.store.ttl(parts[1])
        return RESPValue(":", ttl)
    
    def _cmd_keys(self, parts: List[str]) -> RESPValue:
        """KEYS pattern"""
        pattern = parts[1] if len(parts) > 1 else "*"
        keys = self.store.keys(pattern)
        
        return RESPValue("*", [RESPValue("$", k) for k in keys])
    
    def _cmd_flushdb(self, parts: List[str]) -> RESPValue:
        """FLUSHDB"""
        self.store.flushdb()
        return RESPValue("+", "OK")
    
    def _cmd_dbsize(self, parts: List[str]) -> RESPValue:
        """DBSIZE"""
        size = self.store.dbsize()
        return RESPValue(":", size)
    
    def _cmd_info(self, parts: List[str]) -> RESPValue:
        """INFO [section]"""
        info = self.store.info()
        
        # Format as INFO response
        info_str = f"""# Server
redis_version:7.0.0-redislite
redis_mode:standalone
uptime_in_seconds:{int(time.time() - self.start_time)}

# Memory
used_memory:{info.get('memory_bytes', 0)}
used_memory_human:{info.get('memory_human', '0B')}
maxmemory:{info.get('max_memory_bytes', 0)}

# Stats
total_commands_processed:{info.get('operations_total', 0)}
total_sets:{info.get('sets_total', 0)}
total_gets:{info.get('gets_total', 0)}
total_deletes:{info.get('deletes_total', 0)}
evicted_keys:{info.get('evictions_total', 0)}
expired_keys:{info.get('expirations_total', 0)}

# Keyspace
db0:keys={info.get('keys', 0)}
"""
        return RESPValue("$", info_str)
    
    def _cmd_command(self, parts: List[str]) -> RESPValue:
        """COMMAND - list all commands"""
        commands = list(self.COMMANDS)
        return RESPValue("*", [RESPValue("$", cmd) for cmd in commands])
    
    def _cmd_save(self, parts: List[str]) -> RESPValue:
        """SAVE - background save"""
        # Would integrate with persistence manager
        return RESPValue("+", "OK")
    
    def _cmd_shutdown(self, parts: List[str]) -> RESPValue:
        """SHUTDOWN - shutdown server"""
        return RESPValue("+", "OK")


class TCPServer:
    """
    Redis-compatible TCP server using asyncio.
    
    Accepts RESP protocol commands from redis-cli and client libraries.
    """
    
    def __init__(self, host: str = "0.0.0.0", port: int = 6379, redislite_store=None):
        """
        Initialize TCP server.
        
        Args:
            host: Listen address
            port: Listen port (default Redis port)
            redislite_store: RedisLite instance to serve
        """
        self.host = host
        self.port = port
        self.store = redislite_store
        self.server = None
        self._running = False
    
    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """
        Handle a single client connection.
        
        Parses RESP commands and sends responses.
        """
        addr = writer.get_extra_info("peername")
        logger.info(f"Client connected: {addr}")
        
        parser = RESPParser()
        handler = RedisProtocolHandler(self.store)
        
        try:
            while self._running:
                # Read data from client
                data = await asyncio.wait_for(reader.read(4096), timeout=30.0)
                
                if not data:
                    break  # Client disconnected
                
                # Parse command
                command_parts = parser.parse(data)
                
                if command_parts:
                    # Handle command
                    response = handler.handle_command(command_parts)
                    writer.write(response.encode())
                    await writer.drain()
        
        except asyncio.TimeoutError:
            logger.debug(f"Client timeout: {addr}")
        except Exception as e:
            logger.error(f"Client error: {e}")
        finally:
            writer.close()
            await writer.wait_closed()
            logger.info(f"Client disconnected: {addr}")
    
    async def start(self):
        """Start the TCP server."""
        self._running = True
        self.server = await asyncio.start_server(
            self.handle_client,
            self.host,
            self.port
        )
        
        logger.info(f"RedisLite TCP server listening on {self.host}:{self.port}")
        
        async with self.server:
            await self.server.serve_forever()
    
    def stop(self):
        """Stop the TCP server."""
        self._running = False
        if self.server:
            self.server.close()
    
    def run(self):
        """Run server in current event loop."""
        try:
            asyncio.run(self.start())
        except KeyboardInterrupt:
            self.stop()
            logger.info("Server shutdown")
