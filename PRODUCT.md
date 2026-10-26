# Tell

## Product promise

Tell finds the stories hiding in your everyday work and turns them into posts worth sharing.

It is a discovery and editorial tool, not a writing tool. The user decides what to keep. Nothing is published.

## The moment

Monday, lunch break. You are working on your project and you open Tell's small dashboard. It is already done: two interesting posts about a problem you actually faced, your project looking interesting, paired with research into a perspective and a talking point.

## V1 workflow

1. Register one or more project folders.
2. Tell captures agent conversations for those folders from the session databases the agent already writes, plus Git metadata and recently changed Markdown and plain text.
3. Preview a bounded evidence packet locally. No model call happens in preview.
4. Run a scan with the explicit remote flag. The model proposes research queries, Tell fetches the sources, and the model returns up to five ideas.
5. Every idea must cite work evidence and may cite only fetched research URLs. Each idea splits fact from interpretation and gives one X framing and one LinkedIn framing.
6. Keep or reject each idea, then render the HTML inbox. Nothing is posted automatically.

## Allowed source material

- Git commit messages, dates, hashes, and changed file names from a registered repository.
- Recently changed Markdown and plain-text files inside registered folders.
- Agent conversation turns from session databases on disk: the user's messages plus the agent's final answers. Tool output and reasoning are skipped, not stored.

Do not read source-code contents, hidden files, credentials, environment files, browser data, whole-device history, or unrelated folders. Do not follow symlinks outside a registered folder.

## Candidate quality

A candidate must identify a decision, tension, surprising lesson, before-and-after, or recurring pattern. It should point to specific evidence, mark interpretation clearly, and never invent outcomes, citations, audience reactions, or personal claims. Return no candidate when the evidence is weak. An idea that only restates a planning document is rejected.

## Out of scope

- Publishing to X or LinkedIn, scheduling, analytics, and engagement tracking.
- Always-on screen or keyboard recording. Capture reads existing agent logs only.
- Accounts, cloud sync, mobile app, video, image generation.
- Broad web research beyond the bounded fetch step, and invented references.

## Early success check

During a two-week personal pilot, compare Tell with a weekly manual prompt over the same material. Look for at least five ideas a week that are new angles, truthful about the work, and carry a research-backed perspective. If Tell does not beat the manual prompt, stop adding automation.
