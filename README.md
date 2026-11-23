# MarketLens — Premarket Lab v0.2

An **online-ready educational market research app**. Developed from your two uploaded references: Andrew Aziz's *Advanced Techniques in Day Trading* (2018) and Bear Bull Traders' *TradeBook* (2022). The PDFs themselves are **not packaged** or redistributable here; the research descriptions are newly paraphrased.

**This is not a deployed URL yet.** A person authorized to use the GitHub/Streamlit account must publish it. It cannot place orders, connect to a broker, recommend stock purchases/sales, or guarantee outcomes. Designed for research and paper simulations only.

## What's new in v0.2

- **Book-informed premarket screen** on your chosen tickers, based on Aziz Chapter 3, printed pp. 80–83 (PDF pp. 88–91). It evaluates the measurable criteria:
  - Absolute observed premarket gap of **at least 2%** vs prior completed regular-session close.
  - Premarket trading volume **at least 100,000 shares by 9 a.m. ET**, measured using 5-minute bars beginning 4 a.m. through 8:55 a.m. ET. This remains pending if appropriate 9 a.m. data are not available.
  - Average daily trading volume **over 500,000 shares**. Code convention: 20 prior completed trading sessions, since the book does not define the averaging window.
  - Daily ATR **at least $0.50**. Code convention: simple average of True Range over 14 prior completed trading sessions; book does not define an averaging window or smoothing convention.
  - News catalyst and clean premarket price action must be verified **manually**. No stock is asserted to meet all conditions based only on numerical metrics.
- **5-minute Opening Range Breakout research** based on BBT TradeBook PDF p. 7 and Aziz Chapter 6. The tool marks the first 09:30–09:35 ET candle range and **subsequent completed 5-minute closes** outside that range. It does **not** claim a verified ORB setup; the full book rules also require VWAP, volume, 1-minute chart quality and chart-level judgment. The displayed observation is not an order signal.
- **5-minute-session VWAP** overlays on charts, reset at 09:30 ET. VWAP values are calculated using typical prices (H+L+C)/3 and reported volume; this is an approximation, not transaction-by-transaction VWAP.
- **Up-to-60-calendar-day historical 5-minute ORB observations**, loaded **on demand** for one chosen ticker. Summarizes the fraction of subsequent 5-, 15-, or 30-minute closes that were in the direction of the first observed completed-bar boundary crossing. Uses one observation per session, skips the current day, requires contiguous 5-minute bars, and ignores missing sessions. **Not a trading backtest**: no entries/fills, position sizing, costs, spreads, or other trade rules.
- **Strategy library** cross-referenced to original PDF pages: Fallen Angel/Rising Devil, ABCD/Reverse ABCD, Lightning Bolt, Extreme Reversal, Parabolic Reversal, Mountain Pass, High/Low of Day at round numbers, Bull/Bear Flag, VWAP and ORB. Setups that need discretion remain explicitly labeled *Research checklist*. The TradeBook's 1–2-minute ORB is marked *not specified* because the file lists it as "coming soon."
- Retains v0.1 custom-symbol watchlist, premarket relative volume, charts, 4 example daily patterns, notes, CSV/JSON exports, market-session clock and feed diagnostics.

## Deploy to the web with Streamlit Community Cloud

1. Sign in to **GitHub** and make a new repository, e.g. `marketlens-premarket`.
2. Extract the ZIP and put the extracted contents in the repository **root**, preserving the `.streamlit/config.toml` subfolder.
3. Open **https://share.streamlit.io/**, sign in and select **Create app**, select the repository, main branch, and entrypoint **`app.py`**.
4. Deploy it. The host will install dependencies from `requirements.txt` and assign a `.streamlit.app` web address. Test the dashboard using a single ticker first.

Streamlit official documentation: https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy

**Security:** Only put app *code* into a hosted repository; do **not** upload either copyrighted book, financial account numbers, credentials, or private notes. If your repo is public, everyone can view its source. Provider API keys added in future versions must be stored in the host's secrets management, not committed to Git.

## Run locally

```bash
python -m venv .venv
# Activate it using your operating system's shell instructions.
pip install -r requirements.txt
streamlit run app.py
```

To run automated tests:

```bash
python -m pytest -q
```

## Known limitations (important)

- **Not whole-market discovery.** This scans **only** user-selected tickers (up to 16 at a time), not every U.S. stock. A true broad-market premarket discovery feed, reliable float data, corporate-action event/news catalyst integration and consistently timely quotes need a licensed market-data service. We have not connected one yet.
- **Not deployed or running in the background.** You need to deploy it to your hosting account. Its refresh runs only while the browser page is open, not unattended before the open. Automatic scheduled reports and unattended alerts are not implemented.
- Market data uses `yfinance`/Yahoo's unofficial interface. **Data can be delayed, rate-limited, missing, incomplete or incorrectly adjusted**, especially in premarket. Current bars must be checked by timestamp; 5-minute bars are not a substitute for tick data/Level 2.
- Historical 5-minute data are limited by the provider to roughly **60 days** and may include far fewer actual sessions. Daily studies use about two years. It does not incorporate delisted stocks and cannot validate a historical edge for a strategy.
- One first break per historical session; results ignore additional conditions from the authors, simultaneous signals, fills, costs, slippage, survivorship bias, unobserved news and regime changes. These observations **must not** be interpreted as forward probabilities.
- Book-based screen is a descriptive research filter, not a judgment of trade safety or a buy/sell recommendation. Discretionary conditions must be reviewed by a human.
- Watchlists and journal notes are held temporarily in the app session. Export them to persist. The public app does not store notes in a private database.

## Project files

- `app.py` — Streamlit UI and book research panels
- `analytics.py` — original indicator and daily pattern research
- `book_strategies.py` — book rules/metadata, ATR, gappers and 5-minute ORB research
- `data_source.py` — unofficial Yahoo access; caching and symbol validation
- `.streamlit/config.toml` — UI theme
- `tests/` — offline unit tests with synthetic market data

No book PDFs bundled, no broker login, and no live execution.
