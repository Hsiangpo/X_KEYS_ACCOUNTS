from __future__ import annotations

import re

from src.client.x_transaction import (
    XClientTransaction,
    extract_ondemand_file_url,
    parse_home_page_html,
)


def test_extract_ondemand_file_url_from_home_page() -> None:
    soup = parse_home_page_html(
        """
        <html>
          <head>
            <script>
              window.__SCRIPTS = {"ondemand.s":"2f0364d"};
            </script>
          </head>
        </html>
        """
    )
    assert (
        extract_ondemand_file_url(soup)
        == "https://abs.twimg.com/responsive-web/client-web/ondemand.s.2f0364da.js"
    )


def test_generate_transaction_id_is_deterministic_when_seeded(monkeypatch) -> None:
    soup = parse_home_page_html("<html><head></head><body></body></html>")

    monkeypatch.setattr(
        XClientTransaction,
        "_extract_indices",
        staticmethod(lambda _ondemand_script: (0, [1, 2, 3])),
    )
    monkeypatch.setattr(
        XClientTransaction,
        "_extract_site_verification_key",
        staticmethod(lambda _home_page: "AAECAwQFBgcICQoLDA0ODw=="),
    )
    monkeypatch.setattr(
        XClientTransaction,
        "_build_animation_key",
        lambda self, key_bytes, home_page: "anim-key",
    )

    tx = XClientTransaction(home_page=soup, ondemand_script="ignored")
    first = tx.generate_transaction_id(
        method="GET",
        path="/i/api/graphql/cGK-Qeg1XJc2sZ6kgQw_Iw/SearchTimeline",
        time_now=1771506042,
        random_num=9,
    )
    second = tx.generate_transaction_id(
        method="GET",
        path="/i/api/graphql/cGK-Qeg1XJc2sZ6kgQw_Iw/SearchTimeline",
        time_now=1771506042,
        random_num=9,
    )
    changed_path = tx.generate_transaction_id(
        method="GET",
        path="/i/api/graphql/cGK-Qeg1XJc2sZ6kgQw_Iw/ExploreSidebar",
        time_now=1771506042,
        random_num=9,
    )

    assert first == second
    assert first != changed_path
    assert re.fullmatch(r"[A-Za-z0-9+/]+", first) is not None
    assert len(first) >= 40
