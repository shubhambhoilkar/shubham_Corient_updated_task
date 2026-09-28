"""
Covers failure modes that only show up under partial failure or concurrent load -- the kind
of thing a request-response unit test won't exercise on its own.
"""
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.services import orchestrator
from app.settings_view import SettingsView


class _BrokenAdapter:
    """Simulates a retailer adapter whose search() blows up unexpectedly (parsing bug,
    unhandled response shape, etc) rather than degrading gracefully on its own."""

    source_name = "broken_source"
    errors: list[str] = []

    def __init__(self, settings):
        pass

    def search(self, query, filters):
        raise RuntimeError("simulated unexpected adapter crash")


class _EmptyAdapter:
    """Simulates a retailer that responds successfully but has nothing matching this query
    (as opposed to failing outright) -- a different partial-result scenario."""

    source_name = "empty_source"
    errors: list[str] = []

    def __init__(self, settings):
        pass

    def search(self, query, filters):
        return []


def test_partial_failure_one_adapter_crashing_does_not_fail_the_whole_search(app, db, monkeypatch):
    """One adapter raising must not take down results from the healthy ones, and must be
    visible in partial_failures / crawl.sources_failed rather than silently swallowed."""
    from app.scrapers.croma import CromaAdapter

    monkeypatch.setattr(
        orchestrator,
        "get_enabled_adapters",
        lambda settings, only=None: [CromaAdapter(settings), _BrokenAdapter(settings)],
    )

    settings = SettingsView(app.config)
    result = orchestrator.run_search(settings, "iPhone 17 Pro", {"storage": "256GB"})

    assert len(result["listings"]) > 0  # Croma's results still came through
    assert result["crawl"]["sources_attempted"] == 2
    assert result["crawl"]["sources_succeeded"] == 1
    assert result["crawl"]["sources_failed"] == 1
    assert any(f["source"] == "broken_source" for f in result["partial_failures"])
    assert result["crawl"]["status"] == "completed"  # partial success, not a hard failure


def test_all_adapters_failing_marks_crawl_as_failed_but_does_not_raise(app, db, monkeypatch):
    monkeypatch.setattr(
        orchestrator,
        "get_enabled_adapters",
        lambda settings, only=None: [_BrokenAdapter(settings)],
    )

    settings = SettingsView(app.config)
    result = orchestrator.run_search(settings, "anything", {})

    assert result["listings"] == []
    assert result["crawl"]["status"] == "failed"
    assert result["crawl"]["sources_succeeded"] == 0


def test_empty_result_from_one_source_is_not_treated_as_an_error(app, db, monkeypatch):
    """A source that legitimately has no matching stock is a *result*, not a *failure* --
    these two must stay distinguishable in the response."""
    from app.scrapers.croma import CromaAdapter

    monkeypatch.setattr(
        orchestrator,
        "get_enabled_adapters",
        lambda settings, only=None: [CromaAdapter(settings), _EmptyAdapter(settings)],
    )

    settings = SettingsView(app.config)
    result = orchestrator.run_search(settings, "iPhone 17 Pro", {"storage": "256GB"})

    assert not any(f["source"] == "empty_source" for f in result["partial_failures"])
    assert result["crawl"]["sources_succeeded"] == 1  # only croma actually returned rows


# ---------------------------------------------------------------------------
# Concurrency
# ---------------------------------------------------------------------------

def test_concurrent_searches_do_not_corrupt_each_others_data(client):
    """Fires several /api/search requests at once against the same Flask test client and
    checks each gets back a self-consistent, distinct crawl -- guards against shared
    mutable state (e.g. a module-level cache) leaking between concurrent requests."""

    def do_search(query):
        resp = client.post("/api/search", json={"query": query, "storage": "256GB"})
        return resp.status_code, resp.get_json()

    queries = ["iPhone 17 Pro", "iPhone 17", "iPhone 17 Pro", "iPhone 17"]
    with ThreadPoolExecutor(max_workers=4) as pool:
        outcomes = list(pool.map(do_search, queries))

    for status, data in outcomes:
        assert status == 200
        assert data["crawl"]["query"] in queries
        for r in data["results"]:
            # every listing's own product must match what was actually searched -- if
            # concurrent requests were corrupting shared state, this is where it would show
            assert data["crawl"]["query"].replace(" Pro", "") in r["product"]["product_name"] \
                or "Pro" in data["crawl"]["query"]

    crawl_ids = {data["crawl"]["crawl_id"] for _, data in outcomes}
    assert len(crawl_ids) == len(queries)  # every request got its own crawl record


# ---------------------------------------------------------------------------
# Performance smoke test
# ---------------------------------------------------------------------------

def test_fixture_mode_search_completes_quickly(app, db):
    """Not a load test -- a smoke test that a single search against fixture data (the mode
    used for local dev/CI) stays fast, so a future change that accidentally adds a slow
    per-item DB round trip or an unbounded retry loop gets caught immediately instead of only
    showing up as "the app feels slow" much later."""
    settings = SettingsView(app.config)
    started = time.monotonic()
    result = orchestrator.run_search(settings, "iPhone 17 Pro", {"storage": "256GB"})
    elapsed = time.monotonic() - started

    assert len(result["listings"]) > 0
    assert elapsed < 2.0, f"fixture-mode search took {elapsed:.2f}s, expected < 2s"
