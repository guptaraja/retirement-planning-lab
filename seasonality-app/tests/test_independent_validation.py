"""Independent calendar and endpoint checks for the seasonality calculations."""
from statistics import fmean, median

import numpy as np
import pandas as pd
import pytest

from seasonal.analytics import analyze, monthly_returns


@pytest.mark.parametrize('seed', range(12))
@pytest.mark.parametrize('basis', ['price', 'adjusted'])
def test_daily_to_monthly_against_independent_calendar_reference(seed, basis):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range('2018-12-03', '2025-10-24')
    close = 100*np.exp(np.cumsum(rng.normal(.0002, .012, len(dates))))
    daily = pd.DataFrame({'Close': close, 'Adj Close': close*np.linspace(.85, 1, len(dates))}, index=dates)
    daily = daily[~((daily.index.year == 2021) & (daily.index.month == seed+1))]
    closes = {}
    for day, price in daily['Close' if basis == 'price' else 'Adj Close'].items():
        closes[(day.year, day.month)] = float(price)
    reference = {}
    for (year, month), price in closes.items():
        previous = (year-1, 12) if month == 1 else (year, month-1)
        reference[(year, month)] = price/closes[previous]-1 if previous in closes else np.nan
    actual = analyze(daily, 2019, 2025, basis, as_of='2025-10-24')
    for period, value in actual.monthly.items():
        expected = reference.get((period.year, period.month), np.nan)
        if np.isnan(expected):
            assert pd.isna(value)
        else:
            assert value == pytest.approx(expected, abs=1e-12)
    for month in range(1, 13):
        values = [value for (year, m), value in reference.items()
                  if 2019 <= year <= 2025 and m == month
                  and (year, m) < (2025, 10) and not np.isnan(value)]
        stats = actual.statistics.loc[month]
        assert stats['Count'] == len(values)
        assert stats['Average'] == pytest.approx(fmean(values), abs=1e-12)
        assert stats['Median'] == pytest.approx(median(values), abs=1e-12)
        assert stats['Win rate'] == pytest.approx(sum(v > 0 for v in values)/len(values))
    for year, value in actual.annual.items():
        full = all((year, m) in closes and not np.isnan(reference[(year, m)]) for m in range(1, 13))
        if year < 2025 and full:
            assert value == pytest.approx(closes[(year, 12)]/closes[(year-1, 12)]-1, abs=1e-12)
        elif year < 2025:
            assert pd.isna(value)


def test_no_double_adjustment_of_split_adjusted_close():
    daily = pd.DataFrame({'Close': [100., 102., 103.], 'Adj Close': [98., 101., 103.],
                          'Stock Splits': [0., 4., 0.]},
                         index=pd.to_datetime(['2020-07-31', '2020-08-31', '2020-09-30']))
    assert monthly_returns(daily, 'price').loc['2020-08'] == pytest.approx(.02)
    assert monthly_returns(daily, 'adjusted').loc['2020-08'] == pytest.approx(101/98-1)


def test_flat_prices_and_zero_win_rate():
    daily = pd.DataFrame({'Close': 100., 'Adj Close': 100.},
                         index=pd.date_range('2022-12-31', '2025-12-31', freq='M'))
    result = analyze(daily, 2023, 2025, as_of='2026-01-03')
    assert result.statistics['Average'].eq(0).all()
    assert result.statistics['Median'].eq(0).all()
    assert result.statistics['Count'].eq(3).all()
    assert result.statistics['Flat'].eq(3).all()
    assert result.statistics['Win rate'].eq(0).all()
    assert result.annual_statistics['Count'] == 3
    assert result.annual.eq(0).all()


def test_future_months_do_not_enter_statistics():
    daily = pd.DataFrame({'Close': [100., 110., 121., 133.1]},
                         index=pd.to_datetime(['2024-12-31', '2025-01-31', '2025-02-28', '2025-03-31']))
    result = analyze(daily, 2025, 2025, as_of='2025-02-15')
    assert pd.isna(result.history.loc[2025, 3])
    assert result.statistics.loc[2, 'Count'] == 0
    assert result.statistics.loc[3, 'Count'] == 0


def test_timezone_leap_month_and_duplicate_dates():
    dates = pd.to_datetime(['2024-03-28', '2024-02-29', '2024-01-31', '2024-02-29']).tz_localize('America/New_York')
    daily = pd.DataFrame({'Close': [121., 109., 100., 110.]}, index=dates)
    result = monthly_returns(daily)
    assert result.loc['2024-02'] == pytest.approx(.1)
    assert result.loc['2024-03'] == pytest.approx(.1)


def test_current_january_ytd_does_not_enter_completed_month_statistics():
    daily = pd.DataFrame({'Close': [100., 105.]}, index=pd.to_datetime(['2024-12-31', '2025-01-15']))
    result = analyze(daily, 2025, 2025, as_of='2025-01-15')
    assert result.statistics['Count'].sum() == 0
    assert result.annual.loc[2025] == pytest.approx(.05)
    assert result.annual_statistics['Count'] == 0


def test_missing_adjusted_prices_fail_clearly():
    daily = pd.DataFrame({'Close': [100., 101.]}, index=pd.to_datetime(['2024-12-31', '2025-01-31']))
    with pytest.raises(ValueError, match='Adj Close is unavailable'):
        monthly_returns(daily, 'adjusted')


def test_reversed_years_are_rejected():
    with pytest.raises(ValueError, match='Start year'):
        analyze(pd.DataFrame(), 2025, 2024)
