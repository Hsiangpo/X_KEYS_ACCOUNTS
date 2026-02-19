from __future__ import annotations

import argparse
from datetime import date
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Callable

from src.auth.session_manager import SessionManager
from src.client.x_protocol_client import XProtocolClient
from src.config import (
    DEFAULT_ACCOUNTS_FILE,
    DEFAULT_COOKIES_FILE,
    DOCS_DIR,
    DEFAULT_KEYS_FILE,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_TIMEZONE,
)
from src.crawler.account_search_crawler import AccountSearchCrawler
from src.exceptions import AuthenticationError
from src.export.jsonl_writer import JsonlWriter
from src.io_loader import AccountSpec, load_accounts, load_keywords
from src.logging_utils import TeeStream
from src.parser.post_parser import parse_search_page
from src.utils.date_utils import parse_cli_date


DEFAULT_COOKIES_POOL_MANAGE_FILE = DOCS_DIR / "CookiesPool.txt"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="X account keyword protocol crawler (JSONL output)."
    )
    parser.add_argument("start_date", help="Start date in format YYYY_M_D, inclusive")
    parser.add_argument("end_date", help="End date in format YYYY_M_D, inclusive")
    parser.add_argument(
        "--accounts-file",
        default=str(DEFAULT_ACCOUNTS_FILE),
        help=f"Account URL file (default: {DEFAULT_ACCOUNTS_FILE})",
    )
    parser.add_argument(
        "--keys-file",
        default=str(DEFAULT_KEYS_FILE),
        help=f"Keyword file (default: {DEFAULT_KEYS_FILE})",
    )
    parser.add_argument(
        "--cookies-file",
        default=str(DEFAULT_COOKIES_FILE),
        help=f"Cookie storage path (default: {DEFAULT_COOKIES_FILE})",
    )
    parser.add_argument(
        "--cookies-pool-file",
        default="",
        help="Optional cookie pool file, one cookies.json path per line.",
    )
    return parser.parse_args(argv)


def _is_accounts_mode(argv: list[str]) -> bool:
    return bool(argv) and argv[0].strip().casefold() == "accounts"


def _read_lines(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"Missing input file: {path}")
    return path.read_text(encoding="utf-8").splitlines()


def _probe_cookies(cookies: list[dict]) -> bool:
    client = XProtocolClient(cookies=cookies)
    try:
        return client.verify_credentials()
    finally:
        client.close()


@dataclass
class SessionSlot:
    """One reusable authenticated session in pool."""

    slot_id: int
    cookies_path: Path
    manager: SessionManager
    client: XProtocolClient


@dataclass(frozen=True)
class AccountSlotStatus:
    """Account slot health snapshot for interactive management."""

    slot_id: int
    cookies_path: Path
    has_core_auth: bool
    probe_ok: bool
    error: str


def _resolve_cookie_pool_paths(primary_path: Path, pool_lines: list[str]) -> list[Path]:
    paths: list[Path] = []
    seen: set[str] = set()

    def _append(path: Path) -> None:
        normalized = str(path.expanduser().resolve()).casefold()
        if normalized in seen:
            return
        seen.add(normalized)
        paths.append(path)

    _append(primary_path)
    for line in pool_lines:
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        _append(Path(value))
    return paths


def _read_optional_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return _read_lines(path)


def _path_key(path: Path) -> str:
    return str(path.expanduser().resolve()).casefold()


