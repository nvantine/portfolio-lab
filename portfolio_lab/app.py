"""Convenient foreground service supervisor; systemd is preferred on a server."""
import os
import subprocess
import time
from django.conf import settings


def run(port=8000):
    if not 1 <= port <= 65535: raise ValueError("Port must be between 1 and 65535")
    environment = dict(os.environ)
    environment.pop("LAB_SOCKET", None)
    environment["DJANGO_DEBUG"] = "false"
    subprocess.run(["uv", "run", "--no-sync", "python", "manage.py", "collectstatic", "--noinput"], cwd=settings.BASE_DIR, env=environment, check=True)
    commands = [
        ["gunicorn", "portfolio_lab.wsgi:application", "--bind", f"127.0.0.1:{port}", "--workers", "1", "--threads", "4"],
        ["portfolio-lab", "jobs", "work"],
        ["portfolio-lab", "scheduler", "work"],
        ["portfolio-lab", "serve", "--socket", str(settings.LAB_DATA_DIR / "app.sock")],
    ]
    children = []
    try:
        for command in commands:
            children.append(subprocess.Popen(["uv", "run", "--no-sync", *command], cwd=settings.BASE_DIR, env=environment))
        while all(child.poll() is None for child in children): time.sleep(1)
        raise ValueError("A service exited. Check the terminal output and existing services/ports")
    except KeyboardInterrupt:
        pass
    finally:
        for child in children:
            if child.poll() is None: child.terminate()
        for child in children:
            try: child.wait(timeout=10)
            except subprocess.TimeoutExpired: child.kill(); child.wait()
