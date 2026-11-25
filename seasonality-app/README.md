# Seasonal

Public Streamlit research app for historical monthly seasonality, built with Python, pandas and Plotly.

## Run

Python 3.12 is recommended.

```sh
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Enter a Yahoo symbol such as SPY, QQQ, AAPL, BRK-B, ^GSPC or BTC-USD. Add `?ticker=QQQ` to a shared URL to open that ticker. The app never substitutes synthetic data for unavailable prices.

## Deploy free on Streamlit Community Cloud

At https://share.streamlit.io/, sign in, choose Create app, and select this GitHub repository and the branch containing the app. Set the entrypoint to `seasonality-app/app.py` when this folder is nested in a repository, or `app.py` when it is the repository root. Select Python 3.12 under Advanced settings. Choose an available `streamlit.app` subdomain and deploy. The app must be Public in its sharing settings to allow visitors without invitations.

Community Cloud may sleep after inactivity. Free hosting has memory and usage limits and does not provide an uptime guarantee.

## Persistent storage

The app always uses a bounded local Parquet cache (64 tickers) and a Streamlit memory cache. Local files on free hosting may disappear on reboot or redeployment. For persistence across restarts, create a Supabase **Free** project and a **private** Storage bucket named `seasonal-prices`. Add `SUPABASE_URL`, `SUPABASE_STORAGE_KEY` and `SUPABASE_BUCKET` to Streamlit's secrets panel, using `.streamlit/secrets.toml.example` as a template. A server-only legacy service-role key works with the Storage REST API. Keep it in secrets: never add it to the repository, logs or a client-side page. Cloud persistence is not configured until these secrets and a bucket exist. The footer reports its configured state, and failures show a warning.

Supabase Free currently includes 1 GB Storage and limited egress, with project pausing after inactivity. Download only requested tickers, cache reads, and stay on the Free plan. No paid service is required by the source code. This app does not create accounts or enroll you in a paid plan.

## Data and calculations

- Requests daily Yahoo history with `auto_adjust=False`, retaining Close and Adj Close.
- Price return uses Yahoo Close (split-adjusted, without dividend adjustment); dividend-adjusted return uses Adj Close.
- Month-end return = final close this month / final close last month - 1. Calculate before year filtering so January retains December's baseline.
- Reindex calendar months without forward filling: a missing month cannot silently become a return over multiple months.
- Exclude the current month from monthly statistics by default; show its MTD in the table. Exclude incomplete listing months when no prior close exists.
- Up and down counts exclude zero returns; win-rate denominators include them. Show observation counts in hover details.
- Full-year returns require 12 observed monthly returns and are compounded. Current-year YTD requires the January baseline; incomplete years have no annual total. Annual summary statistics include only full calendar years.
- Drop a changing current-session daily bar until its regular session end when Yahoo provides session metadata.
- Refresh full history on the first request each UTC day to capture adjustment revisions. Use clearly labeled saved data if Yahoo is unavailable. No automatic job runs while the app sleeps.

Yahoo and yfinance availability is not guaranteed. yfinance is independent of Yahoo; its documentation describes the API as intended for personal use. Free access is not a grant of public redistribution rights. Review the applicable data terms for your use. No raw history or keys should be committed to GitHub.

## Verification

```sh
python -m pytest -q
```

Sources: [Streamlit deployment](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy), [Supabase pricing](https://supabase.com/pricing), [yfinance](https://ranaroussi.github.io/yfinance/).
