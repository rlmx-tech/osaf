#!/bin/bash
# Task 6: external site monitor — checks what today's two failures broke:
# (1) site up, (2) CSP still whitelists the tile host, (3) tiles actually fetch,
# (4) markers data present. Quiet on healthy (watchdog pattern), loud on drift.
set -u
BASE="https://osaf.net"
TILE_ZXY="5/10/12"
issues=""

# 1. site up
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 "$BASE/")
[ "$code" = "200" ] || issues="${issues}site-down(http=$code) "

# 2. CSP img-src still allows the bare tile host (catches CSP regressions)
CSP=$(curl -s -D - -o /dev/null --max-time 15 "$BASE/" | grep -i '^content-security-policy:' | head -1)
echo "$CSP" | grep -q 'img-src[^;]*//\?tile\.openstreetmap\.org' || \
  CSP=$(echo "$CSP" | grep -o 'img-src[^;]*')
echo "$CSP" | grep -q 'https://tile\.openstreetmap\.org' || issues="${issues}csp-missing-tile-host "
echo "$CSP" | grep -q 'cartocdn' && issues="${issues}csp-still-has-dead-carto "

# 3. tile endpoint returns an actual image (not a block page or error)
hdr=$(curl -s -o /tmp/mon_tile.bin -w '%{http_code}|%{content_type}|%{size_download}' --max-time 15 "https://tile.openstreetmap.org/$TILE_ZXY.png")
code=${hdr%%|*}
tmp=${hdr#*|}
ctype=${tmp%%|*}
case "$ctype" in
  image/png|image/jpeg|image/webp) tile_ok=1 ;;
  *) tile_ok=0; issues="${issues}tiles-bad-type($ctype) " ;;
esac
[ "$code" = "200" ] || issues="${issues}tiles-bad-status($code) "

# 4. API serving data
api=$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 "$BASE/api/v1/incidents?per_page=1")
[ "$api" = "200" ] || issues="${issues}api-down($api) "

# 5. bundle still carries the OSM tile URL (catches accidental frontend regen)
bundle=$(curl -s --max-time 15 "$BASE/assets/"$(curl -s "$BASE/" | grep -oE 'assets/index-[A-Za-z0-9_-]+\.js' | head -1 | sed 's|assets/||'))
echo "$bundle" | grep -q 'tile.openstreetmap.org' || issues="${issues}bundle-lost-osm-url "

if [ -n "$issues" ]; then
    echo "OSAF MONITOR: ISSUES — $issues"
    echo "CSP: $CSP"
    echo "tile fetch: $hdr"
    exit 1
fi
exit 0