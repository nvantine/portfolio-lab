"""Owner-authorized local interface; socket access grants full application capabilities."""
import json
import os
from pathlib import Path
import socketserver
import socket
import fcntl
import stat

from portfolio_lab.cli import dispatch


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(10)
        try:
            line = self.rfile.readline(4_000_001)
            if len(line) > 4_000_000 or not line.endswith(b"\n"):
                raise ValueError("Request exceeds size limit")
            command = json.loads(line)
            if command.get("group") in {"app", "serve", "scheduler"} or command.get("group") == "jobs" and command.get("action") == "work":
                raise ValueError("Process-management commands run locally, outside the request socket")
            result = dispatch(command, agent=False)
            response = {"ok": True, "result": result}
        except Exception as exc:
            response = {"ok": False, "error": str(exc)[:500] if isinstance(exc, ValueError) else "Invalid request or unavailable resource"}
        self.wfile.write(json.dumps(response, allow_nan=False, default=str).encode() + b"\n")


def serve(path):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.with_suffix(".lock").open("w") as lock:
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise ValueError("Socket service is already running") from None
        if target.exists() or target.is_symlink():
            info = target.lstat()
            if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid(): raise ValueError("Socket path is occupied by a different file")
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as probe:
                probe.settimeout(1)
                try: probe.connect(str(target))
                except ConnectionRefusedError: target.unlink()
                else: raise ValueError("An existing socket owner is alive")
        previous = os.umask(0o177)
        try: server = socketserver.ThreadingUnixStreamServer(str(target), Handler)
        finally: os.umask(previous)
        server.daemon_threads = True
        target.chmod(0o600)
        try:
            with server: server.serve_forever()
        finally: target.unlink(missing_ok=True)
