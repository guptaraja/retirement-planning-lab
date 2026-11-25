from datetime import datetime, timezone, timedelta
from unittest.mock import Mock

import pandas as pd
import pytest

from seasonal.data import DataUnavailable, PriceData, StorageConfig, _pack, _unpack, fetch_history, normalize_ticker


@pytest.mark.parametrize('symbol', ['SPY', ' brk-b ', '^GSPC', 'BTC-USD', 'EURUSD=X'])
def test_valid_symbols(symbol):
    assert normalize_ticker(symbol) == symbol.strip().upper()


@pytest.mark.parametrize('symbol', ['', '../secret', '<script>', 'SPY/AAPL', 'X'*26])
def test_invalid_symbols(symbol):
    with pytest.raises(ValueError):
        normalize_ticker(symbol)


def sample(now):
    return PriceData(pd.DataFrame({'Close': [100., 110.], 'Adj Close': [99., 110.]},
        index=pd.to_datetime(['2024-12-31', '2025-01-31'])), now, 'Sample', 'USD', 'Server cache')


def test_parquet_round_trip_preserves_refresh_time_and_prices():
    item = sample(datetime(2025, 2, 2, tzinfo=timezone.utc))
    restored = _unpack(_pack(item), 'Private cloud storage')
    pd.testing.assert_frame_equal(item.frame, restored.frame)
    assert item.fetched_at == restored.fetched_at
    assert item.name == restored.name


def test_same_day_download_is_reused_and_next_day_failure_is_labeled(monkeypatch, tmp_path):
    now = datetime(2025, 2, 2, 22, tzinfo=timezone.utc)
    security = Mock()
    security.history.return_value = sample(now).frame
    security.history_metadata = {'shortName': 'Sample', 'currency': 'USD'}
    provider = Mock(return_value=security)
    monkeypatch.setattr('seasonal.data.yf.Ticker', provider)
    first = fetch_history('SPY', cache_dir=tmp_path, now=now)
    second = fetch_history('SPY', cache_dir=tmp_path, now=now)
    assert provider.call_count == 1
    pd.testing.assert_frame_equal(first.frame, second.frame)
    security.history.side_effect = RuntimeError('Provider down')
    stale = fetch_history('SPY', cache_dir=tmp_path, now=now+timedelta(days=1))
    assert 'Showing saved data' in stale.warning
    assert stale.fetched_at == now


def test_cloud_cache_survives_absent_local_files(monkeypatch, tmp_path):
    now = datetime(2025, 2, 2, tzinfo=timezone.utc)
    response = Mock(status_code=200, content=_pack(sample(now)))
    monkeypatch.setattr('seasonal.data.requests.get', Mock(return_value=response))
    ticker = Mock(side_effect=AssertionError('Should not download again'))
    monkeypatch.setattr('seasonal.data.yf.Ticker', ticker)
    item = fetch_history('SPY', StorageConfig('https://example.supabase.co', 'test-key'), tmp_path, now)
    assert item.storage == 'Private cloud storage'
    assert ticker.call_count == 0


@pytest.mark.parametrize('timestamp_metadata', [False, True])
def test_changing_session_bar_is_excluded(monkeypatch, tmp_path, timestamp_metadata):
    now = datetime(2025, 2, 3, 15, tzinfo=timezone.utc)
    history = sample(now).frame
    history.loc[pd.Timestamp('2025-02-03')] = [120., 120.]
    security = Mock()
    security.history.return_value = history
    session_end = pd.Timestamp(now)+pd.Timedelta(hours=1) if timestamp_metadata else now.timestamp()+3600
    security.history_metadata = {'currentTradingPeriod': {'regular': {'end': session_end}},
                                'exchangeTimezoneName': 'America/New_York'}
    monkeypatch.setattr('seasonal.data.yf.Ticker', Mock(return_value=security))
    item = fetch_history('SPY', cache_dir=tmp_path, now=now)
    assert item.frame.index.max() == pd.Timestamp('2025-01-31')


def test_unavailable_provider_does_not_invent_data(monkeypatch, tmp_path):
    monkeypatch.setattr('seasonal.data.yf.Ticker', Mock(side_effect=RuntimeError('Provider down')))
    with pytest.raises(DataUnavailable):
        fetch_history('SPY', cache_dir=tmp_path)
