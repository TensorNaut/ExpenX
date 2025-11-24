"""
Rewritten visualizer for ExpenX
- Single long-scroll Streamlit dashboard
- Modularized sections: Overview, Expense Deep Dive, Behavior Insights, Investments, Income & Ledger
- Uses existing project helpers (tracker, finance, investments)
- Designed for easy replacement of app/visualizer.py

Notes:
- This file intentionally follows the project's pattern (matplotlib, pandas, streamlit)
- Keep functions small and testable
- Caching applied to expensive operations
"""
from datetime import datetime
from typing import Optional, Tuple

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import streamlit as st

# Project imports (these must exist in your repo)
from app.tracker import get_expenses, get_category_options
from app.finance import get_accounts
from app.investments import list_investments, portfolio_summary

# -- UI / layout constants
DEFAULT_LOOKBACK_MONTHS = 12

# -------------------------
# Data loading / helpers
# -------------------------
@st.cache_data(ttl=300)
def load_expenses_df(limit: int = 5000) -> pd.DataFrame:
    df = get_expenses(limit=limit)
    if df is None or df.empty:
        cols = ['id','Date','Amount','Description','Category','source','payment_source','account_id','ocr_confidence','created_at']
        return pd.DataFrame(columns=cols)
    df = df.copy()
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
    df['Amount'] = pd.to_numeric(df['Amount'], errors='coerce').fillna(0.0)
    df['Category'] = df['Category'].fillna('Uncategorized')
    if 'created_at' in df.columns:
        df['created_at'] = pd.to_datetime(df['created_at'], errors='coerce')
    else:
        df['created_at'] = pd.NaT
    return df

@st.cache_data(ttl=300)
def load_accounts():
    return get_accounts()

@st.cache_data(ttl=300)
def load_investments():
    inv = list_investments(status=None, include_zero_remaining=True)
    if not inv:
        return pd.DataFrame()
    return pd.DataFrame(inv)

# -------------------------
# Small analytics helpers
# -------------------------

def period_aggregation(df: pd.DataFrame, period: str = 'M') -> pd.DataFrame:
    """Aggregate total spend by period date index. period: 'D','W','M' etc."""
    if df.empty:
        return pd.DataFrame()
    tmp = df.set_index('Date').sort_index()
    agg = tmp['Amount'].resample(period).sum().rename('total_spend')
    return agg.to_frame()


def category_breakdown(df: pd.DataFrame, start: Optional[pd.Timestamp] = None, end: Optional[pd.Timestamp] = None) -> pd.Series:
    if df.empty:
        return pd.Series(dtype=float)
    sub = df
    if start is not None:
        sub = sub[sub['Date'] >= start]
    if end is not None:
        sub = sub[sub['Date'] <= end + pd.Timedelta(days=1)]
    out = sub.groupby('Category')['Amount'].sum().sort_values(ascending=False)
    return out


def daily_spikes(df: pd.DataFrame, start: Optional[pd.Timestamp]=None, end: Optional[pd.Timestamp]=None) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    sub = df.copy()
    if start is not None:
        sub = sub[sub['Date'] >= start]
    if end is not None:
        sub = sub[sub['Date'] <= end + pd.Timedelta(days=1)]
    daily = sub.set_index('Date').resample('D')['Amount'].sum().rename('daily_spend').to_frame()
    daily['day'] = daily.index
    return daily


def spending_heatmap(df: pd.DataFrame) -> pd.DataFrame:
    """Return pivot table day_of_week x hour -> total spend"""
    if df.empty:
        return pd.DataFrame()
    dd = df.copy()
    # prefer created_at for hour, fallback to Date (midnight)
    if 'created_at' in dd.columns and dd['created_at'].notna().any():
        dd['hour'] = dd['created_at'].dt.hour.fillna(0).astype(int)
    else:
        dd['hour'] = 0
    dd['dow'] = dd['Date'].dt.day_name()
    pivot = dd.pivot_table(index='dow', columns='hour', values='Amount', aggfunc='sum', fill_value=0.0)
    # reorder days
    days_order = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
    reindex = [d for d in days_order if d in pivot.index]
    if reindex:
        pivot = pivot.reindex(reindex)
    return pivot


def detect_recurring(df: pd.DataFrame, min_occurrences: int = 3) -> pd.DataFrame:
    """Simple recurring detection by grouping on normalized description + approx amount"""
    if df.empty:
        return pd.DataFrame()
    tmp = df.copy()
    tmp['desc_norm'] = tmp['Description'].str.lower().str.replace('[^a-z0-9 ]','',regex=True).str.strip()
    tmp['amt_round'] = tmp['Amount'].round(-1)  # coarse rounding
    grp = tmp.groupby(['desc_norm','amt_round'])
    rec = grp.agg(count=('id','count'), avg_amount=('Amount','mean'), last_date=('Date','max')).reset_index()
    rec = rec[rec['count'] >= min_occurrences].sort_values(by='count', ascending=False)
    return rec


