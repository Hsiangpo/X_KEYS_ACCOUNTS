import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import quality_gate  # noqa: E402


def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class QualityGateTestCase(unittest.TestCase):
    def test_pass_with_small_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_file(root / "ok.py", "def ok():\n    return 1\n")
            report = quality_gate.collect_report(root, 1000, 200, 10)
            self.assertFalse(report.has_violations())

    def test_detect_file_line_violation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_file(root / "big.md", "\n".join("x" for _ in range(1001)))
            report = quality_gate.collect_report(root, 1000, 200, 10)
            self.assertEqual(len(report.file_violations), 1)
            self.assertEqual(report.file_violations[0].path, "big.md")

    def test_detect_function_line_violation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            body = "\n".join(f"    value_{index} = {index}" for index in range(205))
            write_file(root / "long_func.py", f"def too_long():\n{body}\n    return 1\n")
            report = quality_gate.collect_report(root, 1000, 200, 10)
            self.assertEqual(len(report.function_violations), 1)
            self.assertEqual(report.function_violations[0].name, "too_long")

    def test_detect_directory_file_count_violation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for index in range(11):
                write_file(root / "many" / f"file_{index}.md", "ok\n")
            report = quality_gate.collect_report(root, 1000, 200, 10)
            self.assertEqual(len(report.directory_violations), 1)
            self.assertEqual(report.directory_violations[0].path, "many")


if __name__ == "__main__":
    unittest.main(verbosity=2)
