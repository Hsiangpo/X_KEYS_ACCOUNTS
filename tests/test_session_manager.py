from pathlib import Path

import pytest

from src.auth.session_manager import SessionManager


class _FakeChromium:
    def __init__(self, fail_channels: set[str] | None = None, fallback_fails: bool = False) -> None:
        self.fail_channels = fail_channels or set()
        self.fallback_fails = fallback_fails
        self.calls: list[dict] = []

    def launch(self, **kwargs):
        self.calls.append(kwargs)
        channel = kwargs.get("channel")
        if channel is None and self.fallback_fails:
            raise RuntimeError("fallback launch failed")
        if channel in self.fail_channels:
            raise RuntimeError(f"channel {channel} failed")
        return object()


class _FakePlaywright:
    def __init__(self, chromium: _FakeChromium) -> None:
        self.chromium = chromium


def _manager(channels: tuple[str, ...]) -> SessionManager:
    return SessionManager(cookies_path=Path("state/cookies.json"), browser_channels=channels)


def test_launch_browser_prefers_chrome_channel() -> None:
    chromium = _FakeChromium()
    browser = _manager(("chrome", "msedge"))._launch_browser(_FakePlaywright(chromium))

    assert browser is not None
    assert chromium.calls[0]["channel"] == "chrome"


def test_launch_browser_falls_back_to_second_channel() -> None:
    chromium = _FakeChromium(fail_channels={"chrome"})
    browser = _manager(("chrome", "msedge"))._launch_browser(_FakePlaywright(chromium))

    assert browser is not None
    assert chromium.calls[0]["channel"] == "chrome"
    assert chromium.calls[1]["channel"] == "msedge"


def test_launch_browser_uses_bundled_chromium_when_channels_fail() -> None:
    chromium = _FakeChromium(fail_channels={"chrome", "msedge"})
    browser = _manager(("chrome", "msedge"))._launch_browser(_FakePlaywright(chromium))

    assert browser is not None
    assert chromium.calls[-1].get("channel") is None


def test_launch_browser_raises_if_all_launch_attempts_fail() -> None:
    chromium = _FakeChromium(fail_channels={"chrome"}, fallback_fails=True)

    with pytest.raises(RuntimeError):
        _manager(("chrome",))._launch_browser(_FakePlaywright(chromium))


def test_refresh_cookies_soft_passes_when_probe_fails_but_core_auth_cookies_exist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _manager(("chrome",))
    cookies = [
        {"name": "auth_token", "value": "a"},
        {"name": "ct0", "value": "b"},
    ]

    monkeypatch.setattr(manager, "_interactive_login", lambda: cookies)
    monkeypatch.setattr(manager, "save_cookies", lambda _: None)

    result = manager.refresh_cookies(lambda _: False)

    assert result == cookies


def test_refresh_cookies_still_fails_without_core_auth_cookies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _manager(("chrome",))
    cookies = [
        {"name": "guest_id", "value": "guest"},
    ]

    monkeypatch.setattr(manager, "_interactive_login", lambda: cookies)
    monkeypatch.setattr(manager, "save_cookies", lambda _: None)

    with pytest.raises(RuntimeError):
        manager.refresh_cookies(lambda _: False)


def test_ensure_cookies_reuses_existing_core_auth_cookies_when_probe_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _manager(("chrome",))
    existing = [
        {"name": "auth_token", "value": "a"},
        {"name": "ct0", "value": "b"},
    ]

    monkeypatch.setattr(manager, "load_cookies", lambda: existing)
    monkeypatch.setattr(manager, "refresh_cookies", lambda probe: (_ for _ in ()).throw(RuntimeError("should not refresh")))

    result = manager.ensure_cookies(lambda _: False)

    assert result == existing


def test_ensure_cookies_refreshes_when_no_core_auth_cookies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _manager(("chrome",))
    existing = [
        {"name": "guest_id", "value": "guest"},
    ]
    refreshed = [
        {"name": "auth_token", "value": "new-auth"},
        {"name": "ct0", "value": "new-ct0"},
    ]

    monkeypatch.setattr(manager, "load_cookies", lambda: existing)
    monkeypatch.setattr(manager, "refresh_cookies", lambda probe: refreshed)

    result = manager.ensure_cookies(lambda _: False)

    assert result == refreshed
