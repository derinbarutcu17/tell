# Architecture and agent contracts

## Runtime

Use Python 3.11+ and the standard library. The product is a local CLI. SQLite stores registered source paths and candidate state under the user's application-support directory. Do not store raw source contents in SQLite.

The installed OpenCode CLI is the model adapter. The default model is opencode-go/beam-free, the free Beam model in the Go catalog. No remote model call happens during a normal preview. The scan command requires an explicit --remote flag before it sends the selected context packet.

## Shared data types

The source of truth for these data types is src/story_scout/models.py.

Evidence fields:
- id: stable ID within a scan packet.
- label: relative file path or short commit label. Never include the user's absolute home path in the model packet.
- kind: git_commit, markdown, or text.
- excerpt: bounded source text.
- date: ISO date or null.
- local_path: absolute path kept locally for provenance; never send it to the model.
- commit: short commit hash or null.
- line_start and line_end: line numbers or null.

StoryCandidate fields:
- title: specific, plain-language title.
- angle: the story or point of view.
- rationale: why this may matter to a reader.
- audience: who may care.
- evidence_ids: one or more IDs that must exist in the packet.
- confidence: number from 0 to 1.

## Modules

- sources.py gathers evidence only inside registered paths. It reads Git metadata and eligible text files, not source-code contents.
- model.py calls OpenCode and parses a strict JSON response. It sends only public evidence fields, checks evidence IDs, and rejects malformed or unsupported results.
- store.py owns SQLite schema and CRUD for registered sources and story status.
- cli.py wires commands and keeps preview local unless --remote is present.

## CLI contract

- source add PATH registers an existing folder.
- source list shows registered folders.
- source remove ID unregisters a folder only. It never deletes the folder or files.
- scan --days N previews the evidence packet locally.
- scan --days N --remote asks the model for up to three evidence-backed candidates and stores them.
- stories --status STATUS lists candidates.
- keep ID and reject ID update review state.
- draft ID --remote generates and stores a draft for a kept candidate. It never posts it.

The exact presentation may change if behavior stays the same and the privacy gate remains explicit.

## Safety and limits

- Never scan outside registered paths or follow symlinks out of them.
- Exclude hidden files, environment files, credential-like filenames, and all source-code files.
- Bound packet size and per-file size. Report omissions in the local preview.
- The --remote option is the data-sharing boundary. Tell the user that selected excerpts go to the configured OpenCode model.
- The first release has no background process and no social API.

## Stable function signatures for the first implementation

- sources.collect_evidence(source_paths, *, days=7, now=None) returns (evidence, omissions). Each item is an Evidence instance. Omissions are short local-only explanations.
- model.suggest_stories(evidence, *, model='opencode-go/beam-free', timeout=180) returns at most three StoryCandidate instances.
- model.draft_story(candidate, evidence, *, model='opencode-go/beam-free', timeout=180) returns plain text.
- store.Store(db_path) provides add_source(path), list_sources(), remove_source(id), save_candidates(candidates, evidence), list_stories(status=None), get_story(id), set_status(id, status), and set_draft(id, text).
- Stored story evidence may retain only the bounded excerpts and provenance needed for later review. Never store complete source documents.
