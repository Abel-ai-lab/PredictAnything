# Hosted Paper Contract

Use this reference when promotion or visualization emits
`paper-contract-request.json`, or when the user asks you to make a selected Abel
Invest strategy ready for hosted daily paper execution.

## Goal

Declare how the selected research strategy continues in hosted paper:

```text
research backtest semantics -> selected round cutover -> future daily paper calls
```

The first task is contract design, not source editing. Understand the strategy,
choose the continuation method, declare the paper history boundary, and fill the
request's `reportTemplate`. Edit promoted source only when the contract says
code is required.

Harness facts are observations, not complete semantic truth. Empty observed
lists such as no observed fit calls or no observed state writes are not proof of
absence. Read the source and report semantic dependencies the scan missed.

## Loop

1. Read `paper-contract-request.json`.
2. Use the request's compact facts and `reportTemplate` first. Open the
   request's `contractGuide` when stateful continuation, source edits, or a
   refreshed gate failure need deeper guidance.
3. Choose one continuation method: `stateless_recompute`,
   `stateful_continuation`, or `full_replay_fallback` when the request says
   fallback is eligible.
4. Follow `requirements.sourceEditPolicy`:
   - if `expected=false` and `required=false`, preserve `sourcePath` unless an
     allowed reason is genuinely needed;
   - if `required=true`, edit only `sourcePath`.
5. Write `paper-contract-report.json` beside the request.
6. Rerun the same `visualize-session`, `export-strategy-artifact`, or
   `promote-strategy` command.

Use this compact state machine:

```text
request -> report/source edit -> rerun same command -> pass
                                        |
                                        v
                                  refreshed request
                                        |
                                        v
                         repair from validation.lastGateFailure
                                        |
                                        v
                         fallback eligible -> full_replay_fallback
                                        |
                                        v
                         fallback gate fails -> report failed artifact
```

If the gate returns another request, treat `validation.lastGateFailure` as a
semantic diagnostic. Revisit continuation design, state, history boundary, or
evidence; do not patch individual validation dates. Check
`validation.attemptPolicy` and `requirements.fallback` on each refreshed
request. `fullReplayFallbackEligible=false` is not a stop condition by itself;
keep repairing the contract unless a hard blocker remains.
For tail parity failures, start from the compact mismatch diagnosis in the
request. Inspect `promotion-tail-trace.json` only when you need detailed audit
rows.

Stop the loop only when promotion succeeds, `full_replay_fallback` has been
attempted and fails parity or performance, the required promoted-source edit
cannot be implemented from the available source/context, an unrelated
CLI/runtime/auth blocker prevents progress, or the user explicitly asks to skip
strategy artifacts.

Do not edit the original branch. Do not bypass artifact promotion when
visualizing a session. Do not start by reading Abel-skills promotion internals
or Edge gate internals; the request is the workbench. Inspect internals only
after a refreshed request cannot explain a failure.

## Source Edits

The contract report must say whether source changed:

```json
"sourceEdit": {
  "changed": false,
  "reason": "none",
  "paths": []
}
```

Allowed source-edit reasons are intentionally narrow:

- `stateful_continuation`: implement continuation state and daily advance.
- `full_replay_fallback`: only when the request says fallback is eligible.
- `asset_path_normalization`: replace developer-local paths with runtime path
  helper reads and package immutable assets.
- `source_bug_fix`: a real source defect that prevents the selected strategy
  from running as designed.

Do not add a `get_paper_signal` wrapper for a normal `stateless_recompute`
strategy. Edge can run those strategies through compiled recompute under the
declared `paperExecutionProfile`.

## Runtime Paths

When source edits are needed for assets or state, use:

```python
from abel_edge.runtime_paths import context_runtime_paths
from abel_edge.paper_state import PaperStateStore

paths = context_runtime_paths(self.context)
paths.base_strategy             # read-only files packaged under strategy/**
paths.runtime                   # read-only runtime config under runtime/**
paths.state / "strategy" / ...  # strategy-owned mutable paper state
store = PaperStateStore.from_context(self.context)
```

Rules:

- remove developer-local absolute paths such as `/home/...` or `/Users/...`;
- read immutable packaged assets through `paths.base_strategy`;
- write mutable strategy state only under `paths.state / "strategy"`;
- prefer `PaperStateStore` for hosted paper state paths, JSON/pickle state,
  daily `as_of` keys, idempotence checks, and bootstrap summaries;
- preserve `compute_decisions(ctx)` as the research/backtest authority unless
  the source is semantically unusable;
- do not use selected-round `trade-log.csv`, gate answers, or promotion outputs
  as live strategy inputs.

## Continuation Methods

Choose one runtime shape:

