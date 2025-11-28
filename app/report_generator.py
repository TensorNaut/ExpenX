# app/report_generator.py
"""
Optimized Report Generator for ExpenX
- Cached DB reads
- Cached aggregations
- Cached chart PNGs (memory + disk)
- Selective chart generation to speed up PDF
"""

import io
import os
import hashlib
from datetime import datetime
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib.styles import getSampleStyleSheet
from plotly.io import from_json as plotly_from_json
import kaleido

# Use your project's DB engine
from app.db import engine

# Streamlit caching (keeps in memory between runs)
import streamlit as st

# Cache directory for PNGs
CACHE_DIR = os.path.join("data", "report_cache")
os.makedirs(CACHE_DIR, exist_ok=True)


# ---------------------------
# Utility helpers
# ---------------------------
def _read_table_safe(table_name: str) -> pd.DataFrame:
    """Read a table from DB; fallback to read_sql_query when needed."""
    try:
        df = pd.read_sql_table(table_name, con=engine)
    except Exception:
        try:
            df = pd.read_sql_query(f"SELECT * FROM {table_name}", con=engine)
        except Exception:
            df = pd.DataFrame()
    df.columns = [c.lower() for c in df.columns]
    return df


# ---------------------------
# Cached loaders
# ---------------------------
@st.cache_data(ttl=600)
def load_expenses() -> pd.DataFrame:
    df = _read_table_safe("expenses")
    if not df.empty:
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
        if "amount" in df.columns:
            df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)
        df["category"] = df.get("category", "Uncategorized").fillna("Uncategorized")
    return df


@st.cache_data(ttl=600)
def load_income() -> pd.DataFrame:
    df = _read_table_safe("income")
    if not df.empty and "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        if "amount" in df.columns:
            df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)
    return df


@st.cache_data(ttl=600)
def load_accounts() -> pd.DataFrame:
    df = _read_table_safe("accounts")
    if not df.empty and "balance" in df.columns:
        df["balance"] = pd.to_numeric(df["balance"], errors="coerce").fillna(0.0)
    return df


@st.cache_data(ttl=600)
def load_investments() -> pd.DataFrame:
    df = _read_table_safe("investments")
    if not df.empty:
        for col in ["date", "maturity_date", "last_updated", "created_at"]:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors="coerce")
        for nc in ["amount", "principal_remaining", "quantity", "current_price_per_unit", "current_value"]:
            if nc in df.columns:
                df[nc] = pd.to_numeric(df[nc], errors="coerce").fillna(0.0)
    return df


@st.cache_data(ttl=600)
def load_ledger() -> pd.DataFrame:
    df = _read_table_safe("ledger")
    if not df.empty and "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
    if not df.empty and "amount" in df.columns:
        df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)
    return df


@st.cache_data(ttl=600)
def load_budgets_raw() -> pd.DataFrame:
    df = _read_table_safe("budgets")
    if not df.empty and "amount" in df.columns:
        df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)
    return df


# ---------------------------
# Aggregations (cached)
# ---------------------------
@st.cache_data(ttl=600)
def monthly_aggregate(year: int, month: int):
    exp = load_expenses()
    if exp.empty:
        return pd.DataFrame(), 0.0, pd.DataFrame()
    start = pd.Timestamp(year=year, month=month, day=1)
    end = (start + pd.DateOffset(months=1)) - pd.Timedelta(days=1)
    mdf = exp[(exp["date"] >= start) & (exp["date"] <= end)].copy()
    total = float(mdf["amount"].sum()) if not mdf.empty else 0.0
    per_cat = mdf.groupby("category")["amount"].sum().reset_index().rename(columns={"amount": "spent"})
    return mdf, total, per_cat


@st.cache_data(ttl=600)
def yearly_aggregates(year: int):
    exp = load_expenses()
    if exp.empty:
        return pd.DataFrame(), pd.DataFrame()
    start = pd.Timestamp(year=year, month=1, day=1)
    end = pd.Timestamp(year=year, month=12, day=31)
    ydf = exp[(exp["date"] >= start) & (exp["date"] <= end)].copy()
    ydf["month"] = ydf["date"].dt.to_period("M").dt.to_timestamp()
    month_totals = ydf.groupby("month")["amount"].sum().reset_index().rename(columns={"amount": "total_spent"})
    cat_totals = ydf.groupby("category")["amount"].sum().reset_index().rename(columns={"amount": "total_spent"})
    return month_totals, cat_totals


