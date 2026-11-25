"""Pure return calculations; all returns are stored as decimal fractions."""
from dataclasses import dataclass

import numpy as np
import pandas as pd

MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


@dataclass
class Analysis:
    monthly: pd.Series
    history: pd.DataFrame
    statistics: pd.DataFrame
    annual: pd.Series
    annual_statistics: pd.Series
    annual_labels: dict
    current_month: pd.Period


def monthly_returns(daily: pd.DataFrame, basis: str = 'price') -> pd.Series:
    """Month-end close to prior month-end close, without filling missing months."""
    column = 'Close' if basis == 'price' else 'Adj Close'
    if column not in daily:
        raise ValueError(f'{column} is unavailable for this security.')
    series = daily[column].copy()
    series.index = pd.DatetimeIndex(series.index).tz_localize(None)
    series = pd.to_numeric(series, errors='coerce').where(lambda x: x > 0)
    series = series.sort_index()
    series = series[~series.index.duplicated(keep='last')]
    if series.dropna().empty:
        raise ValueError('No usable closing prices were returned.')
    last = series.groupby(series.index.to_period('M')).last()
    last = last.reindex(pd.period_range(last.index.min(), last.index.max(), freq='M'))
    returns = last.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan)
    returns.name = 'Return'
    return returns


def describe(series: pd.Series) -> pd.Series:
    values = series.dropna()
    return pd.Series({
        'Count': len(values), 'Up': int((values > 0).sum()),
        'Down': int((values < 0).sum()), 'Flat': int((values == 0).sum()),
        'Win rate': float((values > 0).mean()) if len(values) else np.nan,
        'Average': values.mean(), 'Median': values.median(),
    })


def analyze(daily: pd.DataFrame, start: int, end: int, basis: str = 'price',
            include_mtd: bool = False, as_of=None) -> Analysis:
    if start > end:
        raise ValueError('Start year must be on or before end year.')
    today = pd.Timestamp(as_of) if as_of is not None else pd.Timestamp.now(tz='America/New_York')
    current = pd.Period(year=today.year, month=today.month, freq='M')
    monthly = monthly_returns(daily, basis)
    monthly = monthly[(monthly.index.year >= start) & (monthly.index.year <= end)
                      & (monthly.index <= current)]
    history = pd.DataFrame(np.nan, index=range(start, end + 1), columns=range(1, 13))
    for period, value in monthly.items():
        history.loc[period.year, period.month] = value
    eligible = monthly if include_mtd else monthly[monthly.index < current]
    statistics = pd.DataFrame({m: describe(eligible[eligible.index.month == m]) for m in range(1, 13)}).T
    annual = pd.Series(np.nan, index=history.index, name='Year')
    complete = []
    labels = {}
    for year, row in history.iterrows():
        if year < current.year and row.notna().all():
            annual.loc[year] = (1 + row).prod() - 1
            complete.append(annual.loc[year])
            labels[year] = 'Full year'
        elif year == current.year:
            available = row.iloc[:current.month]
            # A partial listing year or a hole in history is not a valid YTD return.
            last = available.last_valid_index()
            if last is not None and available.loc[:last].notna().all():
                annual.loc[year] = (1 + available.loc[:last]).prod() - 1
                labels[year] = 'YTD'
            else:
                labels[year] = 'Incomplete'
        else:
            labels[year] = 'Incomplete'
    return Analysis(monthly, history, statistics, annual,
                    describe(pd.Series(complete, dtype=float)), labels, current)
