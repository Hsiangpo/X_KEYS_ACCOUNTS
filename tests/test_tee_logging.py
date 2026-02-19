from __future__ import annotations

import io
from pathlib import Path

from src.logging_utils import TeeStream


def test_teestream_writes_to_all_targets(tmp_path: Path) -> None:
    sink1 = io.StringIO()
    sink2 = io.StringIO()
    log_path = tmp_path / "crawl.log"
    with log_path.open("w", encoding="utf-8") as fp:
        tee = TeeStream(sink1, sink2, fp)
        tee.write("hello\n")
        tee.write("world\n")
        tee.flush()

    assert sink1.getvalue() == "hello\nworld\n"
    assert sink2.getvalue() == "hello\nworld\n"
    assert log_path.read_text(encoding="utf-8") == "hello\nworld\n"
