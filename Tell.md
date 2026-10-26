# Tell — Project and Research Handoff

**Updated:** 2026-10-24  
**Product name:** Tell  
**Project:** local-first, evidence-grounded story discovery for independent builders  
**Repository:** `/Users/derin/Documents/Codex/ambient-story-finder`

> **Five-second pitch:** Tell finds the stories hiding in your everyday work and turns them into posts worth sharing.

## Executive handoff

Tell addresses a specific gap in the creator workflow: a person may already be doing meaningful work, but overlook the decisions, experiments, lessons, and changes that could become worthwhile public stories. Tell should discover those moments from selected work traces, show why each might matter, and link every claim to evidence. The user decides what to keep and when to draft or publish.

The first local CLI version is implemented. It gathers bounded evidence from folders the user explicitly registers, previews the evidence locally, and can use the free OpenCode Go Beam model to suggest up to three evidence-linked story candidates. Drafting requires the user to keep a candidate. It does not monitor the whole device, run in the background, or publish posts.

The commercial conclusion is **promising personal workflow, unvalidated business**. Do not expand this into a general AI content suite yet. The next product question is whether Tell repeatedly finds useful stories that a weekly prompt to a general agent would miss. The next business question is whether people who already publish professionally will pay for that improvement.

## Product definition

### Problem and promise

When independent builders work across code, design files, project notes, and AI-agent conversations, their work leaves a trail. Reconstructing that trail and deciding what is genuinely worth sharing takes attention. Generic AI can write a post once given an idea, but it may not reveal an overlooked story or show where its interpretation came from.

**Tell turns selected traces of real work into a small, reviewable inbox of possible stories.** It is a discovery and editorial-selection tool. Draft generation is secondary; evidence and user judgment are central.

### First user and possible market

- **First product user:** Derin, an AI-assisted product builder and designer who wants to share work more consistently.
- **Best product-learning group:** indie builders and solo technical/design founders. Their work creates useful digital traces and they already use coding agents.
- **Most promising commercial group to test:** solo consultants and fractional technical/design operators. Professional visibility may support recurring client acquisition, giving this group a clearer reason and budget to publish.
- **Founder-adjacent group:** job-seeking designers and developers. Their need may be strong but episodic, and their budget is likely lower during a job search.
- **Lower-priority first group:** artists and visual creators. Story discovery is only one part of their broader media-production workflow.

This segment ranking is a research judgment, not survey evidence or proof of willingness to pay.

### Candidate quality

A useful candidate should identify a decision, tension, surprising lesson, before-and-after, or recurring pattern. It should say why a reader might care and point to one or more specific evidence items. The system should clearly label interpretation, avoid inventing outcomes or personal claims, and return no candidate when the evidence is weak.

## Current implementation

### What exists

The project is a Python 3.11+ command-line tool using the standard library. SQLite stores registered source paths and story review state in the user’s application-support directory. The model adapter calls the installed OpenCode CLI and defaults to `opencode-go/beam-free`.

The internal working label is still **Story Scout** (`story-scout` executable and `story_scout` Python package). **Tell is the product name.** This handoff does not rename code, commands, or package paths.

Current flow:

1. Register one or more project folders or folders containing conversation exports that the user deliberately saved.
2. Preview a bounded context packet locally. Preview does not call a model.
3. Run a scan with `--remote` to send only that prepared packet to the configured OpenCode model.
4. Review up to three candidates with evidence references; keep or reject them.
5. Generate a local draft only for a kept candidate. Nothing is posted.

### Scope and privacy boundary

The source collector reads Git metadata and eligible Markdown or plain-text files inside registered folders. It excludes source-code contents, hidden files, environment files, credential-like names, and unrelated folders. It does not follow symlinks outside registered folders. It bounds file and packet size and reports omissions in the local preview.

Absolute local paths are retained only for local provenance and are not sent to the model. SQLite does not retain complete source documents; saved story evidence is limited to the excerpts and provenance required for later review. The explicit `--remote` flag is the data-sharing boundary. Before a remote run, review the local preview and confirm that the selected excerpts may be sent to OpenCode Go Beam Free.

V1 has no always-on monitoring, hook, scheduled scan, screen capture, social account, posting API, or public hosting. Codex conversations are not automatically read; the user would need to deliberately save an export inside a registered folder.

