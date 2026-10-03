FROM python:3.13-slim@sha256:bb2988715db2cf7ace7b53f38f3cffbef7c7046a656bee66245eb0ed386e2e81
COPY --from=ghcr.io/astral-sh/uv:0.12.22 /uv /usr/local/bin/uv
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN uv pip install --system --no-cache -r requirements.txt
COPY workers /app/workers
COPY optimizer /app/optimizer
COPY strategies /app/strategies
COPY backtest /app/backtest
RUN uv run --no-project --python /usr/local/bin/python -m ipykernel install --name python3 --prefix /usr/local
USER 65534:65534
ENTRYPOINT []
