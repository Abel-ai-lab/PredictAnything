# Experiment Loop

Use this reference after workspace preflight is complete and
`abel-invest doctor` is ready.

Before creating a new session, confirm the workspace context:

```bash
abel-invest workspace context --path . --json
```

Use the resolved workspace `research_root`. Do not pass `--root` unless this
is an intentional legacy/offline session outside a workspace; in that case pass
`--allow-outside-workspace` too.

## Standard Path

```bash
abel-invest init-session --ticker <TICKER> --exp-id <exp-id>
abel-invest frontier status --session research/<ticker>/<exp_id>
abel-invest init-branch --session research/<ticker>/<exp_id> --branch-id <family-a-branch>
abel-invest init-branch --session research/<ticker>/<exp_id> --branch-id <family-b-branch>

# make each branch declaration explicit
edit research/<ticker>/<exp_id>/branches/<family-a-branch>/branch.yaml
edit research/<ticker>/<exp_id>/branches/<family-b-branch>/branch.yaml
edit research/<ticker>/<exp_id>/research_journal.md  # branch basis and any scout influence

# implement, prepare, debug, and record the agent-chosen branch round
edit research/<ticker>/<exp_id>/branches/<chosen-branch>/engine.py
abel-invest prepare-branch --branch research/<ticker>/<exp_id>/branches/<chosen-branch>
abel-invest debug-branch --branch research/<ticker>/<exp_id>/branches/<chosen-branch>
abel-invest run-branch --branch research/<ticker>/<exp_id>/branches/<chosen-branch> -d "baseline"
edit research/<ticker>/<exp_id>/research_journal.md  # add the round's ledger ref and insight before another run

# only after the user asks to visualize the session, or agrees after a PASS
abel-invest visualize-session --session research/<ticker>/<exp_id>
```

New sessions run live graph discovery by default. Use `--no-discover` only when
auth, service access, or continuity constraints make live graph discovery
unavailable.

When current evidence leaves a frontier question unresolved, expand the
frontier before cutting more strategy variants:

```bash
abel-invest frontier expand --session research/<ticker>/<exp_id> --anchor <NODE_ID> --mode all --limit 20
```

Frontier expansion changes `graph_frontier.json`; it does not record evidence
or prescribe a branch. Do not expand only because a small number of branches
failed or because a metric-selected node looked promising. CAP nodes are causal
priors, not trading directions; they do not provide sign, lag, or guaranteed
strength.

## Research Loop

Each round should answer a mechanism question, not just consume compute.

1. Read `agent_context.md` when resuming.
2. Use `frontier.md` to understand coverage, concentration, input
   realization, and research reflection facts.
3. Use `research_journal.md` for your own hypotheses, observations, open
   questions, and pivot/continue reasoning.
4. Choose a graph/mechanism hypothesis before metric search. Be able to state
   why the branch exists, why its constants are mechanism defaults or simple
   priors, and what evidence would invalidate it.
5. If the next decision is ambiguous between mechanism-deepening, graph
   expansion, or stopping, run one lightweight narrative scout pass or journal
   why it is unavailable, off-target, unnecessary, or skipped.
6. Before widening graph breadth, ask whether the current graph neighborhood
   still has an unresolved sign, lag, regime, interaction, control, or
   risk-shaping question. If yes, answer that mechanism-depth question first.
7. Declare the branch hypothesis in `branch.yaml`.
8. Run `prepare-branch` before trusting branch inputs.
9. Run `debug-branch` before recording evidence.
10. Run `run-branch` only when declaration and debug facts are ready enough for
   the evidence label you want.
11. Re-read `evidence_ledger.json` and `frontier.md`.
12. Update `research_journal.md` for the recorded round before starting another
   recorded round. Cite the round ledger ref and capture what changed, what
   happened, what was learned, and what that implies next.

Standard discovery chooses one declared branch before metric search. Do not run
local parameter, threshold, window, filter, sizing, driver, or asset sweeps to
choose the branch candidate unless the user explicitly requests optimization.
User metric targets are success criteria, not permission to widen local search.

## Layer Ownership

