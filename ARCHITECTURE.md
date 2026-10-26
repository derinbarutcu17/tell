# Architecture and agent contracts

## Runtime

Python 3.11+ and the standard library only. Tell is a local command-line tool that renders a local HTML inbox. SQLite stores registered sources, bounded excerpts, and review state under the user's application-support directory.

The installed OpenCode CLI is the model adapter. Free models only: `opencode-go/beam-free` (default) and `opencode/deepseek-v4.1-flash-free`. No remote model call happens during a preview. A scan requires the explicit `--remote` flag before it sends the packet.

Capture reads agent session databases that already exist on disk. Tell never records the screen or the keyboard, and it never creates a second log of the user's work.

## Shared data types

The source of truth is `src/story_scout/models.py`.

Evidence fields:
- id: stable ID within a packet.
- label: relative file path, short commit label, session title, or page domain. Never an absolute home path.
- kind: `git_commit`, `markdown`, `text`, `agent`, or `research`.
- source: `git`, `file`, `agent`, or `research`.
- excerpt: bounded text.
- date: ISO date or null.
- local_path: absolute path kept locally for provenance, never sent to a model.
- commit, line_start, line_end: provenance or null.
- url: the fetched page for research evidence, otherwise null.

StoryCandidate fields:
- title, angle, rationale, audience.
- fact: what the work evidence literally shows.
- interpretation: what the model inferred. Must stay separate from fact.
- evidence_ids: one or more IDs that must exist in the packet.
- research_urls: only URLs that Tell fetched during that run. Anything else is dropped with a warning.
- channel_x, channel_linkedin: short channel framings.
- confidence: number from 0 to 1.

## Modules

- `capture.py` reads agent session data. It supports the current OpenCode tables (`session_v2`, `session_message`), the older `session`/`message`/`part` tables, Codex-style rollout JSONL, and plain Markdown exports. It pairs each user message with the agent text that followed it, skips child subagent sessions, applies redaction, and bounds output.
- `sources.py` gathers file and Git evidence inside registered paths. It reads Git metadata and eligible text files, not source-code contents.
- `research.py` turns queries into fetched sources. Providers are tried in order and merged: Hacker News search, arXiv, DuckDuckGo HTML, Wikipedia. Only a page that fetched successfully with usable text becomes evidence.
- `model.py` calls OpenCode and parses strict JSON. It sends only public evidence fields, checks evidence IDs, rejects unverified citations, and enforces the free-model allowlist.
- `store.py` owns the SQLite schema and CRUD, including schema migration.
- `render.py` writes one self-contained HTML inbox with escaped text and http/https links only.
- `cli.py` wires commands and keeps preview local unless `--remote` is present.

## CLI contract

- `source add PATH` registers an existing folder.
- `source list` shows registered folders.
- `source remove ID` unregisters a folder only. It never deletes files.
- `capture --days N [--project PATH] [--db PATH] [--export FILE]` previews agent conversation evidence locally.
- `scan --days N` previews the merged evidence packet locally.
- `scan --days N --remote` chooses research queries, fetches sources, asks for up to five ideas, stores them, and renders the inbox.
- `scan --no-agents` skips agent conversations.
- `inbox [--out PATH] [--status STATUS]` renders the HTML inbox from saved ideas.
- `stories --status STATUS` lists candidates.
- `keep ID` and `reject ID` update review state.
- `draft ID --remote` generates and stores a draft for a kept candidate. It never posts.

The presentation may change if behavior stays the same and the privacy gate remains explicit.

## Safety and limits

- Never scan outside registered paths or follow symlinks out of them.
- Exclude hidden files, environment files, credential-like filenames, and all source-code files.
- Never read a session from a project the user did not register.
- Redact credential-shaped strings and absolute home paths before storage and before any remote call.
- Bound packet, session, turn, and per-file size. Report every omission in the local preview.
- `--remote` is the data-sharing boundary. Say which model receives the packet.
- Refuse non-http(s) URLs and private network addresses in research fetches.
- No background daemon, no social API, no publishing.

## Stable function signatures

- `sources.collect_evidence(source_paths, *, days=7, now=None)` returns `(evidence, omissions)`.
- `capture.collect_conversations(project_paths, *, days=7, now=None, db_path=None)` returns `(evidence, omissions)`.
- `capture.collect_from_export(path)` returns `(evidence, omissions)`.
- `capture.redact(text)` returns text with secrets and home paths removed.
- `research.search(query, *, limit=5, timeout=10.0)` returns `SearchHit` records.
- `research.fetch_page(url, *, timeout=15.0, max_chars=4000)` returns `(title, text)` or `None`.
- `research.collect_research(queries, *, limit_per_query=3, max_sources=6)` returns `(evidence, omissions)`.
- `model.suggest_queries(evidence, *, model=DEFAULT_MODEL)` returns up to five keyword queries.
- `model.suggest_stories(evidence, research=(), *, model=DEFAULT_MODEL)` returns at most five `StoryCandidate` records.
- `model.draft_story(candidate, evidence, *, model=DEFAULT_MODEL)` returns plain text.
- `render.render_inbox(ideas, path, *, generated_at=None, title="Tell")` returns a `Path`.
- `store.Store(db_path)` provides `add_source`, `list_sources`, `remove_source`, `save_candidates`, `list_stories`, `get_story`, `set_status`, and `set_draft`.
