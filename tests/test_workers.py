import json
from types import SimpleNamespace
import pytest
from workers.isolation import container_command, runtime_info, IsolationError


def test_container_has_no_mounts_network_or_secrets(settings):
    command = container_command("test", "sha256:fixed")
    assert command[command.index("--network") + 1] == "none"
    assert "--read-only" in command and "--cap-drop" in command
    assert not any(value in command for value in ("-v", "--volume", "--mount", "--env-file", "--privileged"))
    assert "ALPACA" not in " ".join(command)


def test_fail_closed_non_rootless(monkeypatch):
    monkeypatch.setattr("workers.isolation.subprocess.run", lambda *a, **k: SimpleNamespace(stdout=json.dumps({"SecurityOptions": ["name=seccomp"]})))
    with pytest.raises(IsolationError, match="rootless"):
        runtime_info()


def test_requires_resource_limits(monkeypatch):
    monkeypatch.setattr("workers.isolation.subprocess.run", lambda *a, **k: SimpleNamespace(stdout=json.dumps({"SecurityOptions": ["name=rootless"], "CgroupVersion": "1"})))
    with pytest.raises(IsolationError, match="cgroup"):
        runtime_info()
