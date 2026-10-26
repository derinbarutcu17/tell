import sys
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from story_scout import research
from story_scout.research import SearchHit, collect_research, fetch_page, search

DDG_HTML = """
<html><body>
<div class="result">
  <h2 class="result__title">
    <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Falpha%3Futm_source%3Dnews&amp;rut=1">Alpha &amp; Beta</a>
  </h2>
  <a class="result__snippet" href="https://example.com/alpha">First   snippet
    here.</a>
</div>
<div class="result">
  <h2 class="result__title">
    <a class="result__a" href="https://docs.example.org/page">Docs Page</a>
  </h2>
  <a class="result__snippet" href="https://docs.example.org/page">Second <b>snippet</b>.</a>
</div>
</body></html>
"""

SAFE_PAGE = (
    "<html><head><title>Alpha Page</title><style>.x{color:red}</style></head>"
    "<body><h1>Head</h1><p>Hello   <b>world</b>.</p>"
    "<script>var x = 1;</script></body></html>"
)


class _Headers:
    def __init__(self, charset="utf-8"):
        self._charset = charset

    def get_content_charset(self):
        return self._charset


class _FakeResponse:
    def __init__(self, body, status=200, charset="utf-8"):
        self._body = body.encode("utf-8") if isinstance(body, str) else body
        self.status = status
        self.headers = _Headers(charset)
        self.closed = False

    def read(self, amount=-1):
        if amount is None or amount < 0:
            return self._body
        return self._body[:amount]

    def close(self):
        self.closed = True


class _Router:
    """urlopen stand-in: serves an inline search page and per-URL pages."""

    def __init__(self, pages=None, search_body=None):
        self.pages = dict(pages or {})
        self.search_body = search_body
        self.calls = []

    def __call__(self, request, timeout=None):
        url = getattr(request, "full_url", str(request))
        self.calls.append(url)
        if self.search_body is not None and url.startswith(research.SEARCH_ENDPOINT):
            return _FakeResponse(self.search_body)
        entry = self.pages.get(url)
        if entry is None:
            raise urllib.error.URLError(f"no route for {url}")
        if isinstance(entry, Exception):
            raise entry
        return entry


class _PatchMixin:
    def patch(self, pages=None, search_body=None):
        router = _Router(pages=pages, search_body=search_body)
        patcher = mock.patch.object(research, "urlopen", router)
        patcher.start()
        self.addCleanup(patcher.stop)
        return router


class TestSearch(unittest.TestCase, _PatchMixin):
    def test_parses_duckduckgo_html(self):
        router = self.patch(search_body=DDG_HTML)
        hits = search("alpha beta")
        self.assertEqual(len(hits), 2)
        self.assertEqual(
            hits[0],
            SearchHit(
                url="https://example.com/alpha?utm_source=news",
                title="Alpha & Beta",
                snippet="First snippet here.",
            ),
        )
        self.assertEqual(hits[1].url, "https://docs.example.org/page")
        self.assertEqual(hits[1].snippet, "Second snippet.")
        self.assertTrue(
            any(call.startswith(research.SEARCH_ENDPOINT + "?q=") for call in router.calls)
        )
        self.assertIn("alpha+beta", router.calls[0])

    def test_limit_caps_hits(self):
        self.patch(search_body=DDG_HTML)
        self.assertEqual(len(search("alpha", limit=1)), 1)

    def test_returns_empty_on_http_error(self):
        def boom(request, timeout=None):
            raise urllib.error.HTTPError(
                "https://html.duckduckgo.com/html/", 503, "Service Unavailable", None, None
            )

        with mock.patch.object(research, "urlopen", boom):
            self.assertEqual(search("anything"), [])

    def test_returns_empty_on_connection_error(self):
        def boom(request, timeout=None):
            raise urllib.error.URLError("offline")

        with mock.patch.object(research, "urlopen", boom):
            self.assertEqual(search("anything"), [])

    def test_returns_empty_for_blank_query(self):
        router = self.patch(search_body=DDG_HTML)
        self.assertEqual(search("   "), [])
        self.assertEqual(router.calls, [])


