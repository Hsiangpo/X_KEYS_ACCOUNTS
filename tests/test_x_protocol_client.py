from __future__ import annotations

import inspect
from typing import Any

import src.client.x_protocol_client as x_protocol_client_module
from src.client.x_protocol_client import XProtocolClient


class _FakeResponse:
    def __init__(
        self,
        status_code: int,
        *,
        text: str = "",
        data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ):
        self.status_code = status_code
        self.text = text
        self.headers: dict[str, str] = headers or {}
        self._data = data or {}

    def json(self) -> dict[str, Any]:
        return self._data


class _FakeHttpClient:
    def __init__(self, responses: list[_FakeResponse]):
        self._responses = responses
        self.cookies: dict[str, str] = {}

    def get(self, *args: Any, **kwargs: Any) -> _FakeResponse:
        return self._responses.pop(0)

    def close(self) -> None:
        return None


def test_request_headers_attach_transaction_id_and_referer(monkeypatch) -> None:
    client = XProtocolClient(
        cookies=[{"name": "ct0", "value": "csrf-token", "domain": ".x.com", "path": "/"}]
    )
    try:
        monkeypatch.setattr(client, "_next_transaction_id", lambda **kwargs: "tx-123")
        headers = client._request_headers(
            raw_query="(from:OpenAI) codex since:2021-09-01 until:2026-02-20",
            path="/i/api/graphql/example/SearchTimeline",
            method="GET",
        )
    finally:
        client.close()

    assert headers["x-csrf-token"] == "csrf-token"
    assert headers["x-client-transaction-id"] == "tx-123"
    assert headers["referer"].startswith("https://x.com/search?q=")


def test_request_headers_skip_transaction_id_when_unavailable(monkeypatch) -> None:
    client = XProtocolClient(cookies=[])
    try:
        monkeypatch.setattr(client, "_next_transaction_id", lambda **kwargs: None)
        headers = client._request_headers(path="/i/api/graphql/example/SearchTimeline", method="GET")
    finally:
        client.close()

    assert "x-client-transaction-id" not in headers


def test_get_json_with_retry_refreshes_transaction_context_on_404(monkeypatch) -> None:
    client = XProtocolClient(cookies=[], max_retries=2)
    fake_http = _FakeHttpClient(
        [
            _FakeResponse(404, text=""),
            _FakeResponse(200, data={"ok": True}),
        ]
    )
    client._client = fake_http  # type: ignore[assignment]

    ensure_calls: list[bool] = []

    def _fake_ensure(*, force_refresh: bool = False) -> bool:
        ensure_calls.append(force_refresh)
        return force_refresh

    monkeypatch.setattr(client, "_request_headers", lambda **kwargs: {})
    monkeypatch.setattr(client, "_ensure_transaction_context", _fake_ensure)
    monkeypatch.setattr(x_protocol_client_module, "_sleep_backoff", lambda *args, **kwargs: None)

    result = client._get_json_with_retry(
        "/i/api/graphql/example/SearchTimeline",
        params={},
        raw_query="(from:OpenAI) codex",
        has_cursor=False,
    )

    assert result == {"ok": True}
    assert True in ensure_calls


def test_protocol_client_does_not_depend_on_external_xclienttransaction_package() -> None:
    source = inspect.getsource(x_protocol_client_module)
    assert "from x_client_transaction" not in source


def test_verify_credentials_uses_search_probe_when_verify_endpoint_is_unavailable(
    monkeypatch,
) -> None:
    client = XProtocolClient(
        cookies=[{"name": "ct0", "value": "csrf-token", "domain": ".x.com", "path": "/"}],
        max_retries=1,
    )
    fake_http = _FakeHttpClient(
        [
            _FakeResponse(404, text="not found"),
            _FakeResponse(429, text="rate limited"),
        ]
    )
    fake_http.cookies["ct0"] = "csrf-token"
    client._client = fake_http  # type: ignore[assignment]
    monkeypatch.setattr(client, "_request_headers", lambda **kwargs: {})

    assert client.verify_credentials() is True


def test_verify_credentials_returns_false_when_fallback_is_auth_error(
    monkeypatch,
) -> None:
    client = XProtocolClient(
        cookies=[{"name": "ct0", "value": "csrf-token", "domain": ".x.com", "path": "/"}],
        max_retries=1,
    )
    fake_http = _FakeHttpClient(
        [
            _FakeResponse(404, text="not found"),
            _FakeResponse(401, text="unauthorized"),
        ]
    )
    fake_http.cookies["ct0"] = "csrf-token"
    client._client = fake_http  # type: ignore[assignment]
    monkeypatch.setattr(client, "_request_headers", lambda **kwargs: {})

    assert client.verify_credentials() is False


