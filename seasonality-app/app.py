"""Streamlit entrypoint: streamlit run app.py."""
from datetime import datetime, timezone
from html import escape
import os
from pathlib import Path

import pandas as pd
import streamlit as st

from seasonal.analytics import MONTHS, analyze, monthly_returns
from seasonal.data import DataUnavailable, StorageConfig, fetch_history, normalize_ticker
from seasonal.presentation import history_table, percent, seasonality_chart

st.set_page_config(page_title='Seasonal · Market seasonality', page_icon='📊', layout='wide')


def settings():
    def get(key, default=''):
        if os.environ.get(key):
            return os.environ[key]
        secret_files = [Path.cwd() / '.streamlit/secrets.toml',
                        Path(__file__).parent / '.streamlit/secrets.toml',
                        Path.home() / '.streamlit/secrets.toml']
        if not any(path.is_file() for path in secret_files):
            return default
        try:
            return st.secrets.get(key, default)
        except (FileNotFoundError, KeyError):
            return default
    return StorageConfig(get('SUPABASE_URL'), get('SUPABASE_STORAGE_KEY'), get('SUPABASE_BUCKET', 'seasonal-prices'))


@st.cache_data(ttl=3600, max_entries=64, show_spinner=False)
def load(ticker, utc_day, storage):
    return fetch_history(ticker, storage)


def change_range(first, last):
    st.session_state['year_range'] = (first, last)


st.markdown('''<style>
 .stApp{background:#f6f8fc;color:#192438}
 .block-container{max-width:1250px;padding-top:4.5rem;padding-bottom:2rem}
 [data-testid="stHeader"]{background:rgba(246,248,252,.92)}
 [data-testid="stVerticalBlockBorderWrapper"]>div{background:#fff;border-color:#e3e8f0!important;border-radius:12px}
 h1,h2,h3{letter-spacing:-.6px} h1{font-size:2rem!important;padding-top:0!important}
 .brand{display:flex;align-items:center;gap:10px;padding:0 0 18px;border-bottom:1px solid #e3e8f0;margin-bottom:22px}
 .brand-mark{display:inline-grid;place-items:center;background:#3957d5;color:white;border-radius:9px;width:33px;height:33px;font-size:19px}
 .brand-name{font-size:21px;font-weight:700;letter-spacing:-.6px}.brand-sub{font-size:11px;letter-spacing:1.6px;color:#647188;border-left:1px solid #e3e8f0;padding-left:14px;margin-left:5px}
 .eyebrow{font-size:11px;color:#647188;letter-spacing:1.5px;margin-bottom:6px}.lead{color:#647188;margin-top:-7px;margin-bottom:18px;font-size:14px}
 .security{font-size:21px;font-weight:700}.security-name{font-size:12px;color:#647188;margin-top:3px}
 .insights{display:flex;gap:25px;flex-wrap:wrap;color:#647188;font-size:13px;padding:0 8px 12px}.insights strong{color:#192438;font-weight:600}
 .return-table{overflow-x:auto;background:white;border:1px solid #e3e8f0;border-radius:10px;margin-top:6px}
 .return-table table{border-collapse:separate;border-spacing:0;width:100%;font-size:12px;text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}
 .return-table th,.return-table td{padding:10px 8px;border-bottom:1px solid #e3e8f0}
 .return-table thead th{font-weight:500;color:#647188;background:#fff}
 .return-table th:first-child{text-align:left;position:sticky;left:0;z-index:1;background:#fff;min-width:102px}
 .return-table .summary th,.return-table .summary td{font-weight:600}
 .return-table .active-stat td,.return-table .active-stat th{background:#edf0ff}
 .return-table tr.first-year td,.return-table tr.first-year th{border-top:2px solid #e3e8f0}
 .return-table td:last-child{font-weight:650;border-left:1px solid #e3e8f0}
 .return-table tr:last-child td,.return-table tr:last-child th{border-bottom:0}
 .positive{color:#008c75}.negative{color:#d9294d}.neutral{color:#647188}
 .return-table small,.return-table sup{font-size:10px;color:#647188}.foot{border-top:1px solid #e3e8f0;padding-top:13px;margin-top:23px;font-size:11px;color:#647188}
 div[data-testid="stDownloadButton"]{padding-top:0} button[kind="secondary"]{border-radius:6px}
 @media(max-width:650px){.block-container{padding:4.5rem 1rem 1rem}.brand-sub{display:none}h1{font-size:1.6rem!important}.return-table th,.return-table td{padding:9px 7px}}
 </style>''', unsafe_allow_html=True)
st.markdown('<div class="brand"><span class="brand-mark">▥</span><span class="brand-name">Seasonal</span><span class="brand-sub">MARKET RESEARCH</span></div>', unsafe_allow_html=True)
st.markdown('<div class="eyebrow">A CALENDAR VIEW OF THE MARKET</div>', unsafe_allow_html=True)
st.title('Find the pattern in the past.')
st.markdown('<div class="lead">Explore monthly returns across years, stocks, and ETFs.</div>', unsafe_allow_html=True)

storage = settings()
query_ticker = st.query_params.get('ticker', 'SPY')
try:
    initial = normalize_ticker(query_ticker)
except ValueError:
    initial = 'SPY'
with st.container(border=True):
    ticker_col, name_col, basis_col = st.columns([1.1, 2, 1.3])
    with ticker_col:
        typed = st.text_input('Ticker', value=initial, max_chars=25, help='Yahoo symbols: SPY, QQQ, AAPL, BRK-B, ^GSPC, BTC-USD. Press Enter to load.')
    with basis_col:
        basis_label = st.selectbox('Return basis', ['Price return', 'Dividend-adjusted'])
try:
    ticker = normalize_ticker(typed)
