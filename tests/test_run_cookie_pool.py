from pathlib import Path

from run import _resolve_cookie_pool_paths


def test_resolve_cookie_pool_paths_keeps_primary_and_dedupes(tmp_path: Path) -> None:
    primary = tmp_path / "state" / "cookies.json"
    duplicate = tmp_path / "state" / "cookies.json"
    second = tmp_path / "state" / "cookies_2.json"

    paths = _resolve_cookie_pool_paths(
        primary,
        [
            str(duplicate),
            str(second),
        ],
    )

    assert paths == [primary, second]


def test_resolve_cookie_pool_paths_ignores_blank_and_comments(tmp_path: Path) -> None:
    primary = tmp_path / "state" / "cookies.json"
    second = tmp_path / "state" / "cookies_2.json"

    paths = _resolve_cookie_pool_paths(
        primary,
        [
            "",
            "   ",
            "# comment",
            f"  {second}  ",
        ],
    )

    assert paths == [primary, second]
