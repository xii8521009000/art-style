FROM node:22-bookworm-slim AS node
FROM python:3.15-slim-bookworm AS base
RUN useradd -m -u 1000 app && mkdir -p /data && chown app:app /data
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM base AS backend
COPY app ./app
USER app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]

FROM base AS runner
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/npm
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
 && apt-get update && apt-get install -y --no-install-recommends ca-certificates git libatomic1 \
 && rm -rf /var/lib/apt/lists/* \
 && mkdir -p /opt/codex /home/app/.codex \
 && npm install --prefix /opt/codex @openai/codex@0.166.0 --ignore-scripts \
 && chown -R app:app /opt/codex /home/app/.codex
ENV PATH="/opt/codex/node_modules/.bin:${PATH}"
COPY app/codex_runtime.py app/runner.py app/prompts.py app/style_contract.py app/__init__.py ./app/
USER app
CMD ["uvicorn", "app.runner:app", "--host", "0.0.0.0", "--port", "8001"]
