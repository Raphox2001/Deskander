from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

PROJECT_DIR = Path(__file__).resolve().parent.parent
GIT_TIMEOUT_SECONDS = 30
INSTALL_TIMEOUT_SECONDS = 300


def _run(args: list, timeout: int = GIT_TIMEOUT_SECONDS) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _commit_info(ref: str) -> Optional[dict]:
    result = _run(["git", "log", "-1", "--format=%h%x1f%cI%x1f%s", ref])
    if result.returncode != 0 or not result.stdout.strip():
        return None
    short_hash, date, message = result.stdout.strip().split("\x1f", 2)
    return {"hash": short_hash, "date": date, "message": message}


def check_for_updates() -> dict:
    """Fetch the remote and compare HEAD to origin/main.

    Never raises - a Pi without network access or a non-git checkout should
    show an error in the admin GUI rather than break the update page.
    """
    fetch = _run(["git", "fetch", "origin", "main"])
    if fetch.returncode != 0:
        return {"error": fetch.stderr.strip() or "git fetch fehlgeschlagen"}

    current = _commit_info("HEAD")
    remote = _commit_info("origin/main")
    if current is None or remote is None:
        return {"error": "Konnte Commit-Informationen nicht lesen"}

    behind = _run(["git", "rev-list", "--count", "HEAD..origin/main"])
    commits_behind = int(behind.stdout.strip()) if behind.stdout.strip().isdigit() else 0

    return {
        "current": current,
        "remote": remote,
        "commits_behind": commits_behind,
        "up_to_date": commits_behind == 0,
    }


def apply_update() -> None:
    """Pull the latest main, re-run install.sh, then restart the backend
    service a couple seconds later (detached, so this process - which the
    restart will kill - has time to finish handling the current request)."""
    try:
        pull = _run(["git", "pull", "origin", "main"], timeout=60)
        logger.info("update: git pull: %s", pull.stdout.strip() or pull.stderr.strip())
        if pull.returncode != 0:
            logger.error("update: git pull failed, aborting before install.sh/restart")
            return

        install = _run(["./install.sh"], timeout=INSTALL_TIMEOUT_SECONDS)
        logger.info("update: install.sh: %s", install.stdout.strip() or install.stderr.strip())
        if install.returncode != 0:
            logger.error("update: install.sh failed (code %s) - restarting anyway so the service isn't left down", install.returncode)

        subprocess.Popen(
            ["sh", "-c", "sleep 2 && sudo systemctl restart dashboard-backend"],
            cwd=PROJECT_DIR,
            start_new_session=True,
        )
    except Exception:
        logger.exception("Update failed")
