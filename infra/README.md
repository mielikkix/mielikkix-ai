# infra

Deployment infrastructure for mielikkix-ai.

## docker-compose.yml — intentionally still at the repo root

The target layout puts `docker-compose.yml` here, at `infra/docker-compose.yml`.
It has **not** been moved during this restructure.

Why: the repo's docs (`files/CLAUDE.md`, the root `CLAUDE.md`) describe
production as deployed to a Hostinger VPS "via `docker-compose.yml`" — almost
certainly a manual `git pull && docker compose up -d --build` (or similar) run
directly on that VPS. That process lives outside this repo (no deploy script
or CI workflow was found in-tree to update), so there's no way to verify from
here whether it references `docker-compose.yml` by a path that assumes it's
at the repo root. Moving the file could silently break the next production
deploy with no way to catch it in this repo.

`docker-compose.yml`'s `build.context` paths were still updated in place
(`./backend` → `./apps/api`, `./frontend` → `./apps/dashboard`) since those
directories did move — only the file's own location was left alone.

**Before moving it**, confirm how the VPS actually invokes
`docker-compose.yml` (the exact command in whatever deploy runbook/script
exists outside this repo) and update that alongside the move.

## docker/

Placeholder for consolidating one Dockerfile per app/agent here. Not done in
this pass — each app's `Dockerfile` currently still lives alongside it
(`apps/api/Dockerfile`, `apps/dashboard/Dockerfile`) and is referenced by
`dockerfile: Dockerfile` (relative to `build.context`) in the root
`docker-compose.yml`. Moving them here would require also rewriting those
`dockerfile:` paths and was judged out of scope for a structure-preserving
move of a live production service.

## deploy/

Placeholder for deploy scripts + per-env config. CI exists
(`.github/workflows/ci.yml`: API tests + migration check, dashboard and
widget builds) but it doesn't deploy. Deployment today:

- **API + dashboard + db**: manual `git pull && docker compose up -d --build`
  on the Hostinger VPS, behind a TLS reverse proxy configured outside this repo.
- **Marketing site**: static `website/dist/` uploaded to Hostinger shared
  hosting — by hand, or by the admin Articles publish flow
  (`apps/api/app/services/deploy_service.py`, SFTP via `paramiko`, needs the
  `WEBSITE_REPO_PATH` and `WEBSITE_DEPLOY_SFTP_*` settings).
