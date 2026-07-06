# Changelog

All notable public-facing changes are documented here.

## [1.2.0] - 2026-05-28

### Added

- Expert-mode Quant Lab workflow for safe custom strategy signal testing.
- Built-in Quant Lab strategy templates for RSI, SMA crossover, MACD, Bollinger Bands, breakout, buy-and-hold, and momentum-style tests.
- AST-based strategy validation and restricted execution with timeout protection.
- Plain-English strategy result explanations.
- Broker-style dashboard shell with quote header, watchlist, compact metric strips, and denser dark/light themes.
- Chart indicator presets with `Common`, `All`, and `Off` controls.
- Focused Quant Lab unit tests.

### Changed

- Updated the public README for version `1.2.0` and the new repo layout.
- Moved planning docs and legacy scripts into `docs/` to keep the root clean.
- Limited pytest discovery to the maintained `tests/` folder.

## [1.1.2] - 2026-05-26

- Stabilized the Streamlit dashboard experience before the Quant Lab release.
- Kept legacy release notes under `docs/archive/CHANGELOG.md`.