### Commands

From the repository root:

```sh
./story-scout source add /path/to/a/user-selected/project
./story-scout scan --days 7
./story-scout scan --days 7 --remote
./story-scout stories
./story-scout keep <ID>
./story-scout reject <ID>
./story-scout draft <ID> --remote
```

Run the automated suite with:

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

**Handoff verification:** all 39 tests passed on 2026-10-24. They cover local preview, explicit remote gating, model response validation, evidence references, file exclusions, packet bounds, symlink boundaries, SQLite permissions, and review/draft flow. The tests use stubs; no live model call was made during this handoff.

Derin reports that the OpenCode setup now works in Ghostty. The current project contract still requires the OpenCode CLI and a working OpenCode Go connection. Do not silently switch to a paid provider or another model.

### Repository state

At handoff time, `git status --short` showed the project files as untracked. There is no clean committed baseline in this checkout. Preserve the current files; do not reset, commit, push, publish, or deploy without a direct request.

Useful local references: [README.md](README.md), [PRODUCT.md](PRODUCT.md), [ARCHITECTURE.md](ARCHITECTURE.md), and [AGENTS.md](AGENTS.md). The repository instructions require reading the shared agent guide and the product and architecture documents before code edits.

## Research findings

The research report was prepared on **2026-10-23**. Product and price pages were checked again for this handoff on **2026-10-24** where noted. Public prices are snapshots, change over time, and do not prove conversion, retention, or willingness to pay for Tell.

### Commercial verdict

**Narrow the segment. Do not build or market a general-purpose standalone AI personal-brand platform yet.**

People already pay for adjacent social publishing, personal-brand, developer-history, and writing products. That supports the existence of budgets around some neighboring jobs. It does not show that people will pay specifically for passive discovery of stories from private work traces. The free or already-paid-for alternative is strong: once a week, ask a general agent to inspect selected work and suggest three sourced ideas.

The key differentiation cannot be “AI watches my work” or “AI writes a post.” Context capture, connected apps, long-term memory, scheduling, and AI writing are becoming common capabilities. Tell would need to prove its **editorial decision quality**: it finds an overlooked story, understands why it matters, links it to source evidence, respects what should remain private, and carries the approved idea into a draft.

Four properties are worth testing:

- **Discovery:** Tell catches a story the user did not nominate.
- **Persistence:** it connects context across projects or time when that adds real value.
- **Provenance:** the user can verify the evidence behind each statement.
- **Follow-through:** a kept idea becomes an approved draft and then an actual post.

If the advantage is only prompt convenience or polished writing, the stronger form may be a skill, local workflow, or feature inside a broader agent rather than a standalone product.

### Evidence and uncertainty

The available evidence supports some premises but leaves the commercial chain open:

| Question | What the evidence supports | What remains unknown |
|---|---|---|
| Do professionals leave useful work traces? | Git histories, notes, design work, and agent conversations create persistent traces. Developer communities also show that some developers write publicly about work. | How many valuable stories people would have shared but failed to notice. |
| Does visibility matter professionally? | A randomized study of more than 800,000 online-course learners found that facilitating sharing of verifiable credentials increased sharing and was associated with more reported employment a year later. A separate LinkedIn experiment involving over 20 million members supports a causal effect of some weak professional ties on job mobility. | Neither study tested whether AI-assisted story posts create jobs, clients, or referrals. Credential sharing and network recommendations are different interventions. |
| Will ambient suggestions be useful rather than noisy? | Local work-history products and agent integrations show that background context retrieval is technically possible. | Technical feasibility does not establish that story suggestions are novel, safe, or welcome. |
| Will users publish more? | Provenance could reduce context reconstruction; this is a plausible mechanism. | No direct evidence yet that Tell causes more posts or saves meaningful time. Measure posts and editing time. |
| Will people pay? | Neighboring tools publish subscription prices; human content work has transaction-derived hourly rates. | No direct purchase evidence for Tell’s specific discovery job. Ask for an actual payment and renewal. |

The strongest competing explanation is that people already know what they want to say but lack confidence, editing time, media production, distribution habits, or interest in self-promotion. Full social tools bundle idea prompts with drafting, scheduling, analytics, and engagement. Tell should test story discovery separately before adding those downstream features.

### Competitive context and price snapshot

