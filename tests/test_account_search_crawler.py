from datetime import date

from src.crawler.account_search_crawler import AccountSearchCrawler
from src.io_loader import AccountSpec
from src.parser.post_parser import parse_search_page


def _tweet(
    tweet_id: str,
    text: str,
    created_at: str,
    user_id: str = "1",
    quoted_status_id: str | None = None,
    in_reply_to: str | None = None,
) -> dict:
    payload = {
        "id_str": tweet_id,
        "user_id_str": user_id,
        "created_at": created_at,
        "full_text": text,
        "favorite_count": 3,
        "retweet_count": 2,
        "reply_count": 1,
    }
    if quoted_status_id:
        payload["quoted_status_id_str"] = quoted_status_id
    if in_reply_to:
        payload["in_reply_to_status_id_str"] = in_reply_to
    return payload


def _page(tweets: dict[str, dict], cursor: str | None) -> dict:
    entries = []
    if cursor:
        entries.append(
            {
                "entryId": "sq-cursor-bottom-0",
                "content": {"operation": {"cursor": {"value": cursor}}},
            }
        )
    return {
        "globalObjects": {
            "tweets": tweets,
            "users": {"1": {"screen_name": "NBCOlympics"}},
        },
        "timeline": {"instructions": [{"addEntries": {"entries": entries}}]},
    }


class FakeClient:
    def __init__(self, pages: list[dict]):
        self._pages = pages
        self._index = 0

    def search_account_keyword(
        self,
        *,
        handle: str,
        keyword: str,
        start_date: date,
        end_date: date,
        cursor: str | None,
    ) -> dict:
        page = self._pages[self._index]
        self._index += 1
        return page


class LoopingCursorClient:
    def __init__(self, *, fail_after_calls: int):
        self.calls = 0
        self.fail_after_calls = fail_after_calls
        self.page = _page({}, cursor="REPEATED_CURSOR")

    def search_account_keyword(
        self,
        *,
        handle: str,
        keyword: str,
        start_date: date,
        end_date: date,
        cursor: str | None,
    ) -> dict:
        self.calls += 1
        if self.calls > self.fail_after_calls:
            raise RuntimeError("loop was not stopped")
        return self.page


class RotatingCursorClient:
    def __init__(self, *, fail_after_calls: int):
        self.calls = 0
        self.fail_after_calls = fail_after_calls

    def search_account_keyword(
        self,
        *,
        handle: str,
        keyword: str,
        start_date: date,
        end_date: date,
        cursor: str | None,
    ) -> dict:
        self.calls += 1
        if self.calls > self.fail_after_calls:
            raise RuntimeError("empty-page loop was not stopped")
        return _page({}, cursor=f"CURSOR_{self.calls}")


def test_crawler_filters_by_date_and_reply_status() -> None:
    page_1 = _page(
        {
            "101": _tweet(
                "101",
                "target keyword",
                "Wed Sep 08 01:30:00 +0000 2021",
            ),
            "102": _tweet(
                "102",
                "target keyword",
                "Wed Sep 08 01:30:00 +0000 2021",
                in_reply_to="1",
            ),
        },
        cursor="NEXT",
    )
    page_2 = _page(
        {
            "103": _tweet(
                "103",
                "target keyword",
                "Mon Aug 30 01:30:00 +0000 2021",
            ),
        },
        cursor=None,
    )
    crawler = AccountSearchCrawler(
        client=FakeClient([page_1, page_2]),
        timezone_name="Asia/Shanghai",
    )

    records = list(
        crawler.crawl_account_keyword(
            account=AccountSpec(url="https://x.com/NBCOlympics", handle="NBCOlympics"),
            keyword="target",
            start_date=date(2021, 9, 1),
            end_date=date(2021, 9, 30),
            parser=parse_search_page,
        )
    )

    assert len(records) == 1
    assert records[0]["post_url"].endswith("/101")
    assert records[0]["error"] == ""


