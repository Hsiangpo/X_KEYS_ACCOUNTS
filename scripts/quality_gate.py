from __future__ import annotations

import argparse
import ast
import os
from dataclasses import dataclass, field
from pathlib import Path


TEXT_EXTENSIONS = {
    ".py",
    ".md",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".sql",
    ".sh",
    ".ps1",
}

SKIP_DIR_NAMES = {
    "__pycache__",
    ".git",
    ".idea",
    ".vscode",
    "node_modules",
    "dist",
    "build",
    "tmp",
    "reports",
    ".venv",
    "venv",
}

SKIP_FILE_SUFFIXES = {".pyc", ".pyo", ".pyd"}


@dataclass(frozen=True)
class FileViolation:
    path: str
    lines: int
    limit: int


@dataclass(frozen=True)
class FunctionViolation:
    path: str
    name: str
    start: int
    lines: int
    limit: int


@dataclass(frozen=True)
class DirectoryViolation:
    path: str
    files: int
    limit: int


@dataclass(frozen=True)
class EncodingViolation:
    path: str
    detail: str


@dataclass
class GateReport:
    file_violations: list[FileViolation] = field(default_factory=list)
    function_violations: list[FunctionViolation] = field(default_factory=list)
    directory_violations: list[DirectoryViolation] = field(default_factory=list)
    encoding_violations: list[EncodingViolation] = field(default_factory=list)

    def has_violations(self) -> bool:
        return any(
            (
                self.file_violations,
                self.function_violations,
                self.directory_violations,
                self.encoding_violations,
            )
        )


class FunctionCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.class_stack: list[str] = []
        self.function_stack: list[str] = []
        self.functions: list[tuple[str, int, int]] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.class_stack.append(node.name)
        self.generic_visit(node)
        self.class_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        scope = [*self.class_stack, *self.function_stack, node.name]
        full_name = ".".join(scope)
        end_line = node.end_lineno or node.lineno
        self.functions.append((full_name, node.lineno, end_line))
        self.function_stack.append(node.name)
        self.generic_visit(node)
        self.function_stack.pop()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="protocol-crawler 门禁检查")
    parser.add_argument("--root", default=".", help="待检查根目录")
    parser.add_argument("--max-file-lines", type=int, default=1000, help="单文件最大行数")
    parser.add_argument("--max-func-lines", type=int, default=200, help="单函数最大行数")
    parser.add_argument(
        "--max-files-per-dir",
        type=int,
        default=10,
        help="单目录直接文件数上限",
    )
    return parser.parse_args()


def should_skip_dir(name: str) -> bool:
    if name.startswith(".") and name not in {".", ".."}:
        return True
    return name in SKIP_DIR_NAMES


def should_skip_file(path: Path) -> bool:
    return path.suffix.lower() in SKIP_FILE_SUFFIXES


def iter_walk(root: Path) -> list[tuple[Path, list[str], list[str]]]:
    rows: list[tuple[Path, list[str], list[str]]] = []
    for current, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(name for name in dirnames if not should_skip_dir(name))
        rows.append((Path(current), dirnames, sorted(filenames)))
    return rows


def to_relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def count_lines(text: str) -> int:
    if text == "":
        return 0
    return len(text.splitlines()) or 1


def load_utf8(path: Path) -> tuple[str | None, str | None]:
    try:
        return path.read_text(encoding="utf-8"), None
    except UnicodeDecodeError as error:
        return None, str(error)


def collect_file_line_violations(
    root: Path,
    max_file_lines: int,
) -> tuple[list[FileViolation], list[EncodingViolation]]:
    line_violations: list[FileViolation] = []
    encoding_violations: list[EncodingViolation] = []
    for current, _, filenames in iter_walk(root):
        for filename in filenames:
            path = current / filename
            if should_skip_file(path) or path.suffix.lower() not in TEXT_EXTENSIONS:
                continue
            text, error = load_utf8(path)
            if error:
                encoding_violations.append(
                    EncodingViolation(path=to_relative(path, root), detail=error)
                )
                continue
            lines = count_lines(text or "")
            if lines > max_file_lines:
                line_violations.append(
                    FileViolation(path=to_relative(path, root), lines=lines, limit=max_file_lines)
                )
    return sorted(line_violations, key=lambda item: item.path), sorted(
        encoding_violations, key=lambda item: item.path
    )


