from sqlalchemy import text
from app.db import engine, init_db, seed_default_accounts

def bootstrap():
    print("Running bootstrap...")
    init_db(auto_repair_safe=True)

    created = seed_default_accounts()
    if created:
        print("Default accounts created:", created)

