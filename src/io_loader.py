"""Load accounts and keyword input files."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable
from urllib.parse import urlparse


@dataclass(frozen=True)
class AccountSpec:
    """Single account target."""

    url: str
    handle: str


_HANDLE_RE = re.compile(r"^[A-Za-z0-9_]{1,15}$")
_KEYWORD_PART_SPLIT_RE = re.compile(r"[\s,，+]+")


def _iter_clean_lines(lines: Iterable[str]) -> Iterable[str]:
    for line in lines:
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        yield value


def _extract_handle(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"Invalid account URL scheme: {url}")
    if parsed.netloc.lower() not in {"x.com", "www.x.com", "twitter.com", "www.twitter.com"}:
        raise ValueError(f"Account URL must point to x.com/twitter.com: {url}")

    path = parsed.path.strip("/")
    if not path:
        raise ValueError(f"Missing account handle in URL: {url}")
    handle = path.split("/", maxsplit=1)[0]
    if not _HANDLE_RE.match(handle):
        raise ValueError(f"Invalid account handle '{handle}' from URL: {url}")
    return handle


def load_accounts(lines: Iterable[str]) -> list[AccountSpec]:
    """Load account URLs and convert into account specs."""
    result: list[AccountSpec] = []
    seen: set[str] = set()
    for url in _iter_clean_lines(lines):
        handle = _extract_handle(url)
        dedupe_key = handle.casefold()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        result.append(AccountSpec(url=url, handle=handle))
    return result


def load_keywords(lines: Iterable[str]) -> list[str]:
    """Load keyword list with stable dedupe."""
    result: list[str] = []
    seen: set[str] = set()
    for keyword in _iter_clean_lines(lines):
        normalized = _normalize_keyword_rule(keyword)
        if not normalized:
            continue
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result


def _normalize_keyword_rule(raw: str) -> str:
    parts = [part for part in _KEYWORD_PART_SPLIT_RE.split(raw.strip()) if part]
    return " ".join(parts)
