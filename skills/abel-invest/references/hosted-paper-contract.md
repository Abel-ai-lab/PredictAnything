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
choose the continuation method, declare the paper history boundary, and provide
evidence. Edit promoted source only when the contract says code is required.

Harness facts are observations, not complete semantic truth. Empty observed
lists such as no observed fit calls or no observed state writes are not proof of
absence. Read the source and report semantic dependencies the scan missed.

## Loop

1. Read `paper-contract-request.json`.
2. Use the request's compact facts and `reportTemplate` first. Open the
   request's `contractGuide` when stateful continuation, source edits, or a
   refreshed gate failure need deeper guidance.
3. Choose one continuation method: `stateless_recompute`,
   `stateful_continuation`, `full_replay_fallback`, or `not_hostable`.
4. Follow `requirements.sourceEditPolicy`:
   - if `expected=false` and `required=false`, preserve `sourcePath` unless an
     allowed reason is genuinely needed;
   - if `required=true`, edit only `sourcePath`.
5. Write `paper-contract-report.json` beside the request.
6. Rerun the same `visualize-session`, `export-strategy-artifact`, or
   `promote-strategy` command.

If the gate returns another request, treat `validation.lastGateFailure` as a
semantic diagnostic. Revisit continuation design, state, history boundary, or
evidence; do not patch individual validation dates.
For tail parity failures, start from the compact mismatch diagnosis in the
request. Inspect `promotion-tail-trace.json` only when you need detailed audit
rows.

Do not edit the original branch. Do not start by reading Abel-skills promotion
internals or Edge gate internals; the request is the workbench. Inspect
internals only after a refreshed request cannot explain a failure.

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
  daily `as_of` keys, idempotence checks, and small `get_paper_signal` extras;
- preserve `compute_decisions(ctx)` as the research/backtest authority unless
  the source is semantically unusable;
- do not use selected-round `trade-log.csv`, gate answers, or promotion outputs
  as live strategy inputs.

## Continuation Methods

Choose one runtime shape:

- `stateless_recompute`: paper execution computes the current signal from legal
  market data, immutable assets, source parameters, and an explicit history
  boundary. It writes no strategy state and normally does not need source edits.
- `stateful_continuation`: the strategy builds strategy-owned cutover state,
  advances it through paper dates, and persists the advanced state. Use this
  for fitted objects and walking-forward training.
- `full_replay_fallback`: last-resort fallback only when the request says it is
  eligible. It may call the original full path and must pass the fallback
  performance gate.
- `not_hostable`: non-uploadable failure result. Use only when the request says
  fallback is eligible and full replay cannot safely run.

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
limit paper-time feed reads. For expanding, ranking, cumulative, or ordinal
logic, declare the calendar or history origin. Fixed-window indicators may use a
recent lookback; origin-based statistics usually cannot.

## Stateful Bootstrap

Stateful strategies must expose:

```python
def build_paper_initial_state(self, *, cutover_as_of=None) -> dict:
    ...
```

The hook builds state valid through `cutover_as_of` using the same state schema
that `get_paper_signal` consumes. It may return JSON-serializable state or write
files under `paths.state / "strategy"`.

Future `get_paper_signal(as_of=...)` calls should load that state, advance only
the rows/dates after the stored cursor, refit only when the original strategy's
continuation calendar says a refit is due, and persist the updated state. Do
not cold-start the whole training path on every paper call.

The gate calls the bootstrap hook for the validation cutover, then uses Edge
`paper_run_one(...)` for holdout tail replay with prepared market data from the
selected branch dependencies/cache. If parity and idempotence pass, the
strategy-owned state produced by that replay is packaged as
`runtime/initial-state/**`. Do not hand-build final startup files for normal
stateful continuation, and do not encode expected positions or gate answers in
state.

## Stateful PaperStateStore Scaffold

For `stateful_continuation`, adapt this shape. The helper owns state paths,
serialization, daily keys, idempotence checks, and return extras. The strategy
still owns feature construction, fitting, retrain calendars, prediction, and
the exact state schema.

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
        state = self._build_state_through(cutover_as_of)
        state["schema"] = STATE_SCHEMA
        state["last_as_of"] = store.as_of_key(cutover_as_of)
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

`_build_state_through(...)` should replay only what is needed to create
cutover state that matches the selected research strategy through
`cutover_as_of`. `_advance_paper_state(...)` should process only dates after the
stored cursor and should refit only when the original strategy's continuation
calendar says a refit is due.

## Report

Write `paper-contract-report.json` with this shape:

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
  "paths": {
    "packagedFiles": [],
    "initialStateFiles": []
  },
  "paperSignal": {
    "implemented": true,
    "incrementalReady": true,
    "continuation": {
      "method": "stateless_recompute",
      "reason": "why this method preserves selected strategy semantics",
      "futureDailyFlow": "how future as_of calls run"
    },
    "design": {
      "history": {
        "boundary": "fixed_lookback",
        "lookbackBars": 120,
        "origin": null,
        "feeds": ["AAPL"],
        "reason": "history required for one paper signal"
      },
      "state": {
        "usesPersistentState": false,
        "stateFiles": [],
        "schema": null,
        "validThrough": null,
        "reason": "what survives across paper calls"
      },
      "calendar": {
        "usesAbsoluteDecisionOrdinal": false,
        "origin": null,
        "decisionIndexSource": null,
        "nextAdvanceRule": null,
        "reason": "calendar and ordinal semantics"
      },
      "cutover": {
        "requiresStartupState": false,
        "mode": "none",
        "stateEnd": null,
        "bootstrapHook": null,
        "reason": "why startup state is or is not needed"
      },
      "dailyStep": {
        "reason": "one future as_of flow, state update behavior, and expensive work avoided"
      }
    },
    "evidence": {
      "observations": ["source or local evidence facts supporting the method"],
      "agentOverrides": [],
      "semanticChecks": [],
      "whySufficient": "why evidence supports this method"
    },
    "liveReadiness": "how future hosted paper days continue"
  },
  "limitations": [],
  "replacements": []
}
```

`packagedFiles` are immutable files copied under `strategy/**`. For normal
`stateful_continuation`, leave `initialStateFiles` empty and let the gate
package the replayed strategy state. Only list `initialStateFiles` for unusual
manual startup assets that cannot be produced by the replay hook.

Set `paperSignal.incrementalReady=true` only when future hosted paper days can
continue beyond the selected research result.
