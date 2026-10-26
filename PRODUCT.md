# Story Scout V1

## Product promise

Story Scout helps an independent builder notice which real moments in their work could make useful public stories. It searches only project sources the user adds, returns a few story candidates with evidence, and drafts only after the user keeps a candidate.

## First user and problem

The first user is Derin, an AI-assisted product builder and design engineer. The working hypothesis is that good stories already exist in project decisions, changes, lessons, and selected work notes, but are easy to overlook. Generating copy is easy; finding a true, specific, non-obvious story is the product question.

## V1 workflow

1. Add one or more project folders or explicit conversation-export folders.
2. Preview a local context packet for a time window. No model call happens in preview.
3. Run a scan with the explicit remote flag. The tool sends only the selected packet to the configured OpenCode model.
4. Review zero to three candidates. Each one links to evidence and explains the proposed angle.
5. Keep or reject each candidate. A kept candidate can be turned into a draft. Nothing is posted automatically.

## Allowed source material

- Git commit messages, dates, hashes, and changed file names from an explicitly added repository.
- Recently changed Markdown and plain-text files inside explicitly added folders.
- Conversation exports the user deliberately saves inside an added folder.

Do not read source code contents, hidden files, credentials, environment files, browser data, whole-device history, or unrelated folders in V1. Do not follow symlinks outside an added folder.

## Candidate quality

A candidate must be grounded in one or more supplied evidence IDs. It should point to a decision, tension, useful change, surprising lesson, or clear before-and-after. Return no candidate when the evidence is weak. Mark inference clearly. Do not invent outcomes, audience reactions, research, or personal claims.

## Out of scope

- Always-on monitoring, hooks, scheduled scans, or screen capture.
- Social network connections, autoposting, public hosting, or accounts.
- A dashboard or video editor.
- Broad web research or invented book and article references.

## Early success check

During a two-week personal pilot, compare the scan with a weekly manual Codex prompt. Look for at least one story per week that Derin would not have noticed, a keep rate near or above half, at least one draft worth publishing, and zero unsupported or sensitive claims. If the tool does not beat the manual prompt, stop adding automation.