def collect_function_violations(root: Path, max_func_lines: int) -> list[FunctionViolation]:
    violations: list[FunctionViolation] = []
    for current, _, filenames in iter_walk(root):
        for filename in filenames:
            path = current / filename
            if should_skip_file(path) or path.suffix.lower() != ".py":
                continue
            text, error = load_utf8(path)
            if error:
                continue
            tree = ast.parse(text or "", filename=str(path))
            collector = FunctionCollector()
            collector.visit(tree)
            for name, start, end in collector.functions:
                lines = end - start + 1
                if lines > max_func_lines:
                    violations.append(
                        FunctionViolation(
                            path=to_relative(path, root),
                            name=name,
                            start=start,
                            lines=lines,
                            limit=max_func_lines,
                        )
                    )
    return sorted(violations, key=lambda item: (item.path, item.start, item.name))


def collect_directory_violations(root: Path, max_files_per_dir: int) -> list[DirectoryViolation]:
    violations: list[DirectoryViolation] = []
    for current, _, filenames in iter_walk(root):
        real_files = [
            name for name in filenames if not should_skip_file(current / name) and not name.startswith(".")
        ]
        if len(real_files) > max_files_per_dir:
            violations.append(
                DirectoryViolation(
                    path=to_relative(current, root),
                    files=len(real_files),
                    limit=max_files_per_dir,
                )
            )
    return sorted(violations, key=lambda item: item.path)


def collect_report(
    root: Path,
    max_file_lines: int,
    max_func_lines: int,
    max_files_per_dir: int,
) -> GateReport:
    file_violations, encoding_violations = collect_file_line_violations(root, max_file_lines)
    function_violations = collect_function_violations(root, max_func_lines)
    directory_violations = collect_directory_violations(root, max_files_per_dir)
    return GateReport(
        file_violations=file_violations,
        function_violations=function_violations,
        directory_violations=directory_violations,
        encoding_violations=encoding_violations,
    )


def print_report(
    report: GateReport,
    max_file_lines: int,
    max_func_lines: int,
    max_files_per_dir: int,
) -> None:
    if not report.has_violations():
        print(
            f"门禁通过: 文件<={max_file_lines}行, 函数<={max_func_lines}行, "
            f"目录文件数<={max_files_per_dir}"
        )
        return

    if report.encoding_violations:
        print("UTF-8 编码违规:")
        for item in report.encoding_violations:
            print(f"- {item.path}: {item.detail}")

    if report.file_violations:
        print("文件行数超限:")
        for item in report.file_violations:
            print(f"- {item.path} ({item.lines} > {item.limit})")

    if report.function_violations:
        print("函数行数超限:")
        for item in report.function_violations:
            print(f"- {item.path}:{item.start} {item.name} ({item.lines} > {item.limit})")

    if report.directory_violations:
        print("目录文件数超限:")
        for item in report.directory_violations:
            print(f"- {item.path} ({item.files} > {item.limit})")

    print("门禁失败：必须拆分模块/函数/目录，禁止删除健壮性逻辑压线。")


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    report = collect_report(
        root=root,
        max_file_lines=args.max_file_lines,
        max_func_lines=args.max_func_lines,
        max_files_per_dir=args.max_files_per_dir,
    )
    print_report(
        report=report,
        max_file_lines=args.max_file_lines,
        max_func_lines=args.max_func_lines,
        max_files_per_dir=args.max_files_per_dir,
    )
    return 1 if report.has_violations() else 0


if __name__ == "__main__":
    raise SystemExit(main())