class TestFetchPage(unittest.TestCase, _PatchMixin):
    def test_strips_tags_and_collapses_whitespace(self):
        router = self.patch(pages={"https://example.com/a": _FakeResponse(SAFE_PAGE)})
        result = fetch_page("https://example.com/a")
        self.assertEqual(result, ("Alpha Page", "Head Hello world."))
        self.assertEqual(len(router.calls), 1)

    def test_truncates_to_max_chars(self):
        page = "<html><head><title>T</title></head><body><p>" + "x" * 100 + "</p></body></html>"
        self.patch(pages={"https://example.com/a": _FakeResponse(page)})
        title, text = fetch_page("https://example.com/a", max_chars=10)
        self.assertEqual(title, "T")
        self.assertEqual(text, "x" * 10)

    def test_blank_page_returns_none(self):
        page = "<html><head><title></title></head><body>   \n  </body></html>"
        self.patch(pages={"https://example.com/a": _FakeResponse(page)})
        self.assertIsNone(fetch_page("https://example.com/a"))

    def test_non_2xx_returns_none(self):
        self.patch(pages={"https://example.com/a": _FakeResponse(SAFE_PAGE, status=404)})
        self.assertIsNone(fetch_page("https://example.com/a"))

    def test_network_error_returns_none(self):
        self.patch(pages={"https://example.com/a": urllib.error.URLError("boom")})
        self.assertIsNone(fetch_page("https://example.com/a"))


class TestSafety(unittest.TestCase, _PatchMixin):
    UNSAFE = (
        "http://127.0.0.1/x",
        "http://localhost/x",
        "ftp://example.com/x",
        "http://169.254.1.1/x",
        "http://192.168.1.5/x",
        "http://10.0.0.5/x",
        "http://172.16.3.3/x",
        "http://[::1]/x",
        "http://0.0.0.0/x",
        "intranet/x",
    )

    def test_fetch_rejects_unsafe_urls_before_network(self):
        router = self.patch()
        for url in self.UNSAFE:
            with self.subTest(url=url):
                self.assertIsNone(fetch_page(url))
        self.assertEqual(router.calls, [])

    def test_collect_skips_unsafe_hits(self):
        hits = [SearchHit(url=url, title="bad", snippet="") for url in self.UNSAFE]
        router = self.patch()
        with mock.patch.object(research, "search", lambda q, **kw: list(hits)):
            evidence, omissions = collect_research(["q"])
        self.assertEqual(evidence, [])
        self.assertEqual(router.calls, [])
        self.assertTrue(any("unsafe url" in note for note in omissions))

    def test_public_url_is_safe(self):
        self.assertTrue(research.is_safe_url("https://example.com/a"))
        self.assertEqual(
            research.normalize_url("HTTPS://Example.COM/a/?utm_source=x&ref=y#frag"),
            "https://example.com/a",
        )


