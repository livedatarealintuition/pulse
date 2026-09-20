#!/bin/sh
# Pulse container entrypoint — put the static assets where the app expects them.
#
# pulse_free.py resolves one BASE_DIR from $PULSE_HOME (falling back to the
# script directory) and uses it for BOTH the JSON data files and the assets it
# serves at /pulse.css and /pulse_logo.jpg. With PULSE_HOME=/data the assets
# must exist there too, so refresh them from the image on every start.
set -e

mkdir -p "$PULSE_HOME"
cp -f /app/pulse.css /app/pulse_logo.jpg "$PULSE_HOME"/ 2>/dev/null || true

exec "$@"