def detect_anomalies(df: pd.DataFrame, z_thresh: float = 2.5) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    by_cat = df.groupby('Category')['Amount']
    df2 = df.copy()
    df2['zscore'] = df2.groupby('Category')['Amount'].transform(lambda x: (x - x.mean()) / (x.std(ddof=0) + 1e-9))
    out = df2[np.abs(df2['zscore']) >= z_thresh].sort_values(by='zscore', ascending=False)
    return out

# -------------------------
# Plot helpers (matplotlib)
# -------------------------

def plot_line(x, y, title='', xlabel='', ylabel='', annotate_pct=False, figsize=(8,3.5)):
    fig, ax = plt.subplots(figsize=figsize)
    ax.plot(x, y, marker='o', linewidth=2)
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.grid(alpha=0.25)
    if annotate_pct and len(y) >= 2:
        try:
            pct = (y[-1] - y[-2]) / (abs(y[-2]) + 1e-9) * 100.0
            ax.annotate(f'{pct:.1f}% vs prev', xy=(x[-1], y[-1]), xytext=(-80, 10), textcoords='offset points',
                        bbox=dict(boxstyle='round,pad=0.3', alpha=0.9))
        except Exception:
            pass
    return fig


def plot_pie(series: pd.Series, title='', figsize=(6,4)):
    fig, ax = plt.subplots(figsize=figsize)
    if series.sum() <= 0:
        ax.text(0.5, 0.5, 'No data', ha='center', va='center')
        ax.set_title(title)
        return fig
    labels = series.index.tolist()
    sizes = series.values
    ax.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=90)
    ax.axis('equal')
    ax.set_title(title)
    return fig


def plot_bar(df: pd.Series, title='', xlabel='', ylabel='', horizontal=True, figsize=(8,4)):
    fig, ax = plt.subplots(figsize=figsize)
    if horizontal:
        df.plot(kind='barh', ax=ax)
    else:
        df.plot(kind='bar', ax=ax)
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.grid(axis='x', alpha=0.2)
    return fig

# -------------------------
# Dashboard renderers (single long scroll)
# -------------------------

def render_overview(df: pd.DataFrame):
    st.header("📊 Financial Overview")
    today = pd.Timestamp.now().normalize()
    month_start = today.replace(day=1)
    period_months = DEFAULT_LOOKBACK_MONTHS

    # Quick metrics
    sub_month = df[(df['Date'] >= month_start) & (df['Date'] <= today + pd.Timedelta(days=1))]
    total_spent = float(sub_month['Amount'].sum()) if not sub_month.empty else 0.0
    avg_tx = float(sub_month['Amount'].mean()) if not sub_month.empty else 0.0
    num_tx = len(sub_month)
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Spent (this month)", f"₹{total_spent:.2f}")
    c2.metric("Avg per transaction", f"₹{avg_tx:.2f}")
    c3.metric("Transactions (this month)", f"{num_tx}")

    st.markdown("---")

    # Net flow gauge (income vs expense) - approximate using expenses only for now
    st.subheader("Net Flow — Month")
    # We'll approximate income as portfolio/income not available — show expense gauge only
    # Provide a gauge-like donut: spent vs budget (if budget exists; else show spent proportion)
    # For now show donut of spent vs remaining assuming a naive monthly budget (median of past 3 months * 1.1)
    this_period = df[(df['Date'] >= (today - pd.DateOffset(months=1))) & (df['Date'] <= today + pd.Timedelta(days=1))]
    median_recent = df.set_index('Date').resample('M')['Amount'].sum().tail(3).median() if not df.empty else 0.0
    budget = float(median_recent * 1.1) if median_recent and median_recent > 0 else max(5000.0, total_spent * 2)
    spent = float(this_period['Amount'].sum()) if not this_period.empty else 0.0
    remaining = max(0.0, budget - spent)
    donut_series = pd.Series([spent, remaining], index=[f"Spent (₹{spent:.0f})", f"Remaining (₹{remaining:.0f})"])
    fig_d = plot_pie(donut_series, title=f"Monthly budget (approx ₹{budget:.0f})")
    st.pyplot(fig_d)
    plt.close(fig_d)

    st.markdown("---")

    # Income vs Expense trend (last N months) — here we only have expenses; show expense trend and account balances
    st.subheader("Monthly Trend — Expenses (last 12 months)")
    agg = period_aggregation(df, period='M')
    if agg.empty:
        st.info("No expense data yet.")
    else:
        x = agg.index.to_pydatetime()
        y = agg['total_spend'].values
        fig = plot_line(x, y, title="Monthly Expenses", xlabel='Month', ylabel='Amount (₹)', annotate_pct=True)
        st.pyplot(fig)
        plt.close(fig)

    # Account distribution
    st.subheader("Account Distribution")
    accounts = load_accounts()
    if not accounts:
        st.info("No accounts configured.")
    else:
        acct_series = pd.Series({a['name']: float(a.get('balance', 0.0)) for a in accounts})
        fig_a = plot_pie(acct_series, title='Where your money is')
        st.pyplot(fig_a)
        plt.close(fig_a)

    # Investments trend
    st.subheader("Investment Portfolio (summary)")
    inv_df = load_investments()
    if inv_df.empty:
        st.info("No investments recorded.")
    else:
        ps = portfolio_summary()
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Invested", f"₹{ps['total_principal']:.2f}")
        c2.metric("Principal Remaining", f"₹{ps['total_remaining']:.2f}")
        c3.metric("Current Value (est)", f"₹{ps['current_value']:.2f}")

    st.markdown("---")


