# Strategy Research Log

## 2026-07-25 — Real-data baseline and evidence correction

- Scope: 20 liquid US stocks, eight years of Yahoo Finance daily bars, five walk-forward folds, and 10 bps cost per side.
- Worked in development: `SWING_20D / trend_momentum` passed both signal and exact bracket-plan validation.
- Failed untouched holdout: signal expectancy -0.0755%, profit factor 0.966; exact plan expectancy -0.0414%, profit factor 0.986. No strategy was enabled and no entry was published.
- Failed development: a literature-inspired 12-month momentum variant did not meet profit-factor and drawdown gates. It was rejected without touching the final holdout.
- Forward evidence: zero closed trades for the current exact plan, so live execution remains blocked.
- Correction: internal development-validation results are no longer labeled as final holdout results. Among development-pass candidates, selection now uses executable bracket-plan evidence rather than signal score alone.

Decision: keep researching and paper trading; do not weaken gates or claim a consistently winning strategy.

Reference: [Time Series Momentum](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2089463) motivates the rejected 12-month development experiment but does not validate this individual-stock implementation.

## 2026-07-25 — Low-volatility trend

- Hypothesis: retain the existing 200-day trend and 63-day momentum checks, but participate only when 20-day realized volatility is below its trailing one-year median. The rule and windows were fixed before holdout exposure.
- Development-only result: 744 signal trades, 1.0710% expectancy, 1.253 worst-fold profit factor, and all folds positive. The exact bracket plan produced 1.5023% expectancy, 1.421 worst-fold profit factor, and 75% positive symbols.
- Untouched holdout result: 218 signal trades, 0.4561% expectancy, 1.270 profit factor, and -4.26% drawdown. The exact bracket plan produced 1.0982% expectancy and 1.466 profit factor.
- Failed gate: only 55% of symbols had positive exact-plan expectancy versus the unchanged 60% requirement.

Decision: retain the disabled candidate for pre-scheduled future evaluation, publish no entry, and do not tune the volatility threshold or universe against this holdout.

Reference: [Volatility Managed Portfolios](https://www.nber.org/papers/w22208) supports reducing exposure in high-volatility states, but the binary stock-level filter here remains an independently tested implementation.

## 2026-07-25 — Cross-sectional momentum and holdout reuse

- Hypothesis: trade only the top quartile of 12-minus-1-month relative momentum among the fixed universe, with positive absolute momentum and a 200-day trend filter.
- Development-only signal result: 428 trades, 1.5715% expectancy, 1.411 worst-fold profit factor, and all folds positive.
- Failed before outer holdout: the exact bracket plan had a 1.145 worst-fold profit factor and only 50% positive symbols in internal validation. The unused implementation was removed.
- Process mistake corrected: a rejected rule could previously be exposed to substantially the same rolling holdout on every daily run. Rejected strategy names now receive a fixed 90-day holdout cooldown; materially changed rules require a new strategy name.

Decision: discard the cross-sectional candidate, preserve the outer holdout, and spend the next trial on a distinct hypothesis rather than parameter-tuning this one.

Reference: [Momentum Strategies](https://www.nber.org/papers/w5375) supports cross-sectional winner selection, but the exact tradable implementation failed this system's development gates.

## 2026-07-25 — 52-week-high proximity

- Hypothesis: hold a stock for 20 trading days when its prior close is at least 95% of its trailing 252-day high.
- Development-only result: 774 trades, 0.4504% expectancy, 1.018 worst-fold profit factor, -9.29% drawdown, and all folds positive.
- Internal validation: 320 trades, 0.4888% expectancy, and 1.268 profit factor.
- Failed before bracket replay and outer holdout because the development profit factor remained below 1.20.

Decision: discard the implementation and do not tune the proximity threshold against these results.

Reference: [The 52-Week High and Momentum Investing](https://onlinelibrary.wiley.com/doi/10.1111/j.1540-6261.2004.00695.x) supports cross-sectional ranking by nearness to the high; it does not validate this simpler fixed-threshold adaptation.

## 2026-07-25 — Intermediate-horizon momentum

- Hypothesis: require a positive return from 12 to 6 months ago and a current close above the 200-day moving average, then hold for 20 trading days.
- Development-only result: 829 trades, 0.7820% expectancy, 0.770 worst-fold profit factor, -11.00% drawdown, and 67% positive folds.
- Internal validation improved to 1.6797% expectancy and a 2.016 profit factor, but the earlier development folds were not repeatable.
- Failed before bracket replay and outer holdout on both profit-factor and fold-consistency gates.

Decision: discard the implementation and treat the strong late period as regime-specific evidence, not validation.

Reference: [Is Momentum Really Momentum?](https://doi.org/10.1016/j.jfineco.2011.05.003) studies cross-sectional intermediate-horizon performance; it does not validate this long-only time-series adaptation.

## 2026-07-25 — Positive earnings-surprise drift

- Hypothesis: after any positive reported-versus-estimated EPS surprise, wait through the announcement reaction day and hold for 20 trading days.
- Source check: Yahoo exposed 716 usable positive-surprise events across all 20 symbols in the development period.
- Development-only result: 285 trades, 1.0523% expectancy, 0.900 worst-fold profit factor, -10.01% drawdown, and 67% positive folds.
- Internal validation improved sharply to 3.3518% expectancy and a 4.091 profit factor, but the earlier folds did not support a repeatable edge.
- Failed before bracket replay and outer holdout on profit-factor and fold-consistency gates.

Decision: discard the naive positive-surprise rule, do not select a surprise threshold from these results, and remove the exploratory parser dependency because no production path uses it.

Reference: [Post-Earnings-Announcement Drift](https://doi.org/10.2307/2491062) documents delayed response to earnings surprises; it does not validate this unranked long-only implementation.
