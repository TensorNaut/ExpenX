# app/report_generator.py
"""
ExpenX Report Generator (Matplotlib-based, No Plotly, Fast, Stable)
- Monthly + Yearly PDF Reports
- Uses Matplotlib charts (no Kaleido, no Plotly)
- Zero hanging issues
- Cached DB reads
- Generates JSON summary for AI
"""

import io
import os
import hashlib
from datetime import datetime
import pandas as pd
import numpy as np

# Matplotlib (safe backend)
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib.styles import getSampleStyleSheet

import streamlit as st
from app.db import engine

# ---------------------------------------------------------
# Cache Directory
# ---------------------------------------------------------
CACHE_DIR = "data/report_cache"
os.makedirs(CACHE_DIR, exist_ok=True)


# ---------------------------------------------------------
# Safe DB Loader
# ---------------------------------------------------------
def _read_table_safe(name):
    try:
        return pd.read_sql_table(name, engine)
    except:
        try:
            return pd.read_sql_query(f"SELECT * FROM {name}", engine)
        except:
            return pd.DataFrame()


# ---------------------------------------------------------
# Cached DB loaders
# ---------------------------------------------------------
@st.cache_data(ttl=600)
def load_expenses():
    df = _read_table_safe('expenses')
    if not df.empty:
        df.columns = map(str.lower, df.columns)
        df['date'] = pd.to_datetime(df['date'], errors='coerce')
        df['amount'] = pd.to_numeric(df['amount'], errors='coerce').fillna(0.0)
        df['category'] = df['category'].fillna('Uncategorized')
    return df

@st.cache_data(ttl=600)
def load_income():
    df = _read_table_safe('income')
    if not df.empty:
        df.columns = map(str.lower, df.columns)
        df['date'] = pd.to_datetime(df['date'], errors='coerce')
        df['amount'] = pd.to_numeric(df['amount'], errors='coerce').fillna(0.0)
    return df

@st.cache_data(ttl=600)
def load_accounts():
    df = _read_table_safe('accounts')
    if not df.empty:
        df.columns = map(str.lower, df.columns)
        df['balance'] = pd.to_numeric(df['balance'], errors='coerce').fillna(0.0)
    return df

@st.cache_data(ttl=600)
def load_investments():
    df = _read_table_safe('investments')
    if not df.empty:
        df.columns = map(str.lower, df.columns)
        for col in ['date','maturity_date','last_updated']:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors='coerce')
        for col in ['amount','principal_remaining','quantity','current_value']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
    return df

@st.cache_data(ttl=600)
def load_ledger():
    df = _read_table_safe('ledger')
    if not df.empty:
        df.columns = map(str.lower, df.columns)
        df['date'] = pd.to_datetime(df['date'], errors='coerce')
        df['amount'] = pd.to_numeric(df['amount'], errors='coerce').fillna(0.0)
    return df

@st.cache_data(ttl=600)
def load_budgets():
    df = _read_table_safe('budgets')
    if not df.empty:
        df.columns = map(str.lower, df.columns)
        df['amount'] = pd.to_numeric(df['amount'], errors='coerce').fillna(0.0)
    return df


# ---------------------------------------------------------
# Aggregation Helpers
# ---------------------------------------------------------
@st.cache_data(ttl=600)
def monthly_aggregate(year, month):
    exp = load_expenses()
    if exp.empty:
        return pd.DataFrame(), 0.0, pd.DataFrame()

    start = pd.Timestamp(year=year, month=month, day=1)
    end = (start + pd.DateOffset(months=1)) - pd.Timedelta(days=1)

    mdf = exp[(exp['date'] >= start) & (exp['date'] <= end)]
    total = float(mdf['amount'].sum()) if not mdf.empty else 0.0

    if mdf.empty:
        per_cat = pd.DataFrame()
    else:
        per_cat = (
            mdf.groupby('category')['amount']
            .sum().reset_index().rename(columns={'amount':'spent'})
            .sort_values('spent', ascending=False)
        )
    return mdf, total, per_cat


