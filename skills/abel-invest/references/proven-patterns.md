# Proven Patterns — Battle Evidence (NOT Scaffold)

These are patterns that worked on specific assets at specific times.
They are evidence of what's possible, not instructions for what to do.
Read them for inspiration during EXPLORE mode, ideally after the branch already
has a runnable `branch.yaml -> prepare-branch -> debug-branch` path.
Do NOT copy-paste — understand the MECHANISM and decide if it applies.

These notes are not the primary legality contract.

- Author new branch code against `DecisionContext`.
- Use `debug-branch` semantic preflight before trusting a recorded round.
- Treat the temporal caveats below as pattern-specific implementation notes, not
  as a universal authoring checklist.

---

## 1. Dual-Lag Xcorr

**What**: Average cross-correlation at two causal lags instead of one.

**Why it works**: Single-lag xcorr is fragile — it's sensitive to the exact lag choice
and picks up one causal harmonic. Averaging lag-14 and lag-21 captures both primary
and secondary harmonics and averages out noise. Equal weighting (0.5/0.5) outperformed
biased weighting (0.7/0.3) — the lags carry equal causal weight.

**When**: SSTK→ETH causal pair. Dual-lag xcorr is a core component of Dual Resonance
(ETH Sharpe 4.27, Lo 2.48). Systematic lag sweep confirmed: lag-7 added noise and
degraded signal; lags without causal mechanism (17, 20) caused validation failure.

**Failure modes**: More lags is not better. Only average lags with a verified causal
mechanism in the Abel graph. Distant lags (too far apart) capture different phenomena
and add noise rather than signal.

**Look-ahead traps**:
- `parent_ret.shift(lag).rolling(60).corr(target_ret)` — the `.corr()` result at index
  `i` includes `target_ret[i]` and the unshifted `parent_ret[i]`. Must add `.shift(1)`
  after the rolling corr.
- The expanding median used to threshold this xcorr also needs `.shift(1)` (see Pattern 2).

---

## 2. Binary Threshold vs Z-Score

**What**: Convert continuous xcorr into a position multiplier using binary above/below
the expanding median, not a continuous z-score mapping.

**Why it works**: Sharp differentiation commits fully to the causal signal. A z-score
mapping gives scale ≈ 1.0 near the median — no differentiation. Binary 1.75/0.25 gives
maximum information extraction. The transition point matters: at 2.0/0.0 Sharpe and Lo
still rose but IC collapsed 29% — the metric triangle caught concentration gaming
(zeroing positions on low-correlation days inflates apparent per-trade quality).

**When**: SSTK→ETH xcorr multiplier in Dual Resonance. Validated through full scaling
sweep (1.25→2.0 step 0.25). Optimal: UP=1.75, DOWN=0.25.

Apply this as an internal multiplier, then cap the final strategy output so `abs(position) <= 1`.

| Scale Up/Down | Lo   | IC    | Verdict              |
|---------------|------|-------|----------------------|
| 1.50 / 0.50   | 2.35 | 0.549 | Strong               |
| **1.75 / 0.25** | **2.37** | **0.569** | **Optimal**  |
| 2.00 / 0.00   | 2.38 | 0.403 | IC crash — gaming    |

**Failure modes**: Choosing the highest Sharpe/Lo point without watching IC. The triangle
is the only way to detect the gaming transition — single-metric optimization misses it.

**Look-ahead traps**:
- `pd.Series(xcorr).expanding().median()` at index `i` includes `xcorr[i]` itself.
  Must be `.expanding().median().shift(1)`. Handle the NaN at position 0 with
  `np.isnan(xcorr_med) | (xcorr > xcorr_med)` → UP.

---

## 3. SMA(50) Trend Filter

**What**: Long/Flat mode — set position to 0 when `close[T-1] < SMA(50)[T-1]`.

**Why it works**: Forces flat during bear markets. Occam's razor: this is a single
fixed parameter. All adaptive alternatives (KAMA, Kalman, Vol-Adaptive, regime-switch)
add parameters → overfit. On 5 years of crypto data: SMA(50) OOS/IS = 1.07 vs
Vol-Adaptive best = 0.88. Simplicity is regularization. Window sweep (10–200) shows
all windows with Sharpe > 1.0 — the filter is robust, not sensitive to exact window.

**When**: All ETH strategies. SMA window tested exhaustively; 50 is not magic, just
confirmed robust. The filter is the single most consistent improvement across all ETH
backtest variants.

**Failure modes**: Any adaptive or regime-switching trend filter tested inferior in
walk-forward validation. Adding complexity hurt generalization in every case tested.

**Look-ahead traps**:
- Must use `close[T-1]` vs `SMA[T-1]`, not `close[T]` vs `SMA[T]`. The rolling mean
  includes the current bar — `np.roll(close, 1) > np.roll(sma, 1)` or equivalently
  `pd.Series(close).shift(1) > pd.Series(sma).shift(1)`.

---

## 4. Position Persistence Penalty

**What**: Decay position size from day 2 of holding: -0.10/day, floor 0.30.

**Why it works**: Lo-adjusted Sharpe = Sharpe × √(1/cf) where cf depends on PnL
autocorrelation. Persistent long streaks create serial correlation. Decaying position
size breaks the serial correlation mechanically — the more consecutive days held,
the smaller the position, the more varied the daily PnL magnitude.

**When**: Dual Resonance (ETH). Parameter sweep: start-day 1→5, decay 0.05→0.12.
Optimal: start day 2, decay 0.10/day. Too aggressive (day 1, 0.12) → Sharpe drops.
Too gentle (day 5, 0.05) → no measurable effect on Lo.

