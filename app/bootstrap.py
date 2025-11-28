from sqlalchemy import text
from app.db import engine, init_db
from app.finance import create_account

def bootstrap():
    """
    Runs after DB init.
    Creates default accounts if missing.
    """

    # 1. Initialize DB
    init_db(auto_repair_safe=True)

    # 2. Create default accounts if missing
    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM accounts")).fetchone()[0]

    if count == 0:
        print("⚙ Creating default system accounts...")
        create_account("Main", balance=0.0, currency="INR", kind="bank")
        create_account("Cash", balance=0.0, currency="INR", kind="cash")
        create_account("Credit Card", balance=0.0, currency="INR", kind="card")
        print("✔ Default accounts created.")
