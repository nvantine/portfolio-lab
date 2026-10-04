"""Opt-in localhost process checks using a temporary database and synthetic data."""
import http.cookiejar
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import time
import urllib.parse
import urllib.request
import pytest

pytestmark = pytest.mark.skipif(os.getenv("LAB_TEST_SERVER") != "1", reason="Explicit opt-in for localhost subprocess services")
ROOT = Path(__file__).resolve().parent.parent


def command(environment, *args):
    result = subprocess.run(["uv", "run", "--no-sync", *args], cwd=ROOT, env=environment, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    return result.stdout


def wait_for(callback, process):
    deadline = time.monotonic()+30
    while time.monotonic() < deadline:
        if process.poll() is not None: pytest.fail("Local service exited before becoming ready")
        try:
            value = callback()
            if value: return value
        except (OSError, ValueError, KeyError): pass
        time.sleep(.1)
    pytest.fail("Local service did not become ready")


def stop(process):
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGINT)
        try: process.wait(timeout=15)
        except subprocess.TimeoutExpired: os.killpg(process.pid, signal.SIGKILL); process.wait()


def environment(tmp_path):
    values = dict(os.environ)
    values.pop("LAB_SOCKET", None)
    values.update(LAB_DB_PATH=str(tmp_path/"app.sqlite3"), LAB_DATA_DIR=str(tmp_path/"artifacts"), DJANGO_SECRET_KEY="integration-test-secret-only", DJANGO_DEBUG="false")
    command(values, "python", "manage.py", "migrate", "--noinput")
    return values


def test_foreground_stack_queue_dashboard_and_cli(tmp_path):
    values = environment(tmp_path)
    command(values, "python", "manage.py", "shell", "-c", "from django.contrib.auth import get_user_model; get_user_model().objects.create_user(username='integration', password='integration-only', is_staff=True)")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0)); port = probe.getsockname()[1]
    with (tmp_path/"service.log").open("w") as log:
        process = subprocess.Popen(["uv", "run", "--no-sync", "portfolio-lab", "app", "run", "--port", str(port)], cwd=ROOT, env=values, stdout=log, stderr=log, start_new_session=True)
        try:
            base = f"http://127.0.0.1:{port}"
            wait_for(lambda: urllib.request.urlopen(base+"/login/", timeout=2).status == 200, process)
            endpoint = str(tmp_path/"artifacts/app.sock")
            wait_for(lambda: Path(endpoint).exists(), process)
            client = dict(values, LAB_SOCKET=endpoint)
            dataset = json.loads(command(client, "portfolio-lab", "datasets", "demo"))["dataset"]
            config = tmp_path/"experiment.json"
            config.write_text(json.dumps({"dataset": dataset, "method": "equal_weight", "parameters": {"lookback": 30, "rebalance": "weekly"}}))
            result = json.loads(command(client, "portfolio-lab", "experiments", "run", str(config), "--wait"))[0]
            assert result["status"] == "succeeded"
            run = result["run_id"]
            assert json.loads(command(client, "portfolio-lab", "jobs", "health"))["worker"]["available"]
            assert json.loads(command(client, "portfolio-lab", "runs", "show", run))["results"]["weights"]
            jar = http.cookiejar.CookieJar()
            browser = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
            browser.open(base+"/login/").read()
            token = next(cookie.value for cookie in jar if cookie.name == "csrftoken")
            body = urllib.parse.urlencode({"username": "integration", "password": "integration-only", "csrfmiddlewaretoken": token}).encode()
            assert browser.open(base+"/login/", data=body).status == 200
            assert run.encode() in browser.open(base+f"/runs/{run}/").read()
            assert b"chart-dialog" in browser.open(base+"/static/portfolio/lab.js").read()
            assert b"startLivePage" in browser.open(base+"/static/portfolio/live.js").read()
            before = json.loads(browser.open(base+"/activity/status/?scope=datasets").read())["revision"]
            # A CLI-created snapshot changes the authenticated web revision.
            command(client, "portfolio-lab", "datasets", "demo", "--seed", "99")
            after = json.loads(browser.open(base+"/activity/status/?scope=datasets").read())["revision"]
            assert after != before
            assert b"data-live-region" in browser.open(base+"/datasets/").read()
            assert b"katex" in browser.open(base+"/static/vendor/katex/katex.min.css").read()
            command(client, "portfolio-lab", "runs", "trash", run)
            assert not json.loads(command(client, "portfolio-lab", "runs", "list"))
            command(client, "portfolio-lab", "runs", "restore", run)
            assert json.loads(command(client, "portfolio-lab", "runs", "list"))[0]["id"] == run
        finally: stop(process)


def test_socket_recovers_owned_stale_path(tmp_path):
    values = environment(tmp_path)
    endpoint = str(tmp_path/"app.sock")
    processes = []
    with (tmp_path/"socket.log").open("w") as log:
        try:
            for _ in range(2):
                process = subprocess.Popen(["uv", "run", "--no-sync", "portfolio-lab", "serve", "--socket", endpoint], cwd=ROOT, env=values, stdout=log, stderr=log, start_new_session=True)
                processes.append(process)
                def available():
                    if not Path(endpoint).exists(): return False
                    result = subprocess.run(["uv", "run", "--no-sync", "portfolio-lab", "methods", "list"], cwd=ROOT, env=dict(values, LAB_SOCKET=endpoint), capture_output=True, text=True, timeout=5)
                    return result.returncode == 0
                wait_for(available, process)
                assert Path(endpoint).stat().st_mode & 0o777 == 0o600
                os.killpg(process.pid, signal.SIGKILL); process.wait()
        finally:
            for process in processes: stop(process)
