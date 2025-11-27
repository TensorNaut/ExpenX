# app/budget_engine.py

import pandas as pd
from datetime import date


def compute_budget(expenses_df, budgets_df, start_date: date, end_date: date):
    """
    Pure budget computation — returns a clean object:
    {
        total_budget,
        total_spent,
        total_remaining,
        per_category: {
            cat: {budget, spent, remaining, pct_used}
        }
    }
    """

    # Ensure date column is datetime
    expenses_df["Date"] = pd.to_datetime(expenses_df["Date"]).dt.date

    # Filter expenses within period
    df_period = expenses_df[
        (expenses_df["Date"] >= start_date) &
        (expenses_df["Date"] <= end_date)
    ]

    # Total spent
    total_spent = df_period["Amount"].sum()

    # ----- Total Budget -----
    tb = budgets_df[
        budgets_df["category"].isna() &
        (budgets_df["period"] == "monthly") &
        (budgets_df["active"] == True)
    ]

    total_budget = float(tb["amount"].iloc[0]) if not tb.empty else None
    total_remaining = (
        total_budget - total_spent
        if total_budget is not None
        else None
    )

    # ----- Category Budgets -----
    per_category = {}
    cat_rows = budgets_df[
        budgets_df["category"].notna() &
        (budgets_df["period"] == "monthly") &
        (budgets_df["active"] == True)
    ]

    for _, row in cat_rows.iterrows():
        cat = row["category"]
        budget_amt = row["amount"]

        spent_cat = df_period[df_period["Category"] == cat]["Amount"].sum()
        remaining = budget_amt - spent_cat
        pct_used = (spent_cat / budget_amt * 100) if budget_amt > 0 else 0

        per_category[cat] = {
            "budget": budget_amt,
            "spent": spent_cat,
            "remaining": remaining,
            "pct_used": pct_used
        }

    return {
        "total_budget": total_budget,
        "total_spent": total_spent,
        "total_remaining": total_remaining,
        "per_category": per_category
    }


def generate_budget_insights(status):
    """
    Generate human-readable insights based on status output from compute_budget.
    """
    insights = []
    tb = status["total_budget"]
    ts = status["total_spent"]

    # ---------- TOTAL BUDGET INSIGHTS ----------
    if tb:
        pct_total = (ts / tb * 100) if tb > 0 else 0

        if pct_total >= 120:
            insights.append("🔥 You massively overspent your total budget this month.")
        elif pct_total >= 100:
            insights.append("⚠ You have reached or exceeded your total monthly budget.")
        elif pct_total >= 80:
            insights.append("⚠ You're close to exceeding your total monthly budget.")

    # ---------- CATEGORY INSIGHTS ----------
    for cat, info in status["per_category"].items():
        pct = info["pct_used"]

        if pct >= 120:
            insights.append(f"🔥 {cat} budget exceeded by a large margin.")
        elif pct >= 100:
            insights.append(f"⚠ You've exceeded your budget for {cat}.")
        elif pct >= 80:
            insights.append(f"⚠ You’re close to exceeding the {cat} budget.")

    return insights
