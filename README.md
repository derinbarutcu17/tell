# Tell

Tell finds the stories hiding in your everyday work and turns them into posts worth sharing.

It reads the agent conversations, Git history, and notes from project folders you register, fetches real sources to give the idea a perspective, and shows the result as a local HTML inbox. You decide what to keep. Nothing is published.

## Run

From this directory:

    ./story-scout source add /path/to/project
    ./story-scout capture --days 7
    ./story-scout scan --days 7
    ./story-scout scan --days 7 --remote
    ./story-scout inbox

The first scan is a local preview. Only the explicit `--remote` option sends the prepared excerpts to the model. Check `stories` for an idea ID, then keep it before asking for a draft:

    ./story-scout keep <ID>
    ./story-scout draft <ID> --remote

The draft stays local. There is no publishing, no scheduling, and no background scanning.

## Capture

Tell does not record anything itself. It reads the session databases your agent already writes while you work. Supported today:

- OpenCode session databases (`~/.local/share/opencode/opencode.db`), current layout only
- Codex-style rollout `.jsonl` exports
- Any Markdown conversation export

Only projects you registered are read. Subagent sessions are skipped. Credential-shaped strings and absolute home paths are removed before anything is stored or sent.

    ./story-scout capture --days 7 --project /path/to/project

## Research

A remote scan asks the model for short research queries, then fetches matching sources from public, keyless providers: Hacker News search, arXiv, DuckDuckGo HTML, and Wikipedia. An idea may cite only a URL that was fetched successfully in that run. Anything else is dropped and reported.

## Model access

Free models only, and the default is pinned:

- `opencode-go/beam-free` (default)
- `opencode/deepseek-v4.1-flash-free`

The OpenCode CLI and a working OpenCode connection are required. The project does not fall back to a paid model. If a free model hits its usage limit, Tell says so and stops.

## Data boundaries

Only folders you register are scanned. Tell reads Git metadata, recently changed Markdown or plain text, and agent conversation turns. It does not read source-code contents, hidden files, credentials, browser history, or unrelated folders. Sources and bounded excerpts live in a local SQLite database; complete documents are never stored whole. The local preview prints the first 200 characters of each excerpt, while a remote scan sends the full bounded excerpt, at most 12,000 characters per file and 4,000 per conversation turn.

## Checks

    PYTHONPATH=src python3 -m unittest discover -s tests -v

No package dependencies are required.