- `stateless_recompute`: paper execution computes the current signal from legal
  market data, immutable assets, source parameters, and an explicit history
  boundary. It writes no strategy state and normally does not need source edits.
- `stateful_continuation`: the strategy builds minimal strategy-owned cutover
  state, advances it through paper dates, and persists the advanced state. Use
  this for fitted objects and walking-forward training.
- `full_replay_fallback`: last-resort fallback only when the request says it is
  eligible. It may call the original full path and must pass the fallback
  performance gate. If that cannot pass, report the export as failed rather than
  uploading a hosted paper artifact. Full replay is a continuation/cutover
  shape, not a `history.boundary` value.

Any fitted object that participates in the signal makes the strategy stateful:
models, scalers, encoders, calibrators, feature selectors, online learners, and
similar objects should be continued as state instead of refit from scratch on
each daily paper call. A cursor-only state file, last position cache, or last
`as_of` marker is not enough.

If the request sets `requirements.statefulContinuationRequired=true`, implement
`stateful_continuation`. Do not choose `stateless_recompute`.

When ML training or fitted-object state was observed and the request later opens
`fallback.fullReplayFallbackEligible=true`, `full_replay_fallback` becomes
allowed as the last resort. It still must pass the same tail parity gate and the
hosted paper fallback performance limit.

Every method must declare the paper history boundary. The gate packages that
boundary into `manifest.runtime.paperExecutionProfile`, and Edge uses it to
limit paper-time feed reads. This boundary describes market data needed by a
future paper call; it is not the same thing as a retrain calendar anchor.
It also is not the same thing as the history range used to bootstrap startup
state at cutover.

For `stateful_continuation`, store retrain/refit anchors, absolute row cursors,
and fitted-object validity in `design.calendar` and persisted strategy state.
Do not choose `history.boundary=origin_anchored` merely because the source has a
retrain calendar or absolute row ordinal. Use `fixed_lookback` when future paper
calls only need a bounded feed window to compute current features and possible
refits from the persisted state. Use `origin_anchored` for history only when the
future signal itself still needs origin-to-`as_of` market history, such as
expanding, cumulative, ranked, or unresolved history dependencies.

## Stateful Bootstrap

Stateful strategies must expose:

```python
def build_paper_initial_state(self, *, cutover_as_of=None) -> dict:
    ...
```

The hook constructs the minimal state valid through `cutover_as_of` using the
same state schema that `get_paper_signal` consumes. It may return
JSON-serializable state or write files under `paths.state / "strategy"`.

Prefer constructing the still-live cutover state directly from source semantics:
current fitted models/scalers, retrain anchors, feature caches, cursors, and
last emitted position. Do not default to replaying the full selected backtest
history. A bounded suffix replay is acceptable when it is the smallest reliable
way to reconstruct equivalent state; origin-to-cutover replay is a last resort
and must still fit the hosted paper timeout.

For DecisionContext-based bootstrap reads, use
`self.paper_bootstrap_context(start=..., end=cutover_as_of)`. This keeps the
same runtime feeds and state paths but bypasses the future daily paper history
clamp while startup state is being constructed. Future
`get_paper_signal(as_of=...)` calls should keep using the normal paper path, so
the declared `paperExecutionProfile.history` still bounds daily feed reads.

Future `get_paper_signal(as_of=...)` calls should load that state, advance only
the rows/dates after the stored cursor, refit only when the original strategy's
continuation calendar says a refit is due, and persist the updated state. Do
not cold-start the whole training path on every paper call. When a refit is due,
use the bounded market history needed for the source features and train window
whenever the persisted state carries the calendar/cursor needed to align the
refit schedule.

The gate calls the bootstrap hook for the validation cutover, then uses Edge
`paper_run_one(...)` for holdout tail advance with prepared market data from the
selected branch dependencies/cache. If parity and idempotence pass, the
strategy-owned state produced by that advance is packaged as
`runtime/initial-state/**`. Do not hand-build final startup files for normal
stateful continuation, and do not encode expected positions or gate answers in
state.

## Stateful PaperStateStore Scaffold

For `stateful_continuation`, adapt this shape. The helper owns state paths,
serialization, daily keys, idempotence checks, and bootstrap summaries. The
strategy still owns feature construction, fitting, retrain calendars,
prediction, and the exact state schema. `get_paper_signal` should return the
decision only; do not add state bookkeeping fields to the paper ledger.

