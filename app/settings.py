# app/settings.py
from app.db import engine, SessionLocal
from sqlalchemy import text
import json
from datetime import datetime

# DEFAULTS used by UI if DB missing
DEFAULTS = {
    "default_total_budget_max": "100000",   # string stored in DB
    "default_category_budget_max": "20000",
    "currency": "INR",
    "date_format": "%Y-%m-%d",
    "enable_auto_backup": "true"
}

def ensure_settings_table():
    """Make sure settings table exists (safe to call repeatedly)."""
    sql = """
    CREATE TABLE IF NOT EXISTS settings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        key TEXT NOT NULL UNIQUE,
        value TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """
    with engine.connect() as conn:
        conn.execute(text(sql))
        conn.commit()

def get_setting(key: str, default=None):
    ensure_settings_table()
    with engine.connect() as conn:
        row = conn.execute(text("SELECT value FROM settings WHERE key = :k"), {"k": key}).fetchone()
    if row and row[0] is not None:
        return row[0]
    # fallback to DEFAULTS if provided
    if default is not None:
        return default
    return DEFAULTS.get(key)

def set_setting(key: str, value):
    ensure_settings_table()
    now = datetime.utcnow().isoformat(sep=' ')
    with engine.connect() as conn:
        # upsert pattern
        existing = conn.execute(text("SELECT 1 FROM settings WHERE key=:k"), {"k": key}).fetchone()
        if existing:
            conn.execute(text("UPDATE settings SET value=:v, updated_at=:u WHERE key=:k"), {"v": str(value), "u": now, "k": key})
        else:
            conn.execute(text("INSERT INTO settings (key, value, created_at, updated_at) VALUES (:k, :v, :u, :u)"),
                         {"k": key, "v": str(value), "u": now})
        conn.commit()

def get_all_settings():
    ensure_settings_table()
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT key, value FROM settings")).fetchall()
    return {r[0]: r[1] for r in rows}

def reset_to_defaults():
    ensure_settings_table()
    with engine.connect() as conn:
        for k, v in DEFAULTS.items():
            existing = conn.execute(text("SELECT 1 FROM settings WHERE key=:k"), {"k": k}).fetchone()
            now = datetime.utcnow().isoformat(sep=' ')
            if existing:
                conn.execute(text("UPDATE settings SET value=:v, updated_at=:u WHERE key=:k"), {"v": str(v), "u": now, "k": k})
            else:
                conn.execute(text("INSERT INTO settings (key, value, created_at, updated_at) VALUES (:k, :v, :u)"),
                             {"k": k, "v": str(v), "u": now})
        conn.commit()
