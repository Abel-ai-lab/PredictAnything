# Experiment Loop

Use this reference after workspace preflight is complete and
`abel-strategy-discovery doctor` is ready.

## Standard Path

```bash
abel-strategy-discovery init-session --ticker <TICKER> --exp-id <exp-id>
abel-strategy-discovery init-branch --session research/<ticker>/<exp_id> --branch-id <family-a-branch>
abel-strategy-discovery init-branch --session research/<ticker>/<exp_id> --branch-id <family-b-branch>

# make each branch declaration explicit
edit research/<ticker>/<exp_id>/branches/<family-a-branch>/branch.yaml
edit research/<ticker>/<exp_id>/branches/<family-b-branch>/branch.yaml
edit research/<ticker>/<exp_id>/research_journal.md

# implement, prepare, debug, and record the agent-chosen branch round
edit research/<ticker>/<exp_id>/branches/<chosen-branch>/engine.py
abel-strategy-discovery prepare-branch --branch research/<ticker>/<exp_id>/branches/<chosen-branch>
abel-strategy-discovery debug-branch --branch research/<ticker>/<exp_id>/branches/<chosen-branch>
abel-strategy-discovery run-branch --branch research/<ticker>/<exp_id>/branches/<chosen-branch> -d "baseline"
```

New sessions run live graph discovery by default. Use `--no-discover` only when
auth, service access, or continuity constraints make live graph discovery
unavailable.

## Research Loop

Each round should answer a mechanism question, not just consume compute.

1. Read `agent_context.md` when resuming.
2. Use `frontier.md` to understand coverage, concentration, and pivot facts.
3. Use `research_journal.md` for your own hypotheses, observations, open
   questions, and pivot/continue reasoning.
4. Declare the branch hypothesis in `branch.yaml`.
5. Run `prepare-branch` before trusting branch inputs.
6. Run `debug-branch` before recording evidence.
7. Run `run-branch` only when declaration and debug facts are ready enough for
   the evidence label you want.
8. Re-read `evidence_ledger.json` and `frontier.md`.
9. Update `research_journal.md` with evidence references when the result should
   survive as research insight.

## Layer Ownership

- session: discovery and readiness
- branch: branch declaration and `compute_decisions(self, ctx)`
- edge cache: market data reuse
- prepare step: branch input resolution and runtime contract materialization
- debug step: semantic preflight
- run step: evaluation and evidence recording

Session `backtest_start` is the default exploration target. When
`branch.yaml.requested_start` is explicit, that branch start should drive
prepare/debug/run for the branch.

## Evidence Reading

After each render, treat:

- `evidence_ledger.json` as the evidence record
- `frontier.md` / `frontier.json` as factual coverage reports
- `agent_context.md` as the compact factual resume surface
- `research_journal.md` as agent-owned research state

The generated surfaces should show what happened, not tell you which driver,
proxy, threshold, model family, or mechanism to try next.

## Exploration Discipline

- graph/input exploration comes first
- strategy variants come second
- parameter tuning comes last
- multiple branches on one driver set can still be graph/input narrow
- local refinement is useful only while it is still learning something

If repeated variants fail in the same neighborhood, use the frontier and journal
to make that concentration explicit before continuing.
