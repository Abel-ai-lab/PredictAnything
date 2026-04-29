# Experiment Loop

Use this reference after workspace preflight is complete and
`abel-invest doctor` is ready.

## Standard Path

```bash
abel-invest init-session --ticker <TICKER> --exp-id <exp-id>
abel-invest init-branch --session research/<ticker>/<exp_id> --branch-id <family-a-branch>
abel-invest init-branch --session research/<ticker>/<exp_id> --branch-id <family-b-branch>

# make each branch declaration explicit
edit research/<ticker>/<exp_id>/branches/<family-a-branch>/branch.yaml
edit research/<ticker>/<exp_id>/branches/<family-b-branch>/branch.yaml
edit research/<ticker>/<exp_id>/research_journal.md

# implement, prepare, debug, and record the agent-chosen branch round
edit research/<ticker>/<exp_id>/branches/<chosen-branch>/engine.py
abel-invest prepare-branch --branch research/<ticker>/<exp_id>/branches/<chosen-branch>
abel-invest debug-branch --branch research/<ticker>/<exp_id>/branches/<chosen-branch>
abel-invest run-branch --branch research/<ticker>/<exp_id>/branches/<chosen-branch> -d "baseline"
edit research/<ticker>/<exp_id>/research_journal.md  # add the round's ledger ref and insight before another run

# when the branch has candidate evidence worth external inspection
abel-invest upload-dashboard-bundle --branch research/<ticker>/<exp_id>/branches/<chosen-branch> --base-url <router-base-url>
```

New sessions run live graph discovery by default. Use `--no-discover` only when
auth, service access, or continuity constraints make live graph discovery
unavailable.

## Research Loop

Each round should answer a mechanism question, not just consume compute.

1. Read `agent_context.md` when resuming.
2. Use `frontier.md` to understand coverage, concentration, input
   realization, and research reflection facts.
3. Use `research_journal.md` for your own hypotheses, observations, open
   questions, and pivot/continue reasoning.
4. Declare the branch hypothesis in `branch.yaml`.
5. Run `prepare-branch` before trusting branch inputs.
6. Run `debug-branch` before recording evidence.
7. Run `run-branch` only when declaration and debug facts are ready enough for
   the evidence label you want.
8. Re-read `evidence_ledger.json` and `frontier.md`.
9. Update `research_journal.md` for the recorded round before starting another
   recorded round. Cite the round ledger ref and capture what changed, what
   happened, what was learned, and what that implies next.

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

`journal_coverage_complete=false` means at least one recorded round still needs
an agent-written journal entry. `research_reflection_due=true` is derived from
that missing coverage; it does not mean the system has chosen a route.

Input realization separates declaration from runtime behavior: a branch can
declare `input_claim=graph_supported`, but if the strategy does not read
prepared auxiliary inputs, that round is summarized as a graph input read gap
and cannot count as candidate causal evidence solely from the declaration.

The generated surfaces should show what happened, not tell you which driver,
proxy, threshold, model family, or mechanism to try next.

## Dashboard Upload

After a branch has recorded candidate evidence worth inspecting, upload the
branch evidence bundle to the skill dashboard:

```bash
abel-invest upload-dashboard-bundle --branch research/<ticker>/<exp_id>/branches/<branch-id> --base-url <router-base-url>
```

The upload window starts from the branch `created_at` timestamp and ends at the
upload time. Keep those timestamps timezone-aware because the router maps the
window to request-log time.

The dashboard bundle is branch evidence only:

- session identity and current graph/evidence frontier facts
- branch target, selected inputs, requested start, and current evidence status
- recorded rounds and evidence labels
- input realization facts for declared versus realized graph input usage
- evidence-linked `research_journal.md` lines for that branch
- branch events

Do not include promotion bundles, replay snapshots, paper-trading summaries, or
finished strategy narratives. Those are downstream presentation artifacts, not
branch evidence.

## Exploration Discipline

- graph/input exploration comes first
- strategy variants come second
- parameter tuning comes last
- multiple branches on one driver set can still be graph/input narrow
- local refinement is useful only while it is still learning something

If repeated variants fail in the same neighborhood, use the frontier and journal
to make that concentration explicit before continuing.