# ---------------------------
# Chart PNG caching (disk + memory)
# ---------------------------
def _dataframe_hash(df: pd.DataFrame) -> str:
    if df is None or df.empty:
        return "empty"
    # keep deterministic: use columns order + head/tail sample for big df
    h = hashlib.sha256()
    # small representation
    s = df.to_csv(index=False).encode("utf-8")
    h.update(s)
    return h.hexdigest()



@st.cache_data(ttl=300)
def cached_fig_png(fig_json: str, chart_name: str, width=1000, height=450, scale=2) -> bytes:
    """
    fig_json: string (fig.to_json()) — used to compute deterministic hash
    Chart is saved to disk cache for reuse across restarts.
    """
    # compute hash key
    key = hashlib.sha256((fig_json + chart_name).encode("utf-8")).hexdigest()
    png_path = os.path.join(CACHE_DIR, f"{key}.png")

    # If already exists → load from disk
    if os.path.exists(png_path):
        with open(png_path, "rb") as f:
            return f.read()

    # Reconstruct figure from JSON
    fig = plotly_from_json(fig_json)

    # Render
    try:
        img_bytes = fig.to_image(format="png", width=width, height=height, scale=scale)
    except Exception as e:
        raise RuntimeError(f"Plotly → PNG failed (ensure kaleido installed): {e}")

    # Save to disk
    with open(png_path, "wb") as f:
        f.write(img_bytes)

    return img_bytes



# ---------------------------
# Small plot helpers
# ---------------------------
def _fig_daily_cumulative(mdf: pd.DataFrame) -> go.Figure:
    if mdf.empty:
        f = go.Figure()
        f.update_layout(title="No data")
        return f
    daily = mdf.groupby(mdf["date"].dt.day)["amount"].sum().reset_index().rename(columns={"date": "day", "amount": "spent"})
    daily["cumulative"] = daily["spent"].cumsum()
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=daily["day"], y=daily["cumulative"], mode="lines+markers", name="Cumulative"))
    fig.update_layout(title="Daily Cumulative Spend", xaxis_title="Day", yaxis_title="Amount (₹)", template="plotly_dark")
    return fig


def _fig_category_bar(per_cat: pd.DataFrame) -> go.Figure:
    if per_cat.empty:
        f = go.Figure()
        f.update_layout(title="No category data")
        return f
    fig = px.bar(per_cat.sort_values("spent", ascending=False), x="category", y="spent", title="Category Spend", template="plotly_dark")
    return fig


def _fig_monthly_line(month_totals: pd.DataFrame) -> go.Figure:
    if month_totals.empty:
        f = go.Figure()
        f.update_layout(title="No month data")
        return f
    fig = px.line(month_totals, x="month", y="total_spent", markers=True, title="Monthly Spend (Total)", template="plotly_dark")
    return fig


def _fig_top_category_trends(cat_month_df: pd.DataFrame, top_n=6) -> go.Figure:
    if cat_month_df.empty:
        f = go.Figure()
        f.update_layout(title="No category month data")
        return f
    cat_totals = cat_month_df.sum(axis=0).sort_values(ascending=False)
    top = cat_totals.head(top_n).index.tolist()
    trimmed = cat_month_df[top]
    fig = go.Figure()
    for c in trimmed.columns:
        fig.add_trace(go.Scatter(x=trimmed.index, y=trimmed[c], mode='lines+markers', name=str(c)))
    fig.update_layout(title=f"Top {len(trimmed.columns)} Category Trends", xaxis_title='Month', yaxis_title='Amount (₹)', template='plotly_dark')
    return fig


