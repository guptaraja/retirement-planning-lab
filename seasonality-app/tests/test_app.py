from datetime import datetime, timezone

import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest
import streamlit as st

from seasonal.data import DataUnavailable, PriceData


def test_app_interactions_and_exports(monkeypatch):
    st.cache_data.clear()
    index = pd.date_range('2018-12-31', periods=85, freq='M')
    prices = 100*np.cumprod(1+.015*np.sin(np.arange(len(index)))+.005)
    data = PriceData(pd.DataFrame({'Close': prices, 'Adj Close': prices*1.01}, index=index),
                     datetime.now(timezone.utc), 'Test security', 'USD', 'Server Parquet cache')
    monkeypatch.setattr('seasonal.data.fetch_history', lambda *a, **kw: data)
    app = AppTest.from_file('app.py', default_timeout=20).run()
    assert not app.exception
    assert app.subheader[0].value == 'Historical seasonality'
    app.radio[0].set_value('Median').run()
    assert not app.exception
    app.selectbox[0].set_value('Dividend-adjusted').run()
    assert not app.exception
    app.button[0].click().run()
    assert not app.exception
    assert app.slider[0].value[1]-app.slider[0].value[0] == 2
    app.checkbox[0].check().run()
    assert not app.exception
    assert len(app.get('download_button')) == 2


def test_invalid_ticker_has_clear_error(monkeypatch):
    st.cache_data.clear()
    app = AppTest.from_file('app.py', default_timeout=20)
    app.query_params['ticker'] = 'SPY'
    monkeypatch.setattr('seasonal.data.fetch_history', lambda *a, **kw: (_ for _ in ()).throw(DataUnavailable('Temporarily unavailable')))
    app.run()
    assert not app.exception
    app.text_input[0].set_value('../secret').run()
    assert not app.exception
    assert 'Enter a Yahoo symbol' in app.error[0].value
