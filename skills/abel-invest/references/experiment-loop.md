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
read research/<ticker>/<exp_id>/exploration_path.md before choosing the next Edge run

# implement, prepare, debug, and record the agent-chosen branch round
edit research/<ticker>/<exp_id>/branches/<chosen-branch>/engine.py
abel-invest prepare-branch --branch research/<ticker>/<exp_id>/branches/<chosen-branch>
abel-invest debug-branch --branch research/<ticker>/<exp_id>/branches/<chosen-branch>
abel-invest run-branch --branch research/<ticker>/<exp_id>/branches/<chosen-branch> -d "baseline"
edit research/<ticker>/<exp_id>/exploration_path.md  # keep path, why, Edge feedback, and ledger ref concise

# only after the user asks to visualize the session, or agrees after a PASS
abel-invest visualize-session --session research/<ticker>/<exp_id>
```

New sessions run live graph discovery by default. Use `--no-discover` only when
auth, service access, or continuity constraints make live graph discovery
unavailable.

When the known graph is too narrow for the next research question, expand the
frontier before cutting more strategy variants:

```bash
abel-invest frontier expand --session research/<ticker>/<exp_id> --anchor <NODE_ID> --mode all --limit 20
```

Frontier expansion changes `graph_frontier.json`; it does not record evidence
or prescribe a branch.

## Research Loop

Each round should answer a mechanism question, not just consume compute.

1. Read `agent_context.md` when resuming.
2. Use `frontier.md` to understand coverage, concentration, input
   realization, and path coverage facts.
3. Use `exploration_path.md` as the single human-facing log of chosen paths,
   why each path was chosen, Edge feedback, and ledger/artifact refs.
4. Declare the branch hypothesis in `branch.yaml`.
5. Run `prepare-branch` before trusting branch inputs.
6. Run `debug-branch` before recording evidence.
7. Run `run-branch` only when declaration and debug facts are ready enough for
   the evidence label you want.
8. Re-read `evidence_ledger.json` and `frontier.md`.
9. Ensure `exploration_path.md` has the recorded round before starting another
   recorded round. Cite the round ledger ref and keep the path, why, and Edge
   feedback concise.

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
round defaults to `1`. If one submitted strategy was selected from a parameter,
threshold, filter, sizing, or window sweep, pass `--selection-trials N` so DSR
reflects the Alpha search width instead of only the final `engine.py` shape.
Each edge result also appends a session-level `dsr_trials.jsonl` audit row.
Recorded PASS/FAIL validation rounds count toward future DSR; debug runs,
semantic errors, and workflow blockers are recorded for audit but do not increase
future DSR count. Round notes and `evidence_ledger.json` expose the same K
accounting facts for review. Workflow blockers preserve Alpha's declared count
but use `edge_k_source=not_available` because no Edge K was returned.

## Evidence Reading

After each render, treat:

- `evidence_ledger.json` as the evidence record
- `frontier.md` / `frontier.json` as factual coverage reports
- `agent_context.md` as the compact factual resume surface
- `exploration_path.md` as the single human-facing exploration log

`path_coverage_complete=false` means at least one recorded round still needs an
`exploration_path.md` entry with the round ledger ref, chosen path, reason, and
Edge feedback. It does not mean the system has chosen a route.

Input realization separates declaration from runtime behavior: a branch can
declare `input_claim=graph_supported`, but if the strategy does not read
prepared graph inputs, that round is summarized as a graph input read gap and
cannot count as candidate causal evidence solely from the declaration.

The generated surfaces should show what happened, not tell you which driver,
proxy, threshold, model family, or mechanism to try next.

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

If repeated variants fail in the same neighborhood, use the frontier and journal
to make that concentration explicit before continuing.
