# app/db.py
"""
Final Production-Ready Database Layer for ExpenX v1.0
-----------------------------------------------------

✔ PostgreSQL compatible
✔ SQLite compatible
✔ No circular imports
✔ Index-optimized
✔ Clean model structure
✔ Complete helper utilities
✔ Safe migrations table
✔ Compatible with your entire existing codebase

This is the final DB schema freeze for ExpenX v1.0
"""

import os
from datetime import datetime, date
from contextlib import contextmanager
from typing import Optional, List, Tuple

from sqlalchemy import (
    create_engine, Column, Integer, String, Text, Float, Date, DateTime,
    Boolean, ForeignKey, Index, func, text as sql_text
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker, Session
from sqlalchemy.exc import OperationalError

# ---------------------------------------------------------------------
# DATABASE CONFIG
# ---------------------------------------------------------------------

DB_URL = os.environ.get("EXPENX_DATABASE_URL", "sqlite:///data/expenses.db")

engine = create_engine(
    DB_URL,
    connect_args={"check_same_thread": False} if DB_URL.startswith("sqlite") else {},
    future=True,
    echo=False,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

Base = declarative_base()


# ---------------------------------------------------------------------
#  HELPER FUNCTIONS
# ---------------------------------------------------------------------

def get_session() -> Session:
    return SessionLocal()

def get_engine():
    return engine

def is_sqlite() -> bool:
    return engine.dialect.name == "sqlite"

def is_postgres() -> bool:
    return engine.dialect.name in ("postgresql", "postgres")

def now() -> datetime:
    """Consistent timestamp usage."""
    return datetime.utcnow()

@contextmanager
def atomic_session():
    """Context manager for auto-commit/rollback sessions."""
    sess = get_session()
    try:
        yield sess
        sess.commit()
    except:
        sess.rollback()
        raise
    finally:
        sess.close()


# ---------------------------------------------------------------------
#  ORM MODELS — FINAL v1.0 SCHEMA
# ---------------------------------------------------------------------

# ====== ACCOUNTS ======================================================
class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (
        Index("idx_accounts_name", "name"),
        Index("idx_accounts_kind", "kind"),
    )

    id = Column(Integer, primary_key=True)
    name = Column(String(128), nullable=False, unique=True)
    currency = Column(String(8), nullable=True, default="INR")
    balance = Column(Float, nullable=True, default=0.0)
    kind = Column(String(32), nullable=True, default="bank")
    created_at = Column(DateTime, default=now)

    expenses = relationship("Expense", back_populates="account", cascade="save-update")
    incomes = relationship("Income", back_populates="account", cascade="save-update")
    ledger_entries = relationship("Ledger", back_populates="account", cascade="save-update")
    investments = relationship("Investment", back_populates="account", cascade="save-update")


# ====== EXPENSES ======================================================
class Expense(Base):
    __tablename__ = "expenses"
    __table_args__ = (
        Index("idx_exp_date", "date"),
        Index("idx_exp_cat", "category"),
        Index("idx_exp_acc", "account_id"),
    )

    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False)
    amount = Column(Float, nullable=False)
    description = Column(Text)
    category = Column(String(128))
    source = Column(String(64))
    ocr_confidence = Column(Float)
    created_at = Column(DateTime, default=now)
    payment_source = Column(String(64), nullable=False, default="Main")
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="SET NULL"))

    account = relationship("Account", back_populates="expenses")


# ====== INCOME ========================================================
class Income(Base):
    __tablename__ = "income"
    __table_args__ = (
        Index("idx_inc_date", "date"),
        Index("idx_inc_acc", "account_id"),
    )

    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="SET NULL"))
    date = Column(Date, nullable=False)
    amount = Column(Float, nullable=False)
    source = Column(String(128))
    description = Column(Text)
    created_at = Column(DateTime, default=now)

    account = relationship("Account", back_populates="incomes")


# ====== LEDGER PERSON =================================================
class LedgerPerson(Base):
    __tablename__ = "ledger_persons"
    __table_args__ = (
        Index("idx_person_name", "name"),
    )

    id = Column(Integer, primary_key=True)
    name = Column(String(128), nullable=False)
    contact = Column(String(128))
    note = Column(Text)
    created_at = Column(DateTime, default=now)

    ledger_entries = relationship("Ledger", back_populates="person", cascade="save-update")


# ====== LEDGER ========================================================
class Ledger(Base):
    __tablename__ = "ledger"
    __table_args__ = (
        Index("idx_ledger_person", "person_id"),
        Index("idx_ledger_status", "status"),
        Index("idx_ledger_remaining", "remaining_amount"),
    )

    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="SET NULL"))
    date = Column(Date, nullable=False)
    amount = Column(Float, nullable=False)
    direction = Column(String(32), nullable=False)
    party = Column(String(256))
    person_id = Column(Integer, ForeignKey("ledger_persons.id", ondelete="SET NULL"))
    due_date = Column(Date)
    purpose = Column(Text)
    contact = Column(String(128))
    notes = Column(Text)
    affects_balance = Column(Boolean, default=True)
    remaining_amount = Column(Float)
    interest_rate = Column(Float)
    status = Column(String(32))
    created_at = Column(DateTime, default=now)

    account = relationship("Account", back_populates="ledger_entries")
    person = relationship("LedgerPerson", back_populates="ledger_entries")


