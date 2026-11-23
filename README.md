# MarketLens v0.5 — automatic PAPER-trading simulator

**Status: built and unit-tested locally, but NOT deployed or live-data validated.** MarketLens is a virtual, educational market-research simulator. **It never places actual trades, accesses a brokerage, or recommends that you spend real money.** It is not an automated profitable strategy. A future strategy outcome is uncertain, and successful simulation results can be misleading.

## What changed since v0.4

1. **Broader premarket discovery:** optional Massive (formerly Polygon) **full-market stocks snapshot** premarket scanner ranks *actual observed* price gaps and premarket volume. Requires `MASSIVE_API_KEY` and a subscription that includes that endpoint; access can be delayed depending on the plan. With no key, the old Yahoo general active/gainers shortlist remains available and **is not a true broad premarket scanner**. The first 16 ticker candidates are then checked with unofficial Yahoo 5-minute bars. There may be feed timing differences. The news catalyst, order book, spread and true liquidity are NOT verified.
2. **Book strategy checks:** existing Full Research strategy library and now automatic detection for a **simplified 5-minute opening-range breakout + VWAP + EMA9/EMA21 + same-clock relative volume**. BBT's TradeBook, p.7, and Andrew Aziz, *Advanced Techniques in Day Trading*, Chapter 6, contain the underlying ideas. The actual published setups have discretionary conditions not entirely implemented here. Other BBT patterns are reference-only, NOT automated.
3. **Fully automatic virtual orders:** if the virtual account is activated and today's saved 3-symbol watchlist is nonempty, a fresh completed bar can form a virtual setup. The model fills at the **NEXT observed 5-minute bar's open**, with a configurable unfavorable slippage allowance, caps position sizing by virtual cash / exposure / loss budget, and models virtual stop, 2R target and end-of-day close. If both stop and target are touched inside one candle, **the stop is assumed first**. Simulated prices are not executable quotes. Default caps: 0.5% equity hypothetical risk per position, 10% exposure, max two entries per day, max two concurrent positions, 1% closed-trade daily loss ceiling. Losses may still exceed these hypothetical ceilings due to gaps and modeled limitations. **Long-only**, not short selling.
4. **Saved virtual account:** SQLite locally for trial runs; **external PostgreSQL (e.g., Neon) needed for reliable Community Cloud persistence**. The app creates its schema and stores cash, open positions, pending synthetic entries, closed trades, settings and event history. Downloadable JSON/CSV backups are provided. The live account and the Historical Replay tool are separate.
5. **Progress dashboard:** virtual equity, cash, realized P/L, win rate, recent automated decisions, closed-trade drawdown, and a realized-only equity curve.

## Exactly how to upgrade your GitHub + Streamlit app (Windows)

### Step A — Replace v0.4 files

1. Download **MarketLens_v0.5_Auto_Paper_Simulator.zip** and right-click → **Extract All**.
2. In **GitHub Desktop**, choose your existing repository (`marketlens-premarket`), then **Repository → Show in Explorer**.
3. Open the EXTRACTED v0.5 folder in a second Explorer window. Copy **all files and folders inside** into the repository folder, choosing **Replace** for files that already exist. Keep existing files unrelated to MarketLens. Crucially include `.github/workflows/paper-sim.yml`, `.streamlit/config.toml`, `auto_dashboard.py`, `auto_simulator.py`, `auto_store.py`, `market_scanner.py`, `run_scheduled.py`, `app.py`, and `requirements.txt`.
4. Back in GitHub Desktop: enter summary `MarketLens v0.5 automatic paper simulator`, click **Commit to main**, then **Push origin**. No new repository or new Streamlit URL is necessary.
5. Reload the existing Streamlit app. The page should now say `v0.5`. If packages don't install, use **Manage app → Logs** to view deployment errors.

### Step B — Add durable database so virtual balance survives restarts

**Streamlit Community Cloud local file storage is not guaranteed to persist**, so a local SQLite file is for experimentation only.

