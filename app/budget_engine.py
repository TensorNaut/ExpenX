# -----------------------------------------------------------
#  ExpenX - Budget Engine (Final Polished Version)
# -----------------------------------------------------------

import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
#from app.db import engine, get_session, Budget
from sqlalchemy import text
from typing import Optional, List, Dict, Any


# -----------------------------------------------------------
#   CORE BUDGET COMPUTATION
# -----------------------------------------------------------

def compute_budget(exp_df: pd.DataFrame, budgets_df: pd.DataFrame,
                   period_start: date, period_end: date):
    """
    Compute full budget status for the given period.
    Returns dictionary containing:
        - total_budget
        - total_spent
        - total_remaining
        - per_category: {category: {...}}
    """
    if exp_df is None or exp_df.empty:
        return {
            "total_budget": 0,
            "total_spent": 0,
            "total_remaining": 0,
            "per_category": {}
        }

    df = exp_df.copy()
    df.columns = [c.lower() for c in df.columns]
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    df['amount'] = pd.to_numeric(df['amount'], errors='coerce').fillna(0)
    df['category'] = df.get('category', 'Uncategorized').fillna('Uncategorized')

    # Filter period
    mask = (df['date'] >= pd.Timestamp(period_start)) & (df['date'] <= pd.Timestamp(period_end))
    df = df.loc[mask]

    # Load budget frames
    budgets_df.columns = [c.lower() for c in budgets_df.columns]

    total_budget_row = budgets_df[budgets_df['category'].isna()]
    total_budget = float(total_budget_row['amount'].iloc[0]) if not total_budget_row.empty else 0

    cat_budget_rows = budgets_df[budgets_df['category'].notna()]

    # Compute totals
    total_spent = float(df['amount'].sum())
    total_remaining = total_budget - total_spent if total_budget else None

    # category-wise
    per_category_spend = df.groupby('category')['amount'].sum().to_dict()
    per_category = {}

    for cat, spent in per_category_spend.items():
        bud_row = cat_budget_rows[cat_budget_rows['category'] == cat]
        bud_amt = float(bud_row['amount'].iloc[0]) if not bud_row.empty else 0
        remaining = bud_amt - spent
        pct_used = (spent / bud_amt * 100) if bud_amt > 0 else 0
        per_category[cat] = {
            "budget": bud_amt,
            "spent": spent,
            "remaining": remaining,
            "pct_used": pct_used
        }

    # categories that have budgets but no spending yet
    for _, r in cat_budget_rows.iterrows():
        cat = r['category']
        if cat not in per_category:
            per_category[cat] = {
                "budget": float(r['amount']),
                "spent": 0.0,
                "remaining": float(r['amount']),
                "pct_used": 0.0
            }

    return {
        "total_budget": total_budget,
        "total_spent": total_spent,
        "total_remaining": total_remaining,
        "per_category": per_category
    }


# -----------------------------------------------------------
#   1. OVESPEND PREDICTOR PER CATEGORY
# -----------------------------------------------------------

def predict_overspend_per_category(exp_month: pd.DataFrame, budgets: dict,
                                   period_start: pd.Timestamp, period_end: pd.Timestamp):
    """
    Predict if category will exceed its budget based on average pace.
    Returns: {category: {...}}
    """
    if exp_month is None or exp_month.empty:
        return {}

    today = pd.Timestamp.today().normalize()
    days_passed = (today - period_start).days + 1
    days_total = (period_end - period_start).days + 1
    days_remaining = max(days_total - days_passed, 0)

    # Build budget lookup
    budget_map = {c['category']: float(c['amount']) for c in budgets.get("categories", [])}

    # Category spending so far
    grp = exp_month.groupby('category')['amount'].sum().to_dict()
    results = {}

    for cat, spent in grp.items():
        budget = budget_map.get(cat, 0.0)
        avg_daily = spent / max(days_passed, 1)
        proj_total = spent + avg_daily * days_remaining

        will_exceed = (budget > 0 and proj_total > budget)
        days_to_exceed = None

        if will_exceed and avg_daily > 0:
            d = (budget - spent) / avg_daily
            days_to_exceed = max(0.0, d)

        results[cat] = {
            "spent": float(spent),
            "budget": float(budget),
            "avg_daily": float(avg_daily),
            "projected_total": float(proj_total),
            "will_exceed": bool(will_exceed),
            "days_to_exceed": days_to_exceed
        }

    # Include categories with budget but no spend
    for entry in budgets.get("categories", []):
        cat = entry["category"]
        if cat not in results:
            results[cat] = {
                "spent": 0.0,
                "budget": float(entry["amount"]),
                "avg_daily": 0.0,
                "projected_total": 0.0,
                "will_exceed": False,
                "days_to_exceed": None
            }

    return results


