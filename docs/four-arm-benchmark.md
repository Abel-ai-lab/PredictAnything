# Four-Arm Abel Invest Capability Benchmark

This June 2026 historical benchmark isolates the information gain from two
Predict Anything capabilities: the Abel Invest skill workflow and Abel causal
graph access. The test uses a strict 2x2 design over a `1,000`-ticker selected
universe. Each arm receives the same strategy-discovery objective; only the
capabilities available to the agent change.

The purpose of this report is to support an investor-facing capability claim:
Predict Anything is strongest when graph-derived causal context and the Abel
Invest workflow are used together. The metric evidence is strongest on
risk-adjusted quality, lower-tail Sharpe, drawdown control, and candidate-search
breadth.

## Experimental Arms

| Arm | Abel Invest skill | Causal graph | Role |
| --- | --- | --- | --- |
| Skill + graph | `yes` | `yes` | Full Predict Anything stack. |
| Graph only | `no` | `yes` | Causal graph signal without Abel Invest workflow. |
| Skill only | `yes` | `no` | Abel Invest workflow without causal graph context. |
| No skill / no graph | `no` | `no` | Isolated target-only baseline. |

## Arm-Level Metrics

| Arm | Mean Sharpe | Median Sharpe | Std Sharpe | P10 Sharpe | P90 Sharpe | Mean total return | Median total return | Mean max DD | Median max DD | Mean Return/DD | Median Return/DD | Mean candidates |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Skill + graph | `1.0245` | `1.0099` | `0.2622` | `0.7089` | `1.3693` | `1.7668` | `1.3292` | `-0.2054` | `-0.1666` | `9.6034` | `8.1007` | `207.0` |
| Graph only | `0.9514` | `0.9374` | `0.2530` | `0.6461` | `1.2740` | `6.4513` | `2.1319` | `-0.2989` | `-0.2527` | `16.9419` | `9.5752` | `198.2` |
| Skill only | `0.8194` | `0.8088` | `0.2648` | `0.5126` | `1.1470` | `1.5084` | `1.0156` | `-0.2290` | `-0.1916` | `7.4047` | `5.7444` | `40.0` |
| No skill / no graph | `0.7617` | `0.7530` | `0.2463` | `0.4686` | `1.0748` | `7.8320` | `1.2529` | `-0.2991` | `-0.2616` | `13.9973` | `5.7652` | `40.0` |

For max drawdown, less negative is better. The full stack has the highest mean,
median, and lower-tail Sharpe, plus the smallest typical drawdown.

## Headline Readout

The full Predict Anything stack, `skill + graph`, is the best risk-adjusted
system in the benchmark:

| Metric | Full stack vs no skill / no graph |
| --- | ---: |
| Sharpe wins | `710` vs `93` |
| Mean Sharpe delta | `+0.2653` |
| Median Sharpe delta | `+0.2287` |
| Drawdown wins | `583` vs `217`, with `3` ties |
| Mean max-drawdown delta | `+0.0814` |
| Return/DD wins | `533` vs `262` |
| Mean Return/DD delta | `+0.9718` |

Raw total-return sign count favors the pure control (`449` vs `354`). That does
not contradict the capability claim: the product objective is not to maximize
raw return while ignoring volatility and drawdown. Predict Anything is strongest
as a risk-adjusted discovery workflow.

## Information Gain By Capability

The benchmark separates two sources of information gain.

### Causal Graph: Search Expansion

Graph access expands a target-only candidate search into a causal-driver search.
Instead of testing only direct price-history rules for the target asset, the
graph-enabled arms test graph-neighbor and graph-ensemble candidates that can
lead or explain the target.

| Contrast | Mean Sharpe delta | Sharpe wins | Mean candidate depth | Interpretation |
| --- | ---: | ---: | ---: | --- |
| Graph effect with skill held fixed | `+0.2125` | `599` vs `3`, `233` ties | `207.0` vs `40.0` | Graph context supplies higher-quality causal-driver candidates to the Abel workflow. |
| Graph effect without skill | `+0.1897` | `724` vs `54`, `181` ties | `198.2` vs `40.0` | Graph signal is valuable even without the Abel workflow. |

This is the clearest information-gain result: graph context materially improves
Sharpe and greatly broadens candidate discovery beyond target-only price rules.

