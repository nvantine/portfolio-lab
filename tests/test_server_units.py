from pathlib import Path
import sys
import pytest


def test_unit_installer_prepares_all_services_without_starting(tmp_path, monkeypatch):
    from server import install
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(install.shutil, "which", lambda executable: "/usr/bin/uv")
    monkeypatch.setattr(sys, "argv", ["install", "--port", "8010"])
    install.main()
    target = tmp_path/".config/systemd/user"
    assert len(list(target.glob("portfolio-lab*"))) == 5
    assert 'ExecStart="/usr/bin/uv"' in (target/"portfolio-lab-web.service").read_text()
    assert "127.0.0.1:8010" in (target/"portfolio-lab-web.service").read_text()
    assert "%h/Projects" not in (target/"portfolio-lab-worker.service").read_text()
    install.main()  # same configuration is idempotent
    (target/"portfolio-lab-worker.service").write_text("Customized service")
    with pytest.raises(SystemExit): install.main()
