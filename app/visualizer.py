"""
This module provides all data functions needed for the professional dashboard layout.

- Data loaders: load_expenses_df, load_income_df, load_accounts_df, load_investments_df, load_budgets_df
- Period utilities: get_month_range, get_year_range, etc.
- Period-restricted analytics: net_flow, category_breakdown, top_categories, daily_spend, income_source_split
- Trend-only analytics: expense_trend, income_trend, category_trend_area, portfolio_trend
- Behavior: spending_heatmap_matrix, detect_recurring, detect_anomalies
- Investments: investment_summary, investment_gain_loss, investment_distribution
- Budget engine + insights: compute_budget_status, generate_budget_insights
- Ledger helpers: ledger_activity
- Unified aggregator: get_dashboard_data(period_mode, reference_date, range_start, range_end, trend_months)

All functions return plain Python structures (DataFrames / dicts / lists) so UI can render them.
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
import pandas as pd
import numpy as np

from app.tracker import get_expenses
from app.finance import get_income, get_accounts, get_budgets
from app.investments import list_investments

# --------------------------------------------------
# 1. PERIOD UTILITIES
# --------------------------------------------------

def get_month_range(ref: datetime) -> Tuple[datetime, datetime]:
    start = ref.replace(day=1)
    if start.month == 12:
        nxt = start.replace(year=start.year + 1, month=1)
    else:
        nxt = start.replace(month=start.month + 1)
    end = nxt - timedelta(days=1)
    return start, end


def get_year_range(year: int) -> Tuple[datetime, datetime]:
    return datetime(year, 1, 1), datetime(year, 12, 31)


def clamp_to_date(d):
    return pd.Timestamp(d).normalize()

# --------------------------------------------------
# 2. DATA LOADERS
# --------------------------------------------------

def load_expenses_df(limit: int = 5000) -> pd.DataFrame:
    rows = get_expenses(limit=limit)
    if rows is None or isinstance(rows, list) and len(rows) == 0:
        return pd.DataFrame(columns=['id','Date','Amount','Description','Category','payment_source','account_id','created_at'])

    # If rows is already a DataFrame
    if isinstance(rows, pd.DataFrame):
        df = rows.copy()
    else:
        df = pd.DataFrame(rows)

    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
    df['Amount'] = pd.to_numeric(df['Amount'], errors='coerce').fillna(0.0)
    df['Category'] = df.get('Category', df.get('category', pd.Series())).fillna('Uncategorized')

    if 'created_at' in df.columns:
        df['created_at'] = pd.to_datetime(df['created_at'], errors='coerce')
    else:
        df['created_at'] = pd.NaT

    return df



def load_income_df(limit: int = 5000) -> pd.DataFrame:
    rows = get_income(limit=limit)
    if not rows:
        return pd.DataFrame(columns=['id','date','amount','source','description','created_at'])
    df = pd.DataFrame(rows)
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    df['amount'] = pd.to_numeric(df['amount'], errors='coerce').fillna(0.0)
    if 'created_at' in df.columns:
        df['created_at'] = pd.to_datetime(df['created_at'], errors='coerce')
    else:
        df['created_at'] = pd.NaT
    return df


def load_accounts_df() -> pd.DataFrame:
    rows = get_accounts()
    if not rows:
        return pd.DataFrame(columns=['id','name','balance','currency','kind'])
    return pd.DataFrame(rows)


def load_investments_df() -> pd.DataFrame:
    rows = list_investments(status=None, include_zero_remaining=True)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    # normalize certain columns
    for col in ['amount','principal_remaining','current_value','quantity']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
    return df


def load_budgets_df() -> pd.DataFrame:
    rows = get_budgets()
    if not rows:
        return pd.DataFrame(columns=['id','category','amount','period','active','created_at'])
    df = pd.DataFrame(rows)
    if 'created_at' in df.columns:
        df['created_at'] = pd.to_datetime(df['created_at'], errors='coerce')
    return df

# --------------------------------------------------
# 3. PERIOD-RESTRICTED ANALYTICS (for single month/year/range)
# --------------------------------------------------

def filter_expenses(df: pd.DataFrame, start: datetime, end: datetime) -> pd.DataFrame:
    if df.empty:
        return df
    s = clamp_to_date(start)
    e = clamp_to_date(end)
    return df[(df['Date'] >= s) & (df['Date'] <= e + timedelta(days=1))].copy()


def filter_income(df: pd.DataFrame, start: datetime, end: datetime) -> pd.DataFrame:
    if df.empty:
        return df
    s = clamp_to_date(start)
    e = clamp_to_date(end)
    return df[(df['date'] >= s) & (df['date'] <= e + timedelta(days=1))].copy()


def net_flow(exp_df: pd.DataFrame, inc_df: pd.DataFrame) -> Dict[str, float]:
    spent = float(exp_df['Amount'].sum()) if not exp_df.empty else 0.0
    inc = float(inc_df['amount'].sum()) if not inc_df.empty else 0.0
    return {'income': inc, 'expense': spent, 'net': inc - spent}


def category_breakdown(exp_df: pd.DataFrame) -> pd.Series:
    if exp_df.empty:
        return pd.Series(dtype=float)
    return exp_df.groupby('Category')['Amount'].sum().sort_values(ascending=False)


def top_categories(exp_df: pd.DataFrame, top_n: int = 10) -> pd.Series:
    return category_breakdown(exp_df).head(top_n)


def daily_spend(exp_df: pd.DataFrame) -> pd.DataFrame:
    if exp_df.empty:
        return pd.DataFrame(columns=['Date','daily_spend'])
    s = exp_df.set_index('Date')['Amount'].resample('D').sum().rename('daily_spend')
    df = s.to_frame().reset_index()
    return df


def income_source_split(inc_df: pd.DataFrame) -> pd.Series:
    if inc_df.empty:
        return pd.Series(dtype=float)
    return inc_df.groupby('source')['amount'].sum().sort_values(ascending=False)

# --------------------------------------------------
# 4. TREND-ONLY ANALYTICS (multi-month)
# --------------------------------------------------

def expense_trend(exp_df: pd.DataFrame, months: int = 12) -> pd.DataFrame:
    if exp_df.empty:
        return pd.DataFrame()
    end = pd.Timestamp.now().normalize()
    start = end - pd.DateOffset(months=months)
    sub = exp_df[(exp_df['Date'] >= start) & (exp_df['Date'] <= end)].copy()
    s = sub.set_index('Date')['Amount'].resample('M').sum().rename('total')
    return s.to_frame()


def income_trend(inc_df: pd.DataFrame, months: int = 12) -> pd.DataFrame:
    if inc_df.empty:
        return pd.DataFrame()
    end = pd.Timestamp.now().normalize()
    start = end - pd.DateOffset(months=months)
    sub = inc_df[(inc_df['date'] >= start) & (inc_df['date'] <= end)].copy()
    s = sub.set_index('date')['amount'].resample('M').sum().rename('total')
    return s.to_frame()


def category_trend_area(exp_df: pd.DataFrame, months: int = 12) -> pd.DataFrame:
    if exp_df.empty:
        return pd.DataFrame()
    end = pd.Timestamp.now().normalize()
    start = end - pd.DateOffset(months=months)
    sub = exp_df[(exp_df['Date'] >= start) & (exp_df['Date'] <= end)].copy()
    sub['month'] = sub['Date'].dt.to_period('M').dt.to_timestamp()
    pivot = sub.pivot_table(index='month', columns='Category', values='Amount', aggfunc='sum', fill_value=0)
    return pivot


def portfolio_trend(inv_df: pd.DataFrame, months: int = 12) -> pd.DataFrame:
    # Ideally requires historical snapshots; fallback to monthly aggregation of current_value if present
    if inv_df.empty:
        return pd.DataFrame()
    if 'current_value' in inv_df.columns:
        # if there are per-investment historical snapshots, they should be used. For now, return a one-row latest value
        return pd.DataFrame({'Date': [pd.Timestamp.now().normalize()], 'value': [inv_df['current_value'].sum()]})
    return pd.DataFrame()

# --------------------------------------------------
# 5. HEATMAP, RECURRING, ANOMALIES
# --------------------------------------------------

def spending_heatmap_matrix(exp_df: pd.DataFrame) -> pd.DataFrame:
    if exp_df.empty:
        return pd.DataFrame()
    tmp = exp_df.copy()
    if tmp['created_at'].notna().any():
        tmp['hour'] = tmp['created_at'].dt.hour.fillna(0).astype(int)
    else:
        tmp['hour'] = tmp['Date'].dt.hour.fillna(0).astype(int) if 'Date' in tmp.columns else 0
    tmp['dow'] = tmp['Date'].dt.day_name()
    pivot = tmp.pivot_table(index='dow', columns='hour', values='Amount', aggfunc='sum', fill_value=0)
    order = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
    pivot = pivot.reindex(order).fillna(0)
    return pivot


def detect_recurring(exp_df: pd.DataFrame, min_occ: int = 3) -> pd.DataFrame:
    if exp_df.empty:
        return pd.DataFrame()
    tmp = exp_df.copy()
    tmp['desc_norm'] = tmp['Description'].fillna('').str.lower().str.replace('[^a-z0-9 ]','', regex=True)
    tmp['amt_round'] = tmp['Amount'].round(-1)
    g = tmp.groupby(['desc_norm','amt_round'])
    res = g.agg(count=('id','count'), avg=('Amount','mean'), last=('Date','max')).reset_index()
    return res[res['count'] >= min_occ].sort_values('count', ascending=False)


def detect_anomalies(exp_df: pd.DataFrame, z_thresh: float = 2.5) -> pd.DataFrame:
    if exp_df.empty:
        return pd.DataFrame()
    tmp = exp_df.copy()
    tmp['z'] = tmp.groupby('Category')['Amount'].transform(lambda x: (x - x.mean()) / (x.std(ddof=0) + 1e-9))
    return tmp[abs(tmp['z']) >= z_thresh].sort_values('z', ascending=False)

# --------------------------------------------------
# 6. INVESTMENT ANALYTICS
# --------------------------------------------------

def investment_summary(inv_df: pd.DataFrame) -> Dict:
    if inv_df.empty:
        return {'total_principal':0.0,'total_remaining':0.0,'current_value':0.0}
    total_principal = float(inv_df['amount'].sum()) if 'amount' in inv_df.columns else 0.0
    total_remaining = float(inv_df['principal_remaining'].sum()) if 'principal_remaining' in inv_df.columns else total_principal
    current_value = float(inv_df['current_value'].sum()) if 'current_value' in inv_df.columns else total_remaining
    return {'total_principal': total_principal, 'total_remaining': total_remaining, 'current_value': current_value}


def investment_gain_loss(inv_df: pd.DataFrame) -> pd.DataFrame:
    if inv_df.empty:
        return pd.DataFrame(columns=['id','type','amount','current_value','gain','gain_pct'])
    if 'current_value' not in inv_df.columns:
        return pd.DataFrame(columns=['id','type','amount','current_value','gain','gain_pct'])
    df = inv_df.copy()
    df['gain'] = df['current_value'] - df['amount']
    df['gain_pct'] = (df['gain'] / (df['amount'] + 1e-9) * 100).fillna(0)
    return df[['id','type','amount','current_value','gain','gain_pct']]

def investment_distribution(inv_df: pd.DataFrame) -> pd.Series:
    if inv_df.empty:
        return pd.Series(dtype=float)

    df = inv_df.copy()

    # Prefer current_value if available, else fallback to amount
    if 'current_value' in df.columns:
        df['current_value'] = pd.to_numeric(df['current_value'], errors='coerce')
        df['current_value'] = df['current_value'].fillna(df['amount'])
        values = df.groupby('type')['current_value'].sum()
    else:
        values = df.groupby('type')['amount'].sum()

    # Final NaN guard
    values = values.fillna(0)

    return values.sort_values(ascending=False)


# --------------------------------------------------
# 7. LEDGER INSIGHTS
# --------------------------------------------------

def ledger_activity(exp_df: pd.DataFrame, inc_df: pd.DataFrame) -> Dict:
    return {
        'expense_count': int(len(exp_df)) if exp_df is not None else 0,
        'income_count': int(len(inc_df)) if inc_df is not None else 0,
        'total_transactions': int((len(exp_df) if exp_df is not None else 0) + (len(inc_df) if inc_df is not None else 0))
    }

# --------------------------------------------------
# 8. BUDGET ENGINE + INSIGHTS
# --------------------------------------------------

def compute_budget_status(budgets_df: pd.DataFrame, expenses_df: pd.DataFrame, period_start: datetime, period_end: datetime) -> Dict:
    """Return totals and per-category budget progress for the given period."""
    # Total budget row (category is NULL)
    total_budget = None
    per_cat = {}
    if budgets_df is None or budgets_df.empty:
        total_budget = None
    else:
        tb = budgets_df[(budgets_df['category'].isnull()) & (budgets_df['period']=='monthly') & (budgets_df['active']==True)]
        if not tb.empty:
            total_budget = float(tb['amount'].iloc[0])

        cat_b = budgets_df[(budgets_df['category'].notnull()) & (budgets_df['period']=='monthly') & (budgets_df['active']==True)]
        # compute spent in period
        exp_period = filter_expenses(expenses_df, period_start, period_end)
        total_spent = float(exp_period['Amount'].sum()) if not exp_period.empty else 0.0
        for _, r in cat_b.iterrows():
            cat = r['category']
            b_amt = float(r['amount'])
            s_amt = float(exp_period[exp_period['Category']==cat]['Amount'].sum()) if not exp_period.empty else 0.0
            per_cat[cat] = {'budget': b_amt, 'spent': s_amt, 'remaining': b_amt - s_amt, 'pct_used': (s_amt / b_amt * 100.0) if b_amt>0 else None}
    total_spent = float(filter_expenses(expenses_df, period_start, period_end)['Amount'].sum()) if not expenses_df.empty else 0.0
    return {'total_budget': total_budget, 'total_spent': total_spent, 'total_remaining': (total_budget - total_spent) if total_budget is not None else None, 'per_category': per_cat}


def generate_budget_insights(budget_status: Dict) -> List[str]:
    insights = []
    if not budget_status:
        return insights
    tb = budget_status.get('total_budget')
    spent = budget_status.get('total_spent', 0.0)
    per_cat = budget_status.get('per_category', {})
    if tb is not None:
        pct = (spent / tb * 100.0) if tb>0 else 0.0
        if pct >= 110:
            insights.append(f"🔥 You have exceeded the monthly budget by ₹{spent - tb:.0f}.")
        elif pct >= 100:
            insights.append("⚠️ You have reached your monthly budget.")
        elif pct >= 80:
            insights.append(f"⚠️ {pct:.0f}% of budget used — monitor spending.")
        else:
            insights.append(f"✅ Budget usage is {pct:.0f}% — within limits.")
    # category insights
    for cat, info in per_cat.items():
        pct = info.get('pct_used') or 0
        if pct >= 120:
            insights.append(f"🔥 {cat}: Overspent by {pct-100:.0f}%.")
        elif pct >= 100:
            insights.append(f"⚠️ {cat}: Budget exceeded.")
        elif pct >= 80:
            insights.append(f"⚠️ {cat}: {pct:.0f}% used.")
        else:
            insights.append(f"✅ {cat}: {pct:.0f}% used.")
    return insights

# --------------------------------------------------
# 9. UNIFIED AGGREGATOR FOR APP.PY
# --------------------------------------------------

def get_dashboard_data(
    period_mode: str = 'month',             # 'month' | 'year' | 'range'
    reference_date: Optional[datetime] = None,
    range_start: Optional[datetime] = None,
    range_end: Optional[datetime] = None,
    trend_months: int = 12
) -> Dict:
    """Return a dict containing all the pieces the app needs, computed for requested period(s).

    period_mode: 'month' expects reference_date (a date in the month), default today.
    'year' expects reference_date or year can be inferred from reference_date.year
    'range' uses range_start and range_end (both required)
    trend_months used for trend-only sections
    """
    # load raw data
    exp_df = load_expenses_df()
    inc_df = load_income_df()
    acc_df = load_accounts_df()
    inv_df = load_investments_df()
    bud_df = load_budgets_df()

    if reference_date is None:
        reference_date = datetime.now()

    # determine period range
    if period_mode == 'month':
        start, end = get_month_range(reference_date)
    elif period_mode == 'year':
        y = reference_date.year
        start, end = get_year_range(y)
    elif period_mode == 'range':
        if range_start is None or range_end is None:
            raise ValueError('range_start and range_end required for range mode')
        start, end = range_start, range_end
    else:
        raise ValueError('invalid period_mode')

    # period-restricted slices
    exp_period = filter_expenses(exp_df, start, end)
    inc_period = filter_income(inc_df, start, end)

    # compute pieces
    net = net_flow(exp_period, inc_period)
    cat_break = category_breakdown(exp_period)
    top_cat = top_categories(exp_period, 10)
    daily = daily_spend(exp_period)
    income_split = income_source_split(inc_period)
    heatmap = spending_heatmap_matrix(exp_period)
    recurring = detect_recurring(exp_period)
    anomalies = detect_anomalies(exp_period)
    budgets = compute_budget_status(bud_df, exp_df, start, end)
    budget_insights = generate_budget_insights(budgets)
    ledger = ledger_activity(exp_period, inc_period)

    # trend-only
    exp_trend = expense_trend(exp_df, months=trend_months)
    inc_trend = income_trend(inc_df, months=trend_months)
    cat_trend = category_trend_area(exp_df, months=trend_months)
    port_trend = portfolio_trend(inv_df, months=trend_months)

    # investments
    inv_summary = investment_summary(inv_df)
    inv_gain = investment_gain_loss(inv_df)
    inv_dist = investment_distribution(inv_df)

    # accounts snapshot
    accounts = acc_df

    return {
        'period': {'mode': period_mode, 'start': start, 'end': end},
        'exp_period': exp_period,
        'inc_period': inc_period,
        'net_flow': net,
        'category_breakdown': cat_break,
        'top_categories': top_cat,
        'daily_spend': daily,
        'income_split': income_split,
        'heatmap': heatmap,
        'recurring': recurring,
        'anomalies': anomalies,
        'budgets': budgets,
        'budget_insights': budget_insights,
        'ledger': ledger,
        'trend': {'expense_trend': exp_trend, 'income_trend': inc_trend, 'category_trend': cat_trend, 'portfolio_trend': port_trend},
        'investments': {'summary': inv_summary, 'gain_table': inv_gain, 'distribution': inv_dist, 'raw': inv_df},
        'accounts': accounts,
        'raw': {'expenses': exp_df, 'income': inc_df, 'budgets': bud_df}
    }

# End of module
