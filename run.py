from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
import sys
from typing import Callable

from src.auth.session_manager import SessionManager
from src.client.x_protocol_client import XProtocolClient
from src.config import (
    DEFAULT_ACCOUNTS_FILE,
    DEFAULT_COOKIES_FILE,
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


def _parse_args() -> argparse.Namespace:
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
    return parser.parse_args()


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
    args = _parse_args()
    try:
        start_date = parse_cli_date(args.start_date)
        end_date = parse_cli_date(args.end_date)
    except ValueError as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 2

    if start_date > end_date:
        print("[错误] start_date 不能晚于 end_date", file=sys.stderr)
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
