# Tell

> **Status: experiment, parked on 2026-10-27.**
>
> Tell proved that local capture, evidence-linked ideas, and verified citations can work without a cloud service. It did not prove the ideas are worth posting. In the only real run, every candidate was too self-referential for a stranger to follow, because the material was the story of building Tell itself rather than a project with a public introduction.
>
> The daily X idea task now lives in Hermes as a skill. This repository stays as a reference implementation, not an active product. Nothing is scheduled from here.

Tell finds the stories hiding in your everyday work and turns them into posts worth sharing.

It reads the agent conversations, Git history, and notes from project folders you register, fetches real sources to give the idea a perspective, and shows the result as a local HTML inbox. You decide what to keep. Nothing is published.

## Run

From this directory:

    ./story-scout source add /path/to/project
    ./story-scout scan --days 7 --remote
    ./story-scout dashboard

The dashboard is a self-hosted web app served on `127.0.0.1:8765`. It shows the inbox, keeps or rejects ideas, registers folders, and checks the model provider. Stop it with Ctrl+C.

The same work is available from the command line:

    ./story-scout capture --days 7
    ./story-scout scan --days 7
    ./story-scout inbox
    ./story-scout stories
    ./story-scout keep <ID>
    ./story-scout draft <ID> --remote

The first scan is a local preview. Only the explicit `--remote` option sends the prepared excerpts to the model. Drafts stay local and are never published.

## Capture

Tell does not record anything itself. It reads the session databases your agent already writes while you work. Supported today:

- OpenCode session databases (`~/.local/share/opencode/opencode.db`), current layout only
- Codex-style rollout `.jsonl` exports
- Any Markdown conversation export

Only projects you registered are read. Subagent sessions are skipped. Credential-shaped strings and absolute home paths are removed before anything is stored or sent.

    ./story-scout capture --days 7 --project /path/to/project

## Research

Each idea carries its own `research_query`, written by the model when it proposes the idea. Tell then searches public, keyless providers for that specific idea: Hacker News search, arXiv, DuckDuckGo HTML, and Wikipedia. A source is attached only when the fetched page shares at least two content words with the idea, so a plausible but unrelated article cannot become a citation. Code hosts and Hacker News threads are refused as perspectives. An idea with no match carries no citation and says so.

Only fetched text is quoted. The stored quote is the readable article text, not page navigation.

## Model access

Free models only, and the default is pinned:

- `opencode-go/beam-free` (default)
- `opencode/deepseek-v4.1-flash-free`

The OpenCode CLI and a working OpenCode connection are required. The project does not fall back to a paid model. The dashboard's Settings view runs a real connection check and explains any failure, including the free-tier usage limit.

## Data boundaries

Only folders you register are scanned. Tell reads Git metadata, recently changed Markdown or plain text, and agent conversation turns. It does not read source-code contents, hidden files, credentials, browser history, or unrelated folders. Sources and bounded excerpts live in a local SQLite database; complete documents are never stored whole. The local preview prints the first 200 characters of each excerpt, while a remote scan sends the full bounded excerpt, at most 12,000 characters per file and 4,000 per conversation turn.

## Checks

    PYTHONPATH=src python3 -m unittest discover -s tests -v

No package dependencies are required.

## Findings

What worked:

- Capture from OpenCode session tables, with subagent chatter skipped and credentials redacted before storage or any model call.
- Per-idea research. The model names the perspective it needs, Tell fetches that query, and a source is attached only when the fetched page shares content words with the idea. Six of ten stored ideas carried a verified citation.
- The fact versus interpretation split. It kept the output honest at no cost.

What did not work:

- The ideas were obscure. Every candidate quoted an internal detail of building Tell, so a reader with no context could not follow any of them.
- There is no project narrative input. Agent logs and commits never carry the "what this is, why it exists" a stranger needs first.
- The dashboard was never opened after the first look, and zero ideas were kept.

Conclusion carried forward: the citation gate and the fact/interpretation split are worth keeping. The application around them is not.