- session: graph frontier, expansion provenance, and readiness
- branch: branch declaration and `compute_decisions(self, ctx)`
- edge cache: market data reuse
- prepare step: branch input resolution and runtime contract materialization
- debug step: semantic preflight
- run step: evaluation, DSR trial-count declaration, and evidence recording

Session `backtest_start` is the default exploration target. When
`branch.yaml.requested_start` is explicit, that branch start should drive
prepare/debug/run for the branch.

`run-branch` writes `validation_context.dsr_trials.count` into the Alpha context
passed to `abel-edge evaluate`. The count is effective exploration trials:
prior PASS/FAIL rounds contribute their recorded trial count, and the current
round defaults to `1`. If accidental search width or explicitly requested
optimization selected one submitted strategy from a parameter, threshold,
filter, sizing, driver, asset, or window sweep, pass `--selection-trials N` so
DSR reflects the Alpha search width instead of only the final `engine.py` shape.
`--selection-trials` is audit and penalty accounting, not permission to select
standard-discovery candidates from brute-force sweeps.
Each edge result also appends a session-level `dsr_trials.jsonl` audit row.
Recorded PASS/FAIL validation rounds count toward future DSR; debug runs,
semantic errors, and workflow blockers are recorded for audit but do not increase
future DSR count. Round notes and `evidence_ledger.json` expose the same K
accounting facts for review. Workflow blockers preserve Alpha's declared count
but use `edge_k_source=not_available` because no Edge K was returned.

If performance scouting happened during standard discovery, declare the
effective search width, journal what happened, treat the result as
scout-informed or optimization-informed rather than clean standard-discovery
evidence, and return to graph/mechanism-led branch selection.

## Evidence Reading

After each render, treat:

- `evidence_ledger.json` as the evidence record
- `frontier.md` / `frontier.json` as factual coverage reports
- `agent_context.md` as the compact factual resume surface
- `research_journal.md` as agent-owned research state

`journal_coverage_complete=false` means at least one recorded round still needs
an agent-written journal entry. `research_reflection_due=true` is derived from
that missing coverage; it does not mean the system has chosen a route.

Input realization separates declaration from runtime behavior: a branch can
declare `input_claim=graph_supported`, but if the strategy does not read
prepared graph inputs, that round is summarized as a graph input read gap and
cannot count as candidate causal evidence solely from the declaration.

The generated surfaces should show what happened, not tell you which driver,
proxy, threshold, model family, or mechanism to try next.

Abel Ask or narrative context can help form mechanism hypotheses, supplement
driver ideas, and frontier questions. It is scout context, not validation
evidence. If narrative results are off-target or weak, record that plainly and
do not launder them into branch evidence.

Use a lightweight narrative scout pass when the agent cannot yet decide whether
to deepen the current mechanism, expand the graph, or stop. This is not a new
mandatory gate: skip or stop the scout when Abel Ask auth is unavailable, the
current evidence already answers the question, or the result drifts off target.

## Session Visualization

Do not create an online session view automatically. If a candidate round
records a PASS, ask the user whether to create an online visualization of this
session. If the user agrees, or if the user explicitly asks to visualize the
session, pass the session folder to the command:

```bash
abel-invest visualize-session --session research/<ticker>/<exp_id>
```

The command builds the online view from local session evidence. The agent
should not hand-assemble the payload or choose a router URL.

Default router base URL: `https://api.abel.ai/router/`.
`abel-auth` is the canonical owner for API key setup. Maintainers should update
the default URL in the skill code if this endpoint changes.

## Exploration Discipline

- graph breadth exploration comes first
- strategy variants come second
- parameter tuning comes last
- multiple branches on one graph input set can still be graph-breadth narrow
- local refinement is useful only while it is still learning something
- mechanism depth should usually precede distant graph expansion when the
  current neighborhood still has a sign, lag, regime, interaction, control, or
  risk-shaping question
- graph expansion needs a frontier question and enough current-frontier evidence
  to justify widening the node universe
- narrative scout should be used at ambiguous deepen/expand/stop decision
  points, but Edge evidence decides
  whether the branch worked

If repeated variants fail in the same neighborhood, use the frontier and journal
to make that concentration explicit before continuing.
