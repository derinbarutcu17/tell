# Tell

## The moment

Monday, lunch break. I am working on my project and I open Tell's small dashboard. It is already done: two interesting LinkedIn posts about a problem I actually faced, my project looking interesting, paired with research into a genuinely nice perspective and a talking point. I arrive and it is ready. I do not sit down to think.

## What they do today instead

Doomscroll and eat. Nothing gets my voice across, shares my work, or lets me build in public.

## The one number

At least 5 genuinely good post ideas surfaced per week.

Good means: a new angle, truthfully about my work, with a perspective supplied by research. The judgment of "new" and "truthful" is mine to make, not the tool's.

## The riskiest assumption

A week of my real agent output, git history, and project notes, gathered automatically, produces 5 or more good ideas, and better ones than pasting the same material into the same prompt by hand.

How we will test it: one past week of real material, run twice. Once with me pasting it into the prompt, once through Tell's automatic capture. Count good ideas both times by my own definition. The difference is the product. The test also checks that every research source is a real page that was actually fetched, not an invented article.

## Mechanism

Hook plus prompt. The hook gathers information: agent inputs and outputs, context, git, project files. The prompt does research on that information and connects it to relevant articles, problems in the world, and news, to produce an X post and a LinkedIn post.

The prompt is not the product. The hook is the only thing Tell does that I cannot do by pasting into a chat.

## Not in version one

- No accounts, no login, no cloud sync.
- No auto-posting to X or LinkedIn. Tell proposes, I post.
- No scheduling, no analytics, no engagement tracking.
- No mobile app, no video, no image generation.
- No client or work material from folders I did not explicitly register.
- No invented sources. An idea without a fetched URL is not an idea.

## Open questions

- Capture runs while I work (decided). What exactly is captured is not yet decided: whole agent transcripts, or only my messages and the agent's final answers?
- Which agent logs count: OpenCode only, or also Codex and Hermes sessions?
- Research quality is unproven. Whether a broad search produces a real perspective or a forced connection is unknown.
- Whether 5 good ideas a week is achievable at all from a normal working week is unproven.
- Who else this is for is unanswered. Only I have used it.
- What happens with sensitive or client material that lands in a transcript is unanswered.

## Claim check

- "Capture runs while I work" becomes: Tell reads agent session logs that the agent already writes to disk. There is no separate recorder watching the screen.
- "Local-first, nothing leaves your device" becomes: evidence is collected and stored locally; selected excerpts are sent to the configured model only when a scan runs remotely.
- "Research-backed perspective" becomes: every published idea cites at least one URL that Tell fetched successfully during that run, with the fetched excerpt kept.
- "5 good ideas per week" becomes: my own count, recorded in the tool, not a number the tool reports about itself.
