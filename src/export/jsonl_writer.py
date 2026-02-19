"""Streaming JSONL writer."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


class JsonlWriter:
    """Write output rows to per-run JSONL file."""

    def __init__(self, output_dir: Path):
        output_dir.mkdir(parents=True, exist_ok=True)
        self.run_id = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        self.run_dir = output_dir / self.run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.output_path = self.run_dir / "data.jsonl"
        self._fp = self.output_path.open("w", encoding="utf-8")

    def write(self, row: dict) -> None:
        self._fp.write(json.dumps(row, ensure_ascii=False) + "\n")
        self._fp.flush()

    def close(self) -> None:
        self._fp.close()
