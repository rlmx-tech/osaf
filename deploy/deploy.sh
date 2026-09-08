#!/usr/bin/env bash
# Deploy OSAF behind an existing TLS-terminating reverse proxy.

set -euo pipefail

REPO="${OSAF_REPOSITORY_URL:?Set OSAF_REPOSITORY_URL to the canonical Git remote}"
DEPLOY_DIR="${OSAF_DEPLOY_DIR:-$HOME/projects/osaf}"

if [ -d "$DEPLOY_DIR/.git" ]; then
    git -C "$DEPLOY_DIR" pull --ff-only
else
    mkdir -p "$(dirname "$DEPLOY_DIR")"
    git clone "$REPO" "$DEPLOY_DIR"
fi

cd "$DEPLOY_DIR"

if [ ! -f .env ]; then
    echo "Missing .env; copy deploy/.env.example and provide production values." >&2
    exit 1
fi

chmod 600 .env
docker compose config --quiet
docker compose build --pull
docker compose up -d --remove-orphans

# nginx resolves the backend's container IP once, at startup. Rebuilding gives
# the backend a new IP, but nginx is not itself recreated (its image and config
# are unchanged), so it keeps proxying to an address nobody is listening on and
# every request returns 502. Restarting it forces re-resolution. Observed on a
# real deploy: the stack reported healthy while the site was down.
docker compose restart nginx

docker compose exec -T backend alembic upgrade head
docker compose ps

# Through nginx, not straight at the backend — that is the path that breaks.
curl --fail --silent --show-error \
    "http://${OSAF_BIND_ADDRESS:-127.0.0.1}:${OSAF_BIND_PORT:-80}/health"
printf '\nOSAF deployment completed successfully.\n'
