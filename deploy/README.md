# Deploying OSAF

`deploy.sh` deploys the Docker Compose stack behind a reverse proxy that already
terminates TLS. It clones or fast-forwards the checkout, builds, starts the stack,
runs the Alembic migrations and finishes with a health check through nginx.

```bash
OSAF_REPOSITORY_URL=git@github.com:rlmx-tech/osaf.git ./deploy/deploy.sh
```

| Variable | Default | Purpose |
|---|---|---|
| `OSAF_REPOSITORY_URL` | required | Git remote to clone from |
| `OSAF_DEPLOY_DIR` | `$HOME/projects/osaf` | Checkout and Compose project directory |
| `OSAF_BIND_ADDRESS` | `127.0.0.1` | Address the final health check calls |
| `OSAF_BIND_PORT` | `80` | Port the final health check calls |

The checkout needs a `.env` built from `deploy/.env.example` (the script refuses to run
without one and sets it to mode 600).

The script restarts nginx after every rebuild. nginx resolves the backend's
container IP once at startup, so after a rebuild it keeps proxying to the old
address and every request returns 502 while the stack still reports healthy.

`monitor/` holds the external site monitor that runs every 15 minutes on the
production host. See [monitor/README.md](monitor/README.md).
