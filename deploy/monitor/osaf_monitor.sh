#!/bin/bash
# External site monitor. Checks what the two 2026-09-10 map failures broke and
# container health could not see: the site answers, the CSP still allows the
# tile host, a tile comes back as an image, the API serves, and the bundle
# still points at OSM. Silent with exit 0 when healthy; names each issue and
# exits 1 when not.
#
# Matching uses here-strings, not `echo "$x" | grep -q`. grep -q exits on the
# first match, and systemd ignores SIGPIPE, so echo then reports "write error:
# Broken pipe" into the journal on every run.
set -u
BASE="https://osaf.net"
TILE_ZXY="5/10/12"
# The OSM tile usage policy requires an identifying User-Agent.
UA="osaf-monitor/1 (+https://osaf.net)"
issues=""

# 1. site up
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 "$BASE/")
[ "$code" = "200" ] || issues="${issues}site-down(http=$code) "

# 2. CSP img-src still allows the bare tile host, and not the dead Carto one
headers=$(curl -s -D - -o /dev/null --max-time 15 "$BASE/")
img_src=$(grep -i '^content-security-policy:' <<<"$headers" | grep -o 'img-src[^;]*')
grep -q 'https://tile\.openstreetmap\.org' <<<"$img_src" || issues="${issues}csp-missing-tile-host "
grep -q 'cartocdn' <<<"$img_src" && issues="${issues}csp-still-has-dead-carto "

# 3. a tile comes back as an image, not a block page or a watermark page
tile=$(curl -s -o /dev/null -A "$UA" -w '%{http_code}|%{content_type}' --max-time 15 \
    "https://tile.openstreetmap.org/$TILE_ZXY.png")
tile_code=${tile%%|*}
tile_type=${tile#*|}
case "$tile_type" in
  image/png|image/jpeg|image/webp) ;;
  *) issues="${issues}tiles-bad-type($tile_type) " ;;
esac
[ "$tile_code" = "200" ] || issues="${issues}tiles-bad-status($tile_code) "

# 4. API serving data
api=$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 "$BASE/api/v1/incidents?per_page=1")
[ "$api" = "200" ] || issues="${issues}api-down($api) "

# 5. the served bundle still carries the OSM tile URL
index=$(curl -s --max-time 15 "$BASE/")
bundle_path=$(grep -m1 -oE 'assets/index-[A-Za-z0-9_-]+\.js' <<<"$index")
if [ -z "$bundle_path" ]; then
    issues="${issues}bundle-not-found "
else
    bundle=$(curl -s --max-time 15 "$BASE/$bundle_path")
    grep -q 'tile\.openstreetmap\.org' <<<"$bundle" || issues="${issues}bundle-lost-osm-url "
fi

if [ -n "$issues" ]; then
    echo "OSAF MONITOR: ISSUES — $issues"
    echo "img-src: $img_src"
    echo "tile fetch: $tile"
    exit 1
fi
exit 0
