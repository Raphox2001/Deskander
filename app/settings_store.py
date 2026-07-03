from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Dict

from app.models import Settings

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SETTINGS_PATH = DATA_DIR / "settings.json"
DEFAULTS_PATH = DATA_DIR / "settings.default.json"


class SettingsStore:
    """Reads/writes app settings from a single JSON file.

    One writer at a time is assumed (the admin GUI on the LAN), guarded by a
    lock so scheduler reads never race a concurrent admin save. Merges saved
    settings on top of the shipped defaults on every load, so a settings.json
    from an older version that's missing newer fields still loads cleanly.
    """

    def __init__(
        self,
        settings_path: Path = SETTINGS_PATH,
        defaults_path: Path = DEFAULTS_PATH,
    ) -> None:
        self._settings_path = settings_path
        self._defaults_path = defaults_path
        self._lock = threading.Lock()
        self._ensure_file_exists()

    def _ensure_file_exists(self) -> None:
        if not self._settings_path.exists():
            self._atomic_write(self._load_defaults())

    def _load_defaults(self) -> Dict[str, Any]:
        if self._defaults_path.exists():
            with open(self._defaults_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return Settings().model_dump()

    def load(self) -> Settings:
        with self._lock:
            with open(self._settings_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            merged = self._merge_defaults(raw)
            return Settings.model_validate(merged)

    def _merge_defaults(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        defaults = self._load_defaults()
        merged = {**defaults, **raw}
        for key in ("weather", "display"):
            merged[key] = {**defaults.get(key, {}), **raw.get(key, {})}
        return merged

    def save(self, settings: Settings) -> None:
        with self._lock:
            self._atomic_write(settings.model_dump())

    def _atomic_write(self, data: Dict[str, Any]) -> None:
        self._settings_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._settings_path.with_name(self._settings_path.name + ".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, self._settings_path)


settings_store = SettingsStore()
