"""Hermes capability interface: Unix socket access grants research, never approval."""
import json
import os
from pathlib import Path
import socketserver

from portfolio_lab.cli import dispatch


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(10)
        try:
            line = self.rfile.readline(4_000_001)
            if len(line) > 4_000_000 or not line.endswith(b"\n"):
                raise ValueError("Request exceeds size limit")
            result = dispatch(json.loads(line), agent=True)
            response = {"ok": True, "result": result}
        except Exception as exc:
            response = {"ok": False, "error": str(exc)[:500] if isinstance(exc, ValueError) else "Invalid request or unavailable resource"}
        self.wfile.write(json.dumps(response, allow_nan=False, default=str).encode() + b"\n")


def serve(path):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise ValueError("Socket path already exists; check the running service before removing it")
    # Create with owner-only access, then intentionally expose to a shared group.
    previous = os.umask(0o177)
    try:
        server = socketserver.UnixStreamServer(str(target), Handler)
    finally:
        os.umask(previous)
    target.chmod(0o660)
    try:
        with server:
            server.serve_forever()
    finally:
        target.unlink(missing_ok=True)
