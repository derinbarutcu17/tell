from __future__ import annotations

import http.client
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from story_scout import server as server_module
from story_scout.models import Evidence, StoryCandidate
from story_scout.store import Store


class ServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="tell-server-")
        root = Path(self.temp.name)
        self.project = root / "project"
        self.project.mkdir()
        self.store = Store(root / "tell.sqlite")
        self.store.add_source(self.project)
        self.story_id = self.store.save_candidates(
            [
                StoryCandidate(
                    title="A stored idea",
                    angle="Angle",
                    rationale="Why",
                    audience="Builders",
                    evidence_ids=("e1",),
                    confidence=0.9,
                    fact="Something happened",
                    interpretation="Something inferred",
                    channel_x="x",
                    channel_linkedin="li",
                    research_query="query",
                )
            ],
            [Evidence(id="e1", label="notes.md", kind="markdown", excerpt="text")],
        )[0]
        self.server = server_module.TellServer(("127.0.0.1", 0), self.store)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.temp.cleanup()

    def request(self, method: str, path: str, body: dict | None = None) -> tuple[int, dict | bytes]:
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        payload = json.dumps(body).encode() if body is not None else None
        headers = {"Content-Type": "application/json"} if payload else {}
        connection.request(method, path, body=payload, headers=headers)
        response = connection.getresponse()
        raw = response.read()
        connection.close()
        content_type = response.getheader("Content-Type") or ""
        if content_type.startswith("application/json"):
            return response.status, json.loads(raw.decode("utf-8"))
        return response.status, raw

    def test_index_serves_the_dashboard(self) -> None:
        status, body = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b"Tell", body)  # type: ignore[arg-type]

    def test_state_lists_ideas_sources_and_models(self) -> None:
        status, payload = self.request("GET", "/api/state")
        self.assertEqual(status, 200)
        assert isinstance(payload, dict)
        self.assertEqual(len(payload["ideas"]), 1)
        self.assertEqual(payload["ideas"][0]["title"], "A stored idea")
        self.assertEqual(payload["ideas"][0]["channels"]["x"], "x")
        self.assertEqual(len(payload["sources"]), 1)
        self.assertIn("opencode-go/beam-free", payload["settings"]["models"])

    def test_status_can_be_kept_and_rejected(self) -> None:
        status, payload = self.request(
            "POST", f"/api/ideas/{self.story_id}/status", {"status": "kept"}
        )
        self.assertEqual(status, 200)
        assert isinstance(payload, dict)
        self.assertTrue(payload["ok"])
        self.assertEqual(self.store.get_story(self.story_id)["status"], "kept")

        status, _ = self.request("POST", f"/api/ideas/{self.story_id}/status", {"status": "maybe"})
        self.assertEqual(status, 400)

    def test_settings_only_accept_free_models(self) -> None:
        status, payload = self.request(
            "POST", "/api/settings", {"model": "opencode/deepseek-v4.1-flash-free"}
        )
        self.assertEqual(status, 200)
        self.assertEqual(self.store.get_setting("model"), "opencode/deepseek-v4.1-flash-free")

        status, payload = self.request("POST", "/api/settings", {"model": "openai/gpt-6-luna"})
        self.assertEqual(status, 400)
        assert isinstance(payload, dict)
        self.assertIn("free", payload["error"])

    def test_sources_can_be_added_and_removed(self) -> None:
        other = Path(self.temp.name) / "second"
        other.mkdir()
        status, payload = self.request("POST", "/api/sources", {"path": str(other)})
        self.assertEqual(status, 200)
        assert isinstance(payload, dict)
        new_id = payload["id"]

        status, _ = self.request("POST", "/api/sources", {"path": str(other / "missing")})
        self.assertEqual(status, 400)

        status, payload = self.request("DELETE", f"/api/sources/{new_id}")
        self.assertEqual(status, 200)
        self.assertNotIn(new_id, [row["id"] for row in self.store.list_sources()])

    def test_test_connection_reports_success_and_failure(self) -> None:
        original = server_module.check_connection
        try:
            server_module.check_connection = lambda model, **kw: (True, "Connected.")
            status, payload = self.request("POST", "/api/test-connection", {"model": "opencode-go/beam-free"})
            self.assertEqual(status, 200)
            assert isinstance(payload, dict)
            self.assertTrue(payload["ok"])

            server_module.check_connection = lambda model, **kw: (False, "blocked")
            status, payload = self.request("POST", "/api/test-connection", {"model": "opencode-go/beam-free"})
            self.assertEqual(status, 200)
            assert isinstance(payload, dict)
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["message"], "blocked")
        finally:
            server_module.check_connection = original

    def test_unknown_route_is_404(self) -> None:
        status, _ = self.request("GET", "/api/nope")
        self.assertEqual(status, 404)


if __name__ == "__main__":
    unittest.main()
