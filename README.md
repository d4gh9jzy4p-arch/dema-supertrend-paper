# Paper trading bot (pretend money)

Tests one trading strategy on real crypto prices without risking anything.
See `rules.md` for the rules. Results page: `docs/index.html` (published with GitHub Pages).

- `strategy.py` the indicators and the entry rules
- `paper.py` the pretend account (sizing, risk limits, fees)
- `bot.py` runs once per 15 minute candle; GitHub runs it on a schedule (`.github/workflows/bot.yml`)
- `report.py` rebuilds the results page

There is no real broker, no API key and no real money anywhere in this project. Not financial advice.
