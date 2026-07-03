from __future__ import annotations

import socket


def get_lan_ip() -> str:
    """Best-effort LAN-facing IP address, for showing the admin GUI URL on
    the kiosk display. Uses the standard "connect a UDP socket, no packets
    actually sent" trick to ask the OS which local address it would use to
    reach the internet - works even without real internet access."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()
