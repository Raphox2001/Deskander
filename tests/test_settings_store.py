import json

from app.models import CalendarSource, Settings
from app.settings_store import SettingsStore


def test_first_load_creates_file_from_defaults(tmp_path):
    settings_path = tmp_path / "settings.json"
    store = SettingsStore(settings_path=settings_path, defaults_path=tmp_path / "missing.json")

    assert settings_path.exists()
    settings = store.load()
    assert settings.calendar_sources == []
    assert settings.calendar_refresh_minutes == 15
    assert settings.weather.place_name == "Berlin"


def test_save_and_reload_roundtrip(tmp_path):
    settings_path = tmp_path / "settings.json"
    store = SettingsStore(settings_path=settings_path, defaults_path=tmp_path / "missing.json")

    settings = store.load()
    settings.calendar_sources.append(
        CalendarSource(name="Arbeit", url="https://example.com/a.ics", color="#ff0000")
    )
    settings.calendar_refresh_minutes = 5
    settings.weather.place_name = "Muenchen"
    store.save(settings)

    reloaded = store.load()
    assert reloaded.calendar_refresh_minutes == 5
    assert reloaded.weather.place_name == "Muenchen"
    assert len(reloaded.calendar_sources) == 1
    assert reloaded.calendar_sources[0].name == "Arbeit"
    assert reloaded.calendar_sources[0].color == "#ff0000"


def test_missing_nested_fields_are_merged_with_defaults(tmp_path):
    settings_path = tmp_path / "settings.json"
    # Simulate an older settings.json missing a newer nested field
    settings_path.write_text(
        json.dumps({"calendar_sources": [], "calendar_refresh_minutes": 30, "weather": {}}),
        encoding="utf-8",
    )
    store = SettingsStore(settings_path=settings_path, defaults_path=tmp_path / "missing.json")

    settings = store.load()
    assert settings.calendar_refresh_minutes == 30
    # weather block was empty in the saved file - defaults must fill it in
    assert settings.weather.latitude == 52.52
    assert settings.display.timezone == "Europe/Berlin"


def test_old_settings_without_reminder_gets_merged_defaults(tmp_path):
    settings_path = tmp_path / "settings.json"
    # An older settings.json predating the reminder feature: no "reminder" key.
    settings_path.write_text(
        json.dumps({"calendar_sources": [], "calendar_refresh_minutes": 7}),
        encoding="utf-8",
    )
    store = SettingsStore(settings_path=settings_path, defaults_path=tmp_path / "missing.json")

    settings = store.load()
    assert settings.calendar_refresh_minutes == 7
    assert settings.reminder.enabled is False
    assert settings.reminder.lead_minutes == 30
    assert settings.reminder.repeat is True


def test_partial_reminder_block_is_deep_merged(tmp_path):
    settings_path = tmp_path / "settings.json"
    # Only some reminder fields present -> the rest come from defaults (deep
    # merge), rather than the whole block being dropped.
    settings_path.write_text(
        json.dumps({"calendar_sources": [], "reminder": {"enabled": True, "lead_minutes": 45}}),
        encoding="utf-8",
    )
    store = SettingsStore(settings_path=settings_path, defaults_path=tmp_path / "missing.json")

    settings = store.load()
    assert settings.reminder.enabled is True
    assert settings.reminder.lead_minutes == 45
    assert settings.reminder.visible_seconds == 60
    assert settings.reminder.repeat_interval_minutes == 5


def test_atomic_write_leaves_no_tmp_file_behind(tmp_path):
    settings_path = tmp_path / "settings.json"
    store = SettingsStore(settings_path=settings_path, defaults_path=tmp_path / "missing.json")
    store.save(Settings())

    tmp_file = settings_path.with_name(settings_path.name + ".tmp")
    assert not tmp_file.exists()
    assert settings_path.exists()
