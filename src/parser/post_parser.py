"""Parse X search timeline payloads into stable post objects."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.utils.date_utils import parse_x_created_at


@dataclass(slots=True)
class ParsedPost:
    """Normalized post row."""

    tweet_id: str
    account_handle: str
    created_at_utc: datetime
    post_time: str
    text: str
    post_url: str
    views: str
    likes: str
    reposts: str
    replies: str
    quoted_text: str
    in_reply_to_status_id: str | None


@dataclass(slots=True)
class SearchPage:
    """Single page of results."""

    posts: list[ParsedPost]
    next_cursor: str | None


def parse_search_page(payload: dict[str, Any]) -> SearchPage:
    """Parse either modern GraphQL payload or legacy adaptive payload."""
    if "data" in payload:
        return _parse_graphql_search_page(payload)
    return _parse_legacy_search_page(payload)


def _parse_graphql_search_page(payload: dict[str, Any]) -> SearchPage:
    timeline = (
        payload.get("data", {})
        .get("search_by_raw_query", {})
        .get("search_timeline", {})
        .get("timeline", {})
    )
    instructions = timeline.get("instructions", [])

    posts: list[ParsedPost] = []
    next_cursor: str | None = None
    for instruction in instructions:
        entries = instruction.get("entries")
        if isinstance(entries, list):
            for entry in entries:
                post = _parse_graphql_entry(entry)
                if post is not None:
                    posts.append(post)
                cursor = _extract_cursor_from_entry(entry)
                if cursor:
                    next_cursor = cursor

        entry = instruction.get("entry")
        if isinstance(entry, dict):
            cursor = _extract_cursor_from_entry(entry)
            if cursor:
                next_cursor = cursor

    return SearchPage(posts=posts, next_cursor=next_cursor)


def _parse_graphql_entry(entry: dict[str, Any]) -> ParsedPost | None:
    entry_id = str(entry.get("entryId", ""))
    if not entry_id.startswith("tweet-"):
        return None

    content = entry.get("content", {})
    item_content = content.get("itemContent", {})
    tweet_result = item_content.get("tweet_results", {}).get("result")
    tweet = _unwrap_graphql_tweet(tweet_result)
    if not isinstance(tweet, dict):
        return None

    return _tweet_to_parsed_post(tweet)


def _unwrap_graphql_tweet(tweet_result: Any) -> dict[str, Any] | None:
    if not isinstance(tweet_result, dict):
        return None

    typename = tweet_result.get("__typename")
    if typename == "Tweet":
        return tweet_result

    # Common wrapper shape: TweetWithVisibilityResults -> tweet
    nested_tweet = tweet_result.get("tweet")
    if isinstance(nested_tweet, dict):
        return _unwrap_graphql_tweet(nested_tweet)
    return None


def _tweet_to_parsed_post(tweet: dict[str, Any]) -> ParsedPost | None:
    legacy = tweet.get("legacy", {})
    created_raw = legacy.get("created_at")
    if not created_raw:
        return None

    created_at_utc = parse_x_created_at(created_raw)
    tweet_id = str(tweet.get("rest_id") or legacy.get("id_str") or "")
    if not tweet_id:
        return None

    user_result = tweet.get("core", {}).get("user_results", {}).get("result", {})
    account_handle = (
        user_result.get("core", {}).get("screen_name")
        or user_result.get("legacy", {}).get("screen_name")
        or ""
    )
    if not account_handle:
        account_handle = "unknown"

    quoted_text = _extract_graphql_referenced_text(tweet)

    views = ""
    views_obj = tweet.get("views", {})
    if isinstance(views_obj, dict):
        if "count" in views_obj:
            views = str(views_obj["count"])
        elif "state" in views_obj and views_obj["state"] == "Enabled":
            views = ""

    return ParsedPost(
        tweet_id=tweet_id,
        account_handle=str(account_handle),
        created_at_utc=created_at_utc,
        post_time=created_at_utc.isoformat(),
        text=str(legacy.get("full_text", "")),
        post_url=f"https://x.com/{account_handle}/status/{tweet_id}",
        views=views,
        likes=str(legacy.get("favorite_count", "")),
        reposts=str(legacy.get("retweet_count", "")),
        replies=str(legacy.get("reply_count", "")),
        quoted_text=quoted_text,
        in_reply_to_status_id=legacy.get("in_reply_to_status_id_str"),
    )


def _extract_graphql_referenced_text(tweet: dict[str, Any]) -> str:
    # 1) quoted post
    quoted_result = tweet.get("quoted_status_result", {}).get("result")
    quoted_tweet = _unwrap_graphql_tweet(quoted_result)
    if isinstance(quoted_tweet, dict):
        text = str(quoted_tweet.get("legacy", {}).get("full_text", ""))
        if text:
            return text

    # 2) native retweet (observed in multiple GraphQL variants)
    retweet_result = tweet.get("retweeted_status_result", {}).get("result")
    retweet_tweet = _unwrap_graphql_tweet(retweet_result)
    if isinstance(retweet_tweet, dict):
        text = str(retweet_tweet.get("legacy", {}).get("full_text", ""))
        if text:
            return text

    legacy = tweet.get("legacy", {})

    # 3) legacy wrapper for retweet result
    legacy_retweet = legacy.get("retweeted_status_result", {}).get("result")
    legacy_retweet_tweet = _unwrap_graphql_tweet(legacy_retweet)
    if isinstance(legacy_retweet_tweet, dict):
        text = str(legacy_retweet_tweet.get("legacy", {}).get("full_text", ""))
        if text:
            return text

    # 4) legacy inline retweet payload
    inline_retweet = legacy.get("retweeted_status", {})
    if isinstance(inline_retweet, dict):
        text = str(inline_retweet.get("full_text", ""))
        if text:
            return text

    return ""


def _extract_cursor_from_entry(entry: dict[str, Any]) -> str | None:
    content = entry.get("content", {})
    cursor_type = content.get("cursorType")
    value = content.get("value")
    if cursor_type == "Bottom" and isinstance(value, str) and value:
        return value

    operation_cursor = content.get("operation", {}).get("cursor", {})
    if isinstance(operation_cursor, dict):
        value = operation_cursor.get("value")
        if isinstance(value, str) and value:
            return value

    return None


def _parse_legacy_search_page(payload: dict[str, Any]) -> SearchPage:
    tweets = payload.get("globalObjects", {}).get("tweets", {})
    users = payload.get("globalObjects", {}).get("users", {})
    posts: list[ParsedPost] = []
    for tweet_id, tweet in tweets.items():
        created_raw = tweet.get("created_at")
        if not created_raw:
            continue
        created_at_utc = parse_x_created_at(created_raw)
        user_id = str(tweet.get("user_id_str") or tweet.get("user_id") or "")
        account_handle = str(users.get(user_id, {}).get("screen_name", "unknown"))
        quoted_text = ""
        quoted_id = str(tweet.get("quoted_status_id_str") or "")
        if quoted_id and quoted_id in tweets:
            quoted_text = str(tweets[quoted_id].get("full_text", ""))
        if not quoted_text:
            retweet_id = str(tweet.get("retweeted_status_id_str") or "")
            if retweet_id and retweet_id in tweets:
                quoted_text = str(tweets[retweet_id].get("full_text", ""))
        if not quoted_text:
            retweeted_status = tweet.get("retweeted_status", {})
            if isinstance(retweeted_status, dict):
                quoted_text = str(retweeted_status.get("full_text", ""))
        if not quoted_text:
            retweeted_status_result = tweet.get("retweeted_status_result", {}).get("result", {})
            if isinstance(retweeted_status_result, dict):
                quoted_text = str(retweeted_status_result.get("legacy", {}).get("full_text", ""))

        views = ""
        ext_views = tweet.get("ext_views", {})
        if isinstance(ext_views, dict) and "count" in ext_views:
            views = str(ext_views["count"])

        posts.append(
            ParsedPost(
                tweet_id=str(tweet.get("id_str") or tweet_id),
                account_handle=account_handle,
                created_at_utc=created_at_utc,
                post_time=created_at_utc.isoformat(),
                text=str(tweet.get("full_text", "")),
                post_url=f"https://x.com/{account_handle}/status/{tweet.get('id_str') or tweet_id}",
                views=views,
                likes=str(tweet.get("favorite_count", "")),
                reposts=str(tweet.get("retweet_count", "")),
                replies=str(tweet.get("reply_count", "")),
                quoted_text=quoted_text,
                in_reply_to_status_id=tweet.get("in_reply_to_status_id_str"),
            )
        )

    next_cursor: str | None = None
    instructions = payload.get("timeline", {}).get("instructions", [])
    for instruction in instructions:
        entries = instruction.get("addEntries", {}).get("entries", [])
        for entry in entries:
            cursor = _extract_cursor_from_entry(entry)
            if cursor:
                next_cursor = cursor

    return SearchPage(posts=posts, next_cursor=next_cursor)
