#!/usr/bin/env python
"""
Entry point for running the RedisLite API server.

Usage:
    python run.py              # Start server with defaults
    python run.py --port 8080  # Custom port
    python run.py --reload    # Enable auto-reload (development)
"""

import argparse
import uvicorn

from redislite import Config
from redislite.api import app


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="RedisLite API Server")
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host to bind to (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind to (default: 8000)"
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload (development only)"
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="info",
        choices=["debug", "info", "warning", "error"],
        help="Log level (default: info)"
    )
    
    args = parser.parse_args()
    
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║                    RedisLite API Server                      ║
║                                                                  ║
║  Server running at: http://{args.host}:{args.port}                  ║
║  API Documentation:  http://{args.host}:{args.port}/docs          ║
║                                                                  ║
║  Endpoints:                                                    ║
║    GET  /health        - Health check                         ║
║    POST /set           - Set key-value                         ║
║    GET  /get/{{key}}    - Get value                            ║
║    DELETE /delete/{{key}} - Delete key                        ║
║    GET  /exists/{{key}}  - Check existence                    ║
║    GET  /ttl/{{key}}     - Get TTL                            ║
║    GET  /keys           - List all keys                       ║
║    GET  /stats          - Store statistics                    ║
║    DELETE /clear        - Clear all keys                      ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════╝
""")
    
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=args.log_level,
    )


if __name__ == "__main__":
    main()