class TestCollectResearch(unittest.TestCase, _PatchMixin):
    def test_dedupes_url_and_utm_variants(self):
        hits = [
            SearchHit(url="https://example.com/a", title="A", snippet=""),
            SearchHit(url="https://example.com/a?utm_source=x", title="A utm", snippet=""),
            SearchHit(url="https://example.com/a/#frag", title="A frag", snippet=""),
            SearchHit(url="https://EXAMPLE.com/a?fbclid=1", title="A caps", snippet=""),
        ]
        router = self.patch(pages={"https://example.com/a": _FakeResponse(SAFE_PAGE)})
        with mock.patch.object(research, "search", lambda q, **kw: list(hits)):
            evidence, omissions = collect_research(["q"])
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0].url, "https://example.com/a")
        self.assertEqual(omissions, [])
        self.assertEqual(router.calls, ["https://example.com/a"])

    def test_failed_fetch_becomes_omission(self):
        hits = [
            SearchHit(url="https://example.com/ok", title="OK", snippet=""),
            SearchHit(url="https://example.com/gone", title="Gone", snippet=""),
        ]
        self.patch(pages={"https://example.com/ok": _FakeResponse(SAFE_PAGE)})
        with mock.patch.object(research, "search", lambda q, **kw: list(hits)):
            evidence, omissions = collect_research(["q"])
        self.assertEqual([item.url for item in evidence], ["https://example.com/ok"])
        self.assertIn("skipped https://example.com/gone: fetch failed", omissions)

    def test_empty_page_produces_no_evidence(self):
        hits = [SearchHit(url="https://example.com/empty", title="Empty", snippet="")]
        blank = "<html><head><title>Empty</title></head><body>  \t </body></html>"
        self.patch(pages={"https://example.com/empty": _FakeResponse(blank)})
        with mock.patch.object(research, "search", lambda q, **kw: list(hits)):
            evidence, omissions = collect_research(["q"])
        self.assertEqual(evidence, [])
        self.assertEqual(len(omissions), 1)
        self.assertIn("fetch failed", omissions[0])

    def test_evidence_shape_and_stable_id(self):
        hits = [
            SearchHit(url="https://example.com/a", title="", snippet=""),
            SearchHit(url="https://docs.example.org/b", title="Docs", snippet=""),
        ]
        pages = {
            "https://example.com/a": _FakeResponse(SAFE_PAGE),
            "https://docs.example.org/b": _FakeResponse(
                "<html><head><title>Docs</title></head><body><p>Doc body</p></body></html>"
            ),
        }
        self.patch(pages=pages)
        with mock.patch.object(research, "search", lambda q, **kw: list(hits)):
            evidence, omissions = collect_research(["q"])
        self.assertEqual(omissions, [])
        self.assertEqual(len(evidence), 2)
        first, second = evidence
        self.assertIsInstance(first, research.Evidence)
        self.assertEqual(first.kind, "research")
        self.assertEqual(first.source, "research")
        self.assertEqual(first.url, "https://example.com/a")
        self.assertEqual(first.label, "Alpha Page")
        self.assertIn("Head Hello world.", first.excerpt)
        self.assertIsNone(first.date)
        self.assertIsNone(first.local_path)
        self.assertIsNone(first.commit)
        self.assertIsNone(first.line_start)
        self.assertIsNone(first.line_end)
        self.assertEqual(first.id, "research:example-1")
        self.assertRegex(first.id, r"^research:[a-z0-9-]+-\d+$")
        self.assertEqual(second.id, "research:docs-2")
        self.assertEqual(second.label, "Docs")
        self.assertEqual(second.excerpt, "Doc body")

    def test_max_sources_caps_output(self):
        hits = [
            SearchHit(url=f"https://example.com/{name}", title=name, snippet="")
            for name in ("a", "b", "c", "d")
        ]
        pages = {
            f"https://example.com/{name}": _FakeResponse(SAFE_PAGE)
            for name in ("a", "b", "c", "d")
        }
        self.patch(pages=pages)
        with mock.patch.object(research, "search", lambda q, **kw: list(hits)):
            evidence, omissions = collect_research(["q1", "q2"], max_sources=2)
        self.assertEqual(len(evidence), 2)
        self.assertTrue(any("source limit (2)" in note for note in omissions))

    def test_search_failure_is_omission(self):
        self.patch()
        with mock.patch.object(research, "search", lambda q, **kw: []):
            evidence, omissions = collect_research(["quiet query"])
        self.assertEqual(evidence, [])
        self.assertEqual(omissions, ["search failed for query: quiet query"])

    def test_preserves_query_and_hit_order(self):
        pages = {
            "https://example.com/1": _FakeResponse(SAFE_PAGE),
            "https://example.com/2": _FakeResponse(SAFE_PAGE),
        }
        self.patch(pages=pages)

        def fake_search(query, **kwargs):
            return [
                SearchHit(url="https://example.com/2", title="2", snippet=""),
                SearchHit(url="https://example.com/1", title="1", snippet=""),
            ]

        with mock.patch.object(research, "search", fake_search):
            evidence, _ = collect_research(["q"])
        self.assertEqual(
            [item.url for item in evidence],
            ["https://example.com/2", "https://example.com/1"],
        )


if __name__ == "__main__":
    unittest.main()
