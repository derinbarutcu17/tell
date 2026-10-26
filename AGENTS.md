# Project instructions

Read /Users/derin/Desktop/CODING/AGENTS.md, PRODUCT.md, and ARCHITECTURE.md before editing.

Tell is local-first and explicit about data leaving the device.

- Capture runs while Derin works. That was decided on 2026-10-26. Tell reads agent session databases that already exist on disk. It does not record the screen, the keyboard, or a new log of its own.
- Only inspect folders the user registered. Never scan the whole machine, read credentials, or publish content.
- Redact credential-shaped strings and absolute home paths before anything is stored or sent.
- A model call may use only the packet built from selected sources, and only when the command asks for it explicitly. The local preview never calls a model.
- Never invent a citation. An idea may cite only a URL that Tell fetched successfully during that run.
- Use free models only: `opencode-go/beam-free` (default) and `opencode/deepseek-v4.1-flash-free`. Never switch to a paid model.
- The SQLite database holds source paths, bounded excerpts, provenance, and review state. It never holds complete source documents.

Keep agent write scopes disjoint. Run the smallest relevant tests after a change. Do not commit, push, publish, or deploy.
