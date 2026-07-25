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

## 2026-07-25 — Consecutive earnings surprises

- Hypothesis: require two consecutive positive reported-versus-estimated EPS surprises, wait through the latest announcement reaction day, and hold for 20 trading days.
- Source check: 573 qualifying events were available across 19 symbols; Yahoo failed to return LLY earnings history on this refresh.
- Development-only result: 233 trades, 0.7590% expectancy, 0.575 worst-fold profit factor, -8.50% drawdown, and 67% positive folds.
- Internal validation improved to 3.2095% expectancy and a 4.007 profit factor, repeating the prior regime-specific pattern rather than improving stability.
- Failed before bracket replay and outer holdout on profit-factor and fold-consistency gates.

Decision: discard the rule. Do not add an unattended historical-earnings scrape whose symbol coverage changed between consecutive runs, and do not interpret the strong latest period as repeatable evidence.

Reference: [Fundamentally, Momentum is Fundamental Momentum](https://www.nber.org/papers/w20984) supports earnings-surprise momentum as a research family; it does not validate this consecutive-positive implementation or Yahoo's historical scrape.

## 2026-07-25 — Majority-breadth trend

- Hypothesis: retain the existing 200-day trend and 63-day momentum checks, but trade only when at least 50% of the fixed 20-stock universe is above its own 200-day moving average. The threshold was fixed before holdout exposure.
- Development-only signal result: 1,150 trades, 1.1990% expectancy, 1.501 worst-fold profit factor, -12.80% drawdown, and all folds positive. Internal validation produced 329 trades, 1.4473% expectancy, and a 1.793 profit factor.
- Development-only exact-plan result: 1,037 trades, 1.2308% expectancy, 1.440 worst-fold profit factor, 85% positive symbols, and all folds positive.
- Untouched holdout result: the signal produced 253 trades, 0.0659% expectancy, a 1.031 profit factor, and -6.71% drawdown. The exact bracket plan produced 214 trades, 0.0250% expectancy, a 1.009 profit factor, and 50% positive symbols.
- Failed gates: holdout expectancy, profit factor, and exact-plan symbol consistency. No strategy was enabled and no entry was published.

Decision: keep the implementation disabled for its pre-scheduled future evaluation; do not tune the breadth threshold against this holdout.

Reference: [Herding for profits: Market breadth and the cross-section of global equity returns](https://www.sciencedirect.com/science/article/pii/S0264999319312982) supports market breadth as a predictive research family; it does not validate this binary long-only implementation.

## 2026-07-25 — Smooth-trend strength

- Hypothesis: require a positive 63-day trend above the 200-day average, with rolling regression strength above the stock's own trailing median.
- Development-only result: 509 trades, 1.1698% expectancy, 1.110 worst-fold profit factor, -9.17% drawdown, and all folds positive. Internal validation produced 170 trades, 1.4509% expectancy, and a 1.764 profit factor.
- Failed before bracket replay and outer holdout because the development profit factor remained below 1.20.

Decision: discard the implementation and do not tune the strength threshold against the development folds.

Reference: [Slope, Strength, and Retail Extrapolation](https://papers.ssrn.com/sol3/Delivery.cfm/6731259.pdf?abstractid=6731259&mirid=1) studies trend smoothness; it does not validate this rolling-median adaptation.

## 2026-07-25 — Absolute-strength momentum

- Hypothesis: require the 63-day log return to exceed 1.96 times its 63-day volatility-scaled standard error while price remains above the 200-day average.
- Development-only result: 215 trades, 0.3638% expectancy, 0.567 worst-fold profit factor, -3.66% drawdown, and only 33% positive folds. Internal validation produced 61 trades, 0.3354% expectancy, and a 1.211 profit factor.
- Failed before bracket replay and outer holdout on profit-factor and fold-consistency gates.

Decision: discard the implementation; the conventional significance threshold is not a stable trading edge in this universe.

Reference: [Absolute Strength: Exploring Momentum in Stock Returns](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2638004) supports absolute-strength momentum as a research family; it does not validate this volatility-scaled proxy.

## 2026-07-25 — SPY-confirmed trend

- Hypothesis: retain the existing 50/200-day stock trend and positive 63-day momentum checks, but trade only while SPY is above its own 200-day average with positive 63-day momentum. SPY is benchmark context, never a candidate entry.
- Development-only signal result: 800 trades, 1.0631% expectancy, 1.496 worst-fold profit factor, -12.02% drawdown, and all folds positive. Internal validation produced 316 trades, 1.4161% expectancy, and a 1.827 profit factor.
- Development-only exact-plan result: 676 trades, 1.2820% expectancy, 1.394 worst-fold profit factor, 80% positive symbols, and all folds positive. Internal validation produced 287 trades, 1.0604% expectancy, a 1.437 profit factor, and 60% positive symbols.
- Untouched holdout result: the signal produced 232 trades, 0.3252% expectancy, a 1.171 profit factor, and -4.10% drawdown. The exact bracket plan produced 198 trades, 0.2558% expectancy, a 1.095 profit factor, and 50% positive symbols.
- Failed gates: holdout signal profit factor, exact-plan profit factor, and exact-plan symbol consistency. No strategy was enabled and no entry was published.

Decision: retain the disabled fixed rule for its pre-scheduled future evaluation; do not tune the benchmark windows against this holdout.

Reference: [Time Series Momentum](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2089463) supports trend persistence across assets; it does not validate this SPY-gated individual-stock implementation.

## 2026-07-25 — Strategy-family cooldown correction

- Mistake corrected: cooldowns previously blocked only an exact rejected strategy name, allowing closely related trend filters to reuse the same outer holdout under new names.
- Change: a rejected holdout trial now cools down its entire strategy family for 90 days. The current trend family includes moving-average, momentum, low-volatility, breadth-confirmed, benchmark-confirmed, and MACD trend rules.
- Safety effect: new mean-reversion or other genuinely distinct families may still be researched, but another trend variant cannot be selected for the same holdout during cooldown.

Decision: treat the outer holdout as family-level evidence and stop trend-parameter mining until genuinely new data accumulates.

## 2026-07-25 — Extreme weekly reversal

- Hypothesis: after a five-day loss of at least 1.96 volatility-scaled standard errors, wait one day and hold for five trading days.
- Development-only result: 287 trades, -0.4259% expectancy, 0.457 worst-fold profit factor, -8.46% drawdown, and only 33% positive folds.
- Internal validation improved to 96 trades, 0.3987% expectancy, and a 1.681 profit factor, but the earlier folds contradicted a repeatable edge.
- Failed before bracket replay and outer holdout on expectancy, profit-factor, and fold-consistency gates.

Decision: discard the implementation and treat the recent reversal as regime-specific, not as validation.

Reference: [Short-Term Return Reversal: The Long and the Short of It](https://doi.org/10.2139/SSRN.2022061) supports liquidity-driven reversal as a research family; it does not validate this price-only extreme-loss proxy.

## 2026-07-25 — Month-end seasonality

- Hypothesis: enter at the close of the final business day of each month and hold for five trading days, with no price-fitted threshold.
- Development-only result: 1,020 trades, 0.0872% expectancy, 0.904 worst-fold profit factor, -7.04% drawdown, and 67% positive folds.
- Internal validation produced 320 trades, -0.1293% expectancy, and a 0.837 profit factor.
- Failed before bracket replay and outer holdout on expectancy, profit-factor, and fold-consistency gates after costs.

Decision: discard the implementation; the broad historical calendar effect did not survive this executable stock-level adaptation.

Reference: [Are Seasonal Anomalies Real? A Ninety-Year Perspective](https://doi.org/10.1093/rfs/1.4.403) documents turn-of-month seasonality; it does not validate this five-day individual-stock implementation.

## 2026-07-25 — Intraday weekly reversal

- Hypothesis: isolate open-to-close price pressure by requiring a five-day cumulative intraday loss of at least 1.96 recent intraday-volatility units, then wait one day and hold for five trading days.
- Development-only result: 269 trades, 0.1420% expectancy, 0.879 worst-fold profit factor, -2.95% drawdown, and 67% positive folds.
- Internal validation produced 105 trades, 0.0579% expectancy, and a 1.070 profit factor.
- Failed before bracket replay and outer holdout on expectancy, profit-factor, and fold-consistency gates.

Decision: discard the implementation; separating intraday from overnight returns did not create a stable executable reversal edge in this liquid large-cap universe.

Reference: [Short-Term Return Reversals and Intraday Transactions](https://doi.org/10.1142/S2010139219500022) attributes weekly reversal primarily to intraday returns; it does not validate this volatility-threshold adaptation.

## 2026-07-25 — Negative overnight-gap reversal

- Hypothesis: after an overnight open below the prior close by at least 1.96 of the stock's trailing 63-day overnight volatility, enter only after the gap day closes and hold for five trading days.
- Development-only result: 637 trades, 0.4296% expectancy, 0.614 worst-fold profit factor, -6.55% drawdown, and 67% positive folds.
- Internal validation produced 167 trades, 0.1361% expectancy, and a 1.188 profit factor.
- Failed before bracket replay and outer holdout on profit-factor and fold-consistency gates.

Decision: discard the implementation; any gap-day reversal was too inconsistent after an executable close-to-next-day delay.

Reference: [Dark Side of the Day: Overnight Price Jumps and Short-Term Return Predictability](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4335622) studies transient reversal after overnight jumps; it does not validate this long-only delayed-entry rule.

## 2026-07-25 — Immutable family evidence

- Process improvement: every production strategy must now declare a strategy family.
- Research-history records persist the family used at trial time, so later mapping changes cannot silently reinterpret prior holdout evidence.

Decision: future candidate integrations are incomplete unless their family classification is explicit and tested.
