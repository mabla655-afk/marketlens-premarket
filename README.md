# MarketLens v0.8 — MIC Coach + beginner-first paper research

**A virtual-only educational simulator. No live brokerage connection, real orders, automatic short selling, or profit guarantees.**

## NEW — Interactive Market Replay (v0.8)

A fifth tab, **🎞️ MARKET REPLAY**, lets beginners study a past ticker/session using only the candles visible so far. It uses the same simplified BBT long-only opening-range model as the existing **🤖 PAPER SIM** tab, but **does NOT modify the Neon paper-trading account**. The existing automatic simulator, scanner, MIC Coach, data integration, and optional scheduled GitHub Action are preserved.

**How to use Replay**

1. Go to **MARKET REPLAY**. Choose a ticker from the existing watchlist and click **Load historical sessions**.
2. Choose a completed past session that has sufficient opening candles. Only past sessions appear; the current incomplete day is excluded.
3. Start at the opening 9:30–9:35 five-minute candle; click **Reveal next candle**. Use Previous, Restart, or the reveal slider at your pace.
4. Read **What this candle means**, see visible opening high/low levels, and inspect why the ORB strategy checked each requirement as met, failed, or unknown.
5. Optionally save a simple **Higher / Lower / About the same** guess for the next close, then reveal the next candle to receive feedback. The quiz is educational; guesses are not trading signals.
6. If the existing paper model generates a virtual entry/exit, study it in the **virtual event log**. No replay actions write to Neon or your main paper account.
7. Only after revealing the last *available* candle do you see the historical synthetic result. A data provider may supply a partial session.

**What it cannot do:** The replay is not guaranteed to have complete 5-minute history. It does not turn MIC discretionary short-selling checklists or DAS hotkeys into automatic orders. The date/ticker choice is known after the fact, and modeled fills do not represent real-world liquidity. For true unattended real-time paper simulation, a continuously running backend and qualified data feed would still be more reliable than GitHub Actions scheduling.

**Installing v0.8:** It is a complete replacement for v0.7. Download/unzip the ZIP, then copy *the files inside* into your existing GitHub repository folder (including hidden `.github` / `.streamlit`), replace matching files, **Commit to main → Push origin**, and refresh your existing Streamlit URL. Verify you see **v0.8** and the new MARKET REPLAY tab. No new keys or database migrations required.


This release builds on v0.6. It integrates measurable and educational elements from your uploaded **My Investing Club (MIC)** materials, without importing their copyrighted PDFs/worksheets or dangerous DAS order-command configurations into the published app. It preserves the previous BBT long-only 5-minute opening-range paper engine, historical studies, optional Massive market feed, and Neon account storage.

## What's new, in plain English

- **☀️ START HERE** is first. It explains the current market research shortlist; select a ticker to see its available price, gap and (where possible) three **MIC Rock pivot** reference levels.
- **🧭 MIC COACH** offers a beginner glossary; a readable stock information card; a verified-vs-unverified **news / float / dilution** worksheet; MIC-style prior-day **pivot and S/R** levels; and a concise editable **game plan** that downloads as JSON.
- The **float rotation** calculation is only shown after you enter an independently verified float. Missing company data is clearly **Not checked**, never silently assumed positive or negative.
- A **virtual position calculator** translates the MIC position-size spreadsheet into a simple long-only example constrained by 0.5% hypothetical loss-at-level and 10% exposure. It cannot place or log orders.
- **🤖 PAPER SIM** still includes a compact dated virtual P/L review (inspired by the MIC calendar), when simulated closed trades exist.
- **🔬 FULL RESEARCH** charts can annotate MIC pivot/P, first resistance/R1 and first support/S1 when yesterday's complete, internally consistent daily OHLC is available.

## Exactly what was taken from the 13 files

