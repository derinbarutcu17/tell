# Story Scout

A small local tool for finding evidence-backed stories in selected project work.

Story Scout is an experiment. It helps identify what may be worth sharing; it does not publish content.

## Run

From this directory:

    ./story-scout source add /path/to/project
    ./story-scout scan --days 7
    ./story-scout scan --days 7 --remote
    ./story-scout stories

The first scan is a local preview. Only the explicit `--remote` option sends the prepared excerpts to `opencode-go/beam-free`. Check `stories` for a candidate ID, then keep it before asking for a draft:

    ./story-scout keep <ID>
    ./story-scout draft <ID> --remote

The draft stays local. There is no publishing or background scanning.


## Model access

Remote suggestions use the OpenCode Go Beam Free model. The OpenCode CLI and a working OpenCode Go connection are required. V1 is pinned to that free model and does not fall back to a paid model.

## Data boundaries

Only folders you register are scanned. V1 reads Git metadata and recently changed Markdown or plain-text files. It does not read source-code contents, hidden files, credentials, browser history, or unrelated folders. It stores source paths and story records in a local SQLite database. A remote scan sends selected excerpts to the configured model; the local preview shows what would be included.

## Checks

Run:

    PYTHONPATH=src python3 -m unittest discover -s tests -v

No package dependencies are required.
