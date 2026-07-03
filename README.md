# Bildschirmprogramm

Eigenes Dashboard für den Raspberry Pi (Ersatz für MagicMirror): Kalender (mit Start- UND Endzeit), Wetter (Open-Meteo) und ein Admin-GUI zur Konfiguration übers Netzwerk.

## Lokale Entwicklung (Windows)

```
python -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt
.venv\Scripts\python -m uvicorn app.main:app --reload
```

- Kiosk-Ansicht: http://localhost:8000/
- Admin-GUI: http://localhost:8000/admin

Tests: `.venv\Scripts\python -m pytest`

## Installation auf dem Raspberry Pi

Für die eigene Installation (auch für Freunde, die das Projekt selbst nutzen wollen) reicht ein `git clone` + ein Setup-Skript:

```
git clone <repo-url> ~/Bildschirmprogramm
cd ~/Bildschirmprogramm
./install.sh
```

`install.sh` legt die virtualenv an, installiert die Abhängigkeiten und richtet den `dashboard-backend`-systemd-Service ein. Jede Installation hat ihre eigene, nicht versionierte `data/settings.json` - Kalenderquellen, Wetter-Ort etc. werden individuell übers Admin-GUI eingerichtet und landen nicht im Git-Repo.

Danach einmalig manuell (abhängig vom Pi):

1. Admin-GUI von einem anderen PC im selben Netzwerk unter `http://<pi-hostname-oder-ip>:8000/admin` öffnen und Kalenderquellen/Wetter-Ort einrichten.
2. Kiosk-Autostart einrichten (Bookworm/labwc): Inhalt von `deploy/labwc-autostart.snippet` an `~/.config/labwc/autostart` anhängen. Läuft der Pi noch auf X11 (ältere Pi OS-Version), stattdessen eine systemd-User-Unit analog zu `deploy/dashboard-backend.service` für `deploy/kiosk.sh` einrichten.
3. Bildschirmschoner deaktivieren: `raspi-config` -> Display Options -> Screen Blanking -> No.
4. Neu starten und prüfen, dass die Kiosk-Ansicht automatisch erscheint.

### Updates

```
cd ~/Bildschirmprogramm
git pull
./install.sh
sudo systemctl restart dashboard-backend
```