1. Go to [Neon](https://console.neon.tech/), sign up or log in, then **Create project**, e.g. `marketlens-paper`.
2. Open your Neon project → **Connect**, copy the complete **Postgres connection string** (`postgresql://...` including password and SSL settings). Treat this URL as a password; **don't paste it into ChatGPT, GitHub files, screenshots or a public post**.
3. Open [Streamlit Community Cloud](https://share.streamlit.io/), locate your MarketLens app → **Settings** → **Secrets**. Add these three settings in the Secrets editor, replacing placeholders with private values:

```toml
MARKETLENS_DATABASE_URL = "postgresql://YOUR_DB_USER:YOUR_DB_PASSWORD@YOUR_HOST/YOUR_DB?sslmode=require"
MARKETLENS_APP_PASSWORD = "A-LONG-UNIQUE-APP-ACCESS-PASSPHRASE"
MARKETLENS_USE_SCHEDULER = true
```

Do NOT save this as a checked-in `.streamlit/secrets.toml`. The first secret is the database URL; the second protects your single-user paper dashboard with an access password; the third tells the website not to duplicate the scheduled worker's account updates. Password gating is basic single-user access control, not multi-user authentication.

4. Save Streamlit Secrets. When you open the app you will see a password screen. Enter your private `MARKETLENS_APP_PASSWORD` value, then open the **AUTO PAPER SIM** tab. You may create a virtual $10,000 account. **Do not activate until GitHub Actions is configured** if you have enabled `MARKETLENS_USE_SCHEDULER=true`.

### Step C — Make automatic simulation run with the browser CLOSED

1. Open your GitHub repository in a browser → **Settings → Secrets and variables → Actions → New repository secret**.
2. Create a repository secret named **`MARKETLENS_DATABASE_URL`** and paste the **same Neon Postgres connection string** used above. This is required for the workflow to share your saved account with the website.
3. (Optional paid scanner) If you subscribe to Massive's full-market stocks snapshot endpoint, create an additional GitHub secret **`MASSIVE_API_KEY`** with that provider key. Add `MASSIVE_API_KEY = "..."` in your **Streamlit Secrets** too if you want the website to use it. Without a key, Yahoo's limited shortlist is used.
4. Open GitHub **Actions** tab → select **Paper-only market simulation** → **Run workflow** once to test. If you run it outside market hours it will safely report *outside schedule*; if the database secret is invalid, the workflow logs will show an error.
5. In the Streamlit dashboard, choose **Create virtual account** → **Activate fully automatic PAPER simulation**. Leave the activation enabled. The GitHub workflow is scheduled every five minutes during a broad weekday UTC range; the script itself checks the NYSE calendar and Eastern session time.
6. Check GitHub **Actions** periodically for green/failed runs. Schedules can be delayed or skipped, and public repositories with prolonged inactivity can have scheduled workflows disabled. **This is not professional real-time autonomous trading infrastructure.**

GitHub docs: https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets

Streamlit docs: https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app/app-settings

Neon/Streamlit tutorial: https://docs.streamlit.io/develop/tutorials/databases/neon

### Step D — How to use it every morning

- **9:00–9:20 a.m. ET:** open the **AUTO PAPER SIM** tab to review your virtual account and whether today's premarket watchlist (max 3) was identified. During this window the scheduled worker tries to select 3 names using observed premarket price bars and book-style filters. If no data qualify, the correct output is **NO ELIGIBLE SHORTLIST**.
- **9:30–9:40 a.m. ET:** the algorithm observes completed 5-minute opening bars. It does **not** assume that the open or premarket gap is a buy signal.
- **9:40–11:30 a.m. ET:** as eligible completed 5-minute signals arrive, the worker may create pending simulated entries and fill them at subsequent observed candle opens when fresh data and limits allow. **Most days may have zero virtual trades.**
- **Through 4:00 p.m. ET:** simulate conservative stops/targets and, when data are available, the session closing bar. Stale/missing data or delayed scheduled jobs may leave positions unprocessed until a later observation; check the logs and never confuse fills with real execution.
- **4:15 p.m. ET:** review the app's saved journal, realized virtual P/L, win rate, drawdown, and rule explanations. Export a backup periodically.

## Important limitations and precautions

- **No guaranteed gains, no forecast probabilities, and no personalized real-money trading instructions.** This app simulates a strict rule set, including losses. It cannot make your account grow predictably.
- The automatic worker **must be enabled in your account first** and needs both GitHub Actions and Neon secrets for unattended execution. It is not always-on low-latency infrastructure. A delayed cron, provider outage or market holiday can mean no simulated fill.
- Default free scanner is a shortlist of Yahoo **regular-session** active/gainer names, **not** an exchange-wide premarket screener. Optional Massive market snapshot requires a qualifying subscription and still does not replace Yahoo's 5-minute chart feed. **Yahoo is unofficial and may be stale, incomplete, or rate-limited.**
- In the basic simulator, stop/target events inside the same 5-minute candle have ambiguous ordering; it assumes the stop first. No complete Level II/order book, spread/liquidity modeling, news verification, stock split adjustments, taxes, overnight dividends or realistic order queue.
- Closed-equity progress is not marked-to-market drawdown. Paper trades use synthetic next-bar prices with a slippage model. A historical replay chosen after seeing a stock's performance can introduce selection bias. Use separate out-of-sample data to research reliability.
- There is only **one shared paper account** per database; do not share your app password or expose your DB URL. Do not upload the book PDFs, real brokerage details or private secrets to public GitHub.
- No new live data calls or deployed UI testing were possible during creation of this package. The added **28 automated calculation tests passed** in the local environment, but Streamlit/Yahoo/Neon/GitHub end-to-end functionality remains **unverified until your own deployment**.

## Local development and tests

```bash
pip install -r requirements.txt
streamlit run app.py
```

```bash
pip install pytest
python -m pytest -q
```

Without the `MARKETLENS_DATABASE_URL` secret, the app uses local `marketlens_paper.db` and runs the automation only when the browser is open (via Streamlit refreshes). On Community Cloud that local database may be deleted anytime.
