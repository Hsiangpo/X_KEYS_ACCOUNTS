"""Account + keyword crawl loop."""

from __future__ import annotations

from datetime import date
from typing import Callable, Iterator

from src.exceptions import AuthenticationError
from src.io_loader import AccountSpec
from src.parser.post_parser import SearchPage
from src.utils.date_utils import in_date_range, to_local_date


ParserFn = Callable[[dict], SearchPage]


class AccountSearchCrawler:
    """Iterate account-by-keyword pages and yield normalized output rows."""

    def __init__(
        self,
        client,
        timezone_name: str = "Asia/Shanghai",
        max_empty_pages: int = 3,
        logger: Callable[[str], None] | None = None,
    ):
        self.client = client
        self.timezone_name = timezone_name
        self.max_empty_pages = max_empty_pages
        self._logger = logger

    def crawl_account_keyword(
        self,
        *,
        account: AccountSpec,
        keyword: str,
        start_date: date,
        end_date: date,
        parser: ParserFn,
    ) -> Iterator[dict]:
        seen_tweet_ids: set[str] = set()
        seen_cursors: set[str] = set()
        cursor: str | None = None
        empty_page_streak = 0
        page_index = 0
        while True:
            page_index += 1
            try:
                payload = self.client.search_account_keyword(
                    handle=account.handle,
                    keyword=keyword,
                    start_date=start_date,
                    end_date=end_date,
                    cursor=cursor,
                )
            except AuthenticationError:
                raise
            except Exception as exc:
                self._log(
                    f"[页面] 账号={account.handle} 关键词={keyword} 第{page_index}页 请求异常={exc}"
                )
                yield self._error_record(account.handle, keyword, str(exc))
                return

            page = parser(payload)
            if page.posts:
                empty_page_streak = 0
            else:
                empty_page_streak += 1
            self._log(
                f"[页面] 账号={account.handle} 关键词={keyword} 第{page_index}页 "
                f"帖子数={len(page.posts)} 有游标={bool(page.next_cursor)} 连续空页={empty_page_streak}"
            )

            if not page.posts and not page.next_cursor:
                self._log(
                    f"[停止] 账号={account.handle} 关键词={keyword} 原因=无帖子且无游标"
                )
                return

            reached_older_posts = False
            for post in page.posts:
                if post.account_handle.casefold() != account.handle.casefold():
                    continue
                if post.tweet_id in seen_tweet_ids:
                    continue
                seen_tweet_ids.add(post.tweet_id)

                if post.in_reply_to_status_id:
                    continue

                if not in_date_range(post.created_at_utc, start_date, end_date, self.timezone_name):
                    if to_local_date(post.created_at_utc, self.timezone_name) < start_date:
                        reached_older_posts = True
                    continue

                if not _keyword_hit(keyword, post.text, post.quoted_text):
                    continue

                self._log(
                    f"[输出] 账号={account.handle} 关键词={keyword} "
                    f"推文ID={post.tweet_id} 时间={post.post_time}"
                )
                yield {
                    "account": account.handle,
                    "keyword": keyword,
                    "post_time": post.post_time,
                    "text": post.text,
                    "post_url": post.post_url,
                    "views": post.views,
                    "likes": post.likes,
                    "reposts": post.reposts,
                    "replies": post.replies,
                    "quoted_text": post.quoted_text,
                    "error": "",
                }

            if reached_older_posts:
                self._log(
                    f"[停止] 账号={account.handle} 关键词={keyword} 原因=已到起始日期之前"
                )
                return
            if empty_page_streak >= self.max_empty_pages:
                self._log(
                    f"[停止] 账号={account.handle} 关键词={keyword} "
                    f"原因=连续空页达到上限({self.max_empty_pages})"
                )
                return

            next_cursor = page.next_cursor
            if not next_cursor:
                self._log(
                    f"[停止] 账号={account.handle} 关键词={keyword} 原因=无下一页游标"
                )
                return
            if next_cursor == cursor or next_cursor in seen_cursors:
                self._log(
                    f"[停止] 账号={account.handle} 关键词={keyword} 原因=游标重复"
                )
                return
            seen_cursors.add(next_cursor)
            self._log(
                f"[游标] 账号={account.handle} 关键词={keyword} 下一页游标长度={len(next_cursor)}"
            )
            cursor = next_cursor

    def _log(self, message: str) -> None:
        if self._logger is not None:
            self._logger(message)

    @staticmethod
    def _error_record(account: str, keyword: str, error: str) -> dict:
        return {
            "account": account,
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


def _keyword_hit(keyword: str, text: str, quoted_text: str) -> bool:
    terms = [term for term in keyword.casefold().split() if term]
    if not terms:
        return False
    haystack = f"{text}\n{quoted_text}".casefold()
    return all(term in haystack for term in terms)