# ====== INVESTMENTS ====================================================
class Investment(Base):
    __tablename__ = "investments"
    __table_args__ = (
        Index("idx_inv_status", "status"),
        Index("idx_inv_acc", "account_id"),
    )

    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="SET NULL"))
    date = Column(Date, nullable=False)
    amount = Column(Float, nullable=False)
    principal_remaining = Column(Float)
    type = Column(String(64))
    risk = Column(String(64))
    mature_period_months = Column(Integer)
    maturity_date = Column(Date)
    expected_return_percent = Column(Float)
    status = Column(String(32))
    notes = Column(Text)
    currency = Column(String(8), default="INR")

    quantity = Column(Float)
    unit_label = Column(String(32))
    purchase_price_per_unit = Column(Float)
    current_price_per_unit = Column(Float)
    current_value = Column(Float)
    last_updated = Column(DateTime)
    created_at = Column(DateTime, default=now)

    account = relationship("Account", back_populates="investments")
    settlements = relationship("InvestmentSettlement", back_populates="investment", cascade="all, delete-orphan")


class InvestmentSettlement(Base):
    __tablename__ = "investment_settlements"
    id = Column(Integer, primary_key=True)
    investment_id = Column(Integer, ForeignKey("investments.id", ondelete="CASCADE"))
    date = Column(Date, nullable=False)
    amount = Column(Float, nullable=False)
    principal_reduced = Column(Float, nullable=False, default=0.0)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="SET NULL"))
    notes = Column(Text)
    created_at = Column(DateTime, default=now)

    investment = relationship("Investment", back_populates="settlements")
    account = relationship("Account")


# ====== BUDGETS ========================================================
class Budget(Base):
    __tablename__ = "budgets"
    __table_args__ = (
        Index("idx_budget_cat", "category"),
        Index("idx_budget_period", "period"),
    )

    id = Column(Integer, primary_key=True)
    category = Column(String(128))
    amount = Column(Float, nullable=False)
    period = Column(String(32), default="monthly")
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=now)


# ====== AUTOPAY ========================================================
class AutopayRule(Base):
    __tablename__ = "autopay_rules"
    __table_args__ = (
        Index("idx_autopay_next", "next_run_date"),
        Index("idx_autopay_active", "active"),
    )

    id = Column(Integer, primary_key=True)
    name = Column(String(256), nullable=False)
    description = Column(Text)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="SET NULL"))
    amount = Column(Float, nullable=False)
    category = Column(String(128))
    currency = Column(String(8), default="INR")

    frequency = Column(String(32), default="monthly")
    day_of_month = Column(Integer)
    day_of_week = Column(Integer)
    interval_days = Column(Integer)
    next_run_date = Column(Date, nullable=False)
    last_run_date = Column(Date)

    active = Column(Boolean, default=True)
    paused_until = Column(Date)
    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)

    executions = relationship("AutopayExecution", back_populates="rule", cascade="all, delete-orphan")


class AutopayExecution(Base):
    __tablename__ = "autopay_executions"
    __table_args__ = (
        Index("idx_exec_run_date", "run_date"),
    )

    id = Column(Integer, primary_key=True)
    rule_id = Column(Integer, ForeignKey("autopay_rules.id", ondelete="CASCADE"))
    run_date = Column(Date, nullable=False)
    amount = Column(Float, nullable=False)
    status = Column(String(32), nullable=False)
    failure_reason = Column(Text)
    expense_id = Column(Integer, ForeignKey("expenses.id"))
    ledger_id = Column(Integer, ForeignKey("ledger.id"))
    created_at = Column(DateTime, default=now)

    rule = relationship("AutopayRule", back_populates="executions")


# ---------------------------------------------------------------------
#  DATABASE INITIALIZATION
# ---------------------------------------------------------------------

def _create_migrations_table_if_missing(conn):
    """Create migrations table with dialect-aware SQL."""
    if is_sqlite():
        conn.execute(sql_text("""
            CREATE TABLE IF NOT EXISTS migrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """))
    elif is_postgres():
        conn.execute(sql_text("""
            CREATE TABLE IF NOT EXISTS migrations (
                id SERIAL PRIMARY KEY,
                filename TEXT NOT NULL,
                applied_at TIMESTAMP DEFAULT NOW()
            );
        """))
    else:
        conn.execute(sql_text("""
            CREATE TABLE IF NOT EXISTS migrations (
                id INTEGER PRIMARY KEY,
                filename TEXT NOT NULL,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """))


def seed_default_accounts() -> List[Tuple[str, int]]:
    """Ensure Main, Cash, Credit Card exist."""
    sess = get_session()
    created = []
    try:
        existing = {a.name.lower(): a for a in sess.query(Account).all()}

        defaults = [
            ("Main", "INR", 0.0, "bank"),
            ("Cash", "INR", 0.0, "cash"),
            ("Credit Card", "INR", 0.0, "card"),
        ]

        for name, cur, bal, kind in defaults:
            if name.lower() not in existing:
                a = Account(name=name, currency=cur, balance=bal, kind=kind)
                sess.add(a); sess.flush()
                created.append((name, a.id))

        sess.commit()
        return created
    except:
        sess.rollback()
        raise
    finally:
        sess.close()


def init_db(auto_repair_safe: bool = True):
    """Initialize DB, create tables, ensure migrations table & default accounts."""
    Base.metadata.create_all(bind=engine, checkfirst=True)

    # Create migrations table
    try:
        with engine.connect() as conn:
            _create_migrations_table_if_missing(conn)
            conn.commit()
    except Exception as e:
        print("⚠ migrations table creation failed:", e)

    # Default accounts
    try:
        created = seed_default_accounts()
        if created:
            print("✔ Default accounts created:", created)
    except Exception as e:
        print("⚠ seed_default_accounts failed:", e)


# ---------------------------------------------------------------------
# DEBUG tool
# ---------------------------------------------------------------------

def inspect_schema():
    """Print tables and columns."""
    from sqlalchemy import inspect
    insp = inspect(engine)
    for t in insp.get_table_names():
        print("\nTABLE:", t)
        for col in insp.get_columns(t):
            print("   ", col["name"], "-", col["type"], "nullable:", col["nullable"])