def render_expense_deep_dive(df: pd.DataFrame):
    st.header("🔎 Expense Deep Dive")
    today = pd.Timestamp.now().normalize()
    default_start = (today - pd.DateOffset(months=3)).date() if not df.empty else today.date()

    start_dt, end_dt = st.date_input("Date range", value=(default_start, today.date()))
    start_ts = pd.Timestamp(start_dt)
    end_ts = pd.Timestamp(end_dt)

    sub = df[(df['Date'] >= start_ts) & (df['Date'] <= end_ts + pd.Timedelta(days=1))]
    if sub.empty:
        st.info("No data for selected range.")
        return

    # Category breakdown (treemap alternative: pie/top table)
    st.subheader("Category breakdown")
    cat = category_breakdown(sub, start_ts, end_ts)
    top_n = st.select_slider("Top N categories (pie)", options=[3,4,5,6,7,8,9,10], value=6)
    top = cat.head(top_n)
    others = cat.iloc[top_n:].sum()
    if others > 0:
        combined = pd.concat([top, pd.Series({'Other': others})])
    else:
        combined = top
    fig_p = plot_pie(combined, title=f"Category share ({start_ts.date()} → {end_ts.date()})")
    st.pyplot(fig_p)
    plt.close(fig_p)

    st.markdown("Category totals: ")
    st.dataframe(cat.reset_index().rename(columns={'index':'Category','Amount':'Total'}).head(50))

    st.markdown("---")

    # Top categories bar
    st.subheader("Top categories")
    top_k = cat.head(10)
    fig_b = plot_bar(top_k, title='Top spending categories', horizontal=True)
    st.pyplot(fig_b)
    plt.close(fig_b)

    st.markdown("---")

    # Daily expense spikes
    st.subheader("Daily spend timeline")
    daily = daily_spikes(sub)
    if daily.empty:
        st.info("No daily data.")
    else:
        fig, ax = plt.subplots(figsize=(10,3))
        ax.bar(daily.index, daily['daily_spend'])
        ax.set_title('Daily spend')
        ax.set_ylabel('Amount (₹)')
        ax.grid(alpha=0.2)
        st.pyplot(fig)
        plt.close(fig)

    st.markdown("---")

    # Category trend over time (stacked)
    st.subheader("Category trend over time")
    df2 = sub.copy()
    df2['month'] = df2['Date'].dt.to_period('M').dt.to_timestamp()
    cat_totals = df2.groupby('Category')['Amount'].sum().sort_values(ascending=False)
    top_cats = cat_totals.index[:6].tolist()
    df2['CategoryAgg'] = df2['Category'].apply(lambda x: x if x in top_cats else 'Other')
    pivot = df2.pivot_table(index='month', columns='CategoryAgg', values='Amount', aggfunc='sum', fill_value=0.0)
    if pivot.empty:
        st.info('No category trend data.')
    else:
        fig_s, ax_s = plt.subplots(figsize=(10,4))
        pivot.plot(kind='area', stacked=True, ax=ax_s)
        ax_s.set_title('Monthly spend by category')
        ax_s.set_ylabel('Amount (₹)')
        st.pyplot(fig_s)
        plt.close(fig_s)

    st.markdown('---')


