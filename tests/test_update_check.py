from app import scheduler
from app.cache import DisplayCache


def test_display_cache_update_status_roundtrip():
    cache = DisplayCache()
    # Fresh cache defaults to "no update", exposed on every get().
    assert cache.get()["update_available"] is False
    assert cache.get()["update_info"] is None

    info = {"commits_behind": 3, "up_to_date": False}
    cache.set_update_status(True, info)
    data = cache.get()
    assert data["update_available"] is True
    assert data["update_info"] == info


def test_check_update_job_flags_available_when_behind(monkeypatch):
    monkeypatch.setattr(
        scheduler,
        "check_for_updates",
        lambda: {"up_to_date": False, "commits_behind": 2},
    )
    captured = {}
    monkeypatch.setattr(
        scheduler.display_cache,
        "set_update_status",
        lambda available, info: captured.update(available=available, info=info),
    )

    scheduler.check_update_job(scheduler=None)

    assert captured["available"] is True
    assert captured["info"]["commits_behind"] == 2


def test_check_update_job_clears_flag_when_up_to_date(monkeypatch):
    monkeypatch.setattr(
        scheduler,
        "check_for_updates",
        lambda: {"up_to_date": True, "commits_behind": 0},
    )
    captured = {}
    monkeypatch.setattr(
        scheduler.display_cache,
        "set_update_status",
        lambda available, info: captured.update(available=available, info=info),
    )

    scheduler.check_update_job(scheduler=None)

    assert captured["available"] is False
    assert captured["info"] is None


def test_check_update_job_leaves_status_untouched_on_error(monkeypatch):
    monkeypatch.setattr(
        scheduler,
        "check_for_updates",
        lambda: {"error": "git fetch fehlgeschlagen"},
    )
    called = False

    def _fail(available, info):
        nonlocal called
        called = True

    monkeypatch.setattr(scheduler.display_cache, "set_update_status", _fail)

    scheduler.check_update_job(scheduler=None)

    # A failed check must not flip an existing "update available" state.
    assert called is False