def test_sleep_backoff_uses_rate_limit_reset_header(monkeypatch) -> None:
    waited: list[int] = []
    monkeypatch.setattr(x_protocol_client_module.time, "time", lambda: 100)
    monkeypatch.setattr(x_protocol_client_module.time, "sleep", lambda seconds: waited.append(seconds))

    result = x_protocol_client_module._sleep_backoff(
        1,
        retry_after="130",
        kind="rate_limit",
    )

    expected = min(
        max(
            1,
            130
            - 100
            + x_protocol_client_module.DEFAULT_RATE_LIMIT_RESET_BUFFER_SECONDS,
        ),
        x_protocol_client_module.DEFAULT_MAX_RATE_LIMIT_WAIT_SECONDS,
    )
    assert result == expected
    assert waited == [expected]


def test_sleep_backoff_rate_limit_without_reset_header_uses_conservative_wait(monkeypatch) -> None:
    waited: list[int] = []
    monkeypatch.setattr(x_protocol_client_module.time, "sleep", lambda seconds: waited.append(seconds))

    result = x_protocol_client_module._sleep_backoff(2, kind="rate_limit")

    assert result == min(60, x_protocol_client_module.DEFAULT_RATE_LIMIT_FALLBACK_WAIT_SECONDS)
    assert waited == [result]


def test_update_rate_limit_state_from_headers() -> None:
    logs: list[str] = []
    client = XProtocolClient(cookies=[], logger=logs.append)
    try:
        client._update_rate_limit_state(
            {
                "x-rate-limit-remaining": "0",
                "x-rate-limit-reset": "170",
            }
        )
    finally:
        client.close()

    assert client._rate_limit_remaining == 0
    assert client._rate_limit_reset == 170
    assert any("reset_bj=" in line for line in logs)
    assert any("1970-01-01" in line for line in logs)


def test_wait_for_available_quota_when_remaining_is_low(monkeypatch) -> None:
    waited: list[int] = []
    logs: list[str] = []
    client = XProtocolClient(cookies=[], logger=logs.append)
    try:
        client._rate_limit_remaining = 0
        client._rate_limit_reset = 130
        monkeypatch.setattr(x_protocol_client_module.time, "time", lambda: 100)
        monkeypatch.setattr(x_protocol_client_module.time, "sleep", lambda seconds: waited.append(seconds))

        client._wait_for_available_quota(path="/i/api/graphql/example/SearchTimeline")
    finally:
        client.close()

    expected = min(
        max(
            1,
            130
            - 100
            + x_protocol_client_module.DEFAULT_RATE_LIMIT_RESET_BUFFER_SECONDS,
        ),
        x_protocol_client_module.DEFAULT_MAX_RATE_LIMIT_WAIT_SECONDS,
    )
    assert waited == [expected]
    assert any("主动等待" in line for line in logs)
    assert any("重置北京时间=" in line for line in logs)


def test_wait_for_available_quota_skips_when_remaining_above_threshold(monkeypatch) -> None:
    waited: list[int] = []
    client = XProtocolClient(cookies=[])
    try:
        client._rate_limit_remaining = x_protocol_client_module.DEFAULT_RATE_LIMIT_PROACTIVE_THRESHOLD + 1
        client._rate_limit_reset = 130
        monkeypatch.setattr(x_protocol_client_module.time, "time", lambda: 100)
        monkeypatch.setattr(x_protocol_client_module.time, "sleep", lambda seconds: waited.append(seconds))

        client._wait_for_available_quota(path="/i/api/graphql/example/SearchTimeline")
    finally:
        client.close()

    assert waited == []


def test_get_json_with_retry_waits_proactively_before_request(monkeypatch) -> None:
    client = XProtocolClient(cookies=[], max_retries=1)
    fake_http = _FakeHttpClient(
        [
            _FakeResponse(
                200,
                data={"ok": True},
                headers={
                    "x-rate-limit-remaining": "9",
                    "x-rate-limit-reset": "180",
                },
            ),
        ]
    )
    client._client = fake_http  # type: ignore[assignment]
    client._rate_limit_remaining = 0
    client._rate_limit_reset = 130

    waited: list[int] = []
    monkeypatch.setattr(client, "_request_headers", lambda **kwargs: {})
    monkeypatch.setattr(x_protocol_client_module.time, "time", lambda: 100)
    monkeypatch.setattr(x_protocol_client_module.time, "sleep", lambda seconds: waited.append(seconds))

    result = client._get_json_with_retry(
        "/i/api/graphql/example/SearchTimeline",
        params={},
        raw_query="(from:OpenAI) codex",
        has_cursor=False,
    )

    expected_wait = min(
        max(
            1,
            130
            - 100
            + x_protocol_client_module.DEFAULT_RATE_LIMIT_RESET_BUFFER_SECONDS,
        ),
        x_protocol_client_module.DEFAULT_MAX_RATE_LIMIT_WAIT_SECONDS,
    )
    assert waited == [expected_wait]
    assert result == {"ok": True}
