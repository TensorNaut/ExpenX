# app/db.py
"""
Database models and helpers for ExpenX.

Usage (one-time setup after cloning):
    python -c "from app.db import init_db, seed_default_accounts; init_db(); seed_default_accounts(); print('DB ready')"

This file defines:
- Account (id, name, currency, balance, kind)
- Expense (id, date, amount, description, category, payment_source, account_id, ...)
- Income
- Ledger
- Investment

Keep this file single-source-of-truth for schema migrations/sync for new users.
"""
import os
from datetime import datetime
from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Date, DateTime, Text, Boolean,
    ForeignKey, Index, func
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

# Config: DB path (env override supported)
DB_PATH = os.getenv('EXPENX_DB', 'data/expenses.db')
DB_URL = f"sqlite:///{DB_PATH}"

# Ensure directory exists
db_dir = os.path.dirname(DB_PATH)
if db_dir and not os.path.exists(db_dir):
    os.makedirs(db_dir, exist_ok=True)

# Engine + session factory
engine = create_engine(DB_URL, echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

Base = declarative_base()

# -------------------------
# Models
# -------------------------
class Account(Base):
    __tablename__ = 'accounts'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), unique=True, nullable=False)
    currency = Column(String(8), default='INR')
    balance = Column(Float, default=0.0)
    kind = Column(String(16), default='bank')  # 'bank' | 'cash' | 'card'
    created_at = Column(DateTime, default=func.now())

    # relationships
    incomes = relationship("Income", back_populates="account", cascade="all, delete-orphan")
    expenses = relationship("Expense", back_populates="account")
    ledgers = relationship("Ledger", back_populates="account")
    investments = relationship("Investment", back_populates="account")

class Expense(Base):
    __tablename__ = 'expenses'
    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False, index=True)
    amount = Column(Float, nullable=False)
    description = Column(Text)
    category = Column(String(128), index=True)
    source = Column(String(32), default='manual')
    ocr_confidence = Column(Float, nullable=True)
    created_at = Column(DateTime, default=func.now())

    # payment source: account name / 'Cash' / 'Credit Card'
    payment_source = Column(String(128), default='Main', nullable=False, index=True)

    # linkage to accounts table (nullable)
    account_id = Column(Integer, ForeignKey('accounts.id'), nullable=True)
    account = relationship("Account", back_populates="expenses")

class Income(Base):
    __tablename__ = 'income'
    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey('accounts.id'), nullable=False)
    date = Column(Date, nullable=False, index=True)
    amount = Column(Float, nullable=False)
    source = Column(String(128))
    description = Column(Text)
    created_at = Column(DateTime, default=func.now())

    account = relationship("Account", back_populates="incomes")

class Ledger(Base):
    __tablename__ = 'ledger'
    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey('accounts.id'), nullable=True)
    date = Column(Date, nullable=False, index=True)
    amount = Column(Float, nullable=False)
    direction = Column(String(32), nullable=False)   # 'lent' | 'borrowed' | 'transfer' | other
    party = Column(String(128))
    due_date = Column(Date, nullable=True)
    purpose = Column(String(256), nullable=True)
    contact = Column(String(128), nullable=True)
    notes = Column(Text, nullable=True)
    affects_balance = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())

    account = relationship("Account", back_populates="ledgers")

class Investment(Base):
    __tablename__ = 'investments'
    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey('accounts.id'), nullable=True)
    date = Column(Date, nullable=False, index=True)
    amount = Column(Float, nullable=False)  # principal
    description = Column(Text, nullable=True)
    type = Column(String(64), nullable=True)  # FD / MF / Stock / Bond / Crypto / Gold / SIP / etc.
    risk = Column(String(32), nullable=True)  # Low / Medium / High
    mature_period_months = Column(Integer, nullable=True)
    maturity_date = Column(Date, nullable=True)
    expected_return_percent = Column(Float, nullable=True)
    status = Column(String(32), default='active')  # active|matured|redeemed|sold
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())

    account = relationship("Account", back_populates="investments")

# -------------------------
# Indexes
# -------------------------
Index('idx_accounts_name', Account.name)
Index('idx_expenses_date', Expense.date)
Index('idx_expenses_payment_source', Expense.payment_source)
Index('idx_income_date', Income.date)
Index('idx_ledger_date', Ledger.date)
Index('idx_investments_date', Investment.date)

# -------------------------
# Helpers
# -------------------------
def init_db():
    """
    Create tables (if missing). Safe to call repeatedly.
    """
    Base.metadata.create_all(bind=engine)

def get_session():
    """
    Return a new SQLAlchemy session.
    Caller should close() the session when done.
    """
    return SessionLocal()

def seed_default_accounts():
    """
    Ensure default accounts exist: Main (bank), Cash (cash), Credit Card (card).
    Safe to call multiple times; it will not duplicate names.
    """
    sess = get_session()
    try:
        # use case-insensitive check
        existing = {a.name.lower(): a for a in sess.query(Account).all()}
        created = []
        if 'main' not in existing:
            a = Account(name='Main', currency='INR', balance=0.0, kind='bank')
            sess.add(a); sess.flush()
            created.append(('Main', a.id))
        if 'cash' not in existing:
            b = Account(name='Cash', currency='INR', balance=0.0, kind='cash')
            sess.add(b); sess.flush()
            created.append(('Cash', b.id))
        if 'credit card' not in existing and 'creditcard' not in existing:
            c = Account(name='Credit Card', currency='INR', balance=0.0, kind='card')
            sess.add(c); sess.flush()
            created.append(('Credit Card', c.id))
        if created:
            sess.commit()
        else:
            sess.rollback()
        return created  # list of (name, id) created
    except Exception:
        sess.rollback()
        raise
    finally:
        sess.close()

# # Optional: quick utility for schema inspection (helpful on GitHub READMEs/demos)
# if __name__ == "__main__":
#     print("Initializing DB and seeding default accounts (if missing)...")
#     init_db()
#     created = seed_default_accounts()
#     if created:
#         print("Created accounts:", created)
#     else:
#         print("Default accounts already exist.")
#     print("DB path:", DB_PATH)