def render_behavior_insights(df: pd.DataFrame):
    st.header('🧭 Behavior Insights')
    if df.empty:
        st.info('No expenses recorded yet.')
        return

    st.subheader('Burn rate projection')
    # cumulative daily spend vs linear projection
    daily = daily_spikes(df)
    if daily.empty:
        st.info('Not enough daily data for projection.')
    else:
        daily['cum'] = daily['daily_spend'].cumsum()
        days = np.arange(len(daily))
        # linear fit
        coef = np.polyfit(days, daily['cum'].values, 1)
        proj = coef[0] * days + coef[1]
        fig, ax = plt.subplots(figsize=(10,3))
        ax.plot(daily.index, daily['cum'], marker='o', label='Actual')
        ax.plot(daily.index, proj, linestyle='--', label='Projection')
        ax.set_title('Cumulative spend & projection')
        ax.set_ylabel('Cumulative spend (₹)')
        ax.legend()
        st.pyplot(fig)
        plt.close(fig)

    st.markdown('---')

    st.subheader('Spending heatmap (day of week × hour)')
    hm = spending_heatmap(df)
    if hm.empty:
        st.info('No hourly data available (created_at not present).')
    else:
        fig, ax = plt.subplots(figsize=(12,4))
        im = ax.imshow(hm.fillna(0.0).values, aspect='auto')
        ax.set_yticks(range(len(hm.index)))
        ax.set_yticklabels(hm.index)
        ax.set_xlabel('Hour of day')
        ax.set_title('Spending heatmap')
        fig.colorbar(im, ax=ax)
        st.pyplot(fig)
        plt.close(fig)

    st.markdown('---')

    st.subheader('Recurring payments (auto-detected)')
    rec = detect_recurring(df)
    if rec.empty:
        st.info('No recurring payments detected (try expanding date range).')
    else:
        st.dataframe(rec.head(50))

    st.markdown('---')

    st.subheader('Anomalies (outlier transactions)')
    anom = detect_anomalies(df)
    if anom.empty:
        st.info('No anomalies detected.')
    else:
        st.dataframe(anom[['Date','Amount','Description','Category','zscore']].sort_values(by='zscore', ascending=False).head(50))

    st.markdown('---')


def render_investments():
    st.header('📈 Investments')
    inv_df = load_investments()
    if inv_df.empty:
        st.info('No investments recorded.')
        return

    ps = portfolio_summary()
    c1, c2, c3 = st.columns(3)
    c1.metric('Total Invested', f"₹{ps['total_principal']:.2f}")
    c2.metric('Principal Remaining', f"₹{ps['total_remaining']:.2f}")
    c3.metric('Current Value (est)', f"₹{ps['current_value']:.2f}")

    st.markdown('---')

    # Distribution by type
    by_type = inv_df.groupby('type')['amount'].sum().sort_values(ascending=False)
    if not by_type.empty:
        fig = plot_pie(by_type.head(10), title='Investment by type')
        st.pyplot(fig)
        plt.close(fig)

    st.markdown('Investment table')
    st.dataframe(inv_df[['id','date','type','risk','amount','status']].sort_values(by='date', ascending=False), use_container_width=True)

    st.markdown('---')


def render_income_and_ledger(df: pd.DataFrame):
    st.header('💼 Income & Ledger')
    st.info('Income visualizations will be added — income table is needed. For now ledger highlights are shown in main app.')
    st.markdown('---')

# -------------------------
# Main show_dashboard
# -------------------------

def show_dashboard():
    st.header('📊 ExpenX Analytics & Dashboard (Optimized)')
    df = load_expenses_df()

    # Sidebar filters (global)
    st.sidebar.markdown('### Filters')
    # Date range global (optional)
    if df.empty:
        default_start = pd.Timestamp.now() - pd.DateOffset(months=3)
    else:
        default_start = df['Date'].min().normalize()
    default_end = pd.Timestamp.now().normalize()

    date_range = st.sidebar.date_input('Date range (global)', value=(default_start.date(), default_end.date()))
    start_dt = pd.Timestamp(date_range[0])
    end_dt = pd.Timestamp(date_range[1])

    # Navigation anchors (long scroll)
    st.sidebar.markdown('### Sections')
    if st.sidebar.button('Overview'):
        st.experimental_set_query_params(section='overview')
    if st.sidebar.button('Expense Deep Dive'):
        st.experimental_set_query_params(section='deep_dive')
    if st.sidebar.button('Behavior Insights'):
        st.experimental_set_query_params(section='behavior')
    if st.sidebar.button('Investments'):
        st.experimental_set_query_params(section='investments')
    if st.sidebar.button('Income & Ledger'):
        st.experimental_set_query_params(section='income')

    st.markdown('---')

    # Render sections — long scroll style (order important)
    render_overview(df)
    st.markdown('\n')
    render_expense_deep_dive(df)
    st.markdown('\n')
    render_behavior_insights(df)
    st.markdown('\n')
    render_investments()
    st.markdown('\n')
    render_income_and_ledger(df)


# Quick preview when executed directly
if __name__ == '__main__':
    st.set_page_config(page_title='ExpenX Visualizer (optimized)', layout='wide')
    show_dashboard()
