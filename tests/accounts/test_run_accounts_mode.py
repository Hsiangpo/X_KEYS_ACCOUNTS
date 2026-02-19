import json
from pathlib import Path

import run as run_module


def _write_cookie_file(path: Path, cookies: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cookies, ensure_ascii=False), encoding="utf-8")


def test_is_accounts_mode_detects_command() -> None:
    assert run_module._is_accounts_mode(["accounts"]) is True
    assert run_module._is_accounts_mode(["ACCOUNTS"]) is True
    assert run_module._is_accounts_mode(["2025_1_1", "2025_1_2"]) is False
    assert run_module._is_accounts_mode([]) is False


def test_write_cookie_pool_file_excludes_primary(tmp_path: Path) -> None:
    primary = tmp_path / "state" / "cookies.json"
    second = tmp_path / "state" / "cookies_2.json"
    third = tmp_path / "state" / "cookies_3.json"
    pool_file = tmp_path / "docs" / "CookiesPool.txt"

    run_module._write_cookie_pool_file(
        pool_file=pool_file,
        primary_path=primary,
        slot_paths=[primary, second, third],
    )

    lines = pool_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert any("cookies_2.json" in line for line in lines)
    assert any("cookies_3.json" in line for line in lines)

    loaded = run_module._load_slot_paths(primary_path=primary, pool_file=pool_file)
    assert loaded == [primary, second, third]


def test_collect_slot_statuses_reports_probe_and_missing_cookie(
    tmp_path: Path,
    monkeypatch,
) -> None:
    active = tmp_path / "state" / "active.json"
    inactive = tmp_path / "state" / "inactive.json"
    missing = tmp_path / "state" / "missing.json"
    _write_cookie_file(
        active,
        [
            {"name": "auth_token", "value": "ok"},
            {"name": "ct0", "value": "csrf"},
        ],
    )
    _write_cookie_file(
        inactive,
        [
            {"name": "guest_id", "value": "g"},
        ],
    )

    def _fake_probe(cookies: list[dict]) -> bool:
        return any(cookie.get("name") == "auth_token" and cookie.get("value") == "ok" for cookie in cookies)

    monkeypatch.setattr(run_module, "_probe_cookies", _fake_probe)

    statuses = run_module._collect_slot_statuses([active, inactive, missing])
    assert [status.slot_id for status in statuses] == [1, 2, 3]
    assert statuses[0].probe_ok is True
    assert statuses[0].error == ""
    assert statuses[1].probe_ok is False
    assert statuses[1].error == "auth_cookie_missing"
    assert statuses[2].probe_ok is False
    assert statuses[2].error == "cookie_missing"


def test_run_accounts_mode_exits_from_menu(
    tmp_path: Path,
    monkeypatch,
) -> None:
    pool_file = tmp_path / "docs" / "CookiesPool.txt"
    cookies_file = tmp_path / "state" / "cookies.json"
    monkeypatch.setattr(run_module, "DEFAULT_COOKIES_POOL_MANAGE_FILE", pool_file)
    monkeypatch.setattr(run_module, "DEFAULT_COOKIES_FILE", cookies_file)
    monkeypatch.setattr("builtins.input", lambda _: "5")

    assert run_module._run_accounts_mode() == 0


def test_main_rejects_accounts_mode(monkeypatch, capsys) -> None:
    monkeypatch.setattr(run_module.sys, "argv", ["run.py", "accounts"])

    code = run_module.main()
    captured = capsys.readouterr()

    assert code == 2
    assert "暂时禁用会话池管理模式" in captured.err


def test_main_rejects_cookies_pool_arg(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        run_module.sys,
        "argv",
        [
            "run.py",
            "2025_1_1",
            "2025_1_2",
            "--cookies-pool-file",
            "docs/CookiesPool.txt",
        ],
    )

    code = run_module.main()
    captured = capsys.readouterr()

    assert code == 2
    assert "暂时禁用会话池功能" in captured.err
