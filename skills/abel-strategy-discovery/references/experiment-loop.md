# Experiment Loop

## Workspace Preflight

Before following the loop below, determine where the workspace root actually
is:

- if `./alpha.workspace.yaml` exists, the current directory is already the workspace root
- else if `./abel-strategy-discovery-workspace/alpha.workspace.yaml` exists, reuse that child workspace
- only if neither manifest exists should you bootstrap a new workspace

Do not decide that "the workspace does not exist" by checking only whether
`./abel-strategy-discovery-workspace/` is present.

## Standard Path

```bash
abel-strategy-discovery init-session --ticker <TICKER> --exp-id <exp-id> --discover
abel-strategy-discovery frontier-status --session research/<ticker>/<exp_id>
abel-strategy-discovery probe-nodes --session research/<ticker>/<exp_id> --node <node_id>
abel-strategy-discovery expand-frontier --session research/<ticker>/<exp_id> --from-node <node_id>
abel-strategy-discovery init-branch --session research/<ticker>/<exp_id> --branch-id graph-v1

# first make the branch explicit
abel-strategy-discovery select-inputs --branch research/<ticker>/<exp_id>/branches/graph-v1 --node <node_id> --replace
edit research/<ticker>/<exp_id>/branches/graph-v1/engine.py

abel-strategy-discovery prepare-branch --branch research/<ticker>/<exp_id>/branches/graph-v1
abel-strategy-discovery debug-branch --branch research/<ticker>/<exp_id>/branches/graph-v1
abel-strategy-discovery run-branch --branch research/<ticker>/<exp_id>/branches/graph-v1 -d "baseline"
abel-strategy-discovery upload-dashboard-bundle --branch research/<ticker>/<exp_id>/branches/graph-v1 --base-url <router-base-url>
```

Before this loop, the workspace should already exist and `abel-strategy-discovery doctor`
should already be acceptable.
Inside an Abel strategy discovery workspace, keep the research on this session/branch path
under `research/` rather than creating a standalone `causal-edge init`
sidecar project.
This is a compounding search loop, not a checklist of unrelated backtests.
Each round should answer a question about mechanism, not just consume compute.

## What Each Layer Owns

- session: discovery, frontier expansion, and readiness
- branch: branch spec and `compute_decisions(self, ctx)` implementation
- edge cache: market data reuse
- prepare step: branch input resolution and runtime contract materialization
- debug step: semantic preflight
- run step: evaluation and recording

Session `backtest_start` is the default exploration target. When
`branch.yaml.requested_start` is set explicitly, that branch start should drive
prepare/debug/run for the branch.

## Branch Rules

Before a recorded round, the branch should already have:

- `branch.yaml`
- `engine.py`
- `inputs/dependencies.json` from `prepare-branch`
- `inputs/runtime_profile.json`
- `inputs/execution_constraints.json`
- `inputs/data_manifest.json`
- `inputs/window_availability.json`
- `inputs/context_guide.md`
- `inputs/probe_samples.json`

`run-branch` is not the place to decide the branch universe implicitly.
`debug-branch` is the place to test whether the branch can see the world it
thinks it can see.

## KEEP Rule

```
KEEP if: semantic preflight is clean enough to trust the run AND causal-edge verdict == "PASS" AND metrics improve vs latest KEEP baseline
DISCARD: everything else
```

Each KEEP updates the baseline. The next round should compound on the latest
credible result rather than on a pre-declared static experiment grid.
DISCARD is not wasted motion when it narrows the mechanism honestly.

## Explore vs Exploit

- explore: genuinely new information or a different causal angle
- exploit: parameter tuning, threshold tuning, or local refinement on the same idea

Use branch history to compound on the latest credible baseline instead of
pre-defining a large static experiment grid.
If multiple exploit variants die the same death, stop polishing and force a
real explore move.

## Failure Interpretation

Treat failures as localization signals:

- data/setup failure: fix branch spec or prepare step
- semantic/runtime failure: fix engine visibility assumptions or output semantics
- validation failure: change the strategy idea

Do not mix these categories together. A branch that fails validation is still a
useful research result if it tells you which mechanism is weak.
The wrong lesson is "the branch failed." The useful lesson is "what failed:
data path, semantic assumptions, implementation, or idea?"

## Compounding Rule

Serial execution preserves learning. Static grids destroy it.

- if a round reveals a stronger mechanism, compound from that mechanism
- if a round only reveals a local implementation defect, fix the defect before changing the thesis
- if repeated exploit variants keep failing the same way, force a genuine explore move
- if the failure signature changes after a branch edit, that change is itself evidence about the mechanism

## Honest Stop

Do not stop at the first dry patch, and do not keep searching just to avoid
reporting failure.

- repeated discards are acceptable when the branch is still exploring real new dimensions

## Dashboard Upload

After a branch has recorded evidence worth inspecting, upload the branch
evidence bundle to the skill dashboard:

```bash
abel-strategy-discovery upload-dashboard-bundle --branch research/<ticker>/<exp_id>/branches/<branch-id> --base-url <router-base-url>
```

The upload window starts from the branch `created_at` timestamp and ends at the
upload time. Keep those timestamps timezone-aware because the router maps the
window to `api_request_log.event_time` epoch seconds.

The dashboard bundle is branch evidence only:

- session identity and graph frontier summary
- branch target, selected inputs, requested start, and current evidence status
- recorded rounds and reflection fields
- branch memory insights
- branch events

Do not include promotion bundles, replay snapshots, paper-trading summaries, or
finished strategy narratives in this upload. Those are downstream presentation
artifacts, not branch evidence.
- repeated versions of the same weak idea are not progress
- a clean "no usable signal yet" conclusion is better than a noisy pseudo-KEEP
- honest failure is part of research discipline, not an embarrassment to hide
