"""Lightweight stream tee helpers for crawler runtime logs."""

from __future__ import annotations

import sys
from typing import TextIO


class TeeStream:
    """Write the same data into multiple text streams."""

    def __init__(self, *targets: TextIO) -> None:
        self._targets: tuple[TextIO, ...] = tuple(targets)

    def write(self, data: str) -> int:
        for target in self._targets:
            target.write(data)
        return len(data)

    def flush(self) -> None:
        for target in self._targets:
            target.flush()

    def isatty(self) -> bool:
        # Keep terminal behavior when at least one target is an interactive tty.
        return any(getattr(target, "isatty", lambda: False)() for target in self._targets)

    @property
    def encoding(self) -> str:
        return getattr(sys.stdout, "encoding", "utf-8")
