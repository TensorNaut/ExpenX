# app/budget_repo.py

import pandas as pd
from app.finance import get_budgets, set_budget, delete_budget


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


def save_total_budget(amount: float):
    """Save or update the total monthly budget."""
    return set_budget(None, amount)


def save_category_budget(category: str, amount: float):
    """Save or update category-wise budget."""
    return set_budget(category, amount)
