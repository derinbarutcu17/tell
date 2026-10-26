from __future__ import annotations

import ipaddress
import json
import sys
import unittest
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from story_scout import research
from story_scout.research import search

HN_PAYLOAD = {
    "hits": [
        {
            "title": "Show HN: Local memory for agents",
            "url": "https://github.com/example/local-memory",
            "points": 400,
            "num_comments": 90,
            "objectID": "1",
        },
        {
            "title": "Why local memory is hard to get right",
            "url": "https://example.org/essay",
            "points": 120,
            "num_comments": 40,
            "objectID": "2",
        },
        {
            "title": "A discussion post",
            "url": "",
            "points": 5,
            "num_comments": 2,
            "objectID": "77",
        },
    ]
}

DDG_HTML = (
    '<html><body><div class="result">'
    '<a class="result__a" href="https://example.com/ddg">Duck result</a>'
    '<a class="result__snippet" href="https://example.com/ddg">Snippet.</a>'
    "</div></body></html>"
)


class ProviderTests(unittest.TestCase):
    def patch_read(self, responses: dict[str, bytes | None]):
        def fake_read(url, *, timeout):
            for needle, payload in responses.items():
                if needle in url:
                    if isinstance(payload, Exception):
                        raise payload
                    return payload
            return None

        patcher = mock.patch.object(research, "_read", side_effect=fake_read)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_hackernews_is_used_first_and_parses_json(self) -> None:
        self.patch_read({"hn.algolia.com": json.dumps(HN_PAYLOAD).encode()})
        hits = search("local memory agents", limit=3)
        self.assertTrue(hits)
        self.assertEqual(hits[0].url, "https://example.org/essay")
        self.assertTrue(all(hit.url.startswith("http") for hit in hits))

    def test_missing_url_falls_back_to_the_hn_item_page(self) -> None:
        self.patch_read({"hn.algolia.com": json.dumps(HN_PAYLOAD).encode()})
        hits = search("local memory agents", limit=5)
        targets = {hit.url for hit in hits}
        self.assertIn("https://news.ycombinator.com/item?id=77", targets)

    def test_show_hn_launch_posts_are_excluded(self) -> None:
        self.patch_read({"hn.algolia.com": json.dumps(HN_PAYLOAD).encode()})
        hits = search("local memory agents", limit=5)
        titles = [hit.title for hit in hits]
        self.assertNotIn("Show HN: Local memory for agents", titles)
        self.assertIn("Why local memory is hard to get right", titles)

    def test_arxiv_contributes_research_entries(self) -> None:
        arxiv_xml = (
            '<feed xmlns="http://www.w3.org/2005/Atom">'
            "<entry><title>Citation decay in generated references</title>"
            "<id>http://arxiv.org/abs/2601.00001v1</id>"
            "<summary>We measure how often generated citations stop resolving.</summary>"
            "</entry></feed>"
        ).encode()
        self.patch_read(
            {
                "hn.algolia.com": json.dumps({"hits": []}).encode(),
                "export.arxiv.org": arxiv_xml,
            }
        )
        hits = search("citation decay references", limit=3)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].url, "http://arxiv.org/abs/2601.00001v1")
        self.assertIn("Citation decay", hits[0].title)

    def test_duckduckgo_is_used_when_hackernews_returns_nothing(self) -> None:
        self.patch_read(
            {
                "hn.algolia.com": json.dumps({"hits": []}).encode(),
                "html.duckduckgo.com": DDG_HTML.encode(),
            }
        )
        hits = search("local memory agents", limit=3)
        self.assertEqual([hit.url for hit in hits], ["https://example.com/ddg"])

    def test_wikipedia_is_the_last_resort(self) -> None:
        payload = json.dumps(
            [
                "local memory",
                ["Local memory"],
                ["https://en.wikipedia.org/wiki/Local_memory"],
                ["A short description."],
            ]
        ).encode()
        self.patch_read(
            {
                "hn.algolia.com": json.dumps({"hits": []}).encode(),
                "html.duckduckgo.com": b"<html><body>no results</body></html>",
                "en.wikipedia.org": payload,
            }
        )
        hits = search("local memory", limit=3)
        self.assertEqual([hit.url for hit in hits], ["https://en.wikipedia.org/wiki/Local_memory"])

    def test_all_providers_failing_returns_empty_without_raising(self) -> None:
        self.patch_read({})
        self.assertEqual(search("anything at all", limit=3), [])

    def test_empty_query_short_circuits(self) -> None:
        self.patch_read({})
        self.assertEqual(search("   ", limit=3), [])


class SafeUrlTests(unittest.TestCase):
    def test_literal_private_addresses_are_rejected(self) -> None:
        for url in (
            "http://127.0.0.1/",
            "http://10.1.2.3/",
            "http://192.168.1.5/",
            "http://169.254.1.1/",
            "http://[::1]/",
            "http://0.0.0.0/",
            "http://localhost/",
            "ftp://example.com/x",
            "javascript:alert(1)",
        ):
            self.assertFalse(research.is_safe_url(url), url)

    def test_shortcut_loopback_forms_are_rejected_after_resolution(self) -> None:
        loopback = [ipaddress.ip_address("127.0.0.1")]
        for url in ("http://127.1/", "http://0x7f.1/", "http://127.0.0.1.nip.io/"):
            with mock.patch.object(research, "_resolve_addresses", return_value=loopback):
                self.assertFalse(research.is_safe_url(url), url)

    def test_hostname_resolving_to_a_private_address_is_rejected(self) -> None:
        private = [ipaddress.ip_address("10.0.0.5")]
        with mock.patch.object(research, "_resolve_addresses", return_value=private):
            self.assertFalse(research.is_safe_url("https://intruder.example/post"))

    def test_public_hostname_is_allowed(self) -> None:
        public = [ipaddress.ip_address("93.184.216.34")]
        with mock.patch.object(research, "_resolve_addresses", return_value=public):
            self.assertTrue(research.is_safe_url("https://example.com/post"))

    def test_unresolvable_hostname_is_left_to_the_fetch_to_fail(self) -> None:
        with mock.patch.object(research, "_resolve_addresses", return_value=[]):
            self.assertTrue(research.is_safe_url("https://nothing.example/post"))

    def test_redirect_to_a_private_address_is_refused(self) -> None:
        handler = research._SafeRedirectHandler()
        fake_request = mock.Mock()
        with self.assertRaises(HTTPError):
            handler.redirect_request(
                fake_request, None, 302, "Found", {}, "http://192.168.1.1/admin"
            )


if __name__ == "__main__":
    unittest.main()