# -----------------------------------------------------------
#   2. CATEGORY STRESS TEST SIMULATOR
# -----------------------------------------------------------

def category_stress_test(exp_month: pd.DataFrame, budgets: dict, simulate_changes: dict):
    """
    Simulate category-level changes (e.g. +20% on Food).
    simulate_changes example: {"Food": 0.25} for +25%.
    """
    grouped = exp_month.groupby("category")["amount"].sum().to_dict()
    budget_map = {c['category']: float(c['amount']) for c in budgets.get("categories", [])}

    today = pd.Timestamp.today()
    start = today.replace(day=1)
    days_passed = (today - start).days + 1
    end = (start + pd.Timedelta(days=32)).replace(day=1) - pd.Timedelta(days=1)
    days_remaining = max((end - today).days, 0)

    results = {}

    for cat, budget in budget_map.items():
        spent = float(grouped.get(cat, 0.0))
        avg_daily = spent / max(days_passed, 1)

        pct = simulate_changes.get(cat, 0.0)
        new_avg = avg_daily * (1 + pct)

        projected = spent + new_avg * days_remaining

        results[cat] = {
            "spent": spent,
            "budget": budget,
            "change_pct": pct,
            "projected": projected,
            "delta_over_budget": projected - budget
        }

    total_projected = sum(v['projected'] for v in results.values())
    total_budget = float(budgets.get("total_budget", 0))
    overall_delta = total_projected - total_budget

    return {
        "per_category": results,
        "total_projected": total_projected,
        "overall_delta": overall_delta
    }


# -----------------------------------------------------------
#   3. DAILY CATEGORY HEATMAP BUILDER
# -----------------------------------------------------------

def build_daily_category_heatmap(exp_month: pd.DataFrame, fill_value=0.0):
    """
    Returns pivot table:
        index   = category
        columns = day of month
        values  = amount
    """
    if exp_month is None or exp_month.empty:
        return pd.DataFrame()

    df = exp_month.copy()
    df['day'] = df['date'].dt.day

    pivot = df.pivot_table(
        index="category",
        columns="day",
        values="amount",
        aggfunc="sum",
        fill_value=fill_value
    )

    # Ensure consistent ordering
    pivot = pivot.sort_index()
    pivot = pivot.reindex(sorted(pivot.columns), axis=1)

    return pivot


# -----------------------------------------------------------
#   4. BUDGET HEALTH INSIGHTS
# -----------------------------------------------------------

def generate_budget_health_insights(pred_results: dict):
    """
    Turn overspend prediction into human-friendly insights.
    """
    insights = []

    offenders = []
    for cat, r in pred_results.items():
        budget = r["budget"]
        projected = r["projected_total"]
        if budget > 0:
            pct = (projected / budget) * 100
            offenders.append((cat, pct, r))

    offenders.sort(key=lambda x: x[1], reverse=True)

    # Top 3 offenders
    for cat, pct, r in offenders[:3]:
        if pct > 100:
            days = r["days_to_exceed"]
            if days is None or days <= 0:
                insights.append(
                    f"🔴 **{cat}**: already exceeding or will exceed immediately ({pct-100:.1f}% over)."
                )
            else:
                insights.append(
                    f"🔴 **{cat}**: projected to exceed its budget by **{pct-100:.1f}%** in ~{int(days)} days."
                )

    if not insights:
        insights.append("🟢 All categories appear healthy at current pace.")

    insights.append("💡 Tip: Adjust budgets or reduce discretionary expenses to avoid end-month overshoot.")

    return insights


