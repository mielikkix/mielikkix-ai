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

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
