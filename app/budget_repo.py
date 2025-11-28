# app/budget_repo.py

import pandas as pd
from app.finance import get_budgets, set_budget, delete_budget
from app.db import engine
from sqlalchemy import text


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