| Your uploaded MIC material | v0.8 integration | Limits |
| --- | --- | --- |
| `Checklist .docx` | Bullish/bearish research prompts, news, float, ownership/dilution caution | Not a real-time filing verification or a buy/sell score |
| `Game-Plan.docx` | Big picture, ticker, news, key levels, invalidation notes | Download-only notes, not stored on Neon |
| `@Modern_Rock Pivots.xlsx` | All pivot arithmetic implemented; core P/R1/S1 visible | Calculated from prior complete daily high, low, close |
| `Pos. Calc.xlsx` | Virtual risk/exposure share math and 2R example | No real account or margin assumptions; options omitted |
| `MIC_starter_pack_new_look.pdf` | Original plain-English explanations of VWAP, float, rotation and terms | No lengthy copyrighted reproduction |
| `TBRADLEY90_Cheat_Sheet.pdf` | Clear caution labels for very low float / high short float | No automated short entries; qualitative rules need judgment |
| `The-Ultimate-Trading-Basics-Resources.pdf` | Guidance on MIC topics, terminology and sources | Link index is not a verified API or importable scanner |
| `flash_calendar_template_2024_mic.xlsx` | Daily virtual P/L summary for completed simulations | Does not import an outdated 2024 calendar |
| `Das-Trader-Pro-Instructions-for-MIC.pdf` | Research-level reminder that VWAP, previous close and price levels matter | DAS-specific controls and broker instructions not ported |
| `Hotkey.htk`, `Black.cst`, `Line.cst`, `default.dsk` | Classified as DAS configuration assets | NOT imported, executed, or included; platform-specific live order commands are inappropriate for this simulator |

**Important:** MIC's educational short-selling material is not interchangeable with the currently automated BBT-based **long-only** paper method. MIC's news, dilution, float, SSR and 9:29 a.m. checklist elements require additional licensed data and manual interpretation; a 5-minute candle stream cannot verify those conditions to the precision claimed by the original checklist. This release **does not promise** to automate them.

## Install / upgrade your existing app

1. Download `MarketLens_v0.8_MIC_Coach.zip` from the chat. Use **Extract All** to unzip.
2. In **GitHub Desktop**, choose your existing `marketlens-premarket` repository → **Repository > Show in Explorer**.
3. Copy **everything inside** the extracted v0.8 folder into the GitHub repository folder, and replace existing files. Important: include hidden `.github/` and `.streamlit/` folders, plus the new `mic_coach.py`, `mic_ui.py`, and `tests/test_mic_coach.py`.
4. In GitHub Desktop, enter a summary like `Add MarketLens v0.8 MIC beginner coach` → **Commit to main** → **Push origin**.
5. Open the **same Streamlit URL** as before. Verify that the heading says `v0.8`. If deployment fails, see Streamlit **Manage app → Logs**.
6. Check tabs: **START HERE**, **PAPER SIM**, **MARKET REPLAY**, **MIC COACH**, **FULL RESEARCH**.
7. In MIC COACH select a ticker. Start with yesterday's pivot levels and glossary. Only enter float/news/filing information when verified from a trustworthy source. Download your research note if you want to keep it.

## Your existing services

- Keep your existing Neon `MARKETLENS_DATABASE_URL`, app password, and `MARKETLENS_USE_SCHEDULER` settings. **No database schema migration is needed** for the new MIC research tools.
- Keep `MASSIVE_API_KEY` configured as a **private Streamlit secret AND GitHub Actions secret** if you have entitlement. Do **not** publish the actual key, URLs containing passwords, or credential files in GitHub.
- Massive should still power the scanner and OHLCV when a key is present. Without it the app uses unofficial Yahoo data and labels limitations. With delayed data the automatic engine refuses stale new entries.
- The GitHub Actions 5-minute schedule is **not** an always-on real-time execution system; it may run late or be skipped. This release does not replace it with a continuously running backend.

## Daily beginner workflow (Eastern Time, on U.S. trading days)

1. **8:45–9:15 AM:** Open **START HERE** to study the shortlist. Check feed source and freshness. Open **MIC COACH** to understand float, gap, volume and basic news context.
2. **9:20 AM:** Fill in a one-page MIC research note on up to three tickers. Do not mark unknown filings/float as verified.
3. **9:30–9:40 AM:** Observe complete opening candles. No immediate premarket buy predictions.
4. **9:40–11:30 AM:** If the feed and scheduler are healthy, the **PAPER SIM** may log model-based *virtual* trades when the existing BBT-style rule matches. No manual or MIC short trades are opened.
5. **After 4 PM:** Read virtual wins, losses, daily results and no-trade reasons. Paper results don't measure guaranteed real execution.

## Tests and limits

Run locally if you have Python dependencies installed: `python -m pytest -q` and `python -m compileall -q .`. The v0.8 release has **46 passing local tests**, including exact Rock Pivot spreadsheet reference values. Live deployment, API-provider entitlements, exchange timestamps, Streamlit reactivity and Neon/GitHub scheduling integration have **not** been independently tested here.

**Do not equate high frequency of trades with quality.** The default practice simulator intentionally limits the count, applies position caps and refuses stale or incomplete data. It is for structured learning, not placing real funds at risk.
