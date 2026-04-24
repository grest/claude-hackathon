# Team Thunderbolts

> One number. One definition. Defensible in a room full of people who each
> think their version is right.

## Participants

- **Grzegorz** — CTO
- **Adam** — Dev
- **Maciek** — Sales
- **Lukasz** — Dev


We are three people. We played every role. Claude Code filled the gaps.

## Scenario

**Scenario 4: Data & Analytics — "40 Dashboards, One Metric, Four Answers"**

We picked **SaaS churn** as the contested metric. Churn is the canonical
example of a number everyone reports and nobody agrees on: logo vs. revenue,
downgrades counted or not, when the clock starts, how long the reactivation
window is, whether pauses count. A finance director, a CS ops manager, and
the analyst who built the old dashboards will each calculate it differently
and each be defensible. That is the whole point.

## What We Built

A reconciliation-first churn platform. The landing page is not a dashboard —
it's a table that shows, on the same underlying data, what five different
definitions of churn return, row by row, with the disagreements highlighted
and explained. Four of those definitions are the legacy ones we recovered
from stakeholder interviews. The fifth is our proposed `churn_v1.0.0`, the
one definition we argue the business should adopt.

Behind the table: a versioned metric engine that implements all five
definitions as config (not as five different code paths), so the comparison
is apples-to-apples. Every number the engine returns carries the definition
version that produced it and a `finalized` flag reflecting the 30-day
reactivation window. No stray numbers, no unversioned claims.

On top of that, an MCP server with four tools — `get_metric`,
`list_definitions`, `explain_calculation`, `compare_periods` — exposes the
semantic layer to Claude Desktop. A VP can ask questions in English
("what's April churn, and why is it worse than March?") and get answers that
cite the definition version, drill into specific customer cohorts, and
**refuse** questions the data honestly can't answer. The refusal behavior is
the differentiator; it's also what the cert rubric calls false-confidence
rate, which we measure.

What's real: the engine, all five definitions, the reconciliation table,
the MCP server, the evaluation harness. What's synthetic: the data — 200
accounts and ~500 subscription events generated from a committed script,
plus ~15 hand-crafted edge-case rows that each trigger a specific
disagreement between definitions. What's scaffolded: the "explain the
variance" subagent panel (Challenge 9) is designed but not built; we ran
out of time and chose not to fake it.

## Challenges Attempted

| # | Challenge | Status | Notes |
|---|---|---|---|
| 1 | The Room | done | Four stakeholder interviews captured in `/interviews/`, role-played with Claude. Disagreements preserved rather than smoothed over. |
| 2 | The Mess | done | Synthetic data committed. Noise injected deliberately: Europe/Berlin timezone on the EU billing source, retry-storm duplicates, ~4% unlabeled plan tiers. |
| 3 | The Definition | done | `definitions/churn_v1.0.0.md` locked at hour 6. 12 boundary examples with concrete thresholds. Four legacy definitions in `definitions/legacy_*.md`. |
| 4 | The Engine | done | Pure-Python engine. `Result` objects carry `definition_version` and `finalized`. 5 definitions, 1 calculation path. |
| 5 | The One | partial | Dashboard page renders the reconciliation table and a drill-down view. Not polished; polish was deliberately deprioritized per the scenario brief. |
| 6 | The Reconciliation | done | 15 edge-case rows × 5 definitions. Disagreements highlighted, each with a plain-English "why they differ" caption. **This is our money shot.** |
| 7 | The Scorecard | done | 20-question golden set, 5 refusal cases. Metrics: accuracy, refusal accuracy, false-confidence rate. Results committed in `eval/results/`. |
| 8 | The Question | done | MCP server with 4 tools. Few-shot prompt with a negative case and two refusal cases. Validation-retry loop with logged retry count. |
| 9 | The Panel | skipped | Designed (see `decisions/ADR-007-variance-panel.md`) but not built. Would be the next thing we'd tackle. |

## Key Decisions

We wrote six ADRs inline with the work. Each is one page.

- **[ADR-001](decisions/ADR-001-one-definition-five-implementations.md)** — The four legacy definitions are modeled in code, not prose. This is why the reconciliation table is honest.
- **[ADR-002](decisions/ADR-002-hook-vs-prompt-for-pii.md)** — PII redaction on MCP drill-down responses is a `PostToolUse` hook (deterministic), not a prompt instruction (probabilistic). The distinction matters.
- **[ADR-003](decisions/ADR-003-result-contract.md)** — Every `Result` carries `definition_version` and `finalized`. Non-negotiable across the engine/MCP/UI boundary.
- **[ADR-004](decisions/ADR-004-mcp-tool-count.md)** — Four MCP tools, no more. Tool reliability drops past a handful of choices per agent.
- **[ADR-005](decisions/ADR-005-provisional-numbers.md)** — 30-day reactivation window means April's churn is provisional until May 30. We surface that with a flag rather than waiting 30 days to publish.
- **[ADR-006](decisions/ADR-006-validation-retry-loop.md)** — NL query outputs go through a JSON-schema validator with up to 3 retries. Retry count and error type are logged.

