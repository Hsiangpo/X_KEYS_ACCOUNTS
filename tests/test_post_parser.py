from src.parser.post_parser import parse_search_page


def test_parse_search_page_extracts_posts_and_cursor() -> None:
    payload = {
        "globalObjects": {
            "tweets": {
                "100": {
                    "id_str": "100",
                    "user_id_str": "1",
                    "created_at": "Wed Sep 01 01:30:00 +0000 2021",
                    "full_text": "main body",
                    "favorite_count": 10,
                    "retweet_count": 2,
                    "reply_count": 1,
                    "quoted_status_id_str": "99",
                    "ext_views": {"count": "1234"},
                },
                "99": {
                    "id_str": "99",
                    "user_id_str": "2",
                    "created_at": "Tue Aug 31 01:30:00 +0000 2021",
                    "full_text": "quoted body",
                    "favorite_count": 1,
                    "retweet_count": 1,
                    "reply_count": 0,
                },
            },
            "users": {
                "1": {"screen_name": "NBCOlympics"},
                "2": {"screen_name": "Elsewhere"},
            },
        },
        "timeline": {
            "instructions": [
                {
                    "addEntries": {
                        "entries": [
                            {
                                "entryId": "sq-cursor-bottom-0",
                                "content": {"operation": {"cursor": {"value": "CURSOR_1"}}},
                            }
                        ]
                    }
                }
            ]
        },
    }

    page = parse_search_page(payload)

    assert page.next_cursor == "CURSOR_1"
    assert len(page.posts) == 2
    post = next(item for item in page.posts if item.tweet_id == "100")
    assert post.quoted_text == "quoted body"
    assert post.views == "1234"
    assert post.likes == "10"
    assert post.post_url == "https://x.com/NBCOlympics/status/100"


def test_parse_search_page_handles_missing_cursor() -> None:
    payload = {"globalObjects": {"tweets": {}, "users": {}}, "timeline": {"instructions": []}}

    page = parse_search_page(payload)

    assert page.next_cursor is None
    assert page.posts == []


def test_parse_search_page_extracts_retweet_source_text_graphql() -> None:
    payload = {
        "data": {
            "search_by_raw_query": {
                "search_timeline": {
                    "timeline": {
                        "instructions": [
                            {
                                "entries": [
                                    {
                                        "entryId": "tweet-200",
                                        "content": {
                                            "itemContent": {
                                                "tweet_results": {
                                                    "result": {
                                                        "__typename": "Tweet",
                                                        "rest_id": "200",
                                                        "core": {
                                                            "user_results": {
                                                                "result": {
                                                                    "core": {"screen_name": "NBCOlympics"}
                                                                }
                                                            }
                                                        },
                                                        "legacy": {
                                                            "id_str": "200",
                                                            "created_at": "Wed Sep 01 01:30:00 +0000 2021",
                                                            "full_text": "RT shell",
                                                            "favorite_count": 1,
                                                            "retweet_count": 2,
                                                            "reply_count": 3,
                                                        },
                                                        "retweeted_status_result": {
                                                            "result": {
                                                                "__typename": "Tweet",
                                                                "rest_id": "199",
                                                                "legacy": {
                                                                    "id_str": "199",
                                                                    "created_at": "Wed Sep 01 01:00:00 +0000 2021",
                                                                    "full_text": "retweet source body",
                                                                },
                                                            }
                                                        },
                                                    }
                                                }
                                            }
                                        },
                                    }
                                ],
                                "type": "TimelineAddEntries",
                            }
                        ]
                    }
                }
            }
        }
    }

    page = parse_search_page(payload)

    assert len(page.posts) == 1
    assert page.posts[0].quoted_text == "retweet source body"


def test_parse_search_page_extracts_retweet_source_text_legacy() -> None:
    payload = {
        "globalObjects": {
            "tweets": {
                "200": {
                    "id_str": "200",
                    "user_id_str": "1",
                    "created_at": "Wed Sep 01 01:30:00 +0000 2021",
                    "full_text": "retweet shell body",
                    "favorite_count": 10,
                    "retweet_count": 2,
                    "reply_count": 1,
                    "retweeted_status": {
                        "id_str": "199",
                        "full_text": "legacy retweet source body",
                    },
                }
            },
            "users": {
                "1": {"screen_name": "NBCOlympics"},
            },
        },
        "timeline": {"instructions": []},
    }

    page = parse_search_page(payload)

    assert len(page.posts) == 1
    assert page.posts[0].quoted_text == "legacy retweet source body"
