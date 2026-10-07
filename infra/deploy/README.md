# infra/deploy

Placeholder — see [`../README.md`](../README.md#deploy). CI runs tests and
builds (`.github/workflows/ci.yml`) but doesn't deploy; deployment today is
manual, on the Hostinger VPS (target budget 2 vCPU / 8 GB, everything in one
API process), via the root `docker-compose.yml`.