def _path_to_pool_line(path: Path) -> str:
    resolved = path.expanduser().resolve()
    try:
        return str(resolved.relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(resolved)


def _write_cookie_pool_file(
    *,
    pool_file: Path,
    primary_path: Path,
    slot_paths: list[Path],
) -> None:
    primary_key = _path_key(primary_path)
    lines: list[str] = []
    seen: set[str] = set()
    for path in slot_paths:
        key = _path_key(path)
        if key == primary_key:
            continue
        if key in seen:
            continue
        seen.add(key)
        lines.append(_path_to_pool_line(path))

    pool_file.parent.mkdir(parents=True, exist_ok=True)
    if not lines:
        pool_file.write_text("", encoding="utf-8")
        return
    pool_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _load_slot_paths(*, primary_path: Path, pool_file: Path) -> list[Path]:
    pool_lines = _read_optional_lines(pool_file)
    return _resolve_cookie_pool_paths(primary_path, pool_lines)


def _collect_slot_statuses(slot_paths: list[Path]) -> list[AccountSlotStatus]:
    statuses: list[AccountSlotStatus] = []
    for index, slot_path in enumerate(slot_paths, start=1):
        manager = SessionManager(cookies_path=slot_path)
        cookies = manager.load_cookies()
        has_core_auth = bool(cookies and manager._has_core_auth_cookies(cookies))
        probe_ok = False
        error = ""
        if cookies:
            try:
                probe_ok = _probe_cookies(cookies)
            except Exception as exc:  # pragma: no cover - runtime branch
                error = str(exc)
        else:
            error = "cookie_missing"

        if not probe_ok and not error and has_core_auth:
            error = "probe_failed"
        if not probe_ok and not error:
            error = "auth_cookie_missing"

        statuses.append(
            AccountSlotStatus(
                slot_id=index,
                cookies_path=slot_path,
                has_core_auth=has_core_auth,
                probe_ok=probe_ok,
                error=error,
            )
        )
    return statuses


def _slot_state_text(status: AccountSlotStatus) -> str:
    if status.probe_ok:
        return "活跃"
    if status.has_core_auth:
        return "失效"
    return "未登录"


def _print_slot_statuses(statuses: list[AccountSlotStatus]) -> None:
    print("")
    print("槽位 | 状态 | 核心Cookie | 路径 | 备注")
    print("-" * 88)
    for status in statuses:
        print(
            f"{status.slot_id:>2} | "
            f"{_slot_state_text(status):<4} | "
            f"{'Y' if status.has_core_auth else 'N':<8} | "
            f"{status.cookies_path} | "
            f"{status.error or '-'}"
        )
    print("")


def _ask_choice(*, prompt: str, min_value: int, max_value: int, allow_zero: bool = False) -> int:
    while True:
        raw = input(prompt).strip()
        if allow_zero and raw == "0":
            return 0
        if not raw.isdigit():
            print("[输入] 请输入数字。")
            continue
        value = int(raw)
        if min_value <= value <= max_value:
            return value
        print(f"[输入] 请输入 {min_value}~{max_value} 的编号。")


def _suggest_cookie_path(slot_paths: list[Path]) -> Path:
    state_dir = Path(DEFAULT_COOKIES_FILE).resolve().parent
    state_dir.mkdir(parents=True, exist_ok=True)
    index = 1
    existing = {_path_key(path) for path in slot_paths}
    while True:
        candidate = state_dir / f"cookies_pool_{index}.json"
        if _path_key(candidate) not in existing:
            return candidate
        index += 1


def _add_slot_interactive(*, primary_path: Path, pool_file: Path, slot_paths: list[Path]) -> list[Path]:
    default_path = _suggest_cookie_path(slot_paths)
    raw = input(
        f"[新增] 输入 cookies 路径（回车默认 {default_path}）："
    ).strip()
    target = Path(raw) if raw else default_path
    target = target.expanduser()
    if _path_key(target) in {_path_key(path) for path in slot_paths}:
        print(f"[新增] 路径已存在：{target}")
        return slot_paths

    manager = SessionManager(cookies_path=target)
    try:
        manager.refresh_cookies(_probe_cookies)
    except Exception as exc:
        print(f"[新增] 登录失败：{exc}")
        return slot_paths

    updated = slot_paths + [target]
    _write_cookie_pool_file(pool_file=pool_file, primary_path=primary_path, slot_paths=updated)
    print(f"[新增] 成功加入账号槽位：{target}")
    return _load_slot_paths(primary_path=primary_path, pool_file=pool_file)


def _remove_slot_interactive(*, primary_path: Path, pool_file: Path, slot_paths: list[Path]) -> list[Path]:
    if not slot_paths:
        print("[删除] 当前没有可删除槽位。")
        return slot_paths
    statuses = _collect_slot_statuses(slot_paths)
    _print_slot_statuses(statuses)
    index = _ask_choice(
        prompt="[删除] 输入要删除的槽位编号（0 取消）：",
        min_value=1,
        max_value=len(slot_paths),
        allow_zero=True,
    )
    if index == 0:
        print("[删除] 已取消。")
        return slot_paths

    target = slot_paths[index - 1]
    confirm = input(f"[删除] 确认删除槽位 {index} ({target})? [y/N]: ").strip().casefold()
    if confirm != "y":
        print("[删除] 已取消。")
        return slot_paths

    if target.exists():
        try:
            target.unlink()
            print(f"[删除] 已删除 cookie 文件：{target}")
        except OSError as exc:
            print(f"[删除] 删除 cookie 文件失败：{exc}")

    updated = [path for idx, path in enumerate(slot_paths, start=1) if idx != index]
    _write_cookie_pool_file(pool_file=pool_file, primary_path=primary_path, slot_paths=updated)
    if _path_key(target) == _path_key(primary_path):
        print("[删除] 主会话槽位已清空，下次可用“刷新Cookie”重新登录。")
    else:
        print("[删除] 已从账号池移除。")
    return _load_slot_paths(primary_path=primary_path, pool_file=pool_file)


def _refresh_bad_slot_interactive(
    *,
    primary_path: Path,
    pool_file: Path,
    slot_paths: list[Path],
) -> list[Path]:
    statuses = _collect_slot_statuses(slot_paths)
    bad_slots = [status for status in statuses if not status.probe_ok]
    if not bad_slots:
        print("[刷新] 所有账号活跃，无需刷新。")
        return slot_paths

    print("")
    print("异常槽位：")
    for idx, status in enumerate(bad_slots, start=1):
        print(f"{idx}. 槽位={status.slot_id} 路径={status.cookies_path} 原因={status.error}")
    print("")

    choice = _ask_choice(
        prompt="[刷新] 选择要重登的异常槽位编号（0 取消）：",
        min_value=1,
        max_value=len(bad_slots),
        allow_zero=True,
    )
    if choice == 0:
        print("[刷新] 已取消。")
        return slot_paths

    target = bad_slots[choice - 1].cookies_path
    manager = SessionManager(cookies_path=target)
    try:
        manager.refresh_cookies(_probe_cookies)
    except Exception as exc:
        print(f"[刷新] 重登失败：{exc}")
        return slot_paths

    if _path_key(target) not in {_path_key(path) for path in slot_paths}:
        slot_paths = slot_paths + [target]
    _write_cookie_pool_file(pool_file=pool_file, primary_path=primary_path, slot_paths=slot_paths)
    print(f"[刷新] 槽位已刷新：{target}")
    return _load_slot_paths(primary_path=primary_path, pool_file=pool_file)


def _run_accounts_mode() -> int:
    primary_path = Path(DEFAULT_COOKIES_FILE)
    pool_file = DEFAULT_COOKIES_POOL_MANAGE_FILE
    slot_paths = _load_slot_paths(primary_path=primary_path, pool_file=pool_file)

    while True:
        print("")
        print("=== 账号池管理 ===")
        print(f"主会话: {primary_path}")
        print(f"池文件: {pool_file}")
        print("1. 查看账号池状态")
        print("2. 增加账号（登录并验证）")
        print("3. 删除账号")
        print("4. 刷新Cookie（先检测活性，再单选异常槽位重登）")
        print("5. 退出")
        print("")
        choice = input("请选择操作 [1-5]: ").strip()

        if choice == "1":
            statuses = _collect_slot_statuses(slot_paths)
            _print_slot_statuses(statuses)
            continue
        if choice == "2":
            slot_paths = _add_slot_interactive(
                primary_path=primary_path,
                pool_file=pool_file,
                slot_paths=slot_paths,
            )
            continue
        if choice == "3":
            slot_paths = _remove_slot_interactive(
                primary_path=primary_path,
                pool_file=pool_file,
                slot_paths=slot_paths,
            )
            continue
        if choice == "4":
            slot_paths = _refresh_bad_slot_interactive(
                primary_path=primary_path,
                pool_file=pool_file,
                slot_paths=slot_paths,
            )
            continue
        if choice == "5":
            print("[账号池] 已退出。")
            return 0
        print("[输入] 无效选项，请输入 1~5。")


def _build_session_slots(cookie_paths: list[Path], logger: Callable[[str], None]) -> list[SessionSlot]:
    slots: list[SessionSlot] = []
    for index, cookie_path in enumerate(cookie_paths, start=1):
        manager = SessionManager(cookies_path=cookie_path)
        try:
            cookies = manager.ensure_cookies(_probe_cookies)
            client = XProtocolClient(cookies=cookies, logger=logger)
        except Exception as exc:
            logger(
                f"[登录] 槽位={index} 初始化失败 cookies={cookie_path} 错误={exc}"
            )
            continue
        slots.append(
            SessionSlot(
                slot_id=index,
                cookies_path=cookie_path,
                manager=manager,
                client=client,
            )
        )
        logger(f"[登录] 槽位={index} 会话就绪 cookies={cookie_path}")
    return slots


def _empty_error_record(account: AccountSpec, keyword: str, error: str) -> dict:
    return {
        "account": account.handle,
        "keyword": keyword,
        "post_time": "",
        "text": "",
        "post_url": "",
        "views": "",
        "likes": "",
        "reposts": "",
        "replies": "",
        "quoted_text": "",
        "error": error,
    }


def _crawl_keyword(
    *,
    client: XProtocolClient,
    account: AccountSpec,
    keyword: str,
    start_date: date,
    end_date: date,
    writer: JsonlWriter,
    timezone_name: str,
    logger: Callable[[str], None],
) -> int:
    crawler = AccountSearchCrawler(client=client, timezone_name=timezone_name, logger=logger)
    row_count = 0
    error_count = 0
    for row in crawler.crawl_account_keyword(
        account=account,
        keyword=keyword,
        start_date=start_date,
        end_date=end_date,
        parser=parse_search_page,
    ):
        writer.write(row)
        row_count += 1
        if row.get("error"):
            error_count += 1
            logger(
                f"[记录] 账号={account.handle} 关键词={keyword} 错误={row.get('error')}"
            )
        else:
            logger(
                f"[记录] 账号={account.handle} 关键词={keyword} 链接={row.get('post_url')}"
            )
    logger(
        f"[完成] 账号={account.handle} 关键词={keyword} 写入={row_count} 错误记录={error_count}"
    )
    return row_count


def main() -> int:
    argv = sys.argv[1:]
    if _is_accounts_mode(argv):
        print("[错误] 当前版本暂时禁用会话池管理模式。", file=sys.stderr)
        return 2

    args = _parse_args(argv)
    try:
        start_date = parse_cli_date(args.start_date)
        end_date = parse_cli_date(args.end_date)
    except ValueError as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 2

    if start_date > end_date:
        print("[错误] start_date 不能晚于 end_date", file=sys.stderr)
        return 2
    if args.cookies_pool_file:
        print(
            "[错误] 当前版本暂时禁用会话池功能，请移除 --cookies-pool-file 参数。",
            file=sys.stderr,
        )
        return 2

    accounts = load_accounts(_read_lines(Path(args.accounts_file)))
    keywords = load_keywords(_read_lines(Path(args.keys_file)))
    if not accounts:
        print("[错误] Accounts 文件过滤后为空。")
        return 2
    if not keywords:
        print("[错误] Keys 文件过滤后为空。")
        return 2

    writer = JsonlWriter(output_dir=DEFAULT_OUTPUT_DIR)
    log_path = writer.run_dir / "crawl.log"
    total_rows = 0
    client: XProtocolClient | None = None
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    with log_path.open("w", encoding="utf-8") as log_fp:
        sys.stdout = TeeStream(original_stdout, log_fp)
        sys.stderr = TeeStream(original_stderr, log_fp)
        logger = lambda message: print(message, flush=True)
        print(f"[日志] 运行日志文件: {log_path}", flush=True)
        session_manager = SessionManager(cookies_path=Path(args.cookies_file))
        cookies = session_manager.ensure_cookies(_probe_cookies)
        client = XProtocolClient(cookies=cookies, logger=logger)
        try:
            for account in accounts:
                for keyword in keywords:
                    logger(f"[爬取] 账号={account.handle} 关键词={keyword}")
                    try:
                        total_rows += _crawl_keyword(
                            client=client,
                            account=account,
                            keyword=keyword,
                            start_date=start_date,
                            end_date=end_date,
                            writer=writer,
                            timezone_name=DEFAULT_TIMEZONE,
                            logger=logger,
                        )
                    except AuthenticationError:
                        logger("[鉴权] 会话失效，执行一次自动重登...")
                        cookies = session_manager.refresh_cookies(_probe_cookies)
                        client.close()
                        client = XProtocolClient(cookies=cookies, logger=logger)
                        try:
                            total_rows += _crawl_keyword(
                                client=client,
                                account=account,
                                keyword=keyword,
                                start_date=start_date,
                                end_date=end_date,
                                writer=writer,
                                timezone_name=DEFAULT_TIMEZONE,
                                logger=logger,
                            )
                        except AuthenticationError as exc:
                            writer.write(
                                _empty_error_record(
                                    account=account,
                                    keyword=keyword,
                                    error=f"authentication_failed_after_refresh: {exc}",
                                )
                            )
                            logger(
                                f"[鉴权] 重登后仍失败 账号={account.handle} 关键词={keyword}"
                            )
        finally:
            if client is not None:
                client.close()
            writer.close()
            print(f"[结束] 总写入行数={total_rows}", flush=True)
            print(f"[结束] 数据文件={writer.output_path}", flush=True)
            print(f"[结束] 日志文件={log_path}", flush=True)
            sys.stdout = original_stdout
            sys.stderr = original_stderr

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
