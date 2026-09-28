"""
Tests the parts of the scraping layer that only show up once real (or realistically broken)
network/HTML input is involved: timeouts, malformed JSON-LD, robots.txt blocking, and a
retailer page whose markup doesn't match any selector. None of this depends on real network
access -- `requests`/`app.utils.http.get` are monkeypatched so these run fast and
deterministically anywhere, including CI.
"""
from types import SimpleNamespace

import pytest
import requests

from app.scrapers.croma import CromaAdapter
from app.utils.http import can_fetch, get


def _settings(**overrides):
    base = dict(
        SCRAPE_LIVE=True,
        SCRAPE_USER_AGENT="EPI-Test/1.0 (+test)",
        SCRAPE_MAX_RETRIES=1,
        SCRAPE_TIMEOUT_SECONDS=1.0,
        SCRAPE_MIN_DELAY_SECONDS=0.0,
        RESPECT_ROBOTS_TXT=True,
        FIXTURES_DIR="seed_data/fixtures",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


class _FakeResponse:
    def __init__(self, text="", status_code=200):
        self.text = text
        self.status_code = status_code


# ---------------------------------------------------------------------------
# Network / timeout scenarios
# ---------------------------------------------------------------------------

def test_http_get_returns_none_on_timeout(monkeypatch):
    session = requests.Session()

    def raise_timeout(*a, **k):
        raise requests.exceptions.Timeout("simulated timeout")

    monkeypatch.setattr(session, "get", raise_timeout)
    result = get(session, "https://example.com/product", "EPI-Test/1.0", respect_robots=False)
    assert result is None  # must not raise -- caller treats this as "source unavailable"


def test_http_get_returns_none_on_connection_error(monkeypatch):
    session = requests.Session()

    def raise_conn_error(*a, **k):
        raise requests.exceptions.ConnectionError("simulated DNS/connection failure")

    monkeypatch.setattr(session, "get", raise_conn_error)
    result = get(session, "https://example.com/product", "EPI-Test/1.0", respect_robots=False)
    assert result is None


def test_adapter_search_falls_back_to_fixtures_when_live_fetch_times_out(monkeypatch):
    """A live-mode adapter whose HTTP layer times out must not raise or 500 the API -- it
    should silently degrade to fixture data and record the failure in self.errors."""
    adapter = CromaAdapter(_settings())

    def fake_get(*a, **k):
        return None  # what app.utils.http.get returns on any request failure

    monkeypatch.setattr("app.scrapers.base.get", fake_get)
    listings = adapter.search("iPhone 17 Pro", {"storage": "256GB"})

    assert len(listings) > 0  # fixtures kicked in
    assert any("fetch failed" in e for e in adapter.errors)


# ---------------------------------------------------------------------------
# Malformed / unexpected retailer data ("selector changes")
# ---------------------------------------------------------------------------

def test_adapter_search_handles_non_html_garbage_response(monkeypatch):
    """Simulates a retailer returning something that isn't the expected product page at all
    (e.g. an interstitial CAPTCHA page, a maintenance page, truncated response)."""
    adapter = CromaAdapter(_settings())

    def fake_get(*a, **k):
        return _FakeResponse(text="<html><body>Please verify you are human</body></html>")

    monkeypatch.setattr("app.scrapers.base.get", fake_get)
    listings = adapter.search("iPhone 17 Pro", {"storage": "256GB"})

    # no JSON-LD, no matching CSS selectors -- live path legitimately finds nothing, so it
    # must fall back to fixtures rather than returning an empty/broken result
    assert len(listings) > 0


def test_jsonld_parser_ignores_malformed_script_blocks():
    adapter = CromaAdapter(_settings(SCRAPE_LIVE=False))
    from bs4 import BeautifulSoup

    html = """
    <html><body>
      <script type="application/ld+json">{not valid json at all</script>
      <script type="application/ld+json">{"@type": "Product", "name": "Test Phone",
        "offers": {"price": "12999", "availability": "http://schema.org/InStock"}}</script>
    </body></html>
    """
    soup = BeautifulSoup(html, "lxml")
    listings = adapter._parse_jsonld(soup)
    # the malformed block is skipped silently; the valid one still parses
    assert len(listings) == 1
    assert listings[0].selling_price == 12999.0


def test_jsonld_parser_handles_product_missing_offers_entirely():
    adapter = CromaAdapter(_settings(SCRAPE_LIVE=False))
    from bs4 import BeautifulSoup

    html = """
    <script type="application/ld+json">{"@type": "Product", "name": "No Offers Phone"}</script>
    """
    soup = BeautifulSoup(html, "lxml")
    listings = adapter._parse_jsonld(soup)
    assert len(listings) == 1
    assert listings[0].selling_price is None  # absent, not a crash


def test_html_fallback_returns_empty_list_not_exception_on_unrecognized_markup():
    adapter = CromaAdapter(_settings(SCRAPE_LIVE=False))
    from bs4 import BeautifulSoup

    soup = BeautifulSoup("<html><body><div>totally different site layout</div></body></html>", "lxml")
    listings = adapter._parse_html(soup)
    assert listings == []


# ---------------------------------------------------------------------------
# robots.txt
# ---------------------------------------------------------------------------

def test_can_fetch_defaults_to_allow_when_robots_txt_unreachable(monkeypatch):
    import urllib.robotparser

    def raise_on_read(self):
        raise OSError("simulated network failure fetching robots.txt")

    monkeypatch.setattr(urllib.robotparser.RobotFileParser, "read", raise_on_read)
    # cache is module-level in app.utils.http; use a unique host so this test doesn't
    # collide with cached results from other tests
    assert can_fetch("https://robots-unreachable-test.example/product", "EPI-Test/1.0") is True


def test_can_fetch_returns_true_when_respect_robots_disabled():
    assert can_fetch("https://example.com/anything", "EPI-Test/1.0", respect_robots=False) is True
