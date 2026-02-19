from pathlib import Path

import pytest

from src.io_loader import AccountSpec, load_accounts, load_keywords


def test_load_accounts_extracts_handles() -> None:
    lines = [
        "https://x.com/NBCOlympics",
        "https://x.com/TeamUSA/",
    ]

    accounts = load_accounts(lines)

    assert accounts == [
        AccountSpec(url="https://x.com/NBCOlympics", handle="NBCOlympics"),
        AccountSpec(url="https://x.com/TeamUSA/", handle="TeamUSA"),
    ]


def test_load_accounts_rejects_invalid_host() -> None:
    with pytest.raises(ValueError):
        load_accounts(["https://example.com/not-x"])


def test_load_keywords_removes_blank_lines_and_deduplicates() -> None:
    keywords = load_keywords(["alpha", "", " beta ", "alpha", "  "])

    assert keywords == ["alpha", "beta"]


def test_load_keywords_normalizes_multi_term_rules() -> None:
    keywords = load_keywords(
        [
            "China Climate",
            "China，Climate",
            "China, Climate",
            "China+Climate",
            "China + Climate",
            "China   Energy",
        ]
    )

    assert keywords == ["China Climate", "China Energy"]


def test_read_helpers_round_trip(tmp_path: Path) -> None:
    accounts_file = tmp_path / "Accounts.txt"
    keys_file = tmp_path / "Keys.txt"
    accounts_file.write_text("https://x.com/NBCOlympics\n", encoding="utf-8")
    keys_file.write_text("hello\nhello\nworld\nchina，climate\nchina+climate\n", encoding="utf-8")

    loaded_accounts = load_accounts(accounts_file.read_text(encoding="utf-8").splitlines())
    loaded_keys = load_keywords(keys_file.read_text(encoding="utf-8").splitlines())

    assert loaded_accounts[0].handle == "NBCOlympics"
    assert loaded_keys == ["hello", "world", "china climate"]
