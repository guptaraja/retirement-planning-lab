"""Plotly figures and escaped, accessible HTML return tables."""
from html import escape

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from .analytics import MONTHS

UP = '#0ba58b'
DOWN = '#e23857'


def percent(value, digits=2):
    return '—' if pd.isna(value) else f'{value:+.{digits}%}'


def seasonality_chart(analysis, metric='Average'):
    stats = analysis.statistics
    custom = np.column_stack([stats['Count'], stats['Up'], stats['Down'], stats['Win rate']])
    figure = go.Figure(go.Bar(x=MONTHS, y=stats[metric],
        marker_color=[UP if v >= 0 else DOWN for v in stats[metric]],
        text=[percent(v, 1) for v in stats[metric]], textposition='outside', cliponaxis=False,
        customdata=custom,
        hovertemplate='<b>%{x}</b><br>'+metric+': %{y:+.2%}<br>Observed years: %{customdata[0]:.0f}'
                      '<br>Up: %{customdata[1]:.0f} · Down: %{customdata[2]:.0f}'
                      '<br>Win rate: %{customdata[3]:.0%}<extra></extra>'))
    values = stats[metric].dropna()
    lo = min(0, values.min()) if len(values) else 0
    hi = max(0, values.max()) if len(values) else .01
    span = max(hi - lo, .01)
    figure.update_layout(height=325, margin=dict(l=10, r=62, t=28, b=32),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        bargap=.32, showlegend=False, font=dict(family='sans-serif', size=13),
        xaxis=dict(fixedrange=True, showgrid=False, zeroline=False),
        yaxis=dict(side='right', tickformat='+.1%', range=[lo-span*.22, hi+span*.25],
                   zeroline=True, zerolinewidth=1, gridcolor='rgba(128,128,128,.12)',
                   zerolinecolor='rgba(128,128,128,.3)', fixedrange=True),
        modebar=dict(bgcolor='rgba(0,0,0,0)'))
    return figure


def _value(value):
    color = 'positive' if value > 0 else 'negative' if value < 0 else 'neutral'
    return f'<span class="{color}">{percent(value)}</span>'


def history_table(analysis, metric, show_all=False):
    stats = analysis.statistics
    annual = analysis.annual_statistics
    head = '<thead><tr><th scope="col">Year / metric</th>'+''.join(f'<th scope="col">{m}</th>' for m in MONTHS)+'<th scope="col">Year</th></tr></thead>'
    body = ''
    for label in ['Up / Down', 'Win rate', 'Average', 'Median']:
        active = ' active-stat' if label == metric else ''
        body += f'<tr class="summary{active}"><th scope="row">{label}</th>'
        for column in list(range(1, 13))+['Year']:
            s = annual if column == 'Year' else stats.loc[column]
            title = 'Annual statistics use complete calendar years only.' if column == 'Year' else f'{int(s["Count"])} observed years; {int(s["Flat"])} flat.'
            if not s['Count']:
                text = '—'
            elif label == 'Up / Down':
                text = f'<span class="positive">↑{int(s["Up"])}</span> <span class="negative">↓{int(s["Down"])}</span>'
            elif label == 'Win rate':
                text = f'{s["Win rate"]:.0%}'
            else:
                text = _value(s[label])
            body += f'<td title="{escape(title)}">{text}</td>'
        body += '</tr>'
    years = list(reversed(analysis.history.index))
    for i, year in enumerate(years if show_all else years[:6]):
        label = analysis.annual_labels.get(year, 'Incomplete')
        suffix = ' <small>YTD</small>' if label == 'YTD' else ''
        body += f'<tr class="{"first-year" if i == 0 else ""}"><th scope="row">{year}{suffix}</th>'
        values = list(analysis.history.loc[year])+[analysis.annual.loc[year]]
        for m, value in enumerate(values, 1):
            partial = m <= 12 and pd.Period(year=year, month=m, freq='M') == analysis.current_month
            marker = '<sup>*</sup>' if partial and pd.notna(value) else ''
            text = percent(value)+marker
            if pd.isna(value):
                style = ''
            else:
                opacity = min(.65, .08+abs(value)*5)
                channel = '11,165,139' if value >= 0 else '226,56,87'
                style = f'background:rgba({channel},{opacity:.3f})'
            title = f'{MONTHS[m-1]} {year}' if m <= 12 else f'{year} {label}'
            if partial:
                title += ' month to date'
            body += f'<td style="{style}" title="{escape(title)}">{text}</td>'
        body += '</tr>'
    return '<div class="return-table"><table aria-label="Monthly returns and summary statistics">'+head+'<tbody>'+body+'</tbody></table></div>'