@st.cache_data(ttl=600)
def yearly_aggregate(year):
    exp = load_expenses()
    if exp.empty:
        return pd.DataFrame(), pd.DataFrame()

    start = pd.Timestamp(year=year, month=1, day=1)
    end = pd.Timestamp(year+1, month=1, day=1) - pd.Timedelta(days=1)

    ydf = exp[(exp['date'] >= start) & (exp['date'] <= end)]
    if ydf.empty:
        return pd.DataFrame(), pd.DataFrame()

    ydf['month'] = ydf['date'].dt.to_period('M').dt.to_timestamp()
    month_totals = ydf.groupby('month')['amount'].sum().reset_index().rename(columns={'amount': 'total_spent'})
    cat_totals = ydf.groupby('category')['amount'].sum().reset_index().rename(columns={'amount': 'total_spent'})

    return month_totals, cat_totals


# ---------------------------------------------------------
# Matplotlib Chart Generators
# ---------------------------------------------------------
def mpl_daily_chart(mdf):
    fig, ax = plt.subplots(figsize=(10, 4))
    if mdf.empty:
        ax.text(0.5, 0.5, "No transactions", ha="center", va="center")
        ax.axis("off")
        return fig

    daily = mdf.groupby(mdf['date'].dt.day)['amount'].sum()
    cum = daily.cumsum()

    ax.plot(daily.index, cum.values, marker='o', color='#008cba')
    ax.set_title("Daily Cumulative Spend")
    ax.set_xlabel("Day")
    ax.set_ylabel("Amount (₹)")
    ax.grid(alpha=0.3)
    return fig


def mpl_category_chart(per_cat):
    fig, ax = plt.subplots(figsize=(10, 4))
    if per_cat.empty:
        ax.text(0.5, 0.5, "No category data", ha="center", va="center")
        ax.axis("off")
        return fig

    ax.bar(per_cat['category'], per_cat['spent'], color='#e67e22')
    ax.set_title("Category Spend")
    ax.set_ylabel("Amount (₹)")
    plt.xticks(rotation=45, ha="right")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    return fig


def mpl_monthly_chart(month_totals):
    fig, ax = plt.subplots(figsize=(10,4))
    if month_totals.empty:
        ax.text(0.5, 0.5, "No data", ha="center", va="center")
        ax.axis("off")
        return fig
    months = month_totals['month'].dt.strftime("%Y-%m")
    ax.plot(months, month_totals['total_spent'], marker='o', color='#27ae60')
    ax.set_title("Monthly Total Spend")
    ax.set_xlabel("Month")
    ax.set_ylabel("Amount (₹)")
    plt.xticks(rotation=45, ha='right')
    ax.grid(alpha=0.3)
    fig.tight_layout()
    return fig


# ---------------------------------------------------------
# Convert Matplotlib → PNG Bytes
# ---------------------------------------------------------
def fig_to_png(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=110, bbox_inches='tight')
    plt.close(fig)
    buf.seek(0)
    return buf.read()


# ---------------------------------------------------------
# PDF Composer
# ---------------------------------------------------------
def _compose_pdf(pages):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=landscape(A4))
    W, H = landscape(A4)
    styles = getSampleStyleSheet()

    for page in pages:
        if page['type'] == 'cover':
            c.setFont("Helvetica-Bold", 24)
            c.drawString(40, H-60, page.get("title","ExpenX Report"))
            c.setFont("Helvetica", 10)
            c.drawString(40, H-90, page.get("subtitle",""))            
            y = H-120
            for line in page.get("lines", []):
                c.drawString(40, y, line)
                y -= 14
            c.showPage()

        elif page['type'] == 'img':
            img = ImageReader(io.BytesIO(page['bytes']))
            c.drawImage(img, 30, 40, W-60, H-80, preserveAspectRatio=True)
            c.showPage()

        elif page['type'] == 'text':
            c.setFont("Helvetica-Bold", 16)
            c.drawString(40, H-60, page['title'])
            c.setFont("Helvetica", 10)
            y = H-100
            for line in page['lines']:
                c.drawString(40, y, line)
                y -= 14
                if y < 80:
                    c.showPage()
                    y = H-80
            c.showPage()

    c.save()
    buffer.seek(0)
    return buffer.read()


