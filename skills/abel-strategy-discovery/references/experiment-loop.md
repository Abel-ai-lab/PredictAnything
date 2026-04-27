# Experiment Loop

## Workspace Preflight

Before following the loop below, determine where the workspace root actually
is:

- if `./alpha.workspace.yaml` exists, the current directory is already the workspace root
- else if `./abel-alpha-workspace/alpha.workspace.yaml` exists, reuse that child workspace
- only if neither manifest exists should you bootstrap a new workspace

Do not decide that "the workspace does not exist" by checking only whether
`./abel-alpha-workspace/` is present.

## Standard Path

```bash
abel-alpha init-session --ticker <TICKER> --exp-id <exp-id>
abel-alpha init-branch --session research/<ticker>/<exp_id> --branch-id <family-a-branch>
abel-alpha init-branch --session research/<ticker>/<exp_id> --branch-id <family-b-branch>

# make each branch declaration explicit
edit research/<ticker>/<exp_id>/branches/<family-a-branch>/branch.yaml
edit research/<ticker>/<exp_id>/branches/<family-b-branch>/branch.yaml
edit research/<ticker>/<exp_id>/research_journal.md

# implement, prepare, debug, and record the agent-chosen branch round
edit research/<ticker>/<exp_id>/branches/<chosen-branch>/engine.py
abel-alpha prepare-branch --branch research/<ticker>/<exp_id>/branches/<chosen-branch>
abel-alpha debug-branch --branch research/<ticker>/<exp_id>/branches/<chosen-branch>
abel-alpha run-branch --branch research/<ticker>/<exp_id>/branches/<chosen-branch> -d "baseline"
```

Before this loop, the workspace should already exist and `abel-alpha doctor`
should already be acceptable.
Inside an Abel-alpha workspace, keep the research on this session/branch path
under `research/` rather than creating a standalone `causal-edge init`
sidecar project.
This is a compounding search loop, not a checklist of unrelated backtests.
Each round should answer a question about mechanism, not just consume compute.
Each branch should stay a hypothesis family. If a new round changes drivers,
mechanism, model family, or complexity class, record that dimension explicitly
or use a new branch when the thesis has materially changed.
New sessions run live graph discovery by default. Treat graph/input coverage as
the opening priority, then let strategy variants and parameters follow from the
agent's research judgment. Multiple branches on one driver set can still be
narrow; use frontier facts to see whether graph/input breadth has actually
expanded.

After each render, treat `evidence_ledger.json` as the evidence record and
`frontier.md` / `frontier.json` as factual coverage reports. They should show
what happened, not tell you which branch, proxy, threshold, or mechanism to try
next.

Use `agent_context.md` to resume the session and `research_journal.md` to carry
your own research state forward. Journal freely, but cite `ledger:*`,
`frontier.md`, or raw artifact references when a statement should count as a
durable research conclusion.

## What Each Layer Owns

- session: discovery and readiness
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
- `inputs/context_guide.md`
- `inputs/probe_samples.json`

For protocol-complete candidate evidence, `branch.yaml` should explicitly
declare:

- `hypothesis`
- `evidence_intent`
- `input_claim`
- `mechanism_family`
- `invalidation_condition`
- `requested_start`
- `selected_inputs` or legacy `selected_drivers`

`run-branch` is not the place to decide the branch universe implicitly.
`debug-branch` is the place to test whether the branch can see the world it
thinks it can see.

When recording a round, use changed dimensions when they clarify what changed:

```bash
abel-alpha run-branch --branch ... -d "..." \
  --changed-dimension sizing
```

Keep continuation and pivot reasoning in `research_journal.md`, where it can be
read as agent-owned research state instead of a per-round protocol form.

## Evidence Admission Rule

The primary question after a run is not "KEEP or DISCARD?" It is "what kind of
evidence did this produce?"

- complete graph-supported claim + actual discovered-driver reads +
  completed validation: candidate causal evidence
- mixed or supplement claims with auxiliary reads: supplemental evidence, not
  graph-first candidate coverage
- complete target-only claim + completed validation: target control evidence
- missing declaration fields: protocol incomplete
- auth, cache, setup, command, or missing artifact failure: workflow blocker
- semantic or temporal visibility violation: runtime invalid
- debug/preflight-only run: diagnostic only

KEEP/DISCARD can remain a secondary profile-specific note, but it is not the
evidence class. Do not rank blocked, invalid, incomplete, or non-comparable
runs as lead candidates.

## Explore vs Exploit

- explore: genuinely new information or a different causal angle
- exploit: parameter tuning, threshold tuning, or local refinement on the same idea

Use branch history, the ledger, and the frontier to understand what has already
been covered. The framework records broad exploration, local refinement,
controls, ablations, diagnostics, model-family coverage, and pivot checkpoint
facts. If multiple exploit variants die the same death, write the reflection in
`research_journal.md` and choose the next research move yourself rather than
following generated route guidance.

## Failure Interpretation

Treat failures as localization signals:

- data/setup failure: fix branch spec or prepare step
- semantic/runtime failure: fix engine visibility assumptions or output semantics
- validation failure: the mechanism has produced research evidence, but the
  framework should not decide the next strategy route

Do not mix these categories together. A branch that fails validation is still a
useful research result if it tells you which mechanism is weak.
The wrong lesson is "the branch failed." The useful lesson is "what failed:
data path, semantic assumptions, implementation, or idea?"

## Compounding Rule

Serial execution preserves learning. Static grids can hide it.

- if a round reveals a stronger mechanism, compound from that mechanism
- if a round only reveals a local implementation defect, fix the defect before changing the thesis
- if repeated exploit variants keep failing the same way, use the frontier and
  journal to make that concentration explicit before continuing
- if the failure signature changes after a branch edit, that change is itself evidence about the mechanism

## Honest Stop

Do not stop at the first dry patch, and do not keep searching just to avoid
reporting failure.

- repeated discards are acceptable when the branch is still exploring real new dimensions
- repeated versions of the same weak idea are not progress
- a clean "no usable signal yet" conclusion is better than a noisy pseudo-KEEP
- honest failure is part of research discipline, not an embarrassment to hide
