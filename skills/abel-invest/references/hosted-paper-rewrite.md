# Hosted Paper Rewrite

Use this reference when promotion or visualization returns
`needs_agent_refactor` with `kind=hosted_paper_rewrite`, or when the user asks
you to make a selected Abel Invest strategy paper-ready for hosted daily
execution.

## Goal

Rewrite the promoted copy into a live-paper continuation of the selected
research strategy:

```text
research backtest semantics -> selected round cutover -> future daily paper calls
```

Your task is not to repair the promotion gate. The gate is a verifier. First
understand how the strategy naturally continues after the selected round
cutover, then implement that continuation and provide evidence.

Harness facts are observations, not complete semantic truth. Empty observed
lists such as no observed fit calls or no observed state writes are not proof of
absence. Read the source and report semantic dependencies the scan missed.

## Loop

1. Read `refactor-request.json` for this branch/round's facts and hard
   requirements, then keep this guide open for the rewrite method and report
   contract.
2. Choose the continuation method: `stateless_recompute`,
   `stateful_continuation`, `full_replay_fallback`, or `not_hostable`.
3. Use request facts as evidence: feeds, selected window, source observations,
   calendar anchors, imports, branch files, and validation date/index anchors.
4. Edit only the promoted source named by `sourcePath`.
5. Implement `BranchEngine.get_paper_signal(as_of=...)`.
6. For `stateful_continuation`, also implement
   `BranchEngine.build_paper_initial_state(cutover_as_of=...)`.
7. Write `refactor-report.json` beside the request.
8. Rerun the same `visualize-session`, `export-strategy-artifact`, or
   `promote-strategy` command.

If the gate returns another request, treat `validation.lastGateFailure` as a
semantic diagnostic. Revisit continuation design, state, or evidence; do not
patch individual validation dates.

Do not edit the original branch. Do not start by reading Abel-skills promotion
internals or Edge promotion-gate internals; the request is the workbench. Inspect
internals only after a refreshed request cannot explain a failure.

## Runtime Paths

Inside hosted paper code, use the path helper:

```python
from abel_edge.runtime_paths import context_runtime_paths

paths = context_runtime_paths(self.context)
paths.base_strategy             # read-only files packaged under strategy/**
paths.runtime                   # read-only runtime config under runtime/**
paths.state / "strategy" / ...  # strategy-owned mutable paper state
```

Rules:

- remove developer-local absolute paths such as `/home/...` or `/Users/...`;
- read immutable packaged assets through `paths.base_strategy`;
- write mutable strategy state only under `paths.state / "strategy"`;
- preserve `compute_decisions(ctx)` as the research/backtest authority unless
  the source is semantically unusable;
- do not use selected-round `trade-log.csv`, gate answers, or promotion outputs
  as live strategy inputs.

`get_paper_signal` returns a dict with finite numeric `next_position`.
`next_position` is the compiled absolute target exposure for `as_of`, matching
the selected round trade-log meaning. It is not an order delta, order size, or
only-on-change event.

## Continuation Methods

Choose one runtime shape:

- `stateless_recompute`: each paper call computes the current signal from legal
  market data, immutable assets, source parameters, and an explicit history
  boundary. It writes no strategy state.
- `stateful_continuation`: promotion builds strategy-owned cutover state, and
  future paper calls load, advance, and persist that state.
- `full_replay_fallback`: last-resort fallback only when the request says it is
  eligible. It may call the original full path and must pass the fallback
  performance gate.
- `not_hostable`: non-uploadable failure result. Use it only when the request
  says fallback is eligible and full replay fallback cannot safely run.

Any fitted object that participates in the signal makes the strategy stateful:
models, scalers, encoders, calibrators, feature selectors, online learners, and
similar objects should be continued as state instead of refit from scratch on
each daily paper call.

If the request sets `requirements.statefulContinuationRequired=true`, implement
`stateful_continuation`. Do not choose `stateless_recompute` for that promotion.

For expanding, ranking, cumulative, or ordinal logic, declare the calendar or
history origin. Fixed-window indicators may use a recent lookback; origin-based
statistics usually cannot.

## Stateful Bootstrap

Stateful strategies must expose:

```python
def build_paper_initial_state(self, *, cutover_as_of=None) -> dict:
    ...
```

The hook builds state valid through `cutover_as_of` using the same state schema
that `get_paper_signal` consumes. It may return JSON-serializable state or a
manifest of files written under the staged state directory when fitted objects
need file serialization.

The gate calls the hook for validation cutover before the hidden holdout tail.
Use the same hook and state schema to create the production startup files listed
in `paths.initialStateFiles`. Do not hand-write separate validation state. Do
not encode expected positions or gate answers in state.

## Report

Write `refactor-report.json` with this shape:

```json
{
  "schema": "abel-invest.agent-refactor-report/v1",
  "kind": "hosted_paper_rewrite",
  "scope": "hosted_paper_rewrite",
  "summary": "brief rewrite summary",
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
        "minBars": 120,
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

`packagedFiles` are immutable files copied under `strategy/**`.
`initialStateFiles` are mutable startup seeds copied under
`runtime/initial-state/**` and hydrated into state by the hosted runner.
Do not list the same source file in both lists.

Set `paperSignal.incrementalReady=true` only when future hosted paper days can
continue beyond the selected research result.