def test_crawler_matches_quoted_text() -> None:
    page = _page(
        {
            "199": _tweet("199", "quoted target", "Mon Sep 06 01:30:00 +0000 2021"),
            "200": _tweet(
                "200",
                "main body",
                "Mon Sep 06 01:30:00 +0000 2021",
                quoted_status_id="199",
            ),
        },
        cursor=None,
    )
    crawler = AccountSearchCrawler(
        client=FakeClient([page]),
        timezone_name="Asia/Shanghai",
    )

    records = list(
        crawler.crawl_account_keyword(
            account=AccountSpec(url="https://x.com/NBCOlympics", handle="NBCOlympics"),
            keyword="target",
            start_date=date(2021, 9, 1),
            end_date=date(2021, 9, 30),
            parser=parse_search_page,
        )
    )

    assert len(records) == 2


def test_crawler_stops_on_repeated_cursor_without_error_record() -> None:
    client = LoopingCursorClient(fail_after_calls=5)
    crawler = AccountSearchCrawler(client=client, timezone_name="Asia/Shanghai")

    records = list(
        crawler.crawl_account_keyword(
            account=AccountSpec(url="https://x.com/NBCOlympics", handle="NBCOlympics"),
            keyword="target",
            start_date=date(2021, 9, 1),
            end_date=date(2021, 9, 30),
            parser=parse_search_page,
        )
    )

    assert records == []
    assert client.calls <= 2


def test_crawler_stops_after_max_empty_pages() -> None:
    client = RotatingCursorClient(fail_after_calls=6)
    crawler = AccountSearchCrawler(
        client=client,
        timezone_name="Asia/Shanghai",
        max_empty_pages=3,
    )

    records = list(
        crawler.crawl_account_keyword(
            account=AccountSpec(url="https://x.com/NBCOlympics", handle="NBCOlympics"),
            keyword="target",
            start_date=date(2021, 9, 1),
            end_date=date(2021, 9, 30),
            parser=parse_search_page,
        )
    )

    assert records == []
    assert client.calls == 3


def test_crawler_emits_progress_logs() -> None:
    page = _page(
        {
            "100": _tweet(
                "100",
                "target keyword",
                "Wed Sep 08 01:30:00 +0000 2021",
            ),
        },
        cursor=None,
    )
    logs: list[str] = []
    crawler = AccountSearchCrawler(
        client=FakeClient([page]),
        timezone_name="Asia/Shanghai",
        logger=logs.append,
    )

    records = list(
        crawler.crawl_account_keyword(
            account=AccountSpec(url="https://x.com/NBCOlympics", handle="NBCOlympics"),
            keyword="target",
            start_date=date(2021, 9, 1),
            end_date=date(2021, 9, 30),
            parser=parse_search_page,
        )
    )

    assert len(records) == 1
    assert any("[页面]" in line for line in logs)
    assert any("[输出]" in line for line in logs)

def test_crawler_requires_all_terms_for_multi_term_keyword_rule() -> None:
    page = _page(
        {
            "100": _tweet(
                "100",
                "China policy update",
                "Wed Sep 08 01:30:00 +0000 2021",
            ),
            "101": _tweet(
                "101",
                "China climate policy update",
                "Wed Sep 08 02:30:00 +0000 2021",
            ),
        },
        cursor=None,
    )
    crawler = AccountSearchCrawler(
        client=FakeClient([page]),
        timezone_name="Asia/Shanghai",
    )

    records = list(
        crawler.crawl_account_keyword(
            account=AccountSpec(url="https://x.com/NBCOlympics", handle="NBCOlympics"),
            keyword="China Climate",
            start_date=date(2021, 9, 1),
            end_date=date(2021, 9, 30),
            parser=parse_search_page,
        )
    )

    assert len(records) == 1
    assert records[0]["post_url"].endswith("/101")
