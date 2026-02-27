"""
Issue #7: Graceful Shutdown Handler

Handles SIGTERM/SIGINT for Kubernetes-compatible graceful shutdown.
Ensures all data is flushed and connections are closed cleanly.
"""

import signal
import logging
import asyncio
from typing import Optional, Callable, List

logger = logging.getLogger(__name__)


class GracefulShutdownHandler:
    """
    Handles graceful shutdown on SIGTERM/SIGINT.
    
    Behavior:
    1. Signal received (SIGTERM/SIGINT)
    2. Stop accepting new connections
    3. Flush all pending data (AOF, snapshots)
    4. Close open connections gracefully (with timeout)
    5. Exit cleanly
    
    Compatible with Kubernetes shutdown sequence.
    """
    
    def __init__(self, timeout_sec: float = 30.0):
        """
        Initialize graceful shutdown handler.
        
        Args:
            timeout_sec: Timeout to wait for clean shutdown
        """
        self.timeout_sec = timeout_sec
        self.should_stop = asyncio.Event()
        self.on_shutdown_callbacks: List[Callable] = []
    
    def register_callback(self, callback: Callable) -> None:
        """
        Register a callback to be called on shutdown.
        
        Args:
            callback: Function to call (can be async or sync)
        """
        self.on_shutdown_callbacks.append(callback)
    
    def register_signal_handlers(self) -> None:
        """
        Register SIGTERM and SIGINT handlers.
        
        Should be called once on startup.
        """
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, initiating graceful shutdown...")
            asyncio.create_task(self._shutdown())
        
        signal.signal(signal.SIGTERM, signal_handler)  # Kubernetes sends this
        signal.signal(signal.SIGINT, signal_handler)   # Ctrl+C
        
        logger.info("Graceful shutdown handlers registered for SIGTERM, SIGINT")
    
    async def _shutdown(self) -> None:
        """Internal shutdown sequence."""
        try:
            logger.info("Starting graceful shutdown sequence...")
            
            # Call all registered callbacks
            for callback in self.on_shutdown_callbacks:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback()
                    else:
                        callback()
                    logger.info(f"✓ Shutdown callback completed: {callback.__name__}")
                except Exception as e:
                    logger.error(f"Error in shutdown callback {callback.__name__}: {e}")
            
            logger.info("Graceful shutdown complete")
            self.should_stop.set()
            
        except Exception as e:
            logger.error(f"Error during graceful shutdown: {e}")
            self.should_stop.set()
    
    async def wait_for_shutdown(self) -> None:
        """
        Wait for shutdown signal.
        
        Can be awaited in main async loop.
        """
        await self.should_stop.wait()
    
    @property
    def is_stopping(self) -> bool:
        """Check if shutdown was triggered."""
        return self.should_stop.is_set()


# Global instance
_shutdown_handler: Optional[GracefulShutdownHandler] = None


def get_shutdown_handler() -> GracefulShutdownHandler:
    """Get or create the global shutdown handler."""
    global _shutdown_handler
    if _shutdown_handler is None:
        _shutdown_handler = GracefulShutdownHandler()
    return _shutdown_handler


def register_shutdown_callback(callback: Callable) -> None:
    """Register a callback to run on graceful shutdown."""
    get_shutdown_handler().register_callback(callback)
