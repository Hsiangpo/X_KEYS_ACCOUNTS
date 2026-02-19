import json
from pathlib import Path

from src.export.jsonl_writer import JsonlWriter


def test_jsonl_writer_creates_run_directory_output_file(tmp_path: Path) -> None:
    writer = JsonlWriter(output_dir=tmp_path)

    writer.write({"account": "NBCOlympics", "keyword": "abc"})
    writer.close()

    assert writer.output_path.exists()
    assert writer.output_path.name == "data.jsonl"
    assert writer.output_path.parent == writer.run_dir
    lines = writer.output_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["account"] == "NBCOlympics"
