import numpy as np
import pandas as pd
import pytest

from seasonal.analytics import analyze, describe, monthly_returns
from seasonal.presentation import history_table, seasonality_chart


def daily(dates, values):
    return pd.DataFrame({'Close': values, 'Adj Close': np.array(values)*1.01}, index=pd.to_datetime(dates))


def test_january_keeps_previous_december_before_year_filter():
    data = daily(['2023-12-29', '2024-01-31', '2024-02-29'], [100, 110, 99])
    result = analyze(data, 2024, 2024, as_of='2025-01-15')
    assert result.history.loc[2024, 1] == pytest.approx(.1)
    assert result.history.loc[2024, 2] == pytest.approx(-.1)


def test_missing_month_is_not_filled_and_not_bridged():
    result = monthly_returns(daily(['2024-01-31', '2024-03-28', '2024-04-30'], [100, 120, 132]))
    assert pd.isna(result.loc['2024-02'])
    assert pd.isna(result.loc['2024-03'])
    assert result.loc['2024-04'] == pytest.approx(.1)


def test_partial_listing_month_does_not_create_a_return_or_full_year():
    data = daily(['2024-05-16', '2024-05-31', '2024-06-28'], [10, 11, 12])
    result = analyze(data, 2024, 2024, as_of='2025-01-02')
    assert pd.isna(result.history.loc[2024, 5])
    assert result.history.loc[2024, 6] == pytest.approx(12/11-1)
    assert pd.isna(result.annual.loc[2024])
    assert result.annual_statistics['Count'] == 0


def test_current_month_mtd_displayed_but_excluded_unless_selected():
    data = daily(['2024-10-31', '2024-11-29', '2024-12-31', '2025-01-31', '2025-11-20'], [100, 110, 120, 130, 140])
    # Include October 2025 as a valid current-month baseline.
    data.loc[pd.Timestamp('2025-10-31')] = [130, 131.3]
    result = analyze(data, 2024, 2025, as_of='2025-11-24')
    included = analyze(data, 2024, 2025, include_mtd=True, as_of='2025-11-24')
    assert result.statistics.loc[11, 'Count'] == 1
    assert included.statistics.loc[11, 'Count'] == 2
    assert pd.notna(result.history.loc[2025, 11])
    assert pd.isna(result.history.loc[2025, 12])


def test_annual_is_compounded_not_summed_and_ytd_is_excluded():
    dates = pd.date_range('2022-12-31', '2024-02-29', freq='M')
    data = daily(dates, 100*1.01**np.arange(len(dates)))
    result = analyze(data, 2023, 2024, as_of='2024-02-29')
    assert result.annual.loc[2023] == pytest.approx(1.01**12-1)
    assert result.annual.loc[2024] == pytest.approx(1.01**2-1)
    assert result.annual_statistics['Count'] == 1
    assert result.annual_labels[2024] == 'YTD'


def test_ytd_unavailable_for_current_year_listing():
    data = daily(['2025-03-14', '2025-03-31', '2025-04-30'], [10, 11, 12])
    result = analyze(data, 2025, 2025, as_of='2025-05-01')
    assert pd.isna(result.annual.loc[2025])
    assert result.annual_labels[2025] == 'Incomplete'


def test_zero_counts_in_win_denominator_but_not_up_or_down():
    stats = describe(pd.Series([.1, -.1, 0, np.nan]))
    assert stats['Count'] == 3
    assert stats['Up'] == stats['Down'] == stats['Flat'] == 1
    assert stats['Win rate'] == pytest.approx(1/3)


def test_adjusted_basis_is_explicit():
    data = daily(['2023-12-29', '2024-01-31'], [100, 100])
    data['Adj Close'] = [98, 100]
    assert monthly_returns(data, 'price').loc['2024-01'] == 0
    assert monthly_returns(data, 'adjusted').loc['2024-01'] == pytest.approx(100/98-1)


def test_chart_and_table_come_from_same_statistics():
    data = daily(pd.date_range('2023-12-31', periods=14, freq='M'), 100*1.01**np.arange(14))
    result = analyze(data, 2024, 2025, as_of='2025-02-01')
    chart = seasonality_chart(result)
    assert list(chart.data[0].y) == list(result.statistics['Average'])
    table = history_table(result, 'Average')
    assert 'Monthly returns and summary statistics' in table
    assert '+12.68%' in table
