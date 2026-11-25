"""Yahoo daily history with local Parquet and optional private Supabase persistence."""
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
import logging
import os
from pathlib import Path
import re
import tempfile
import threading

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import requests
import yfinance as yf

LOG = logging.getLogger(__name__)
LOCK = threading.Lock()
SCHEMA = 'daily-v1'


class DataUnavailable(Exception):
    pass


@dataclass(frozen=True)
class StorageConfig:
    url: str = ''
    key: str = ''
    bucket: str = 'seasonal-prices'

    @property
    def enabled(self):
        return bool(self.url and self.key)


@dataclass
class PriceData:
    frame: pd.DataFrame
    fetched_at: datetime
    name: str
    currency: str
    storage: str
    warning: str = ''


def normalize_ticker(value: str) -> str:
    ticker = value.strip().upper()
    if not re.fullmatch(r'[A-Z0-9^][A-Z0-9.^=_-]{0,24}', ticker):
        raise ValueError('Enter a Yahoo symbol such as SPY, AAPL, BRK-B, ^GSPC, or BTC-USD.')
    return ticker


def _key(ticker):
    return f'{SCHEMA}/{sha256(ticker.encode()).hexdigest()[:24]}.parquet'


def _pack(data):
    table = pa.Table.from_pandas(data.frame)
    metadata = dict(table.schema.metadata or {})
    metadata.update({b'seasonal_fetched_at': data.fetched_at.isoformat().encode(),
                     b'seasonal_name': data.name.encode(), b'seasonal_currency': data.currency.encode()})
    sink = BytesIO()
    pq.write_table(table.replace_schema_metadata(metadata), sink, compression='zstd')
    return sink.getvalue()


def _unpack(content, storage):
    table = pq.read_table(BytesIO(content))
    meta = table.schema.metadata or {}
    fetched = datetime.fromisoformat(meta[b'seasonal_fetched_at'].decode())
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=timezone.utc)
    frame = table.to_pandas()
    if frame.empty or 'Close' not in frame or not isinstance(frame.index, pd.DatetimeIndex):
        raise ValueError('Invalid price cache.')
    return PriceData(frame, fetched, meta.get(b'seasonal_name', b'').decode(),
                     meta.get(b'seasonal_currency', b'').decode(), storage)


def _remote_url(config, key, authenticated=False):
    if not re.fullmatch(r'https://[a-z0-9-]+\.supabase\.co', config.url.rstrip('/')):
        raise ValueError('Invalid Supabase project URL.')
    if not re.fullmatch(r'[a-zA-Z0-9_-]+', config.bucket):
        raise ValueError('Invalid storage bucket.')
    prefix = '/authenticated' if authenticated else ''
    return f'{config.url.rstrip("/")}/storage/v1/object{prefix}/{config.bucket}/{key}'


def _headers(config):
    return {'apikey': config.key, 'Authorization': f'Bearer {config.key}'}


def fetch_history(ticker, config=None, cache_dir=None, now=None):
    ticker = normalize_ticker(ticker)
    config = config or StorageConfig()
    now = now or datetime.now(timezone.utc)
    cache_root = Path(cache_dir or os.environ.get('SEASONAL_CACHE_DIR', Path(__file__).resolve().parents[1] / '.cache'))
    cache_root.mkdir(parents=True, exist_ok=True)
    key = _key(ticker)
    local = cache_root / Path(key).name
    cached = None
    storage_warning = ''
    if local.exists():
        try:
            cached = _unpack(local.read_bytes(), 'Server Parquet cache')
        except Exception:
            LOG.warning('Ignoring an unreadable local price cache.')
    if cached is None and config.enabled:
        try:
            response = requests.get(_remote_url(config, key, True), headers=_headers(config), timeout=12)
            if response.status_code == 200:
                if len(response.content) > 20_000_000:
                    raise ValueError('Price cache exceeds the file size limit.')
                cached = _unpack(response.content, 'Private cloud storage')
                local.write_bytes(response.content)
            elif response.status_code != 404:
                storage_warning = 'Cloud storage is unavailable; using the server cache.'
        except (requests.RequestException, ValueError, KeyError):
            storage_warning = 'Cloud storage is unavailable; using the server cache.'
    if cached and cached.fetched_at.date() == now.date():
        cached.warning = storage_warning
        return cached
    # A full refresh also picks up Yahoo revisions and historical dividend adjustments.
    try:
        with LOCK:
            security = yf.Ticker(ticker)
            history = security.history(period='max', interval='1d', auto_adjust=False,
                                       actions=True, timeout=20, raise_errors=True)
            if history.empty:
                raise DataUnavailable('No daily history was found for this symbol.')
            metadata = security.history_metadata or {}
        history = history.copy()
        # Discard today's changing session bar until its regular session has ended.
        regular = (metadata.get('currentTradingPeriod') or {}).get('regular') or {}
        session_end = regular.get('end')
        if session_end and now.timestamp() < session_end:
            exchange_tz = metadata.get('exchangeTimezoneName', 'America/New_York')
            local_today = pd.Timestamp(now).tz_convert(exchange_tz).date()
            history = history[[d.date() != local_today for d in history.index]]
        history.index = history.index.tz_localize(None).normalize()
        history = history[~history.index.duplicated(keep='last')].sort_index()
        wanted = [c for c in ['Open', 'High', 'Low', 'Close', 'Adj Close', 'Volume', 'Dividends', 'Stock Splits', 'Capital Gains'] if c in history]
        history = history[wanted]
        history = history[pd.to_numeric(history['Close'], errors='coerce') > 0]
        if len(history) < 2:
            raise DataUnavailable('At least two daily observations are needed for this symbol.')
        result = PriceData(history, now, metadata.get('longName') or metadata.get('shortName') or ticker,
                           metadata.get('currency', ''), 'Server Parquet cache', storage_warning)
    except Exception as exc:
        if cached:
            cached.warning = 'Yahoo could not refresh this symbol. Showing saved data; check the data-through date.'
            return cached
        raise DataUnavailable('Yahoo could not return history right now. Check the symbol or try again later.') from exc
    payload = _pack(result)
    # Atomic replacement protects readers if requests for a ticker arrive together.
    with tempfile.NamedTemporaryFile(dir=cache_root, delete=False) as temporary:
        temporary.write(payload)
        temporary_name = temporary.name
    os.replace(temporary_name, local)
    files = sorted(cache_root.glob('*.parquet'), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in files[64:]:
        old.unlink(missing_ok=True)
    if config.enabled:
        try:
            response = requests.post(_remote_url(config, key), headers={**_headers(config),
                'Content-Type': 'application/octet-stream', 'x-upsert': 'true'}, data=payload, timeout=15)
            response.raise_for_status()
            result.storage = 'Private cloud storage'
        except (requests.RequestException, ValueError):
            result.warning = 'Cloud saving is unavailable. This download is saved in the server cache.'
    return result
