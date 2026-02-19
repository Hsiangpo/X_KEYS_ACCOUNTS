"""X protocol HTTP client based on SearchTimeline GraphQL API."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
import time
from typing import Any, Callable, Mapping
from urllib.parse import quote

import httpx

from src.client.x_transaction import (
    XClientTransaction,
    extract_ondemand_file_url,
    parse_home_page_html,
)
from src.config import (
    DEFAULT_BEARER_TOKEN,
    DEFAULT_MAX_RATE_LIMIT_WAIT_SECONDS,
    DEFAULT_MAX_RETRIES,
    DEFAULT_PAGE_SIZE,
    DEFAULT_RATE_LIMIT_MAX_INTERVAL_SECONDS,
    DEFAULT_RATE_LIMIT_FALLBACK_WAIT_SECONDS,
    DEFAULT_RATE_LIMIT_MIN_INTERVAL_SECONDS,
    DEFAULT_RATE_LIMIT_PACING_FACTOR,
    DEFAULT_RATE_LIMIT_PACING_USAGE_RATIO,
    DEFAULT_RATE_LIMIT_PROACTIVE_THRESHOLD,
    DEFAULT_RATE_LIMIT_RESET_BUFFER_SECONDS,
    DEFAULT_SEARCH_TIMELINE_QUERY_ID,
    DEFAULT_TIMEOUT_SECONDS,
)
from src.exceptions import AuthenticationError, ProtocolRequestError


class XProtocolClient:
    """Thin retrying client for X internal APIs."""

    def __init__(
        self,
        *,
        cookies: list[dict],
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        query_id: str = DEFAULT_SEARCH_TIMELINE_QUERY_ID,
        bearer_token: str = DEFAULT_BEARER_TOKEN,
        logger: Callable[[str], None] | None = None,
    ) -> None:
        self.query_id = query_id
        self.max_retries = max_retries
        self.bearer_token = bearer_token
        self._logger = logger
        self._features = _default_features()
        self._transaction_context: XClientTransaction | None = None
        self._rate_limit_limit: int | None = None
        self._rate_limit_remaining: int | None = None
        self._rate_limit_reset: int | None = None

        self._client = httpx.Client(
            base_url="https://x.com",
            timeout=timeout_seconds,
            follow_redirects=True,
            headers={
                "user-agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/145.0.0.0 Safari/537.36"
                ),
                "accept-language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
                "content-type": "application/json",
                "authorization": f"Bearer {self.bearer_token}",
                "x-twitter-client-language": "en",
                "x-twitter-active-user": "yes",
                "x-twitter-auth-type": "OAuth2Session",
                "accept": "*/*",
            },
        )
        self._apply_cookies(cookies)

    def _apply_cookies(self, cookies: list[dict]) -> None:
        for cookie in cookies:
            name = cookie.get("name")
            value = cookie.get("value")
            if not name or value is None:
                continue
            self._client.cookies.set(
                name=name,
                value=value,
                domain=cookie.get("domain"),
                path=cookie.get("path", "/"),
            )

    def _csrf_token(self) -> str:
        return self._client.cookies.get("ct0", "")

    def _request_headers(
        self,
        *,
        raw_query: str | None = None,
        path: str | None = None,
        method: str = "GET",
    ) -> dict[str, str]:
        headers = {
            "x-csrf-token": self._csrf_token(),
        }
        if raw_query:
            encoded = quote(raw_query, safe="(): ")
            encoded = encoded.replace(" ", "%20")
            headers["referer"] = f"https://x.com/search?q={encoded}&src=typed_query&f=live"
        if path:
            transaction_id = self._next_transaction_id(method=method, path=path)
            if transaction_id:
                headers["x-client-transaction-id"] = transaction_id
        return headers

    def verify_credentials(self) -> bool:
        """Check if current cookie jar is still authenticated."""
        csrf = self._csrf_token()
        if not csrf:
            self._log("[\u63a2\u6d4b] \u7f3a\u5c11 ct0\uff0c\u5224\u5b9a\u672a\u767b\u5f55")
            return False

        # This endpoint can return false negatives on X (observed 404 while session is usable).
        try:
            response = self._client.get(
                "/i/api/1.1/account/verify_credentials.json",
                params={"include_entities": "false", "skip_status": "true"},
                headers=self._request_headers(),
            )
            if response.status_code == 200:
                self._log("[\u63a2\u6d4b] verify_credentials=200\uff0c\u5224\u5b9a\u767b\u5f55\u6709\u6548")
                return True
            if response.status_code in {401, 403}:
                self._log(
                    f"[\u63a2\u6d4b] verify_credentials={response.status_code}\uff0c"
                    "\u5224\u5b9a\u672a\u767b\u5f55"
                )
                return False
            self._log(
                f"[\u63a2\u6d4b] verify_credentials={response.status_code}\uff0c"
                "\u56de\u9000\u5230 SearchTimeline \u63a2\u6d4b"
            )
        except httpx.RequestError as exc:
            self._log(
                f"[\u63a2\u6d4b] verify_credentials \u7f51\u7edc\u5f02\u5e38: {exc}\uff0c"
                "\u56de\u9000\u5230 SearchTimeline \u63a2\u6d4b"
            )

        # Fallback probe: only treat 401/403 as hard auth failure.
        raw_query = "(from:OpenAI) codex since:2025-09-01 until:2025-09-02"
        variables = {
            "rawQuery": raw_query,
            "count": 1,
            "querySource": "typed_query",
            "product": "Latest",
            "withGrokTranslatedBio": False,
        }
        params = {
            "variables": json.dumps(variables, separators=(",", ":"), ensure_ascii=False),
            "features": json.dumps(self._features, separators=(",", ":"), ensure_ascii=False),
        }
        path = f"/i/api/graphql/{self.query_id}/SearchTimeline"
        try:
            response = self._client.get(
                path,
                params=params,
                headers=self._request_headers(raw_query=raw_query, path=path, method="GET"),
            )
        except httpx.RequestError as exc:
            self._log(
                f"[\u63a2\u6d4b] SearchTimeline \u7f51\u7edc\u5f02\u5e38: {exc}\uff0c"
                "\u9ed8\u8ba4\u5224\u5b9a\u4f1a\u8bdd\u53ef\u590d\u7528"
            )
            return True

        if response.status_code in {401, 403}:
            self._log(
                f"[\u63a2\u6d4b] SearchTimeline={response.status_code}\uff0c\u5224\u5b9a\u672a\u767b\u5f55"
            )
            return False
        self._log(
            f"[\u63a2\u6d4b] SearchTimeline={response.status_code}\uff0c\u5224\u5b9a\u767b\u5f55\u6709\u6548"
        )
        return True
    def close(self) -> None:
        self._client.close()

    def search_account_keyword(
        self,
        *,
        handle: str,
        keyword: str,
        start_date: date,
        end_date: date,
        cursor: str | None,
    ) -> dict[str, Any]:
        """Query account timeline by keyword using SearchTimeline."""
        raw_query = _build_raw_query(handle, keyword, start_date, end_date)
        variables: dict[str, Any] = {
            "rawQuery": raw_query,
            "count": DEFAULT_PAGE_SIZE,
            "querySource": "typed_query",
            "product": "Latest",
            "withGrokTranslatedBio": False,
        }
        if cursor:
            variables["cursor"] = cursor

        params = {
            "variables": json.dumps(variables, separators=(",", ":"), ensure_ascii=False),
            "features": json.dumps(self._features, separators=(",", ":"), ensure_ascii=False),
        }
        path = f"/i/api/graphql/{self.query_id}/SearchTimeline"

        return self._get_json_with_retry(
            path,
            params=params,
            raw_query=raw_query,
            has_cursor=bool(cursor),
        )

    def _get_json_with_retry(
        self,
        path: str,
        *,
        params: dict[str, Any],
        raw_query: str,
        has_cursor: bool,
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            self._wait_for_available_quota(path=path)
            self._log(
                f"[\u8bf7\u6c42] \u63a5\u53e3=SearchTimeline \u5c1d\u8bd5={attempt}/{self.max_retries} "
                f"\u6709\u6e38\u6807={has_cursor}"
            )
            try:
                response = self._client.get(
                    path,
                    params=params,
                    headers=self._request_headers(raw_query=raw_query, path=path, method="GET"),
                )
            except httpx.RequestError as exc:
                last_error = exc
                wait = _sleep_backoff(attempt)
                self._log(f"[\u91cd\u8bd5] \u539f\u56e0=\u7f51\u7edc\u5f02\u5e38 \u7b49\u5f85={wait}s \u5f02\u5e38={exc}")
                continue
            self._update_rate_limit_state(response.headers)
            self._log(f"[\u54cd\u5e94] \u72b6\u6001\u7801={response.status_code} \u5c1d\u8bd5={attempt}")

            if response.status_code in {401, 403}:
                self._log(f"[\u9274\u6743] \u5931\u8d25 \u72b6\u6001\u7801={response.status_code}")
                raise AuthenticationError(f"Authentication failed with status {response.status_code}")

            if response.status_code == 429:
                retry_after = response.headers.get("x-rate-limit-reset")
                wait = _sleep_backoff(attempt, retry_after=retry_after, kind="rate_limit")
                self._log(f"[\u9650\u6d41] 429 \u7b49\u5f85={wait}s")
                continue

            if response.status_code >= 500:
                wait = _sleep_backoff(attempt)
                self._log(
                    f"[\u91cd\u8bd5] \u539f\u56e0=\u670d\u52a1\u7aef\u9519\u8bef \u72b6\u6001\u7801={response.status_code} \u7b49\u5f85={wait}s"
                )
                continue

            if response.status_code == 404:
                self._log("[\u91cd\u8bd5] \u539f\u56e0=404 \u5c1d\u8bd5\u5237\u65b0\u4e8b\u52a1\u4e0a\u4e0b\u6587")
                if self._ensure_transaction_context(force_refresh=True):
                    wait = _sleep_backoff(attempt)
                    self._log(f"[\u91cd\u8bd5] \u4e8b\u52a1\u4e0a\u4e0b\u6587\u5df2\u5237\u65b0 \u7b49\u5f85={wait}s")
                    continue

            if response.status_code >= 400:
                raise ProtocolRequestError(
                    f"Request failed ({response.status_code}) for {path}: {response.text[:300]}"
                )

            return response.json()

        if last_error is not None:
            raise ProtocolRequestError(f"Request failed after retries: {last_error}") from last_error
        raise ProtocolRequestError(f"Request failed after retries: {path}")

    def _parse_int_header(self, headers: Mapping[str, Any], name: str) -> int | None:
        value = None
        for key, header_value in headers.items():
            if str(key).lower() == name.lower():
                value = header_value
                break
        if value is None:
            return None
        text = str(value).strip()
        if not text or not text.isdigit():
            return None
        return int(text)

    def _update_rate_limit_state(self, headers: Mapping[str, Any]) -> None:
        self._rate_limit_limit = self._parse_int_header(headers, "x-rate-limit-limit")
        self._rate_limit_remaining = self._parse_int_header(headers, "x-rate-limit-remaining")
        self._rate_limit_reset = self._parse_int_header(headers, "x-rate-limit-reset")

        if (
            self._rate_limit_limit is None
            and self._rate_limit_remaining is None
            and self._rate_limit_reset is None
        ):
            return

        reset_bj = self._format_reset_time_beijing(self._rate_limit_reset)
        usage_ratio = self._rate_limit_usage_ratio()
        usage_text = f"{usage_ratio:.3f}" if usage_ratio is not None else "unknown"
        self._log(
            "[配额] "
            f"limit={self._rate_limit_limit} "
            f"remaining={self._rate_limit_remaining} "
            f"reset={self._rate_limit_reset} "
            f"reset_bj={reset_bj} "
            f"usage_ratio={usage_text}"
        )

    def _wait_for_available_quota(self, *, path: str) -> None:
        remaining = self._rate_limit_remaining
        reset_ts = self._rate_limit_reset
        if remaining is None or reset_ts is None:
            return

        now = int(time.time())
        if reset_ts <= now:
            return

        if remaining <= DEFAULT_RATE_LIMIT_PROACTIVE_THRESHOLD:
            wait_seconds = min(
                max(1, reset_ts - now + DEFAULT_RATE_LIMIT_RESET_BUFFER_SECONDS),
                DEFAULT_MAX_RATE_LIMIT_WAIT_SECONDS,
            )
            reset_bj = self._format_reset_time_beijing(reset_ts)
            self._log(
                "[配额] "
                f"接口={path} 剩余={remaining} 阈值={DEFAULT_RATE_LIMIT_PROACTIVE_THRESHOLD} "
                f"重置时间戳={reset_ts} 重置北京时间={reset_bj} 主动等待={wait_seconds}s"
            )
            time.sleep(wait_seconds)
            return

        self._wait_for_rate_limit_pacing(path=path, remaining=remaining, reset_ts=reset_ts)

    def _wait_for_rate_limit_pacing(self, *, path: str, remaining: int, reset_ts: int) -> None:
        usage_ratio = self._rate_limit_usage_ratio()
        if usage_ratio is None:
            return
        if usage_ratio < DEFAULT_RATE_LIMIT_PACING_USAGE_RATIO:
            return

        seconds_to_reset = reset_ts - time.time() + DEFAULT_RATE_LIMIT_RESET_BUFFER_SECONDS
        if seconds_to_reset <= 0:
            return

        base_wait = (seconds_to_reset / max(remaining, 1)) * DEFAULT_RATE_LIMIT_PACING_FACTOR
        wait_seconds = min(
            DEFAULT_RATE_LIMIT_MAX_INTERVAL_SECONDS,
            max(DEFAULT_RATE_LIMIT_MIN_INTERVAL_SECONDS, base_wait),
        )
        if wait_seconds <= 0:
            return

        reset_bj = self._format_reset_time_beijing(reset_ts)
        self._log(
            "[配额] "
            f"接口={path} 使用率={usage_ratio:.3f} "
            f"重置北京时间={reset_bj} 平滑节流等待={wait_seconds:.2f}s "
            f"(阈值={DEFAULT_RATE_LIMIT_PACING_USAGE_RATIO})"
        )
        time.sleep(wait_seconds)

    def _rate_limit_usage_ratio(self) -> float | None:
        if self._rate_limit_limit is None or self._rate_limit_remaining is None:
            return None
        if self._rate_limit_limit <= 0:
            return None
        usage = 1.0 - (self._rate_limit_remaining / self._rate_limit_limit)
        return max(0.0, min(1.0, usage))

    def _format_reset_time_beijing(self, reset_ts: int | None) -> str:
        if reset_ts is None:
            return "unknown"
        try:
            beijing_tz = timezone(timedelta(hours=8))
            beijing_time = datetime.fromtimestamp(reset_ts, tz=timezone.utc).astimezone(beijing_tz)
            return beijing_time.strftime("%Y-%m-%d %H:%M:%S %z")
        except (OSError, OverflowError, ValueError):
            return "invalid"

    def _next_transaction_id(self, *, method: str, path: str) -> str | None:
        if not self._ensure_transaction_context():
            self._log("[\u4e8b\u52a1] \u4e0a\u4e0b\u6587\u4e0d\u53ef\u7528\uff0c\u65e0\u6cd5\u751f\u6210 x-client-transaction-id")
            return None
        assert self._transaction_context is not None
        try:
            return str(self._transaction_context.generate_transaction_id(method=method, path=path))
        except Exception:
            self._log("[\u4e8b\u52a1] \u751f\u6210\u5931\u8d25\uff0c\u5c1d\u8bd5\u5f3a\u5236\u5237\u65b0\u4e0a\u4e0b\u6587")
            if not self._ensure_transaction_context(force_refresh=True):
                return None
            assert self._transaction_context is not None
            try:
                return str(self._transaction_context.generate_transaction_id(method=method, path=path))
            except Exception:
                self._log("[\u4e8b\u52a1] \u5237\u65b0\u540e\u4ecd\u751f\u6210\u5931\u8d25")
                return None
    def _ensure_transaction_context(self, *, force_refresh: bool = False) -> bool:
        if self._transaction_context is not None and not force_refresh:
            self._log("[\u4e8b\u52a1] \u590d\u7528\u5df2\u6709\u4e8b\u52a1\u4e0a\u4e0b\u6587")
            return True
        self._log(f"[\u4e8b\u52a1] \u6784\u5efa\u4e8b\u52a1\u4e0a\u4e0b\u6587 force_refresh={force_refresh}")

        try:
            bootstrap_headers = {
                "user-agent": str(self._client.headers.get("user-agent", "")),
                "accept-language": str(self._client.headers.get("accept-language", "")),
                "accept": "text/html,*/*",
            }

            with httpx.Client(
                timeout=self._client.timeout,
                follow_redirects=True,
                headers=bootstrap_headers,
                cookies=self._client.cookies,
            ) as bootstrap_client:
                homepage = bootstrap_client.get("https://x.com")
                if homepage.status_code >= 400:
                    self._log(f"[\u4e8b\u52a1] \u9996\u9875\u8bf7\u6c42\u5931\u8d25 \u72b6\u6001\u7801={homepage.status_code}")
                    return False
                homepage_soup = parse_home_page_html(homepage.text)
                ondemand_url = extract_ondemand_file_url(homepage_soup)
                if not ondemand_url:
                    self._log("[\u4e8b\u52a1] \u672a\u627e\u5230 ondemand.s \u811a\u672c\u5730\u5740")
                    return False
                ondemand_file = bootstrap_client.get(
                    ondemand_url,
                    headers={"accept": "*/*", "referer": "https://x.com/"},
                )
                if ondemand_file.status_code >= 400:
                    self._log(
                        f"[\u4e8b\u52a1] ondemand \u811a\u672c\u8bf7\u6c42\u5931\u8d25 \u72b6\u6001\u7801={ondemand_file.status_code}"
                    )
                    return False
                self._transaction_context = XClientTransaction(
                    home_page=homepage_soup,
                    ondemand_script=ondemand_file.text,
                )
                self._log("[\u4e8b\u52a1] \u4e8b\u52a1\u4e0a\u4e0b\u6587\u6784\u5efa\u6210\u529f")
                return True
        except Exception:
            self._transaction_context = None
            self._log("[\u4e8b\u52a1] \u6784\u5efa\u4e8b\u52a1\u4e0a\u4e0b\u6587\u5f02\u5e38")
            return False
    def _log(self, message: str) -> None:
        if self._logger is not None:
            self._logger(message)


def _build_raw_query(handle: str, keyword: str, start_date: date, end_date: date) -> str:
    end_exclusive = end_date + timedelta(days=1)
    # "until" on X behaves as exclusive. Shift by one day to make user input inclusive.
    return (
        f"(from:{handle}) {keyword} "
        f"since:{start_date.isoformat()} until:{end_exclusive.isoformat()}"
    )


def _sleep_backoff(
    attempt: int,
    *,
    retry_after: str | None = None,
    kind: str = "default",
) -> int:
    if retry_after and retry_after.isdigit():
        wait = max(
            1,
            int(retry_after)
            - int(time.time())
            + DEFAULT_RATE_LIMIT_RESET_BUFFER_SECONDS,
        )
        wait = min(wait, DEFAULT_MAX_RATE_LIMIT_WAIT_SECONDS)
        time.sleep(wait)
        return wait

    if kind == "rate_limit":
        wait = min(attempt * 30, DEFAULT_RATE_LIMIT_FALLBACK_WAIT_SECONDS)
        time.sleep(wait)
        return wait

    wait = min(2 ** (attempt - 1), 8)
    time.sleep(wait)
    return wait


def _default_features() -> dict[str, bool]:
    # Captured from real X SearchTimeline request via Chrome MCP.
    return {
        "rweb_video_screen_enabled": False,
        "profile_label_improvements_pcf_label_in_post_enabled": True,
        "responsive_web_profile_redirect_enabled": False,
        "rweb_tipjar_consumption_enabled": False,
        "verified_phone_label_enabled": False,
        "creator_subscriptions_tweet_preview_api_enabled": True,
        "responsive_web_graphql_timeline_navigation_enabled": True,
        "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
        "premium_content_api_read_enabled": False,
        "communities_web_enable_tweet_community_results_fetch": True,
        "c9s_tweet_anatomy_moderator_badge_enabled": True,
        "responsive_web_grok_analyze_button_fetch_trends_enabled": False,
        "responsive_web_grok_analyze_post_followups_enabled": True,
        "responsive_web_jetfuel_frame": True,
        "responsive_web_grok_share_attachment_enabled": True,
        "responsive_web_grok_annotations_enabled": True,
        "articles_preview_enabled": True,
        "responsive_web_edit_tweet_api_enabled": True,
        "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
        "view_counts_everywhere_api_enabled": True,
        "longform_notetweets_consumption_enabled": True,
        "responsive_web_twitter_article_tweet_consumption_enabled": True,
        "tweet_awards_web_tipping_enabled": False,
        "responsive_web_grok_show_grok_translated_post": False,
        "responsive_web_grok_analysis_button_from_backend": True,
        "post_ctas_fetch_enabled": True,
        "freedom_of_speech_not_reach_fetch_enabled": True,
        "standardized_nudges_misinfo": True,
        "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
        "longform_notetweets_rich_text_read_enabled": True,
        "longform_notetweets_inline_media_enabled": True,
        "responsive_web_grok_image_annotation_enabled": True,
        "responsive_web_grok_imagine_annotation_enabled": True,
        "responsive_web_grok_community_note_auto_translation_is_enabled": False,
        "responsive_web_enhance_cards_enabled": False,
    }
