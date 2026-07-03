#!/bin/sh
# One-shot setup for a fresh Raspberry Pi checkout:
#   git clone https://github.com/Raphox2001/Deskander.git ~/Deskander
#   cd ~/Deskander
#   ./install.sh
#
# Safe to re-run after `git pull` to pick up dependency or service changes.
set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVICE_NAME=dashboard-backend

echo "==> Virtualenv"
if [ ! -d "$PROJECT_DIR/.venv" ]; then
  python3 -m venv "$PROJECT_DIR/.venv"
fi
"$PROJECT_DIR/.venv/bin/pip" install --upgrade pip -q
"$PROJECT_DIR/.venv/bin/pip" install -r "$PROJECT_DIR/requirements.txt" -q

echo "==> systemd service"
sed "s#/home/pi/Deskander#$PROJECT_DIR#g; s#User=pi#User=$(whoami)#" \
  "$PROJECT_DIR/deploy/dashboard-backend.service" | sudo tee /etc/systemd/system/$SERVICE_NAME.service > /dev/null
sudo systemctl daemon-reload
sudo systemctl enable --now $SERVICE_NAME

echo "==> Kiosk script"
chmod +x "$PROJECT_DIR/deploy/kiosk.sh"

AUTOSTART_LINE="$PROJECT_DIR/deploy/kiosk.sh &"
if [ -d "$HOME/.config/labwc" ]; then
  touch "$HOME/.config/labwc/autostart"
  if ! grep -qF "$AUTOSTART_LINE" "$HOME/.config/labwc/autostart"; then
    echo "$AUTOSTART_LINE" >> "$HOME/.config/labwc/autostart"
    echo "==> Kiosk-Autostart zu ~/.config/labwc/autostart hinzugefügt"
  else
    echo "==> Kiosk-Autostart bereits vorhanden"
  fi
else
  echo "==> Kein ~/.config/labwc gefunden (kein labwc/Wayland-Desktop?) - Autostart manuell einrichten, siehe README"
fi

echo "==> Done."
echo "Backend läuft: sudo systemctl status $SERVICE_NAME"
echo "Admin-GUI: http://$(hostname -I | awk '{print $1}'):8000/admin"
echo ""
echo "Noch manuell (einmalig):"
echo "  raspi-config -> Display Options -> Screen Blanking -> No"
echo "  sudo reboot"