# ---------------------------
# PDF composition (selective charts)
# ---------------------------
def _compose_pdf(pages: list) -> bytes:
    """
    pages: list of dict: {"type":"cover"|"img"|"text", "content": ...}
    Returns PDF bytes.
    """
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=landscape(A4))
    width, height = landscape(A4)
    styles = getSampleStyleSheet()
    for page in pages:
        ptype = page.get("type")
        if ptype == "cover":
            title = page.get("title", "ExpenX Report")
            subtitle = page.get("subtitle", "")
            lines = page.get("lines", [])
            c.setFont("Helvetica-Bold", 24)
            c.drawString(40, height - 60, title)
            c.setFont("Helvetica", 10)
            c.drawString(40, height - 90, subtitle)
            y = height - 120
            for ln in lines:
                c.drawString(40, y, ln)
                y -= 16
            c.showPage()
        elif ptype == "img":
            img_bytes = page.get("bytes")
            if img_bytes:
                img = ImageReader(io.BytesIO(img_bytes))
                c.drawImage(img, 30, 40, width - 60, height - 80, preserveAspectRatio=True)
            else:
                c.setFont("Helvetica", 12)
                c.drawString(40, height - 60, "Empty chart")
            c.showPage()
        elif ptype == "text":
            title = page.get("title", "")
            body_lines = page.get("lines", [])
            c.setFont("Helvetica-Bold", 16)
            c.drawString(40, height - 50, title)
            c.setFont("Helvetica", 10)
            y = height - 80
            for ln in body_lines:
                c.drawString(40, y, ln)
                y -= 14
                if y < 80:
                    c.showPage()
                    y = height - 80
            c.showPage()
    c.save()
    buffer.seek(0)
    pdf_bytes = buffer.read()
    buffer.close()
    return pdf_bytes


