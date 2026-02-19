from datetime import date

import pytest

from src.utils.date_utils import in_date_range, parse_cli_date, parse_x_created_at


def test_parse_cli_date_supports_underscore_format() -> None:
    assert parse_cli_date("2021_9_1") == date(2021, 9, 1)


def test_parse_cli_date_rejects_invalid_input() -> None:
    with pytest.raises(ValueError):
        parse_cli_date("2021-09-01")


def test_in_date_range_is_inclusive_for_start_and_end_day() -> None:
    start = date(2021, 9, 1)
    end = date(2021, 9, 1)
    created_at = parse_x_created_at("Wed Sep 01 01:30:00 +0000 2021")

    assert in_date_range(created_at, start, end, "Asia/Shanghai")


def test_in_date_range_returns_false_outside_window() -> None:
    start = date(2021, 9, 1)
    end = date(2021, 9, 30)
    created_at = parse_x_created_at("Sun Oct 03 01:30:00 +0000 2021")

    assert not in_date_range(created_at, start, end, "Asia/Shanghai")
