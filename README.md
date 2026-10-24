# Clearsift

Halal stock screener and portfolio analyser for Trading 212.

Clearsift sifts every stock through strict Sharia screening rules, so you only see what's clearly compliant. It then rates those stocks and lets you backtest the ratings against a halal benchmark.

> 🚧 **Work in progress.** Currently building the screening engine (milestone 1).

## Planned features

- **Screening engine:** checks any ticker against AAOIFI business-activity and financial-ratio rules, with strict "fail closed" handling of missing data
- **Trading 212 integration:** read-only view of your portfolio, with non-compliant holdings flagged for review
- **Dashboard:** holdings, profit and loss, and sector allocation
- **Ratings:** Buy, Hold or Sell with price levels and reasons, for compliant stocks and ETFs
- **Backtester:** tests whether the ratings beat a halal benchmark
- **Paper trading bot and alerts:** demo account only, with Telegram notifications

## Running locally (Windows)

```
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
pytest
```

Copy `.env.example` to `.env` and add your own Trading 212 demo API key. Never commit `.env`.

## Disclaimer

Clearsift is a personal software project. It is not financial advice or a religious ruling. Screening depends on free data, which can be incomplete. Check important decisions with a qualified scholar or adviser.