These are adjacent products and substitutes, not exact equivalents:

| Product or substitute | Observed snapshot | Relevance to Tell |
|---|---|---|
| Buffer | Free plan; Essentials listed at $5 per channel/month with annual billing. | Ideas, AI assistance, scheduling, and analytics set a low price anchor for creator utilities. |
| Metricool | Free plan; Starter listed from €16/month on annual billing. | AI social assistant, LinkedIn connection, publishing, and analytics bundle several downstream jobs. |
| WakaTime | $9 Basic and $14 Premium/month. | Paid developer activity history is adjacent to the work-trace layer. |
| AuthoredUp | $19.95/month for an individual plan. | Drafting, hooks, post reuse, scheduling, and analytics sit near the proposed test price. |
| Taplio | Starter listed at $39/month; higher tiers cost more. | A broader LinkedIn growth workflow can command a higher posted price, but that is not evidence Tell can. |
| Screenpipe | Local work-history capture and retrieval; its site offers a free local starting tier and also advertises paid history/sync options. | Screen/audio capture, local history, APIs, MCP, and workflows make generic “ambient memory” a weak moat. |
| Pieces | Local long-term memory with MCP integrations; its MCP offering is listed as part of Pro. | Persistent context across development and AI tools is already an adjacent capability. Verify current tier details before comparing cost. |
| General agents | OpenAI documents connected workspace agents and scheduled tasks. | A weekly sourced-story prompt is the minimum-cost benchmark for users who already have an agent subscription. |
| Human content support | Upwork’s current guidance lists social-media manager rates around $14–$35/hour and social-media content creator rates around $15–$40/hour. | This is stronger behavioral spending evidence than a survey, but it is global marketplace data and not direct willingness to pay for Tell. |

**Price hypothesis:** €9–€29/month is a test corridor inferred from adjacent prices, not a willingness-to-pay estimate. €19 is a useful paid-pilot test price, not a proven optimum. The economic risk is less about model tokens than support, onboarding, privacy incidents, integration maintenance, churn, and acquisition.

### Market interpretation

The most promising commercial segment to test is solo consultants and fractional technical/design operators because publishing may support recurring client acquisition. Indie builders are probably the best group for improving the product because their work traces are rich and they use agents. Job seekers are personally relevant to the founding use case but appear episodic and budget-constrained. These are hypotheses, not validated segments.

Social-network research offers a reason to care about professional visibility, but it does not validate the proposed causal claim that posting leads to work. Track qualified replies, introductions, client conversations, recruiter contacts, interviews, and collaborations rather than likes alone. Do not claim Tell creates jobs or clients without longer-term outcome evidence.

Local-first design is strategically useful. Keep raw work history on the user’s device, index only explicitly selected folders, and send only bounded excerpts after explicit user action. Avoid building a cloud transcript warehouse or social publishing integrations before the discovery behavior passes a real test.

## Validation plan

### Stage 1: personal comparison

Run the existing personal pilot for two weeks. Compare Tell with a weekly manual prompt to ChatGPT/Codex using the same user-selected sources and time window. Record:

- candidates surfaced and how many were genuinely new to the user;
- candidates kept, rejected, wrong, sensitive, or too obvious;
- drafts completed and posts actually published;
- active minutes from candidate to publish;
- whether cross-project or older context was necessary.

The current product brief’s early success bar is at least one story per week that Derin would not have noticed, a keep rate around or above half, at least one draft worth publishing, and zero unsupported or sensitive claims. If Tell does not beat the manual prompt, stop adding automation and reconsider the product boundary.

### Stage 2: paid, four-week external pilot

Only if Stage 1 shows useful discovery, test with eight external users; exclude the founder from commercial pass/fail counts. Recruit solo technical/design consultants, fractional builders, or indie professionals who have substantial work traces, have published at least twice professionally in the last 90 days while wanting to publish more, and already spend on at least one relevant tool.

1. **Week 1 baseline:** give participants a reusable weekly agent prompt that returns three sourced story ideas from participant-selected work. Track preparation time, useful candidates, drafts, and posts.
2. **Weeks 2–4 product simulation:** twice per week, provide no more than two candidates with the story, why it may matter, intended reader, exact evidence, direct fact versus interpretation, and a privacy/uncertainty flag. Draft only after the participant accepts an idea.
3. **Charge for the test:** after one sample, request €19 for the four-week pilot. Ask for another €19 for month two before discussing a feature wishlist.

