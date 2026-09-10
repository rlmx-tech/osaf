# OSAF external site monitor

`osaf_monitor.sh` — the watchdog that would have caught both 2026-09-10
map failures (Carto watermarking the tiles, then the CSP `img-src` wildcard
never matching the bare tile host). Container health checks pass through
both; this checks the site the way a browser does.

Runs on the production VPS (`games.rlmx.tech`) every 15 minutes via
`osaf-monitor.timer` + `osaf-monitor.service` (systemd oneshot, watchdog
pattern: silent + exit 0 when healthy, output + exit 1 on drift).

## What it checks

1. **Site up** — `GET /` returns 200
2. **CSP intact** — the `content-security-policy` header still whitelists
   `https://tile.openstreetmap.org` in `img-src` (regression guard for the
   `3e713aa` fix), and does NOT contain the dead `cartocdn` entry
3. **Tiles fetchable** — `GET tile.openstreetmap.org/{z}/{x}/{y}.png`
   returns 200 with an image content-type (catches provider block pages,
   the Carto-style watermark-replacement failure mode, and OSM policy
   blocks that return non-image bodies)
4. **API serving** — `GET /api/v1/incidents?per_page=1` returns 200
5. **Bundle coherent** — the served JS bundle still carries the OSM tile
   URL (catches an accidental frontend regen reverting the provider)

## Manual run

```bash
ssh games.rlmx.tech 'bash /opt/osaf/osaf_monitor.sh'
```

Exit 0 silent = healthy. Exit 1 with an `OSAF MONITOR: ISSUES —` line names
each failure (e.g. `csp-missing-tile-host`, `tiles-bad-type`).

## Alerting

The timer runs it every 15 minutes; failures land in
`journalctl -u osaf-monitor.service`. Wire notification by adding
`OnFailure=` to the unit pointing at your preferred notifier (currently the
journal is the delivery — a deliberate first step; hook it to Telegram
webhook or email when wanted).

## Install on a fresh VPS

```bash
scp osaf_monitor.sh root@HOST:/opt/osaf/osaf_monitor.sh
scp osaf-monitor.{service,timer} HOST:/etc/systemd/system/
ssh HOST 'systemctl daemon-reload && systemctl enable --now osaf-monitor.timer'
```