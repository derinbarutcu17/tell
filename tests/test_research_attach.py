from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from story_scout import research
from story_scout.models import StoryCandidate
from story_scout.research import SearchHit, attach_research


def _candidate(**overrides) -> StoryCandidate:
    base = dict(
        title="Two weeks of zero use ended the export button",
        angle="Usage data made the maintenance cost impossible to defend",
        rationale="A concrete, checkable removal",
        audience="Builders",
        evidence_ids=("agent:abc:1",),
        confidence=0.8,
        fact="Two weeks, zero recorded uses",
        interpretation="Maintenance outweighed value",
        research_query="feature removal maintenance cost",
    )
    base.update(overrides)
    return StoryCandidate(**base)


class AttachResearchTests(unittest.TestCase):
    def test_relevant_source_is_attached(self) -> None:
        hit = SearchHit(url="https://example.com/essay", title="The cost of unused features", snippet="")
        page = (
            "The cost of unused features",
            "Dead features still carry maintenance cost. Removing unused features saves engineering time.",
        )
        with mock.patch.object(research, "search", return_value=[hit]):
            with mock.patch.object(research, "fetch_page", return_value=page):
                updated, evidence, notes = attach_research([_candidate()])
        self.assertEqual(updated[0].research_urls, ("https://example.com/essay",))
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0].kind, "research")
        self.assertEqual(evidence[0].source, "research")
        self.assertEqual(evidence[0].url, "https://example.com/essay")
        self.assertTrue(any("cited" in note for note in notes))

    def test_unrelated_source_is_refused(self) -> None:
        hit = SearchHit(url="https://pharmacy.example/risk", title="Absolute risk reduction", snippet="")
        page = ("Absolute risk reduction", "Statins lowered absolute risk in a trial of patients.")
        with mock.patch.object(research, "search", return_value=[hit]):
            with mock.patch.object(research, "fetch_page", return_value=page):
                updated, evidence, notes = attach_research([_candidate()])
        self.assertEqual(updated[0].research_urls, ())
        self.assertEqual(evidence, [])
        self.assertTrue(any("no concrete overlap" in note for note in notes))

    def test_failed_fetch_is_not_a_citation(self) -> None:
        hit = SearchHit(url="https://example.com/dead", title="Unused features", snippet="")
        with mock.patch.object(research, "search", return_value=[hit]):
            with mock.patch.object(research, "fetch_page", return_value=None):
                updated, evidence, notes = attach_research([_candidate()])
        self.assertEqual(updated[0].research_urls, ())
        self.assertEqual(evidence, [])
        self.assertTrue(any("fetch failed" in note for note in notes))

    def test_no_hits_leaves_the_idea_clean(self) -> None:
        with mock.patch.object(research, "search", return_value=[]):
            updated, evidence, notes = attach_research([_candidate()])
        self.assertEqual(updated[0].research_urls, ())
        self.assertEqual(evidence, [])
        self.assertTrue(any("no source found" in note for note in notes))

    def test_missing_query_is_derived_from_the_idea(self) -> None:
        hit = SearchHit(url="https://example.com/a", title="Unused features cost money", snippet="")
        page = ("Unused features cost money", "Removing unused features saves maintenance cost.")
        with mock.patch.object(research, "search", return_value=[hit]) as search:
            with mock.patch.object(research, "fetch_page", return_value=page):
                attach_research([_candidate(research_query="")])
        query = search.call_args.args[0]
        self.assertTrue(query.strip())
        self.assertIn("export", query.lower())

    def test_sources_on_the_same_domain_get_unique_ids(self) -> None:
        hits = [
            SearchHit(url="http://arxiv.org/abs/2001.00001v1", title="Unused features cost", snippet=""),
            SearchHit(url="http://arxiv.org/abs/2002.00002v1", title="Maintenance cost of unused features", snippet=""),
        ]
        pages = {
            "http://arxiv.org/abs/2001.00001v1": (
                "Unused features cost",
                "Unused features carry maintenance cost and removing them saves time.",
            ),
            "http://arxiv.org/abs/2002.00002v1": (
                "Maintenance cost of unused features",
                "Removing unused features reduces maintenance cost in engineering teams.",
            ),
        }
        with mock.patch.object(research, "search", side_effect=[[hits[0]], [hits[1]]]):
            with mock.patch.object(
                research, "fetch_page", side_effect=lambda url, **kw: pages.get(url)
            ):
                updated, evidence, _ = attach_research(
                    [_candidate(), _candidate(title="Second idea about unused features")]
                )
        ids = [item.id for item in evidence]
        urls = {item.url for item in evidence}
        self.assertEqual(len(ids), 2)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(
            urls, {"http://arxiv.org/abs/2001.00001v1", "http://arxiv.org/abs/2002.00002v1"}
        )
        self.assertTrue(all(item.research_urls for item in updated))

    def test_weak_source_hosts_are_skipped(self) -> None:
        hit = SearchHit(url="https://github.com/x/y", title="Unused features cost", snippet="")
        with mock.patch.object(research, "search", return_value=[hit]):
            with mock.patch.object(research, "fetch_page") as fetch:
                updated, evidence, notes = attach_research([_candidate()])
        fetch.assert_not_called()
        self.assertEqual(updated[0].research_urls, ())
        self.assertTrue(any("code host" in note for note in notes))

    def test_best_overlapping_source_wins(self) -> None:
        weak = SearchHit(url="https://example.com/weak", title="Feature flags", snippet="")
        strong = SearchHit(url="https://example.com/strong", title="Unused features and maintenance", snippet="")
        pages = {
            "https://example.com/weak": ("Feature flags", "Flags let teams ship faster."),
            "https://example.com/strong": (
                "Unused features and maintenance",
                "Unused features carry maintenance cost, so removing them saves engineering time.",
            ),
        }
        with mock.patch.object(research, "search", return_value=[weak, strong]):
            with mock.patch.object(
                research, "fetch_page", side_effect=lambda url, **kw: pages.get(url)
            ):
                updated, evidence, _ = attach_research([_candidate()])
        self.assertEqual(updated[0].research_urls, ("https://example.com/strong",))
        self.assertEqual(evidence[0].url, "https://example.com/strong")


if __name__ == "__main__":
    unittest.main()
