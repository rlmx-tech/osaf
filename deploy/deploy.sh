#!/usr/bin/env bash
# deploy.sh — OSAF production deployment script for Hera
# Run this script on Hera as the russ user.
# Prereqs: git, docker, docker compose v2, certbot

set -euo pipefail

DOMAIN="osaf.net"
REPO="https://github.com/russmorefield/osaf.git"
DEPLOY_DIR="$HOME/projects/OSAF"
CERTBOT_WEBROOT="/var/www/certbot"

# ── Colors ────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[OSAF]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# ── 1. Clone or update repo ───────────────────────────────
if [ -d "$DEPLOY_DIR/.git" ]; then
    info "Pulling latest code..."
    git -C "$DEPLOY_DIR" pull --ff-only
else
    info "Cloning repo to $DEPLOY_DIR..."
    mkdir -p "$(dirname "$DEPLOY_DIR")"
    git clone "$REPO" "$DEPLOY_DIR"
fi
cd "$DEPLOY_DIR"

# ── 2. Verify .env exists ─────────────────────────────────
if [ ! -f .env ]; then
    error ".env not found. Copy deploy/.env.example to $DEPLOY_DIR/.env and fill in values."
fi

# ── 3. Create certbot webroot dir ─────────────────────────
sudo mkdir -p "$CERTBOT_WEBROOT"
sudo chown "$USER":"$USER" "$CERTBOT_WEBROOT"

# ── 4. Phase 1: Bootstrap stack (HTTP only, no SSL) ───────
info "Phase 1: Starting bootstrap stack (HTTP only)..."

# Temporarily use bootstrap nginx config
cp nginx/nginx.bootstrap.conf nginx/nginx.active.conf

docker compose \
    -f docker-compose.yml \
    -f docker-compose.prod.yml \
    -f deploy/docker-compose.bootstrap.yml \
    up -d --build

info "Waiting for containers to be healthy..."
sleep 10
docker compose ps

# ── 5. Run Alembic migrations ─────────────────────────────
info "Running database migrations..."
docker compose exec backend alembic upgrade head

# ── 6. Seed reference data ────────────────────────────────
info "Seeding species and incident data..."
docker compose exec backend python -m app.utils.seed_data || warn "Seed data already loaded or failed — check manually."

# ── 7. Obtain TLS certificate ─────────────────────────────
if [ -d "/etc/letsencrypt/live/$DOMAIN" ]; then
    info "Certificate already exists — skipping certbot."
else
    info "Obtaining Let's Encrypt certificate for $DOMAIN..."
    sudo certbot certonly \
        --webroot \
        -w "$CERTBOT_WEBROOT" \
        -d "$DOMAIN" \
        -d "www.$DOMAIN" \
        --non-interactive \
        --agree-tos \
        --email admin@"$DOMAIN"

    if [ ! -d "/etc/letsencrypt/live/$DOMAIN" ]; then
        error "certbot failed — check DNS and port 80 forwarding before retrying."
    fi
fi

# ── 8. Phase 2: Restart with full TLS config ──────────────
info "Phase 2: Switching to production TLS config..."

docker compose \
    -f docker-compose.yml \
    -f docker-compose.prod.yml \
    down

docker compose \
    -f docker-compose.yml \
    -f docker-compose.prod.yml \
    up -d

info "Waiting for stack to come up..."
sleep 10
docker compose ps

# ── 9. Verify health ──────────────────────────────────────
info "Checking API health..."
curl -sf http://localhost:8000/health | jq .version || warn "Health check failed — check docker compose logs backend"

info "Checking HTTPS (requires DNS to point to this machine)..."
curl -sf "https://$DOMAIN/health" | jq .version || warn "HTTPS health check failed — DNS may not be propagated yet"

# ── 10. Certbot auto-renewal ──────────────────────────────
CRON_JOB="0 3 * * * certbot renew --quiet && docker compose -f $DEPLOY_DIR/docker-compose.yml -f $DEPLOY_DIR/docker-compose.prod.yml exec nginx nginx -s reload"
if ! crontab -l 2>/dev/null | grep -q "certbot renew"; then
    (crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -
    info "Added certbot auto-renewal cron (daily at 03:00)."
fi

echo ""
info "Deployment complete!"
echo ""
echo "  Site:     https://$DOMAIN"
echo "  API docs: https://$DOMAIN/api/v1/docs"
echo "  Logs:     docker compose logs -f"
echo ""
echo "Next steps:"
echo "  1. Verify site loads at https://$DOMAIN"
echo "  2. Create admin user via API or seed script"
echo "  3. Configure Cloudflare / DNS provider to point $DOMAIN A record to this machine's public IP"
