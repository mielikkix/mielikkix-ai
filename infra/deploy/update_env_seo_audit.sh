#!/usr/bin/env bash
# Adds the 9 env keys introduced by the SEO Audit & Optimize agent / Articles
# publish-to-live pipeline (commit 3f56a28) to an existing production .env.
#
# Idempotent: keys already present (by name, ignoring value) are left
# untouched and skipped -- safe to re-run. Existing values are never
# overwritten. Always backs up the file first.
#
# Usage (from the VPS, in the directory that holds docker-compose.yml):
#   bash infra/deploy/update_env_seo_audit.sh [path-to-env-file]
# Defaults to ./.env if no path is given.
set -euo pipefail

ENV_FILE="${1:-.env}"

if [ ! -f "$ENV_FILE" ]; then
  echo "Error: $ENV_FILE not found." >&2
  exit 1
fi

BACKUP="${ENV_FILE}.bak.$(date +%Y%m%d%H%M%S)"
cp "$ENV_FILE" "$BACKUP"
echo "Backed up $ENV_FILE -> $BACKUP"

# key, default value (optional)
KEYS=(
  "GOOGLE_ANALYTICS_OAUTH_CLIENT_ID|"
  "GOOGLE_ANALYTICS_OAUTH_CLIENT_SECRET|"
  "GOOGLE_PAGESPEED_API_KEY|"
  "WEBSITE_REPO_PATH|"
  "WEBSITE_DEPLOY_SFTP_HOST|"
  "WEBSITE_DEPLOY_SFTP_PORT|22"
  "WEBSITE_DEPLOY_SFTP_USERNAME|"
  "WEBSITE_DEPLOY_SFTP_PASSWORD|"
  "WEBSITE_DEPLOY_REMOTE_PATH|"
)

to_add=()
for entry in "${KEYS[@]}"; do
  key="${entry%%|*}"
  default="${entry#*|}"
  if grep -qE "^${key}=" "$ENV_FILE"; then
    echo "skip (already present): $key"
  else
    to_add+=("${key}=${default}")
  fi
done

if [ "${#to_add[@]}" -eq 0 ]; then
  echo "Nothing to add -- all keys already present in $ENV_FILE."
  exit 0
fi

{
  echo ""
  echo "# --- SEO Audit & Optimize / Articles publish pipeline (added $(date +%Y-%m-%d)) ---"
  for line in "${to_add[@]}"; do
    echo "$line"
  done
} >> "$ENV_FILE"

echo "Added ${#to_add[@]} key(s) to $ENV_FILE:"
for line in "${to_add[@]}"; do
  echo "  ${line%%=*}"
done
echo ""
echo "Next: edit $ENV_FILE and fill in real values, then:"
echo "  docker compose build backend"
echo "  docker compose exec backend alembic upgrade head"
echo "  docker compose up -d backend"
