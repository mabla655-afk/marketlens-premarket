# MarketLens v0.4 — Morning Brief + virtual paper-trading worksheet

A **browser-based Streamlit app** built using the chart/scan concepts in your supplied PDFs: Andrew Aziz's *Advanced Techniques in Day Trading* and Bear Bull Traders' *TradeBook*. The full PDFs are **not distributed** in the app.

**Status:** application package created; **not hosted yet**. Streamlit must be deployed from your GitHub repository. The rules are educational research heuristics, **not live-trading recommendations, future probabilities, or broker order instructions**.

## New: Simple Morning Brief (the first tab)

1. Open the app during the NYSE **premarket window (4:00–9:30 a.m. Eastern)**.
2. The optional **Find active stocks automatically (experimental)** toggle uses Yahoo Finance's **general** most-active and day-gainer screeners to discover candidate symbols. This is **not** dedicated premarket discovery or comprehensive market coverage. Discovery is rate-limited, incomplete, and may fail. Your own watchlist always remains usable.
3. The app loads available 5-minute extended-hours bars for a combined maximum of **16** symbols, and filters today's actual observed premarket gaps, shares traded, 20-day average daily volume, and 14-day ATR according to a subset of the book's criteria. It displays at most five current **watch ideas**, or explicitly reports **no matches** when appropriate. Results older than 25 minutes are excluded from this watch ranking.
4. Select a ticker to view **premarket high, low, previous close, gap, last price**, and *why* the stock is interesting. The app cannot verify news catalysts, spread/Level 2, or clean price action, which the book discusses.
5. **No simulated entry is suggested before the opening bell.** From the regular session, the app checks completed 5-minute opening-range breaks, VWAP, EMA 9/21 and same-clock relative volume. A qualifying candle may be labeled PAPER BUY CANDIDATE; bearish observations are PAPER SELL / EXIT WATCH. There can be no signal at all. Market-data freshness checks suppress stale signals. These are simplified original heuristics, not the book's entire strategies.
6. When a **fresh** paper-only bullish example qualifies, the app displays a **virtual share count, last completed candle close as reference, an illustrative technical invalidation level, and an illustrative 2R target**. The math is from **virtual account settings**, not from your personal money. For example, the defaults assume a virtual $10,000 account, 0.5% virtual risk budget and a 10% maximum virtual exposure per example. Virtual shares are rounded **down** and can be 0.
7. **Log simulated BUY/SELL** buttons update a temporary in-app journal only. They **never place orders**. Export the journal CSV before leaving: the public Streamlit session does not persist it. The simulated fills ignore actual spreads/slippage, fees, and taxes; the target is not a forecast.

### Included from earlier releases

Open the **Full Research** tab for detailed scanner observations, candlestick charts, volume/VWAP/EMA overlays, book-strategy checklists, 5-minute opening range research and daily historical pattern comparisons. The source PDFs are cited by chapter/page inside the app. Other BBT patterns still require human review, so the app does not claim to detect all of them automatically.

## Publish online (new app)

1. Extract the v0.4 ZIP onto your computer. **Upload the files inside**, not the ZIP file itself.
2. Create a repository on https://github.com/new, e.g. `marketlens-premarket`.
3. Add the extracted source files to the **root of the repository**. Preserve `.streamlit/config.toml`, and ensure `app.py`, `requirements.txt`, `morning_brief.py`, `analytics.py`, `paper_signals.py`, `data_source.py`, and `book_strategies.py` all appear at the root.
4. In https://share.streamlit.io/ choose **Create app**, select your GitHub repository, branch **main**, and main file path **`app.py`**. Deploy and open the generated URL.

Official guide: https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy

## Update your existing v0.3 hosted app

1. Open the GitHub repository that currently hosts MarketLens. On Windows, GitHub Desktop simplifies updating many files: https://desktop.github.com/ .
2. Extract the new v0.4 ZIP. Copy the extracted files into your cloned repository, **replacing matching source files**, and adding the two new files `morning_brief.py` and `tests/test_morning_brief.py`. Preserve the folder structure. Do not replace or erase your unrelated files.
3. In GitHub Desktop, **Commit to main**, then **Push origin**. Streamlit Community Cloud reflects pushes to the connected repository without a new app URL.
4. Reload your existing `.streamlit.app` address. The heading should say **MarketLens — Morning Trading Research** and the caption **v0.4**.

Streamlit official editing guide: https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app/edit-your-app

If you work only inside the GitHub website, upload each new file or edit existing files with its pencil/Edit button and commit the changes. For changing many existing files, the desktop option is easier and less prone to confusing duplicate file names.

## Data accuracy and operational limits

- Data come from unofficial `yfinance`/Yahoo, **not an exchange-certified live or guaranteed premarket feed**. Current prices, timestamps, and screener symbols can be stale, missing, wrong, or rate-limited; the app does not have a real-time professional news/catalyst source or broad premarket screener.
- **Market screeners are not premarket leaders.** They supply names *to investigate*; the app separately requires current-session price bars to form its watch ranking. When discovery fails, defaults/user tickers remain.
- An observed 5-minute candle close is **not an executable order price**. Virtual sizing assumes an exact reference close and technical level, which is rarely what would be filled. Stop/exit calculations do not guarantee anything about trades or returns.
- **No unattended morning briefing, push notifications, or email delivery.** The app refreshes *only while the page is open* and won't send reports on its own. Scheduled scans require an additional service/workflow.
- If market is closed, the app must say so. No invented fresh premarket watchlist or current-paper signals.
- **Paper journal is browser-session-only** and should be exported to keep it. No broker, real bank/brokerage credentials, or auto-orders.
- Unverified news, chart quality, spreads and market microstructure mean these strategies need human research; the current rules are not fully validated through out-of-sample trading backtests.

## Development / tests

```bash
pip install -r requirements.txt
streamlit run app.py
```

```bash
pip install pytest
python -m pytest -q
```

There are **23 offline unit tests** of the calculations and pre-existing rule logic. Because Yahoo network access and Streamlit's runtime were not available in the build environment, live-data retrieval and cloud UI were **not** end-to-end tested. After deployment, test in the browser with a few symbols and use the provider diagnostics if charts do not load.

**Keep the GitHub repository free of your copyrighted PDFs, passwords, personal finance records, and any future API keys.** For any future API provider, put its key in Streamlit secrets, not in source code.
