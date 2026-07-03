#!/bin/sh
# Launches Chromium in kiosk mode against the local dashboard backend and
# restarts it automatically if it crashes/is killed, so the display keeps
# working unattended (no keyboard/mouse on the Pi).

URL="http://localhost:8000/"

# Prevent the screen from blanking/sleeping (belt-and-suspenders; also set
# via raspi-config -> Display Options -> Screen Blanking -> No).
xset -dpms 2>/dev/null
xset s off 2>/dev/null
xset s noblank 2>/dev/null

while true; do
  chromium-browser \
    --kiosk \
    --noerrdialogs \
    --disable-infobars \
    --no-first-run \
    --disable-translate \
    --overscroll-history-navigation=0 \
    --ozone-platform=wayland \
    "$URL"
  sleep 5
done
