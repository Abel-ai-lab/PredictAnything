# Hosted Paper Rewrite

Use this reference when promotion or visualization returns
`needs_agent_refactor` with `kind=hosted_paper_rewrite`, or when the user asks
you to make a selected strategy paper-ready for hosted daily execution.

The rewrite goal is:

```text
Preserve the research strategy's decision semantics while making the promoted
copy runnable as a hosted daily paper strategy.
```

The system owns paths, packaging, paper cursor semantics, and verification. The
agent owns the strategy-specific rewrite: how to compute the next signal, how to
persist strategy-owned state, and when a candidate is not safely hostable.

## Rewrite Loop

1. Read the emitted `refactor-request.json`.
2. Read the promoted source named by `sourcePath`; edit only that promoted copy.
3. Inspect `dependencyScanPath`, request `signals`, the original branch source,
   nearby branch-local assets, and `.abel-runtime/state/**` when present.
4. Rewrite the promoted source for the runtime contract below.
5. Write `refactor-report.json` beside the request.
6. Rerun the same `visualize-session`, `export-strategy-artifact`, or
   `promote-strategy` command that produced the request.
7. If promotion asks again, use the new request/gate facts as the next edit
   target. Do not start a separate agent process.

Do not edit the original research branch during promotion. Promotion packages
the promoted copy plus files declared in the report.

## Runtime Contract

Allowed path surfaces:

```python
ctx.paths.base_strategy          # read-only files packaged under strategy/**
ctx.paths.runtime                # read-only runtime config under runtime/**
ctx.state_dir / "strategy" / ... # strategy-owned mutable paper state
```

Rules:

- Remove developer-local absolute paths such as `/home/...` or `/Users/...`.
- Read immutable external data through `ctx.paths.base_strategy`.
- Write mutable model/cache/checkpoint/retrain files only under
  `ctx.state_dir / "strategy"`.
- Do not write under `ctx.paths.base_strategy` or `ctx.paths.runtime`.
- Treat `paper-log.csv` as runtime-owned paper ledger and cursor evidence, not
  as a private strategy-state store.
- Preserve `compute_decisions(self, ctx)` as the backtest authority unless the
  request explicitly says the source is not semantically usable.
- Implement `get_paper_signal(self, *, as_of=None)` for hosted paper. Simple
  technical strategies should still provide this path, usually by recomputing a
  bounded lookback window. Stateful strategies should load/update state under
  `ctx.state_dir / "strategy"`.

`get_paper_signal` should return scalar audit-friendly values, including
`next_position`. Include a date/as-of field when useful. It must not require
future data beyond `as_of`, and rerunning the same `as_of` should be idempotent.

## Packaging Report

Write `refactor-report.json` with this minimal shape:

```json
{
  "schema": "abel-invest.agent-refactor-report/v1",
  "kind": "hosted_paper_rewrite",
  "scope": "hosted_paper_rewrite",
  "summary": "brief hosted paper rewrite summary",
  "paths": {
    "packagedFiles": [
      {
        "sourcePath": "branch/or/absolute/source.csv",
        "artifactPath": "strategy/assets/source.csv",
        "purpose": "read-only data required by the promoted strategy"
      }
    ],
    "initialStateFiles": [
      {
        "sourcePath": "model/latest.joblib",
        "artifactPath": "runtime/initial-state/strategy/model/latest.joblib",
        "purpose": "startup model seed for hosted paper"
      }
    ]
  },
  "paperSignal": {
    "implemented": true,
    "incrementalReady": true,
    "notes": "uses runtime cursor plus strategy-owned state"
  },
  "limitations": [],
  "replacements": [
    {
      "path": "old local path or dependency",
      "replacement": "new runtime path or state helper",
      "reason": "why this rewrite was needed"
    }
  ]
}
```

`packagedFiles` are copied into the artifact under `strategy/**` and must be
treated as immutable. `initialStateFiles` are copied under
`runtime/initial-state/**`; the hosted runner hydrates them into
`ctx.state_dir/**` only when there is no newer persisted state snapshot.

Do not use `state_intent.json`, `stateIntent`, `auto_adapter`, `stateRoot`, or
`stateFiles` as active promotion protocol fields. They belong to the replaced
lightweight promotion path.

## Common Rewrite Patterns

External CSV or replay file:

- Declare it in `paths.packagedFiles` under `strategy/assets/...`.
- Read it with `ctx.paths.base_strategy / "assets" / "<file>"`.
- If the file only supports finite historical replay and cannot produce future
  paper signals, record that limitation instead of forcing promotion.

Walk-forward model:

- Store checkpoints, scalers, feature windows, and retrain metadata under
  `ctx.state_dir / "strategy" / ...`.
- Use `paths.initialStateFiles` only for startup seeds that must exist before
  the first hosted paper run.
- Persist enough metadata to know the last training window and last processed
  `as_of`.
- Make same-day reruns idempotent.

Simple indicator strategy:

- Add `get_paper_signal` even when no persisted state is needed.
- Recompute only the bounded lookback needed for the next signal.
- Keep full-history `compute_decisions` for validation/backtest behavior.

Non-standard imports:

- Confirm whether the hosted runtime already provides the package.
- Do not hide dependency installation inside strategy code.
- If a dependency is essential but not available in hosted paper, record a
  limitation and leave promotion blocked.

## Failure Triage

If rerun still returns `needs_agent_refactor`, inspect the new request and gate
evidence first.

Common failures:

- `missing_paper_signal`: promoted source does not define `get_paper_signal`.
- `developer_local_absolute_path`: a local absolute path remains in source.
- `developer_local_file_access`: a file read still targets a local path instead
  of a packaged artifact/runtime path.
- missing packaged source file: `sourcePath` in the report does not exist.
- invalid artifact path: report paths must be relative and start with
  `strategy/**` or `runtime/initial-state/**`.
- replay mismatch: hosted-paper behavior changed materially from full-history
  validation, or same-`as_of` reruns are not idempotent.

When a safe hosted paper rewrite is not possible, say so in `limitations` and
stop promotion instead of weakening the strategy or hiding the issue.
