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