```python
from abel_edge.paper_state import PaperStateStore

STATE_SCHEMA = "my-strategy.paper-state/v1"


class BranchEngine(StrategyEngine):
    def _paper_store(self):
        return PaperStateStore.from_context(
            self.context,
            "strategy/paper_state.pkl",
        )

    def build_paper_initial_state(self, *, cutover_as_of=None):
        store = self._paper_store()
        # Inside _build_cutover_state, call self.paper_bootstrap_context(...)
        # if startup state needs a different range than future daily paper reads.
        state = self._build_cutover_state(cutover_as_of)
        state["schema"] = STATE_SCHEMA
        state = store.mark_current(state, cutover_as_of)
        store.save(state)
        return store.summary(state, as_of=cutover_as_of)

    def get_paper_signal(self, *, as_of=None):
        store = self._paper_store()
        state = store.load(default={})
        if store.is_current(state, as_of):
            return store.signal(
                next_position=state["next_position"],
                payload=state,
                as_of=as_of,
            )

        state = self._advance_paper_state(state, as_of=as_of)
        state = store.mark_current(state, as_of)
        store.save(state)
        return store.signal(
            next_position=state["next_position"],
            payload=state,
            as_of=as_of,
        )
```

`_build_cutover_state(...)` should construct only what is needed to create
cutover state that matches the selected research strategy through
`cutover_as_of`. For example, if the source refits every N rows, build the
model/scaler for the last active retrain anchor at cutover instead of refitting
every earlier anchor. If that bootstrap needs more history than future daily
paper reads, use `self.paper_bootstrap_context(...)` for bootstrap only.
`_advance_paper_state(...)` should process only dates after the stored cursor
and should refit only when the original strategy's continuation calendar says a
refit is due.

For common walk-forward ML strategies, keep the implementation small: identify
the active retrain anchor at cutover, bootstrap the current fitted model/scaler
with `paper_bootstrap_context(...)`, persist fitted objects plus cursor/calendar
state through `PaperStateStore`, make `build_paper_initial_state` create that
cutover state, make `get_paper_signal(as_of=...)` load and advance only new
dates, then rerun the same promotion command.

## Report

For normal `stateless_recompute`, preserve the promoted source and write only
the profile fields requested by `reportTemplate`:

```json
{
  "schema": "abel-invest.agent-paper-contract-report/v1",
  "kind": "hosted_paper_contract",
  "scope": "hosted_paper_contract",
  "sourceEdit": {
    "changed": false,
    "reason": "none",
    "paths": []
  },
  "paperSignal": {
    "continuation": {
      "method": "stateless_recompute"
    },
    "design": {
      "history": {
        "boundary": "fixed_lookback",
        "lookbackBars": 120,
        "origin": "",
        "reason": "source-backed reason for the chosen boundary"
      }
    }
  }
}
```

For `origin_anchored`, set `history.origin` to a parseable ISO date such as the
effective backtest/history start from the request facts. Do not use symbolic
strings such as `effective_window_start`.

For `stateful_continuation`, use the full shape because the gate needs the
state, cutover, calendar, daily-step, and evidence fields:

```json
{
  "schema": "abel-invest.agent-paper-contract-report/v1",
  "kind": "hosted_paper_contract",
  "scope": "hosted_paper_contract",
  "summary": "brief contract summary",
  "sourceEdit": {
    "changed": false,
    "reason": "none",
    "paths": []
  },
  "paperSignal": {
    "implemented": true,
    "incrementalReady": true,
    "continuation": {
      "method": "stateful_continuation",
      "reason": "why this method preserves selected strategy semantics",
      "futureDailyFlow": "how future as_of calls run"
    },
    "design": {
      "history": {
        "boundary": "fixed_lookback",
        "lookbackBars": 120,
        "origin": null,
        "feeds": ["AAPL"],
        "reason": "market-data window needed by future daily paper execution"
      },
      "state": {
        "usesPersistentState": true,
        "stateFiles": ["strategy/paper_state.pkl"],
        "reason": "models/scalers/cursors/cache that survive across paper calls"
      },
      "calendar": {
        "usesAbsoluteDecisionOrdinal": false,
        "origin": null,
        "decisionIndexSource": null,
        "nextAdvanceRule": null,
        "reason": "retrain/refit cadence, row ordinals, and calendar anchor"
      },
      "cutover": {
        "requiresStartupState": true,
        "mode": "minimal_cutover_state",
        "stateEnd": "YYYY-MM-DD",
        "bootstrapHook": "build_paper_initial_state",
        "reason": "why startup state is needed and how it is built"
      },
      "dailyStep": {
        "reason": "one future as_of flow, state update behavior, and expensive work avoided"
      }
    },
    "evidence": {
      "observations": ["source or local evidence facts supporting the method"],
      "whySufficient": "why evidence supports this method"
    }
  }
}
```

If the strategy has immutable external assets, add a top-level `paths` object
with `packagedFiles` copied under `strategy/**`. For normal
`stateful_continuation`, do not list manual `initialStateFiles`; let the gate
package the advanced strategy state after parity passes.

Set `paperSignal.incrementalReady=true` only when future hosted paper days can
continue beyond the selected research result.
