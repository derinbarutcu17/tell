import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from story_scout.render import render_inbox


def make_idea(**overrides):
    idea = {
        "title": "A small tool that found a big gap",
        "angle": "The gap was in the handoff, not the code.",
        "why": "Other small teams hit the same handoff problem.",
        "fact": "Two commits removed the manual export step.",
        "interpretation": "The team may value fewer handoffs over more features.",
        "audience": "Solo developers running small tools",
        "confidence": 0.42,
        "work_evidence_ids": ["ev-1", "ev-2"],
        "research_urls": ["https://example.com/report"],
        "channels": {"x": "Short framing for X.", "linkedin": "Longer framing for LinkedIn."},
    }
    idea.update(overrides)
    return idea


class RenderInboxTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def render(self, ideas, name="inbox.html", **kwargs):
        return render_inbox(ideas, self.root / name, **kwargs)

    def test_renders_file_and_returns_path(self):
        destination = self.root / "nested" / "inbox.html"
        returned = render_inbox([make_idea()], destination, generated_at="2026-10-26T10:00:00Z")
        self.assertIsInstance(returned, Path)
        self.assertEqual(returned, destination)
        self.assertTrue(destination.exists())
        text = destination.read_text(encoding="utf-8")
        self.assertIn("<!DOCTYPE html>", text)
        self.assertIn("A small tool that found a big gap", text)

    def test_script_in_title_is_escaped(self):
        destination = self.render([make_idea(title="<script>alert(1)</script>")])
        text = destination.read_text(encoding="utf-8")
        self.assertNotIn("<script>", text)
        self.assertNotIn("<script", text.lower())
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", text)

    def test_javascript_url_is_skipped(self):
        destination = self.render(
            [make_idea(research_urls=["javascript:alert(1)", "JaVaScRiPt:alert(2)"])]
        )
        text = destination.read_text(encoding="utf-8")
        self.assertNotIn("javascript:", text.lower())
        self.assertNotIn("<a ", text)

    def test_https_url_becomes_safe_link(self):
        destination = self.render([make_idea(research_urls=["https://example.com/report"])])
        text = destination.read_text(encoding="utf-8")
        self.assertIn('href="https://example.com/report"', text)
        self.assertIn('target="_blank"', text)
        self.assertIn('rel="noopener noreferrer"', text)

    def test_empty_list_renders_empty_state(self):
        destination = self.render([])
        text = destination.read_text(encoding="utf-8")
        self.assertIn("Nothing yet", text)

    def test_output_is_deterministic(self):
        ideas = [make_idea(), make_idea(title="Second idea", confidence=0.9)]
        first = self.root / "first.html"
        second = self.root / "second.html"
        render_inbox(ideas, first, generated_at="2026-10-26T10:00:00Z")
        render_inbox(ideas, second, generated_at="2026-10-26T10:00:00Z")
        self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_missing_optional_keys_do_not_raise(self):
        idea = {
            "title": "Bare idea",
            "angle": "Only the required text is present.",
            "why": "",
            "fact": "One commit.",
            "interpretation": "",
            "audience": "",
        }
        destination = self.render([idea])
        text = destination.read_text(encoding="utf-8")
        self.assertIn("Bare idea", text)
        self.assertIn("Fact from your work", text)
        self.assertIn("Interpretation", text)

    def test_confidence_renders_as_percentage(self):
        destination = self.render([make_idea(confidence=0.42)])
        text = destination.read_text(encoding="utf-8")
        self.assertIn("42%", text)


if __name__ == "__main__":
    unittest.main()