# ---------------------------------------------------------
# Monthly Report
# ---------------------------------------------------------
def generate_monthly_report(year, month):
    mdf, total_exp, per_cat = monthly_aggregate(year, month)

    income = load_income()
    start = pd.Timestamp(year=year, month=month, day=1)
    end = (start + pd.DateOffset(months=1)) - pd.Timedelta(days=1)
    inc_m = income[(income['date'] >= start)&(income['date'] <=end)]
    total_inc = float(inc_m['amount'].sum()) if not inc_m.empty else 0.0
    net = total_inc - total_exp

    # Charts
    daily_fig = mpl_daily_chart(mdf)
    daily_png = fig_to_png(daily_fig)

    cat_fig = mpl_category_chart(per_cat)
    cat_png = fig_to_png(cat_fig)

    # Accounts
    acc = load_accounts()
    acc_lines = [
        f"{row['name']}: ₹{float(row['balance']):,.2f} ({row.get('kind','')})"
        for _, row in acc.iterrows()
    ]

    # Investments
    inv = load_investments()
    inv_lines = []
    if not inv.empty:
        for _, r in inv.iterrows():
            inv_lines.append(f"{r.get('type','')} | Invested: ₹{r.get('amount',0):,.2f} | Current: ₹{r.get('current_value',0):,.2f}")
    else:
        inv_lines.append("No investments found.")

    # Ledger
    ledger = load_ledger()
    ledger_month = ledger[(ledger['date'] >= start)&(ledger['date'] <= end)]
    lent = float(ledger_month[ledger_month['direction']=='lent']['amount'].sum()) if not ledger_month.empty else 0.0
    borrowed = float(ledger_month[ledger_month['direction']=='borrowed']['amount'].sum()) if not ledger_month.empty else 0.0

    pages = [
        {
            "type": "cover",
            "title": "ExpenX — Monthly Report",
            "subtitle": f"{start.strftime('%B %Y')} • Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "lines": [
                f"Total Income: ₹{total_inc:,.2f}",
                f"Total Expense: ₹{total_exp:,.2f}",
                f"Net Flow: ₹{net:,.2f}",
            ]
        },
        {"type":"img","bytes":daily_png},
        {"type":"img","bytes":cat_png},
        {"type":"text","title":"Accounts Snapshot","lines":acc_lines},
        {"type":"text","title":"Investments Snapshot","lines":inv_lines},
        {"type":"text","title":"Ledger Summary",
         "lines":[f"Total Lent: ₹{lent:,.2f}", f"Total Borrowed: ₹{borrowed:,.2f}"]},
    ]

    return _compose_pdf(pages)


# ---------------------------------------------------------
# Yearly Report
# ---------------------------------------------------------
def generate_yearly_report(year):
    month_totals, cat_totals = yearly_aggregate(year)

    monthly_fig = mpl_monthly_chart(month_totals)
    monthly_png = fig_to_png(monthly_fig)

    cat_fig = mpl_category_chart(cat_totals.rename(columns={'total_spent':'spent'}))
    cat_png = fig_to_png(cat_fig)

    inv = load_investments()
    ledger = load_ledger()

    inv_lines = []
    if not inv.empty:
        for _, r in inv.iterrows():
            inv_lines.append(f"{r.get('type','')} • Current: ₹{r.get('current_value',0):,.2f}")
    else:
        inv_lines.append("No investments found.")

    ledger_year = ledger[ledger['date'].dt.year == year]
    lent = float(ledger_year[ledger_year['direction']=='lent']['amount'].sum()) if not ledger_year.empty else 0.0
    borrowed = float(ledger_year[ledger_year['direction']=='borrowed']['amount'].sum()) if not ledger_year.empty else 0.0

    pages = [
        {
            "type":"cover",
            "title":f"ExpenX — Yearly Report ({year})",
            "subtitle": f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "lines":[]
        },
        {"type":"img","bytes":monthly_png},
        {"type":"img","bytes":cat_png},
        {"type":"text","title":"Investments","lines":inv_lines},
        {"type":"text","title":"Ledger Summary",
         "lines":[f"Total Lent: ₹{lent:,.2f}", f"Total Borrowed: ₹{borrowed:,.2f}"]},
    ]

    return _compose_pdf(pages)


