# Clearsift

A halal stock screener that only lets through what it can show is compliant.

Clearsift checks a stock's line of business and its balance sheet against Sharia screening rules, using free data from Yahoo Finance. It tells you whether the stock passes, why, and how much of its dividends to give to charity. If the data is missing or out of date, the stock doesn't get in.

> **Work in progress.** The screening engine and Trading 212 portfolio check work. The dashboard, ratings and backtesting are still to come.

## Quick start (Windows)

You need Python 3.12 or newer.

```
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
clearsift screen AAPL
```

To screen your Trading 212 holdings, copy `.env.example` to `.env` and add your own API key (see [Trading 212](#trading-212)). Never commit `.env`.

You can screen several stocks at once, e.g. `clearsift screen AAPL MSFT XOM`.

Data is cached in `data/cache.db` so repeat runs are quick. Add `--refresh` to fetch everything fresh.

The exit code is 0 if every stock passes, 1 if any fails and 2 if `config.yaml` has a problem, so you can use it in scripts.

## Example

Example output from October 2026.

```
> clearsift screen AAPL MSFT XOM
AAPL: PASS (doubtful)
  Technology / Consumer Electronics
  check by hand: interest income isn't in the latest report
  purify 0.98% of dividends (based on 2023)
  - industry 'Consumer Electronics' isn't excluded or marked for review
  - debt is 1.67% of market cap, AAOIFI limit is 30%
  - cash is 1.23% of market cap, AAOIFI limit is 30%
  - interest income is 0.98% of revenue (from 2023, newer years not reported), AAOIFI limit is 5%

MSFT: PASS (compliant)
  Technology / Software - Infrastructure
  purify 1.00% of dividends
  - industry 'Software - Infrastructure' isn't excluded or marked for review
  - debt is 3.26% of market cap, AAOIFI limit is 30%
  - cash is 1.95% of market cap, AAOIFI limit is 30%
  - interest income is 0.99% of revenue, AAOIFI limit is 5%

XOM: PASS (doubtful)
  Energy / Oil & Gas Integrated
  check by hand: interest income isn't in the latest report
  purification: can't work out, interest income not disclosed
  - industry 'Oil & Gas Integrated' isn't excluded or marked for review
  - debt is 5.58% of market cap, AAOIFI limit is 30%
  - cash is 1.40% of market cap, AAOIFI limit is 30%
  - interest income not disclosed in recent reports, check by hand
```

This was run in standard mode, which is why the two doubtful stocks still pass.

## Comparing standards

```
clearsift screen MSFT --compare
```

Example output from October 2026.

```
MSFT
  Technology / Software - Infrastructure
  - industry 'Software - Infrastructure' isn't excluded or marked for review
  purify 1.00% of dividends
  AAOIFI: PASS (compliant)
    - debt is 3.26% of market cap, AAOIFI limit is 30%
    - cash is 1.95% of market cap, AAOIFI limit is 30%
    - interest income is 0.99% of revenue, AAOIFI limit is 5%
  FTSE: PASS (compliant)
    - debt is 7.49% of total assets, FTSE limit is 33.333%
    - cash is 10.11% of total assets, FTSE limit is 33.333%
    - receivables plus cash is 20.77% of total assets, FTSE limit is 50%
    - interest income is 0.99% of revenue, FTSE limit is 5%
  MSCI: PASS (compliant)
    - debt is 7.49% of total assets, MSCI limit is 33.33%
    - cash is 10.11% of total assets, MSCI limit is 33.33%
    - receivables plus cash is 20.77% of total assets, MSCI limit is 33.33%
    - interest income is 0.99% of revenue, MSCI limit is 5%
  passes under 3 of 3 standards
```

`--compare` screens the stock under every standard in `config.yaml` and shows the result for each one, then a line like "passes under 2 of 3 standards". The business screen and the data are the same for all of them, only the ratio limits change. The exit code still follows the standard picked in `config.yaml`.

## Trading 212

```
clearsift portfolio
```

This reads your open Trading 212 positions, read-only. It converts each Trading 212 ticker to a Yahoo one, screens it, then lists anything you should review. It only shows tickers and quantities, never prices or money values.

`--compare` and `--refresh` work the same as with `screen`. The exit code is 0 if every holding passes, 1 if any fails or couldn't be checked, and 2 if `config.yaml` or Trading 212 has a problem.

### Creating a read-only API key

1. In the Trading 212 app, go to Settings → API (Beta).
2. Create a key, and untick "Orders - Execute" and "Pies - Write".
3. Copy the key and the secret somewhere safe. You'll need both.

Live and demo accounts use separate keys, so make one in whichever account you want to screen. The API only works with Invest and Stocks ISA accounts.

### Setting up .env

Copy `.env.example` to `.env` and fill in:

- `T212_API_KEY`: your API key
- `T212_API_SECRET`: your API secret
- `T212_ENV`: `live` or `demo`, to match the account the key came from

**Never commit `.env`.** It holds your key and secret. It's already in `.gitignore`, so leave it there.

### Example

Made-up holdings, not a real portfolio. Run in standard mode.

```
> clearsift portfolio
ISUS.L (ISUSl_EQ), quantity 40
ISUS.L: PASS (compliant)
  fund (ETF)
  purification: check the fund's own reports
  - Sharia-certified fund, on your approved list

MSFT (MSFT_US_EQ), quantity 2.5
MSFT: PASS (compliant)
  Technology / Software - Infrastructure
  purify 1.00% of dividends
  - industry 'Software - Infrastructure' isn't excluded or marked for review
  - debt is 3.26% of market cap, AAOIFI limit is 30%
  - cash is 1.95% of market cap, AAOIFI limit is 30%
  - interest income is 0.99% of revenue, AAOIFI limit is 5%

MO (MO_US_EQ), quantity 10
MO: FAIL (excluded)
  Consumer Defensive / Tobacco
  - industry 'Tobacco' falls under excluded group 'tobacco'
  - debt is 12.41% of market cap, AAOIFI limit is 30%
  - cash is 2.13% of market cap, AAOIFI limit is 30%
  - interest income is 0.48% of revenue, AAOIFI limit is 5%

Not checked
  SAPd_EQ, quantity 3: couldn't convert ticker, check by hand

Review
  MO (MO_US_EQ): FAIL, industry 'Tobacco' falls under excluded group 'tobacco'
  SAPd_EQ: not checked, couldn't convert ticker, check by hand

4 holdings: 2 pass, 1 fail, 1 not checked
```

Funds skip the business and ratio checks. Only funds on your `approved_funds` list in `config.yaml` count as compliant, any other fund is doubtful.

### Which tickers work

- **US shares**, like `AAPL_US_EQ`, become `AAPL`.
- **London shares**, like `VODl_EQ`, become `VOD.L`.

Anything else, like other exchanges or share classes such as `BRK.B`, shows as "not checked". Guessing the Yahoo ticker could screen the wrong company, so it's left for you to check by hand.

### Safety

Clearsift has no code that can place, change or cancel orders. The Trading 212 client only ever sends read requests. With "Orders - Execute" unticked, the key itself can't place orders either, so even a bug couldn't trade for you.

## How screening works

### Business activity

Each company's Yahoo sector and industry are checked against a list of excluded groups: conventional banking and insurance, lending, alcohol, pork, tobacco, gambling, adult entertainment, and weapons and defence. Some industries can't be judged from the label alone, like restaurants or grocery stores, so they're marked doubtful and need checking by hand. You can also exclude specific tickers in `config.yaml`.

### Financial ratios

Each standard sets limits on:

- **Debt:** Yahoo's total debt. This includes leases, so it can be a little higher than interest-bearing debt alone.
- **Cash:** cash plus short-term investments. This includes ordinary cash, not just interest-bearing deposits.
- **Receivables and cash:** money owed to the company plus cash (FTSE and MSCI only).
- **Impermissible income:** interest income as a share of revenue from the same year.

Counting leases and ordinary cash makes Clearsift slightly stricter than the standards themselves. Every ratio has to be strictly below its limit.

| Standard | Divided by | Debt | Cash | Receivables + cash | Impermissible income |
|---|---|---|---|---|---|
| AAOIFI (default) | market cap | 30% | 30% | not checked | 5% |
| FTSE | total assets | 33.333% | 33.333% | 50% | 5% |
| MSCI | total assets | 33.33% | 33.33% | 33.33% | 5% |

All limits live in `config.yaml`, nothing is hard-coded.

### Standard and strict mode

Every stock comes out as compliant, doubtful or excluded.

- **Standard mode** (the default): doubtful stocks pass, with a "check by hand" warning.
- **Strict mode:** only compliant stocks pass.

A stock is doubtful when its industry needs a manual check, or when its interest income only comes from an older report.

### Fail closed

Missing, stale or unclear data means the stock is excluded, in both modes. Financial data counts as stale after 120 days and market cap after 1 day. A negative number where one can't be negative is treated as bad data.

Some companies stop reporting interest income. Clearsift then uses the newest report that has it, as long as it's no more than 3 years older than the latest report (`max_interest_income_age_years` in `config.yaml`). A stock screened on an older figure is doubtful rather than compliant. If there's nothing that recent, interest income counts as not disclosed.

## Purification

A compliant company can still earn a small amount of impermissible income, up to 5% of revenue. Investors give that share of their dividends to charity, which is called purification.

For every stock that passes, Clearsift shows the share to give away, e.g. `purify 0.98% of dividends`. If the figure comes from an older report it says which year. If the company doesn't disclose interest income, it says it can't work it out.

Percentages and amounts always round up, so you never give less than you should. That means the purification figure can be a little higher than the interest income line in the screen output. For example, MSFT shows interest income at 0.99% of revenue but `purify 1.00% of dividends`, because the real ratio sits between the two.

## Limitations

- **Free data:** Yahoo Finance data can be incomplete or wrong. Clearsift excludes what it can't trust, but it can't catch every mistake.
- **Interest income only:** it's the only impermissible income measured. Income from other sources, like a side business, isn't counted, so treat the purification figure as a minimum.
- **Undisclosed interest income:** some companies don't report it. Those stocks are doubtful and need checking by hand.
- **Not advice:** Clearsift is not financial advice or a religious ruling. Check important decisions with a qualified scholar or adviser.

## Running the tests

```
pytest
ruff check .
```

## Roadmap

- **Dashboard:** holdings, profit and loss, and sector allocation.
- **Ratings:** Buy, Hold or Sell for compliant stocks, with reasons.
- **Backtesting:** test whether the ratings beat a halal benchmark.

## Licence

MIT, see [LICENSE](LICENSE).