except ValueError as exc:
    st.error(str(exc))
    st.stop()
basis = 'price' if basis_label == 'Price return' else 'adjusted'
st.query_params['ticker'] = ticker
try:
    with st.spinner(f'Loading {ticker} daily history…'):
        data = load(ticker, datetime.now(timezone.utc).date().isoformat(), storage)
except DataUnavailable as exc:
    st.error(str(exc))
    st.caption('No illustrative prices are substituted for unavailable market data.')
    st.stop()
with name_col:
    st.markdown(f'<div class="security">{escape(ticker)}</div><div class="security-name">{escape(data.name)} · {escape(data.currency)}</div>', unsafe_allow_html=True)
if data.warning:
    st.warning(data.warning)
as_of = pd.Timestamp.now(tz='America/New_York')
try:
    available = monthly_returns(data.frame, basis).dropna()
except ValueError as exc:
    st.error(str(exc))
    st.stop()
if available.empty:
    st.info('This symbol does not yet have two month-end observations. Try another ticker.')
    st.stop()
minimum = int(available.index.year.min())
maximum = int(min(available.index.year.max(), as_of.year))
identity = (ticker, minimum, maximum)
if st.session_state.get('range_identity') != identity:
    st.session_state['year_range'] = (minimum, maximum)
    st.session_state['range_identity'] = identity

with st.container(border=True):
    heading, statistic = st.columns([2.5, 1])
    with heading:
        st.subheader('Historical seasonality')
    with statistic:
        metric = st.radio('Monthly statistic', ['Average', 'Median'], horizontal=True, label_visibility='collapsed')
    period_label, *presets = st.columns([2.8, .45, .45, .45, .45, .45])
    with period_label:
        st.caption('Selected calendar years')
    for column, label in zip(presets, ['3Y', '5Y', '10Y', '20Y', 'All']):
        with column:
            first = minimum if label == 'All' else max(minimum, maximum-int(label[:-1])+1)
            st.button(label, on_click=change_range, args=(first, maximum), use_container_width=True)
    if minimum == maximum:
        start = end = minimum
        st.caption(f'{minimum} · all available history')
    else:
        start, end = st.slider('Year range', minimum, maximum, key='year_range', label_visibility='collapsed')
    include_mtd = st.checkbox('Include current MTD in statistics', value=False,
        help='By default, the current calendar month is excluded from monthly averages, medians and win rates.')
    analysis = analyze(data.frame, start, end, basis, include_mtd, as_of)
    st.caption(f'{metric} monthly {basis_label.lower()} · {start}–{end} · '+('MTD included' if include_mtd else 'Completed months only'))
    st.plotly_chart(seasonality_chart(analysis, metric), use_container_width=True,
        config={'displayModeBar': False, 'responsive': True}, key='monthly-chart')
    values = analysis.statistics[metric].dropna()
    if len(values):
        best, worst = int(values.idxmax()), int(values.idxmin())
        st.markdown(f'<div class="insights"><span>Strongest <strong>{MONTHS[best-1]} {percent(values.loc[best])}</strong></span><span>Weakest <strong>{MONTHS[worst-1]} {percent(values.loc[worst])}</strong></span><span>{len(analysis.history)} calendar years selected</span></div>', unsafe_allow_html=True)

title_col, export_col = st.columns([4, 1])
with title_col:
    st.subheader('Monthly return history')
with export_col:
    export = analysis.history.copy()
    export.columns = MONTHS
    export['Annual / YTD'] = analysis.annual
    export['Period type'] = pd.Series(analysis.annual_labels)
    export.index.name = 'Year'
    st.download_button('Export CSV', export.to_csv(float_format='%.8f'), f'{ticker}-monthly-returns.csv', 'text/csv',
        help='Returns are decimal fractions: 0.01 means 1%. Annual statistics exclude incomplete years.')
show_all = st.checkbox('Show all selected years', value=False, disabled=len(analysis.history) <= 6)
st.markdown(history_table(analysis, metric, show_all), unsafe_allow_html=True)
st.caption('↑ positive · ↓ negative · zero-return months count in win-rate denominators · * current MTD · — unavailable. Annual summary statistics use full calendar years only.')
st.download_button('Download summary statistics', analysis.statistics.rename(index=dict(enumerate(MONTHS, 1))).to_csv(), f'{ticker}-seasonality-statistics.csv', 'text/csv')
with st.expander('How the returns are calculated'):
    st.markdown('''Monthly returns compare the last available trading close of each month with the previous month's last trading close. January includes the prior December close. Missing months are not filled, and the first partial listing month has no return without a prior month-end baseline.

**Price return** uses Yahoo's split-adjusted Close, without dividend adjustment. **Dividend-adjusted** uses Yahoo's Adj Close, an adjusted-price return proxy that includes distributions. Data revisions and provider adjustments can change historical figures.

The current calendar month is shown as MTD and excluded from monthly statistics unless selected. Full-year returns compound 12 monthly returns; partial listing years and incomplete history show no full-year total. The current year's YTD is shown only when its January baseline is available. Annual averages, medians and win rates exclude YTD and incomplete years.

Downloads are refreshed on the next request each UTC day. No background scheduler runs while the app sleeps. Yahoo service interruptions may cause a clearly labeled saved-data fallback. This app is independent of Yahoo and does not provide live quotes.''')
storage_text = 'Private cloud persistence enabled' if storage.enabled else 'Server cache · may reset when the app restarts'
st.markdown(f'<div class="foot">Data source: Yahoo Finance via yfinance · Daily closes through {data.frame.index.max().date().isoformat()} · Retrieved {data.fetched_at:%Y-%m-%d %H:%M} UTC<br>{escape(storage_text)} · Historical patterns do not guarantee future returns.</div>', unsafe_allow_html=True)
