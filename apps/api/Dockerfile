FROM python:3.12-slim

# WORKDIR mirrors this repo's real layout (/repo/apps/api, with
# /repo/packages/agent-core alongside it) rather than a flat /app --
# requirements.txt's `-e ../../packages/agent-core` line is a *relative*
# path, so it only resolves correctly if the directory structure inside
# the image matches the structure it resolves against for a local
# `cd apps/api && pip install -r requirements.txt`. Keeping them identical
# means there's exactly one install path to keep working, not two.
WORKDIR /repo

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc && rm -rf /var/lib/apt/lists/*

COPY apps/api/requirements.txt apps/api/requirements.txt
COPY packages/agent-core packages/agent-core

WORKDIR /repo/apps/api
RUN pip install --no-cache-dir -r requirements.txt

COPY apps/api/ .

# --proxy-headers + --forwarded-allow-ips='*': the VPS deploy binds this
# container's port to 127.0.0.1 only (docker-compose.yml) and puts a
# TLS-terminating reverse proxy in front of it (outside this repo -- see
# infra/README.md), which forwards to uvicorn over plain HTTP internally.
# Without this flag uvicorn takes that literally and reports every request
# as scheme=http regardless of what the real client connection used --
# oauthlib's InsecureTransportError check (calendar_oauth.py's callback())
# reads exactly that scheme, so a genuinely-HTTPS request from the browser
# was failing token exchange with "OAuth 2 MUST utilize https" the moment
# this codebase's first real per-tenant OAuth redirect flow got exercised
# in production. '*' (not a specific IP) is safe here specifically because
# the port binding above already means only local processes on this same
# host can reach uvicorn at all -- nothing external can spoof
# X-Forwarded-Proto by connecting directly.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
