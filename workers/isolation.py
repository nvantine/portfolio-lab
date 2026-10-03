"""Rootless-only, resource-bounded container subprocess. No host mounts."""
import json
import os
import selectors
import subprocess
import time
import uuid

from django.conf import settings


class IsolationError(RuntimeError):
    pass


def runtime_info():
    try:
        process = subprocess.run([settings.LAB_CONTAINER_RUNTIME, "info", "--format", "{{json .}}"], capture_output=True, text=True, timeout=15, check=True)
        info = json.loads(process.stdout)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise IsolationError("Rootless Docker unavailable. Configure the runtime before running generated code") from exc
    if not any("rootless" in option for option in info.get("SecurityOptions", [])):
        raise IsolationError("Generated code requires rootless Docker")
    if str(info.get("CgroupVersion")) != "2" or info.get("CgroupDriver") != "systemd" or not all(info.get(flag) for flag in ("MemoryLimit", "SwapLimit", "PidsLimit", "CpuCfsQuota")):
        raise IsolationError("Rootless runtime must support cgroup v2 CPU, memory, and process limits")
    return info


def container_command(name, image):
    return [settings.LAB_CONTAINER_RUNTIME, "run", "--rm", "-i", "--name", name,
            "--network", "none", "--read-only", "--cpus", "2", "--memory", "4g",
            "--memory-swap", "4g", "--pids-limit", "128", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", "--user", "65534:65534",
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=256m,mode=1777",
            "--env", "PYTHONDONTWRITEBYTECODE=1", "--env", "OMP_NUM_THREADS=2",
            "--env", "OPENBLAS_NUM_THREADS=2", "--env", "IPYTHONDIR=/tmp/ipython",
            "--env", "UV_CACHE_DIR=/tmp/uv",
            image, "uv", "run", "--no-project", "--python", "/usr/local/bin/python", "-m", "workers.entry"]


class StrategyProcess:
    def __init__(self, source=None, seed=42):
        self.source, self.seed = source, seed
        self.process = None
        self.name = "portfolio-lab-" + uuid.uuid4().hex
        self.deadline = time.monotonic() + 900
        self.buffer = b""

    def __enter__(self):
        runtime_info()
        try:
            self.image_digest = subprocess.run([settings.LAB_CONTAINER_RUNTIME, "image", "inspect", "--format", "{{.Id}}", settings.LAB_WORKER_IMAGE], capture_output=True, text=True, timeout=15, check=True).stdout.strip()
            if not self.image_digest.startswith("sha256:"):
                raise IsolationError("Worker image has no immutable ID")
            self.process = subprocess.Popen(container_command(self.name, self.image_digest), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            os.set_blocking(self.process.stdout.fileno(), False)
            self.selector = selectors.DefaultSelector()
            self.selector.register(self.process.stdout, selectors.EVENT_READ)
            if self.source is not None:
                self.request({"action": "load", "source": self.source, "seed": self.seed})
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def request(self, payload):
        encoded = json.dumps(payload, allow_nan=False).encode() + b"\n"
        if len(encoded) > 4_000_000:
            raise IsolationError("Worker input exceeds limit")
        # Writes are bounded too: a strategy can stop reading stdin.
        os.set_blocking(self.process.stdin.fileno(), False)
        writer = selectors.DefaultSelector()
        writer.register(self.process.stdin, selectors.EVENT_WRITE)
        position = 0
        call_deadline = min(self.deadline, time.monotonic() + 120)
        try:
            while position < len(encoded):
                if time.monotonic() > call_deadline:
                    raise IsolationError("Worker input timed out")
                if writer.select(1):
                    position += os.write(self.process.stdin.fileno(), encoded[position:position + 65536])
        finally:
            writer.close()
        while b"\n" not in self.buffer:
            if time.monotonic() > self.deadline:
                raise IsolationError("Worker exceeded 15-minute limit")
            if self.selector.select(1):
                data = os.read(self.process.stdout.fileno(), 65536)
                if not data:
                    raise IsolationError("Worker terminated without a result")
                self.buffer += data
                if len(self.buffer) > 4_000_000:
                    raise IsolationError("Worker output exceeds limit")
        line, self.buffer = self.buffer.split(b"\n", 1)
        response = json.loads(line)
        if not response.get("ok"):
            raise IsolationError("Generated code failed inside the isolated worker")
        return response["result"]

    def weights(self, history, current_weights, parameters):
        return self.request({"action": "weights", "dates": [str(day.date()) for day in history.index], "tickers": list(history.columns), "prices": history.to_numpy().tolist(), "current": current_weights, "parameters": parameters})

    def __exit__(self, *args):
        if self.process:
            self.process.kill()
            self.process.wait(timeout=10)
            for stream in (self.process.stdin, self.process.stdout):
                stream.close()
        if hasattr(self, "selector"):
            self.selector.close()
        try:
            subprocess.run([settings.LAB_CONTAINER_RUNTIME, "rm", "--force", self.name], capture_output=True, timeout=15, check=False)
        except (OSError, subprocess.SubprocessError):
            pass