**Failure modes**: Any signal that makes positions MORE persistent over time hurts Lo
(ETH momentum, volatility-ratio sizing, drawdown-aware sizing all tested and confirmed
harmful to Lo). The persistence penalty is anti-momentum by design.

**Look-ahead traps**:
- Counter must use `positions[i-1]` (yesterday's position), not `positions[i]`.
  Using today's position to compute today's count is a circular reference.

---

## 5. RSI Contrarian Overlay

**What**: RSI(20) — overbought (>70) → multiply position by 0.60, oversold (<30) → 1.40×.

**Why it works**: Anti-serial-correlation by construction. When the asset has been
trending up for many days, RSI is elevated and the overlay scales down exposure,
reducing the autocorrelation footprint of momentum streaks. Complements the persistence
penalty: the penalty handles run-length, RSI handles price-level extremes.

**When**: Dual Resonance (ETH Sharpe 4.27, Lo 2.48). RSI(20) > RSI(14) > RSI(10):
longer period triggers only at genuine extremes, not noise. Scaling sweep 0.85/1.15
through 0.50/1.50 — Sharpe-Lo tradeoff. Optimal 0.60/1.40 maximizes Lo without
collapsing Sharpe below threshold.

**Failure modes**: RSI as an ML feature is noise. RSI as a position overlay is signal.
This distinction was confirmed in BNB research: adding RSI as a feature degraded Sharpe
by 8%; using it as an overlay improved Lo. Do not conflate the two uses. After the
overlay, cap the final position so `abs(position) <= 1`.

**Look-ahead traps**:
- `compute_rsi(close, period=20).shift(1)` — RSI at index `i` already incorporates
  `close[i]`. Must shift before using in position sizing decisions.

---

## 6. Multi-Horizon GBDT Ensemble

**What**: Train separate GBDTs for H=1, H=3, H=5 day forward returns; combine
predictions with per-asset tuned weights.

**Why it works**: Each horizon captures a different causal timescale. H=1 captures
fast mean-reversion; H=3/5 capture multi-day momentum. Ensemble weights are tuned
per asset because each asset has a different dominant timescale. Walk-forward retrain
prevents look-ahead: the target for H=k is `return.shift(-k)` applied only during
training, not inference.

**When**: META (Sharpe 2.52), AAPL (Sharpe 1.69), BNB (Sharpe 2.82). Optimal weights
differ per asset:
- META: H=1/3/5 weights 70/20/10 — fast-moving large-cap, short horizon dominates
- AAPL: H=1/3/5 weights 50/30/20 — more balanced, sector peers add medium-horizon signal
- BNB: H=1/3/5 weights 50/30/20 — crypto volatility benefits from multi-horizon

**Failure modes**: Copying META weights to AAPL degraded performance — each asset
must run independent autoresearch to find its optimal horizon weights.

**Look-ahead traps**:
- Training targets: `y = returns.shift(-H)` — correct, this is the future return.
  But features must all use `shift(+lag)` where lag >= 1. The shift directions are
  opposite for features (backward) and targets (forward) — this asymmetry is a common
  source of leakage. Verify feature/target shift directions in every new implementation.

---

## 7. Cross-Asset Spread Signal

**What**: Compute rolling momentum spread between target and peer assets
(e.g., BNB 5-day return minus ETH/SOL/XRP 5-day returns).

**Why it works**: Captures relative crypto momentum. When BNB is outperforming peers,
it's experiencing idiosyncratic flow, not just beta lift. The spread signal is
mean-reverting over medium horizons and provides information orthogonal to
single-asset momentum. Abel shows ETH→BNB causal weight = 0, so this is a
correlation-derived supplement rather than a causal core signal. It was still
tradeable, but only as an empirically validated add-on.

**When**: BNB Phase 1 research. Adding 8 crypto peers (ADA, ETH, SOL, XRP, etc.)
was the single biggest breakthrough: IC +34%, top-18 parent list includes ADA and ETH.
Direct Abel parents only gave 2 of the top-18 — 2-hop + crypto sector peers dominated.

**Failure modes**: Spreading against equities (GOLD, SPX) did not work for BNB — the
mechanism is crypto-specific relative momentum, not broad risk-off/risk-on. Abel probe
confirmed ETHUSD xcorr threshold 1.50/0.50 outperformed GOLD xcorr for BNB.

**Look-ahead traps**:
- `peer_ret.rolling(5).mean()` includes today's return. Must add `.shift(1)` before
  using as a feature or signal component.

---

## 8. Vote² Sizing

**What**: For multi-component ensemble: `position = vote_fraction²`. If 6 of 8
components vote long, `position = (6/8)² = 0.5625`.

**Why it works**: Nonlinear sizing rewards high conviction (near-unanimous agreement)
and punishes split votes. At 4/8 (50% agreement), position = 0.25 — near-flat despite
a slight majority. At 8/8 (100%), position = 1.0. Squared response amplifies the
signal-to-noise ratio of the vote count.

**When**: TON multi-component strategy (8 causal pairs, Sharpe 1.78). The quadratic
response function was chosen over linear (vote_fraction) or cubic (vote_fraction³)
based on backtest sweep — cubic was too aggressive, linear too timid.

**Failure modes**: Vote² is only meaningful if each component uses a shifted signal.
If any component leaks the current day's return, the vote is contaminated and the
squared amplification makes the leak worse, not better.

**Look-ahead traps**:
- Each component's vote must be computed from features that are fully shifted:
  `signal[i]` must use only information from `[0..i-1]`. With 8 components, one
  leaky component out of 8 can still materially inflate the aggregate position
  because squared sizing amplifies agreement.
