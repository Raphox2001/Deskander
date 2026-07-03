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
  chromium \
    --kiosk \
    --noerrdialogs \
    --disable-infobars \
    --no-first-run \
    --disable-translate \
    --overscroll-history-navigation=0 \
    --ozone-platform=wayland \
    --disable-gpu \
    --disable-gpu-compositing \
    --password-store=basic \
    --disable-features=Translate \
    "$URL"
  # --disable-gpu(-compositing): avoids a blank/white render seen on this
  #   Pi's Wayland+GPU-rasterization combo; --password-store=basic skips
  #   Chromium trying to use the (headless, keyboard-less) OS keyring;
  #   --disable-features=Translate suppresses the "translate this page?"
  #   bubble (page is German, browser UI language is English) - the older
  #   --disable-translate switch alone no longer suppresses it.
  sleep 5
done