Proposed pass thresholds (decision rules, not industry benchmarks):

- at least 6 of 8 external users pay €19;
- at least 50% of candidates are worth developing;
- fewer than 20% are wrong, sensitive, creepy, or useless;
- at least 5 of 8 publish two product-originated posts;
- median active effort from accepted candidate to post is 20 minutes or less and below baseline;
- at least 40% of accepted stories depend on cross-session/project context;
- conversion from accepted idea to published post beats the weekly-agent baseline by 25 percentage points;
- at least 4 of 8 pay for month two.

Stop treating Tell as a standalone business if any two proposed kill signals occur: fewer than 3 of 8 pay or renew; fewer than 30% of candidates are accepted after tuning; more than 25% are wrong/sensitive/intrusive; the weekly prompt is within 10 percentage points of Tell on publication conversion; fewer than 3 users publish twice; ongoing hidden editorial work exceeds about 10 minutes/user/week after week two; users mainly request scheduling/media/analytics; or persistent context rarely beats a single-week review.

## Immediate next steps

1. Keep the current opt-in CLI small. Do not add background capture, hooks, screen recording, auto-posting, or a broad creator dashboard before the personal comparison.
2. Run the local preview against only a folder Derin explicitly chooses. Check the packet before any remote call.
3. Compare Tell’s accepted stories with the controlled weekly-agent prompt. Preserve examples of both useful and failed candidates.
4. If Tell wins on discovery and trust, improve onboarding and story review, then recruit the narrow external cohort and ask for payment.
5. Revisit the business model after observing paid use. If users value the workflow but will not pay for another subscription, consider an open-source tool or skill that fits inside an existing agent/context product.

## Source register

Primary product, pricing, and research references used for this handoff. Prices are snapshots, not durable facts.

- [Screenpipe product](https://screenpipe.com/) and [Screenpipe MCP documentation](https://github.com/screenpipe/screenpipe/blob/main/packages/screenpipe-mcp/README.md): local work history, agent access, MCP, and workflow capabilities.
- [Pieces MCP documentation](https://docs.pieces.app/products/mcp) and [Pieces MCP product page](https://pieces.app/mcp): local long-term memory and integrations.
- [OpenAI workspace agents](https://help.openai.com/en/articles/20001143/) and [scheduled tasks](https://developers.openai.com/training/walkthroughs/scheduled-tasks): connected tools and recurring agent workflows.
- [Buffer pricing](https://buffer.com/pricing/) and [Metricool pricing](https://metricool.com/pricing/): creator-tool price and feature anchors.
- [WakaTime pricing](https://wakatime.com/pricing/solo?billing_cycle=yearly), [AuthoredUp pricing](https://authoredup.com/pricing), and [Taplio pricing](https://taplio.com/pricing): developer-history and LinkedIn tool anchors.
- [Upwork social-media manager rates](https://www.upwork.com/hire/social-media-managers/cost/) and [social-media content creator rates](https://www.upwork.com/hire/social-media-content-creators/): marketplace rate guidance.
- Athey and Palikot, [“The Value of Non-Traditional Credentials in the Labor Market”](https://arxiv.org/abs/2405.00247), 2024: randomized credential-sharing intervention. It is evidence about making verifiable credentials visible, not about story posts.
- Rajkumar et al., [“A causal test of the strength of weak ties”](https://doi.org/10.1126/science.abl4476), *Science*, 2022: LinkedIn connection recommendations and job mobility. It does not test posting.
- Papoutsoglou, Wachs, and Kapitsaki, [“Mining DEV for social and technical insights about software development”](https://arxiv.org/abs/2103.17054), 2021: analysis of a self-selected developer-writing community.

The October 23 research report also referred to a Claude Duet announcement dated October 21, 2026. This handoff pass did not find a reliable primary source for that specific claim, so treat it as **unverified** and do not use it as a decision premise until independently confirmed. The stable competitive conclusion does not depend on it: Screenpipe, Pieces, social-publishing tools, and general scheduled agents already cover significant adjacent parts of the workflow.

---

**Decision to carry forward:** prove that Tell finds overlooked, evidence-backed stories that users actually publish. Keep the product local, opt-in, and review-first while testing that claim.
