# Tell build plan

Status: Phase 0, Phase 1, and Phase 2 are implemented and verified on 2026-10-26. Phase 2's forced-connection gate is not built: the model decides whether to cite, and its citation rate varies with how specific the work material is. Phase 3 is partly done: the HTML inbox renders saved ideas with research links; keep and reject are still CLI-only. Phase 4 is not started.

Target: the version described in `IDEA.md`. Capture runs while I work. Small dashboard. Research-backed angles. X and LinkedIn.

Guiding rule: the first milestone is a test, not a product. It has to answer one question: does automatic capture beat me pasting the same material into the same prompt?

Stack stays as it is: Python 3.11+, standard library, SQLite, `opencode-go/beam-free`. No new dependencies.

---

## Phase 0: the test rig (today, 2 to 3 hours)

Goal: point Tell at one repo and one agent conversation, get ideas with real research links, judge them.

1. `src/story_scout/capture.py` (new)
   - `capture_conversation(path)` reads one exported or on-disk agent transcript (JSONL or markdown) and turns it into `Evidence` items.
   - Default extraction: my messages plus the agent's final answers. Tool calls are summarized by name, not by full output.
   - Bounded per item, deduplicated, `source="agent"`.
2. `src/story_scout/research.py` (new)
   - `find_sources(queries, limit)` performs the search and fetches each result page.
   - A source is only kept if the fetch succeeds and the excerpt is non-empty. Otherwise it is recorded as an omission, never as a citation.
   - `source="research"`, keeps `url` and fetched excerpt.
3. `models.py`
   - `Evidence` gains `source` and `url`.
   - Research evidence is never allowed to carry a claim; it carries a quote.
4. `model.py`
   - New prompt: given work evidence plus fetched research excerpts, return up to 5 ideas. Each idea needs a title, the angle, the truthfulness split (what is fact from my work, what is my interpretation), the cited work evidence IDs, the cited research URLs, one X framing, one LinkedIn framing.
   - Reject an idea that cites a URL not present in the fetched set.
   - Keep the existing strict validation style.
5. `render.py` (new)
   - `render_inbox(ideas, path)` writes a single self-contained `inbox.html`: one card per idea, with the angle, the research link, and the work evidence it came from.
   - This is the "small dashboard" for the test. No server.
6. `cli.py`
   - `tell scan --days 7 --remote` keeps working.
   - `tell inbox` renders and prints the path.

Check for Phase 0: a run over one real repo plus one real conversation produces ideas, every research citation opens in a browser, and I can say yes or no to each idea. If fewer than 5 good ones appear, that is the answer to the spike, not a bug to paper over.

Also in Phase 0: update `AGENTS.md`, `PRODUCT.md`, and `ARCHITECTURE.md`. All three currently forbid background capture and describe a CLI-only product. My decision overrides them, so the docs must stop contradicting the code.

---

## Phase 1: capture that actually runs while I work (half day)

1. Discover agent sessions automatically from configured locations, starting with OpenCode's storage and Codex's session files.
2. Register projects, not files. One entry per repo, with an allowlist. Nothing outside it is read.
3. Incremental capture with a cursor: running twice adds only new material.
4. Redaction pass before storage and before any remote call: credential-like strings, long tokens, absolute home paths.
5. `tell capture` runs silently and reports counts only.

Check: run capture twice and confirm the second run adds nothing new. Plant a fake key in a transcript and confirm it never reaches storage or the packet.

---

## Phase 2: research that holds up (half day)

1. Query generation per candidate angle, two to three queries each.
2. Fetch, extract, and store the quote, not just the link.
3. Recency window and a hard filter on link rot.
4. A forced-connection gate: an idea is dropped when the research excerpt shares no concrete term with my work evidence.

Check: a fabricated URL is rejected. A page that 404s is recorded as an omission. An idea built on a forced connection is dropped, and the drop is visible.

---

## Phase 3: the dashboard I actually open (one day)

1. Persistent inbox in SQLite, newest first.
2. Keep, reject, and draft per idea, from the page as well as the CLI.
3. Per-channel framing stored separately: X and LinkedIn.
4. Draft generation stays behind an explicit remote flag and never publishes.

Check: close the laptop, reopen, and the inbox still shows the same state.

---

## Phase 4: make Monday lunch break real (two days)

1. A scheduled capture run, so Monday is already populated.
2. Failure handling: a clear message when the model is unreachable, and no half-written ideas.
3. Privacy pass: what is stored, what is sent, what is deleted, and a command to delete a project's data.
4. Version bump and a short README rewrite for the new shape.

Check: two consecutive Mondays with no manual step.

---

## Decisions I still need from you

1. Which transcript to test with today: one you export and drop in a folder, or let me read the on-disk OpenCode session storage directly.
2. Which agent logs count as capture: OpenCode only, or also Codex and Hermes.
3. Whether tool output is captured, or only my messages and the agent's answers. Full output is far richer and far riskier.

## Risks

- `beam-free` may be weak at synthesis. If it is, the fix is a better prompt and a stronger retrieval step before it is a different model.
- Search without an API key is brittle. Phase 2 may need a paid search key; that is a cost decision, not a build decision.
- Capture while working means transcripts with client and personal material land in a local database. That needs the allowlist and the delete command to be real, not aspirational.
- The 5-ideas-per-week bar may simply be too high for a normal week. If so, the number changes, not the tool.
