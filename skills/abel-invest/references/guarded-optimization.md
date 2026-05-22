# Guarded Optimization

Use this reference when a hard performance target is set, such as Sharpe, Lo,
MaxDD, PnL, or a constrained risk-return objective.

Optimization is first-class. When the user gives a hard performance target,
Abel Invest should behave like an alpha searcher, not like a hand-authored
mechanism essay. The failure mode is not search; the failure mode is reporting a
raw search winner as robust before legality, search-width accounting, and
validation evidence support that claim. Passing gates is a reliability signal,
not the purpose of the search; the objective remains high Sharpe, high return,
or the user's constrained risk-return target.

Self-contained: the agent runs this via abel-invest's own CLI only. No external
optimizer skill is required.

## Objective

- Objective = one primary scalar matched to the strategy goal, normally Sharpe
  or Lo-adjusted Sharpe.
- MaxDD / PnL / LossYrs / Lo / IC / DSR / triangle are validation gates or
  diagnostics, not a reason to hide the primary objective.
- Use target/baseline behavior to measure whether graph-enriched candidates add
  value beyond target self-history, but keep graph-derived search active when
  graph candidates are live.

## Two-Stage Loop

### 1. Exploration Screening

Use a bounded candidate universe and search it empirically. For construction
choices, use `data-driven-construction.md`; this file only owns performance
target handling and reportability.

During screening:

- do not use future information
- do not search an unbounded universe unless the user explicitly asks for that
  scope
- record enough detail to reproduce the submitted candidate
- keep count of effective search width
- for a fresh or unfamiliar ticker, prefer a compact first-look scout before a
  broad recorded run; when the scout needs market data, use a prepared
  scout/candidate branch first
- failures are information; they do not need to pass final validation
- use `research/<ticker>/<session_id>/scratch/`, a one-off shell heredoc,
  notebook cell, or query cell for disposable screening when useful

### 2. Validation Selection

Submit selected candidates through Abel Invest / Edge:

```bash
<command_prefix> prepare-branch --branch <branch-path>
<command_prefix> debug-branch --branch <branch-path>
<command_prefix> run-branch --branch <branch-path> -d "<candidate description>" --selection-trials <N>
```

`N` is this round's effective search width only: every variant tried to select
the submitted candidate for this round, not a cumulative campaign total.

Only report, promote, or visualize as a robust candidate after the selected
strategy passes the required validation.

## Gate

Final reported candidates must pass the applicable validation profile:

1. semantic preflight and legal reads
2. recorded gate / DSR / triangle profile
3. leakage checks
4. walk-forward or requested-window validation
5. final-K accounting when the candidate was selected from a broader search

Failing a gate disqualifies the candidate from robust reporting, but it does not
invalidate the usefulness of the search path. A high-Sharpe/high-return
near-pass is often a better lead than a low-objective candidate that is merely
easy to validate.

K accounting makes the search reportable. It should not make the agent avoid a
promising high-capacity lead; it should make the reported claim honest.

## K Rule

`--selection-trials N` = this round's search width only. The framework
accumulates campaign K from recorded rounds. Never pass a running/cumulative
total, because that double-counts prior rounds.

If preflight or workflow failures occurred during screening and would otherwise
be invisible to future DSR accounting, fold that width into a later recorded
round's `--selection-trials` or include it in the final-K analytic check.

## Final-K Revalidation

Before reporting an optimum selected from multiple candidates, ensure the
selected candidate still passes validation at final campaign K. If stored PASS
metrics were computed at smaller mid-campaign K, analytically recompute the
DSR/gate against stored artifacts rather than issuing another recorded
`run-branch`.

If the selected candidate fails at final K, check the next strongest candidate.
Report the null honestly when no candidate passes final-K validation.

## Honest Outcomes

- A candidate that passes validation at final K and meets the objective -> report it.
- A raw-metric winner that fails validation -> report it as a failed or
  near-pass candidate, not success.
- None clears after a bounded, K-accounted search -> report the null honestly.

## Anti-Patterns

- Reporting a raw search winner as robust.
- Hiding search width inside one branch.
- Treating the whole depth-1 frontier as the only legitimate first candidate.
- Letting target-only become the default escape from live graph-derived search.
- Treating graph-supported hand-written rules as a substitute for feature
  factories, model-family comparison, denoise, subset search, or ensembles.
- Refusing to report a validated target-only candidate when it is honestly the
  strongest strategy found.
- Under-counting `--selection-trials`.
- Passing cumulative `--selection-trials`.
- Adding complexity without accounting for the search width it introduced.
- Any external-skill dependency.