# ---------------------------------------------------------
# Unified Wrapper
# ---------------------------------------------------------
def generate_overall_report(year, month=None, period='monthly'):
    if period == 'monthly':
        if month is None:
            raise ValueError("month required")
        return generate_monthly_report(year, month)
    return generate_yearly_report(year)


# ---------------------------------------------------------
# JSON Summary for AI
# ---------------------------------------------------------
@st.cache_data(ttl=300)
def generate_summary_json(period='monthly', year=None, month=None):
    exp = load_expenses()
    inc = load_income()
    acc = load_accounts()
    inv = load_investments()
    ldg = load_ledger()
    bud = load_budgets()

    if period=='monthly':
        start = pd.Timestamp(year=year, month=month, day=1)
        end = (start + pd.DateOffset(months=1)) - pd.Timedelta(days=1)
        label = start.strftime("%B %Y")
    else:
        start = pd.Timestamp(year=year, month=1, day=1)
        end = pd.Timestamp(year=year, month=12, day=31)
        label = str(year)

    exp_p = exp[(exp['date']>=start)&(exp['date']<=end)] if not exp.empty else pd.DataFrame()
    inc_p = inc[(inc['date']>=start)&(inc['date']<=end)] if not inc.empty else pd.DataFrame()
    ldg_p = ldg[(ldg['date']>=start)&(ldg['date']<=end)] if not ldg.empty else pd.DataFrame()

    total_exp = float(exp_p['amount'].sum()) if not exp_p.empty else 0.0
    total_inc = float(inc_p['amount'].sum()) if not inc_p.empty else 0.0
    net = total_inc - total_exp

    cat_list = []
    if not exp_p.empty:
        cat_list = (
            exp_p.groupby('category')['amount']
            .sum().reset_index().rename(columns={'amount':'spent'})
            .sort_values('spent', ascending=False)
            .to_dict(orient='records')
        )

    acc_list = [
        {"name": r.get('name',''),
         "kind": r.get('kind',''),
         "balance": float(r.get('balance',0))}
        for _, r in acc.iterrows()
    ]

    inv_list = [
        {
            "type": r.get('type',''),
            "invested": float(r.get('amount',0)),
            "current": float(r.get('current_value',0)),
            "status": r.get('status','')
        }
        for _, r in inv.iterrows()
    ]

    ledger_summary = {
        "lent": float(ldg_p[ldg_p['direction']=='lent']['amount'].sum()) if not ldg_p.empty else 0.0,
        "borrowed": float(ldg_p[ldg_p['direction']=='borrowed']['amount'].sum()) if not ldg_p.empty else 0.0,
        "entries": ldg_p.to_dict(orient='records')
    }

    budgets_list = bud.to_dict(orient='records') if not bud.empty else []

    return {
        "period": period,
        "label": label,
        "range": {"start": str(start), "end": str(end)},
        "totals": {
            "income": total_inc,
            "expense": total_exp,
            "net_flow": net,
            "category_totals": cat_list
        },
        "accounts": acc_list,
        "investments": inv_list,
        "ledger": ledger_summary,
        "budgets": budgets_list
    }