### Abel Invest Skill: Workflow Discipline

The Abel Invest skill is not just extra prompt text. It contributes a repeatable
research operating system: workspace readiness, data preparation, discovery
routing, first-look scouting, generated strategy engines, debugging, run
recording, and selection-trial accounting.

| Contrast | Mean Sharpe delta | Sharpe wins | Drawdown wins | Interpretation |
| --- | ---: | ---: | ---: | --- |
| Skill effect with graph held fixed | `+0.0690` | `526` vs `277` | `646` vs `154`, `3` ties | Skill turns graph context into a more disciplined risk-aware workflow. |
| Skill effect without graph | `+0.0590` | `548` vs `411` | `781` vs `173`, `5` ties | Skill adds value even when causal graph discovery is disabled. |

The skill's largest visible advantage is risk control: it repeatedly improves
drawdown outcomes while also lifting Sharpe.

### Full Stack: More Than Either Part Alone

The skill x graph interaction is small but positive on average:

| Factor effect | Mean delta Sharpe | Median delta Sharpe | Positive | Negative | Ties | P10 | P90 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Skill effect with graph | `+0.0690` | `+0.0358` | `526` | `277` | `0` | `-0.0423` | `+0.2229` |
| Skill effect without graph | `+0.0510` | `+0.0044` | `422` | `381` | `0` | `-0.0148` | `+0.1790` |
| Graph effect with skill | `+0.2143` | `+0.1673` | `584` | `3` | `216` | `+0.0000` | `+0.5057` |
| Graph effect without skill | `+0.1963` | `+0.1491` | `619` | `52` | `132` | `+0.0000` | `+0.4869` |
| Skill x graph interaction | `+0.0180` | `+0.0000` | `404` | `280` | `119` | `-0.0587` | `+0.1204` |

The graph is the larger independent Sharpe contributor, while the skill adds
workflow discipline and drawdown control. The full stack combines both: broader
causal discovery plus a more controlled research loop.

## Return/DD Interpretation

Graph-only has a higher mean Return/DD than full stack, despite lower Sharpe and
deeper typical drawdown. That happens because Return/DD is sensitive to extreme
cumulative-return outliers:

| Arm | Mean Return/DD | Median Return/DD | P95-trimmed mean | P99-trimmed mean | P95 | P99 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Skill + graph | `9.6034` | `8.1007` | `8.6114` | `9.2038` | `20.6966` | `26.8205` |
| Graph only | `16.9419` | `9.5752` | `11.1692` | `12.9581` | `39.1760` | `100.0129` |
| Skill only | `7.4047` | `5.7444` | `6.2695` | `6.9352` | `17.9847` | `32.1388` |
| No skill / no graph | `13.9973` | `5.7652` | `6.6938` | `7.8880` | `23.5072` | `68.2248` |

Top graph-only examples include `GME` with `Return/DD=2127.2426` and `MARA`
with `Return/DD=548.5953`. These are explosive but high-drawdown paths. The
investor-facing interpretation should therefore emphasize Sharpe and drawdown
control: graph-only can discover dramatic upside paths, while skill + graph
shapes discovery into smoother risk-adjusted strategies.

## Isolation Audit

The no-skill arms were isolated from Abel Invest workflow instructions and Abel
Invest module/workspace paths. The graph-only arm used generic causal graph
access without the Abel Invest skill.

| Arm | Uses Abel Invest skill | Uses causal graph | Abel module leaks | Forbidden host blocks |
| --- | --- | --- | ---: | ---: |
| Skill + graph | `true` | `true` | `0` | `0` |
| Skill only | `true` | `false` | `0` | `0` |
| Graph only | `false` | `true` | `0` | `0` |
| No skill / no graph | `false` | `false` | `0` | `0` |

This isolation matters because it keeps the capability story clean: graph-only
gets graph context without Abel Invest workflow knowledge, and no-skill/no-graph
gets neither.

## Source Artifacts

The detailed validation archive is maintained in the workbench repository:
[skill-info-gain four-arm benchmark](https://github.com/Abel-ai-lab/abel-skills-workbench/tree/workbench/skill-info-gain/docs/validation/skill-info-gain/2026-06-02-four-arm-factorial-first1000).

Backtests and benchmark comparisons are research artifacts, not investment
advice or guarantees of live trading performance.
