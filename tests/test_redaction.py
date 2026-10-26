from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from story_scout.models import Evidence, StoryCandidate
from story_scout.redact import redact
from story_scout.sources import collect_evidence
from story_scout.store import Store


class RedactionTests(unittest.TestCase):
    def test_redact_removes_keys_tokens_and_home_paths(self) -> None:
        dirty = (
            "exported sk-abcdefghijklmnop1234 and ghp_abcdefghijklmnopqrstuvwxyz, "
            "password=hunter2, Authorization: Bearer abcdefghijklmnop, "
            "see /Users/derin/secret/plan.md"
        )
        clean = redact(dirty)
        self.assertNotIn("sk-abcdefghijklmnop1234", clean)
        self.assertNotIn("ghp_abcdefghijklmnopqrstuvwxyz", clean)
        self.assertNotIn("hunter2", clean)
        self.assertNotIn("abcdefghijklmnop", clean)
        self.assertNotIn("/Users/derin", clean)
        self.assertIn("[redacted]", clean)
        self.assertIn("~/secret/plan.md", clean)

    def test_file_evidence_is_redacted_before_it_can_be_sent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "notes.md").write_text(
                "# Setup\nMy api_key=supersecretvalue and my notes live in /Users/derin/notes.\n",
                encoding="utf-8",
            )
            evidence, _ = collect_evidence([root], days=3650)
        self.assertEqual(len(evidence), 1)
        excerpt = evidence[0].excerpt
        self.assertNotIn("supersecretvalue", excerpt)
        self.assertNotIn("/Users/derin", excerpt)
        self.assertIn("[redacted]", excerpt)

    def test_store_roundtrips_research_citations_and_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = Store(Path(temporary) / "tell.sqlite")
            work = Evidence(
                id="agent:abc:1",
                label="Session #1",
                kind="agent",
                excerpt="I removed the export button after two weeks of zero use.",
                source="agent",
                local_path="/repo",
            )
            research = Evidence(
                id="research:arxiv-1",
                label="Citation decay",
                kind="research",
                excerpt="Generated references often stop resolving.",
                source="research",
                url="http://arxiv.org/abs/2601.00001v1",
            )
            candidate = StoryCandidate(
                title="Deleting a feature nobody used",
                angle="Two weeks of zero use ended a feature.",
                rationale="A visible, checkable decision.",
                audience="Builders",
                evidence_ids=("agent:abc:1",),
                confidence=0.8,
                fact="Usage was zero for two weeks.",
                interpretation="The maintenance cost outweighed the value.",
                research_urls=("http://arxiv.org/abs/2601.00001v1",),
                channel_x="I deleted a button nobody pressed.",
                channel_linkedin="Two weeks, zero uses, one deletion.",
            )
            ids = store.save_candidates([candidate], [work, research])
            story = store.get_story(ids[0])

        self.assertEqual(story["research_urls"], ["http://arxiv.org/abs/2601.00001v1"])
        self.assertEqual(story["channel_x"], "I deleted a button nobody pressed.")
        self.assertEqual(story["fact"], "Usage was zero for two weeks.")
        sources = {item["id"]: item for item in story["evidence"]}
        self.assertEqual(sources["agent:abc:1"]["source"], "agent")
        self.assertEqual(sources["research:arxiv-1"]["url"], "http://arxiv.org/abs/2601.00001v1")


if __name__ == "__main__":
    unittest.main()
