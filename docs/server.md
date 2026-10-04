# Run the dashboard and CLI on your server

This setup uses one Linux owner account, SQLite, a localhost web application, an automatic queue worker, a scheduler, and an owner-only command socket. No dedicated agent account or environment is required. The server needs Python 3.13 through uv, systemd user services, and rootless Docker for uploaded Python/notebooks. Built-in recipes do not require containers.

## Prepare the checkout

```bash
cd ~/Projects/portfolio-lab
uv sync --locked
uv run python manage.py migrate
uv run python manage.py collectstatic --noinput
uv run python manage.py createsuperuser
```

Create `.env` from `.env.example` in your editor if it does not already exist. Set a private `DJANGO_SECRET_KEY`, historical Alpaca credentials, and optionally `LAB_OPERATOR_USERNAME` to identify the CLI owner in the ledger. Create `.env.paper` from its example for account execution. Do not paste credentials into chat or commands. Follow [credential instructions](paper.md).

Build the worker after dependency or pure numerical source updates:

```bash
uv run python -m workers.build_image --cached
```

The helper reuses uv's local dependency cache; if unavailable, use the normal builder without `--cached`. Both use the same rootless execution restrictions. Verify actual rootless/cgroup resource enforcement before running submitted code.

## Install supervised services

```bash
uv run python -m server.install
systemctl --user daemon-reload
systemctl --user enable --now portfolio-lab.target
systemctl --user status portfolio-lab-web portfolio-lab-worker portfolio-lab-scheduler portfolio-lab-socket
```

The installer writes user units with this checkout's path and the discovered uv executable. It does not overwrite customized units or start services. Default web port is 8000; select another with `uv run python -m server.install --port 8010` before first installation.

For boot without an interactive login, enable lingering for your server user using `loginctl enable-linger YOUR_SERVER_USERNAME` (your server may require administrator authorization). This is a server installation step, not performed automatically by the project.

```bash
journalctl --user -u portfolio-lab-worker -u portfolio-lab-scheduler -f
export LAB_SOCKET="$XDG_RUNTIME_DIR/portfolio-lab/app.sock"
uv run portfolio-lab jobs health
uv run portfolio-lab methods list
```

Give an agent the same project working directory and `LAB_SOCKET` setting. A socket-mode command loads no local Django settings or credential file. The server executes the same service calls as the dashboard. No HTTP token or public agent endpoint is needed.

## Access from your computer

```bash
ssh -N -L 8000:127.0.0.1:8000 YOUR_SERVER_USERNAME@YOUR_SERVER_HOST
```

Open `http://127.0.0.1:8000` locally. Use matching port substitutions if you chose another server port. Gunicorn serves the application; WhiteNoise serves collected Plotly/KaTeX/static assets. The web app remains bound to localhost.

## Foreground local alternative

```bash
uv run portfolio-lab app run --port 8010
```

This starts web, worker, scheduler, and socket together and stops them on Ctrl+C. It requires a private Django secret and collects static files first. Choose an unused port and stop this foreground stack before starting systemd services against the same database. The ordinary `manage.py runserver` command starts only the web app.

## Updates and recovery

Stop the target before migration/code updates, copy `db.sqlite3` and ignored artifacts into a private backup, sync locked dependencies, apply migrations, collect static files, and rebuild the worker when needed. Restart the target after checks. Code/dependency changes invalidate prior execution fingerprints: rerun the experiment and activate a new version. Existing holdings remain visible and can be paused/closed.

Interrupted research jobs are recorded as failed rather than silently rerun. An interrupted broker submission remains an intent/unknown and blocks new orders until reconciliation proves its outcome. The socket service detects a live owner and safely recovers its own stale socket after a crash. Services expose heartbeat/state details through `jobs health` and the dashboard.

Existing execution sessions migrate to paused with scheduling disabled. Adopt unmanaged shares explicitly before resuming an old sleeve, or stop it and activate a newly evaluated version. No migration submits orders.
