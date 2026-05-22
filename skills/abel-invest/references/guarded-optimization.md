# Search Accounting And Reporting Gates

Use this reference whenever a formal candidate was selected from empirical
search, whether the target was user-specified or the default Abel Invest target
of Sharpe > 2 / strong tradable edge.

Search is first-class. The failure mode is not search; the failure mode is
reporting a raw search winner as robust before legality, K accounting, and Edge
validation agree.

Self-contained: the agent runs this via abel-invest's own CLI only. No external
optimizer skill is required.

## Objective

- Default objective = find a strong tradable strategy, with Sharpe > 2 as the
  aspirational target unless the user gives a different target.
- Explicit user targets override or constrain the default objective; they do not
  grant permission that was missing before.
- MaxDD / PnL / LossYrs / Lo / IC / DSR / triangle are validation gates or
  diagnostics, not a reason to hide the primary objective.
- Use target/baseline behavior to measure whether graph-enriched candidates add
  value beyond target self-history, but keep graph-derived search active when
  graph candidates are live.

## Wide Universe, Narrow Scout, High-Capacity Promotion

Use a wide but scoped candidate universe and search it empirically. Candidate
universe sources can include:

- target-only features as baseline and competitor
- validated baseline or catalog strategies
- graph nodes and graph-derived feeds as the default high-value expanded feature
  universe
- sector, cross-asset, liquidity, volume, and regime features when justified by
  user goal or evidence
- proven patterns, feature factories, learned models, and ensembles

Search degrees of freedom can include:

- parameter grids or random search
- graph-node subset search
- lag, sign, transformation, ratio, and rolling-window search
- model-family comparison
- HPO
- feature-factory and ensemble screening
- regime, sizing, and filter search
- denoise or compression when temporally legal

During scouting:

- do not use future information
- do not search an unbounded universe unless the user explicitly asks for that
  scope
- use a disposable scout surface such as
  `research/<ticker>/<session_id>/scratch/`, a one-off heredoc, a notebook cell,
  or a query cell
- ask one sharp question at a time: sign, horizon, subset, feature family,
  model family, regime, sizing, filter, or risk shape
- record enough detail to reproduce the submitted candidate
- keep count of effective search width when scouting influences formal
  candidate selection
- failures are information; they do not need to clear the gauntlet

Do not submit an unscouted whole-frontier or whole-feature basket as formal
evidence when a narrow scout question can first identify sign, horizon, subset,
feature family, model family, regime, sizing, filter, or risk-shape facts.

Formal candidates do not have to be simple. They can be learned models,
dense ensembles, feature-factory outputs, graph-node subset models, or hybrids.
Promote the discovered form faithfully instead of replacing a model,
feature-factory, dense ensemble, or hybrid lead with a simple proxy. Formal
promotion means reproducible, temporally legal, selected, and honestly
K-accounted; it does not mean low-capacity.

## Validation Selection

Submit selected candidates through Abel Invest / Edge:

```bash
<command_prefix> prepare-branch --branch <branch-path>
<command_prefix> debug-branch --branch <branch-path>
<command_prefix> run-branch --branch <branch-path> -d "<candidate description>" --selection-trials <N>
```

`N` is this round's effective search width only: every materially compared
variant used to select the submitted candidate for this round, not a cumulative
campaign total.

Raw graph-node count or raw generated-feature count is not automatically K. It
becomes K only when those nodes, features, or variants were screened as competing
choices for the submitted candidate.

Only report, promote, or visualize as a robust candidate after the selected
strategy clears the required validation.

## Reporting Gate

Final reported candidates must clear the applicable validation profile:

1. semantic preflight and legal reads
2. recorded gate / DSR / triangle profile
3. leakage checks
4. walk-forward or requested-window validation
5. final-K accounting when the candidate was selected from a broader search

Failing a gate disqualifies the candidate from robust reporting, but it does not
invalidate the usefulness of the search path.

## K Rule

`--selection-trials N` = this round's search width only. The framework
accumulates campaign K from recorded rounds. Never pass a running/cumulative
total, because that double-counts prior rounds.

If preflight or workflow failures occurred during scouting and would otherwise
be invisible to future DSR accounting, fold that width into a later recorded
round's `--selection-trials` or include it in the final-K analytic check.

## Final-K Revalidation

Before reporting an optimum selected from multiple candidates, ensure the
survivor still clears the reporting gate at final campaign K. If stored PASS
metrics were computed at smaller mid-campaign K, analytically recompute the
DSR/gate against stored artifacts rather than issuing another recorded
`run-branch`.

If the survivor fails at final K, check the next survivor. Report the null
honestly when no survivor clears final-K validation.

## Honest Outcomes

- A survivor that clears validation at final K meets the target -> report it.
- A raw-metric winner that fails validation -> report it as a failed or
  near-pass candidate, not success.
- None clears after a scoped, K-accounted search -> report the null honestly.

## Anti-Patterns

- Reporting a raw search winner as robust.
- Hiding search width inside one branch.
- Treating the whole depth-1 frontier as the only legitimate first candidate.
- Submitting an unscouted whole-feature basket as formal evidence.
- Letting target-only become the default escape from live graph-derived search.
- Treating graph-supported hand-written rules as a substitute for feature
  factories, model-family comparison, denoise, subset search, or ensembles.
- Refusing to report a validated target-only candidate when it is honestly the
  strongest strategy found.
- Under-counting `--selection-trials`.
- Passing cumulative `--selection-trials`.
- Adding complexity without accounting for the search width it introduced.
- Any external-skill dependency.