# -------------------------
# Budget model helpers (CRUD)
# -------------------------
def set_budget(category: Optional[str], amount: float, period: str = 'monthly', active: bool = True) -> int:
    from app.db import Budget, get_session
    """
    Create or update a budget.
    If a budget exists for the same category + period, update it (overwrite amount & active).
    If category is None -> total budget for the period.
    """
    if amount <= 0:
        raise ValueError("Budget amount must be positive")
    period = period if period in ('monthly', 'yearly') else 'monthly'
    sess = get_session()
    try:
        # find existing
        q = sess.query(Budget).filter(func.coalesce(Budget.category, '') == (category or ''), Budget.period == period)
        existing = q.first()
        if existing:
            existing.amount = float(amount)
            existing.active = bool(active)
            sess.commit()
            return existing.id
        b = Budget(category=category, amount=float(amount), period=period, active=bool(active))
        sess.add(b)
        sess.commit()
        return b.id
    except Exception:
        sess.rollback()
        raise
    finally:
        sess.close()

def get_budgets(active_only: bool = False) -> list:
    from app.db import Budget, get_session
    sess = get_session()
    try:
        q = sess.query(Budget).order_by(Budget.period, Budget.category.nullsfirst(), Budget.id.desc())
        if active_only:
            q = q.filter(Budget.active == True)
        rows = q.all()
        out = []
        for r in rows:
            out.append({
                'id': r.id,
                'category': r.category,
                'amount': float(r.amount),
                'period': r.period,
                'active': bool(r.active),
                'created_at': r.created_at.isoformat() if r.created_at else None
            })
        return out
    finally:
        sess.close()

def get_budget_for_category(category: Optional[str], period: str = 'monthly'):
    from app.db import Budget, get_session
    sess = get_session()
    try:
        r = sess.query(Budget).filter(func.coalesce(Budget.category, '') == (category or ''), Budget.period == period).first()
        if not r:
            return None
        return {
            'id': r.id,
            'category': r.category,
            'amount': float(r.amount),
            'period': r.period,
            'active': bool(r.active),
            'created_at': r.created_at.isoformat() if r.created_at else None
        }
    finally:
        sess.close()

def delete_budget(budget_id: int) -> bool:
    from app.db import Budget, get_session
    sess = get_session()
    try:
        b = sess.query(Budget).filter(Budget.id == budget_id).first()
        if not b:
            return False
        sess.delete(b)
        sess.commit()
        return True
    except Exception:
        sess.rollback()
        raise
    finally:
        sess.close()



def load_budget_df():
    """
    Loads budgets from DB and returns a clean Pandas DataFrame.
    """
    raw = get_budgets()  # list of dicts
    if not raw:
        return pd.DataFrame(columns=[
            "id", "category", "amount", "period", "active", "created_at"
        ])

    df = pd.DataFrame(raw)
    df["category"] = df["category"].replace({None: pd.NA})
    return df


def load_budgets():
    from app.db import engine
    """Return budgets in normalized dict format used by both tabs."""
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT * FROM budgets WHERE active = 1")).fetchall()

    if not rows:
        return {"total_budget": 0, "categories": []}

    # Convert SQL rows to dict
    df = pd.DataFrame(rows, columns=["id","category","amount","period","active","created_at"])

    # Total Budget = rows where category is NULL
    total_budget_row = df[df["category"].isna()]
    total_budget = float(total_budget_row["amount"].iloc[0]) if not total_budget_row.empty else 0

    # Category Budgets = rows where category is NOT NULL
    cat_rows = df[df["category"].notna()]
    categories = [
        {"category": row["category"], "amount": float(row["amount"])}
        for _, row in cat_rows.iterrows()
    ]

    return {"total_budget": total_budget, "categories": categories}



def save_total_budget(amount: float):
    """Save or update the total monthly budget."""
    return set_budget(None, amount)


def save_category_budget(category: str, amount: float):
    from app.db import engine
    with engine.connect() as conn:
        # deactivate existing entry
        conn.execute(text("""
            UPDATE budgets 
            SET active = 0 
            WHERE category = :c
        """), {"c": category})

        # insert new
        conn.execute(text("""
            INSERT INTO budgets (category, amount, period, active)
            VALUES (:c, :a, 'monthly', 1)
        """), {"c": category, "a": amount})

        conn.commit()