# ---------------------------
# Public report generation (fast / selective)
# ---------------------------
def generate_monthly_report(year: int, month: int, include_charts: dict = None) -> bytes:
    """
    include_charts: dict controlling which charts to render, keys:
      daily, categories, accounts, investments, ledger, top_categories_trend
    default: generate daily + categories + accounts + investments + ledger
    """
    if include_charts is None:
        include_charts = {"daily": True, "categories": True, "accounts": True, "investments": True, "ledger": True}

    # load small datasets (cached)
    mdf, total_exp, per_cat = monthly_aggregate(year, month)
    inc = load_income()
    acc = load_accounts()
    inv = load_investments()
    ldg = load_ledger()

    # compute income for month
    start = pd.Timestamp(year=year, month=month, day=1)
    end = (start + pd.DateOffset(months=1)) - pd.Timedelta(days=1)
    inc_month = inc[(inc["date"] >= start) & (inc["date"] <= end)] if not inc.empty else pd.DataFrame()
    total_inc = float(inc_month["amount"].sum()) if not inc_month.empty else 0.0
    net_flow = total_inc - total_exp

    # pages builder
    pages = []
    pages.append({"type": "cover",
                  "title": "ExpenX — Monthly Report",
                  "subtitle": f"{start.strftime('%B %Y')}  •  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                  "lines": [f"Total Income: ₹{total_inc:,.2f}", f"Total Expense: ₹{total_exp:,.2f}", f"Net Flow: ₹{net_flow:,.2f}"]})

    # charts (use cached PNG generator)
    if include_charts.get("daily", True):
        fig = _fig_daily_cumulative(mdf)
        fig_json = fig.to_json()
        img = cached_fig_png(fig_json, chart_name=f"monthly_daily_{year}_{month}")
        pages.append({"type": "img", "bytes": img})

    if include_charts.get("categories", True):
        fig = _fig_category_bar(per_cat)
        fig_json = fig.to_json()
        img = cached_fig_png(fig_json, chart_name=f"monthly_cat_{year}_{month}")
        pages.append({"type": "img", "bytes": img})

    # accounts snapshot (text page)
    acc_rows = []
    for _, r in acc.iterrows() if not acc.empty else []:
        acc_rows.append(f"{r.get('name','')}  |  Balance: ₹{float(r.get('balance',0)):,.2f}  |  Kind: {r.get('kind','')}")
    pages.append({"type": "text", "title": "Accounts Snapshot", "lines": acc_rows or ["No accounts found."]})

    # investments snapshot (text)
    inv_rows = []
    if not inv.empty:
        for _, r in inv.iterrows():
            inv_rows.append(f"ID:{int(r.get('id',0))} | {r.get('type','')} | Invested: ₹{float(r.get('amount',0)):,.2f} | Current: ₹{float(r.get('current_value',0)):,.2f}")
    else:
        inv_rows.append("No investments found.")
    pages.append({"type": "text", "title": "Investments Snapshot", "lines": inv_rows})

    # ledger highlights
    if not ldg.empty:
        ldg_m = ldg[(ldg["date"] >= start) & (ldg["date"] <= end)]
        lent = float(ldg_m[ldg_m["direction"] == "lent"]["amount"].sum()) if not ldg_m.empty else 0.0
        borrowed = float(ldg_m[ldg_m["direction"] == "borrowed"]["amount"].sum()) if not ldg_m.empty else 0.0
        pages.append({"type": "text", "title": "Ledger Highlights", "lines": [f"Total Lent: ₹{lent:,.2f}", f"Total Borrowed: ₹{borrowed:,.2f}"]})
    else:
        pages.append({"type": "text", "title": "Ledger Highlights", "lines": ["No ledger entries found."]})

    pdf_bytes = _compose_pdf(pages)
    return pdf_bytes


def generate_yearly_report(year: int, include_charts: dict = None) -> bytes:
    """
    include_charts: keys: monthly_line, top_category_trends
    """
    if include_charts is None:
        include_charts = {"monthly_line": True, "top_category_trends": True}

    month_totals, cat_totals = yearly_aggregates(year)
    inv = load_investments()
    ldg = load_ledger()
    acc = load_accounts()

    pages = []
    pages.append({"type": "cover",
                  "title": f"ExpenX — Yearly Report ({year})",
                  "subtitle": f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                  "lines": []})

    if include_charts.get("monthly_line", True) and not month_totals.empty:
        fig = _fig_monthly_line(month_totals)
        fig_json = fig.to_json()
        img = cached_fig_png(fig_json, chart_name=f"yearly_monthline_{year}")
        pages.append({"type": "img", "bytes": img})

    # top categories
    if include_charts.get("top_category_trends", True) and not cat_totals.empty:
        # create a cross-month pivot for top categories (lightweight): reuse yearly_aggregates results if needed
        top_cats = cat_totals.sort_values("total_spent", ascending=False).head(12)["category"].tolist()
        # For simplicity include cat_totals as text summary
        cat_lines = [f"{row['category']}: ₹{row['total_spent']:,.2f}" for _, row in cat_totals.sort_values("total_spent", ascending=False).head(20).iterrows()]
        pages.append({"type": "text", "title": "Top Categories (Year)", "lines": cat_lines})

    # investments summary
    inv_rows = []
    if not inv.empty:
        for _, r in inv.iterrows():
            inv_rows.append(f"ID:{int(r.get('id',0))} | {r.get('type','')} | Current: ₹{float(r.get('current_value',0)):,.2f}")
    else:
        inv_rows.append("No investments found.")
    pages.append({"type": "text", "title": "Investments Summary (Year)", "lines": inv_rows})

    # ledger yearly totals
    if not ldg.empty:
        ldg_year = ldg[ldg["date"].dt.year == year]
        lent = float(ldg_year[ldg_year["direction"] == "lent"]["amount"].sum()) if not ldg_year.empty else 0.0
        borrowed = float(ldg_year[ldg_year["direction"] == "borrowed"]["amount"].sum()) if not ldg_year.empty else 0.0
        pages.append({"type": "text", "title": "Ledger Summary (Year)", "lines": [f"Total Lent: ₹{lent:,.2f}", f"Total Borrowed: ₹{borrowed:,.2f}"]})
    else:
        pages.append({"type": "text", "title": "Ledger Summary (Year)", "lines": ["No ledger data."]})

    pdf_bytes = _compose_pdf(pages)
    return pdf_bytes


def generate_overall_report(year: int, month: int = None, period: str = "monthly", include_charts: dict = None) -> bytes:
    """Wrapper to generate monthly or yearly report. include_charts is forwarded."""
    if period == "monthly":
        if month is None:
            raise ValueError("month required for monthly report")
        return generate_monthly_report(year, month, include_charts=include_charts)
    elif period == "yearly":
        return generate_yearly_report(year, include_charts=include_charts)
    else:
        raise ValueError("period must be 'monthly' or 'yearly'")


# ---------------------------
# Summary JSON (cached)
# ---------------------------
@st.cache_data(ttl=300)
def generate_summary_json(period: str = "monthly", year: int = None, month: int = None) -> dict:
    """
    Return structured summary suitable for AI: income, expense, net, category totals,
    accounts, investments, ledger entries, budgets.
    """
    exp = load_expenses()
    inc = load_income()
    acc = load_accounts()
    inv = load_investments()
    ldg = load_ledger()
    budgets = load_budgets_raw()

    if period == "monthly":
        if year is None or month is None:
            raise ValueError("monthly requires year & month")
        start = pd.Timestamp(year=year, month=month, day=1)
        end = (start + pd.DateOffset(months=1)) - pd.Timedelta(days=1)
        period_label = start.strftime("%B %Y")
    elif period == "yearly":
        if year is None:
            raise ValueError("yearly requires year")
        start = pd.Timestamp(year=year, month=1, day=1)
        end = pd.Timestamp(year=year, month=12, day=31)
        period_label = str(year)
    else:
        raise ValueError("period must be 'monthly' or 'yearly'")

    exp_p = exp[(exp["date"] >= start) & (exp["date"] <= end)].copy() if not exp.empty else pd.DataFrame()
    inc_p = inc[(inc["date"] >= start) & (inc["date"] <= end)].copy() if not inc.empty else pd.DataFrame()
    ldg_p = ldg[(ldg["date"] >= start) & (ldg["date"] <= end)].copy() if not ldg.empty else pd.DataFrame()

    total_exp = float(exp_p["amount"].sum()) if not exp_p.empty else 0.0
    total_inc = float(inc_p["amount"].sum()) if not inc_p.empty else 0.0
    net_flow = total_inc - total_exp

    cat_list = []
    if not exp_p.empty:
        cat_list = exp_p.groupby("category")["amount"].sum().reset_index().rename(columns={"amount": "spent"}).sort_values("spent", ascending=False).to_dict(orient="records")

    accounts_list = []
    if not acc.empty:
        for _, r in acc.iterrows():
            accounts_list.append({
                "id": int(r.get("id", 0)),
                "name": r.get("name", ""),
                "kind": r.get("kind", ""),
                "balance": float(r.get("balance", 0)),
                "currency": r.get("currency", "")
            })

    investments_list = []
    if not inv.empty:
        for _, r in inv.iterrows():
            investments_list.append({
                "id": int(r.get("id", 0)),
                "type": r.get("type", ""),
                "amount_invested": float(r.get("amount", 0)),
                "principal_remaining": float(r.get("principal_remaining", 0)) if "principal_remaining" in r.index else 0.0,
                "current_value": float(r.get("current_value", 0)) if "current_value" in r.index else 0.0,
                "status": r.get("status", "")
            })

    ledger_entries = []
    ledger_summary = {"total_lent": 0.0, "total_borrowed": 0.0}
    if not ldg_p.empty:
        ledger_summary["total_lent"] = float(ldg_p[ldg_p["direction"] == "lent"]["amount"].sum()) if "direction" in ldg_p.columns else 0.0
        ledger_summary["total_borrowed"] = float(ldg_p[ldg_p["direction"] == "borrowed"]["amount"].sum()) if "direction" in ldg_p.columns else 0.0
        ledger_entries = ldg_p.sort_values("date", ascending=False).to_dict(orient="records")

    budgets_list = []
    if not budgets.empty:
        budgets = budgets.copy()
        budgets.columns = [c.lower() for c in budgets.columns]
        for _, r in budgets.iterrows():
            budgets_list.append({
                "category": r.get("category"),
                "amount": float(r.get("amount", 0)),
                "period": r.get("period"),
                "active": bool(r.get("active", 1))
            })

    summary = {
        "period_type": period,
        "period_label": period_label,
        "range": {"start": str(start), "end": str(end)},
        "totals": {"income": total_inc, "expense": total_exp, "net_flow": net_flow, "category_totals": cat_list},
        "accounts": accounts_list,
        "investments": investments_list,
        "ledger": {"summary": ledger_summary, "entries": ledger_entries},
        "budgets": budgets_list
    }
    return summary
