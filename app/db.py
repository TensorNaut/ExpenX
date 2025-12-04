# app/db.py
"""
Finalized DB models for ExpenX v1.0
- Principal change: InvestmentSettlement.principal_reduced is included (default 0.0)
- Keeps relationships + helper functions intact
- init_db() avoids circular imports by using local seed_default_accounts()
"""

import os
from datetime import datetime
from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Date, DateTime, Text, Boolean,
    ForeignKey, Index, func
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from app.schema_validator import validate_and_repair_schema

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

class LedgerPerson(Base):
    __tablename__ = 'ledger_persons'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), unique=True, nullable=False)
    contact = Column(String(128), nullable=True)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())

    entries = relationship("Ledger", back_populates="person", cascade="all, delete-orphan")

class Ledger(Base):
    __tablename__ = 'ledger'
    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey('accounts.id'), nullable=True)
    date = Column(Date, nullable=False, index=True)
    amount = Column(Float, nullable=False)
    direction = Column(String(16), nullable=False)  # 'lent' or 'borrowed' or 'transfer'
    party = Column(String(128))    # legacy free-text party
    person_id = Column(Integer, ForeignKey('ledger_persons.id'), nullable=True)  # new link
    due_date = Column(Date, nullable=True)
    purpose = Column(String(256), nullable=True)
    contact = Column(String(128), nullable=True)
    notes = Column(Text, nullable=True)
    affects_balance = Column(Boolean, default=False)
    remaining_amount = Column(Float, nullable=True)      # outstanding amount (NULL => treat as amount)
    interest_rate = Column(Float, default=0.0, nullable=True)
    status = Column(String(32), default='active')  # active|settled
    created_at = Column(DateTime, default=func.now())

    account = relationship("Account", back_populates="ledgers")
    person = relationship("LedgerPerson", back_populates="entries")

# Investment model
class Investment(Base):
    __tablename__ = 'investments'
    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey('accounts.id'), nullable=True)
    date = Column(Date, nullable=False, index=True)
    amount = Column(Float, nullable=False)                        # invested principal
    principal_remaining = Column(Float, nullable=True)            # outstanding principal (may be NULL for old rows)
    type = Column(String(64), nullable=True)
    risk = Column(String(32), nullable=True)
    mature_period_months = Column(Integer, nullable=True)
    maturity_date = Column(Date, nullable=True)
    expected_return_percent = Column(Float, nullable=True)
    status = Column(String(32), default='active')                 # active | partially_redeemed | redeemed
    notes = Column(Text, nullable=True)
    currency = Column(String(8), default='INR')
    quantity = Column(Float, nullable=True)                       # units / shares / grams
    unit_label = Column(String(64), nullable=True)                # 'shares', 'units', 'grams', 'kg'
    purchase_price_per_unit = Column(Float, nullable=True)        # price when bought
    current_price_per_unit = Column(Float, nullable=True)         # market price or manual
    current_value = Column(Float, nullable=True)                  # quantity * current_price or manual value
    last_updated = Column(DateTime, default=func.now(), onupdate=func.now())
    created_at = Column(DateTime, default=func.now())

    account = relationship("Account", back_populates="investments")

class InvestmentSettlement(Base):
    __tablename__ = 'investment_settlements'
    id = Column(Integer, primary_key=True, index=True)
    investment_id = Column(Integer, ForeignKey('investments.id'), nullable=False)
    date = Column(Date, nullable=False)
    amount = Column(Float, nullable=False)          # value redeemed/returned (monetary)
    principal_reduced = Column(Float, default=0.0, nullable=False)  # principal portion reduced
    account_id = Column(Integer, ForeignKey('accounts.id'), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())

    investment = relationship("Investment", backref="settlements")

class InvestmentSnapshot(Base):
    __tablename__ = 'investment_snapshots'
    id = Column(Integer, primary_key=True, index=True)
    snapshot_date = Column(Date, nullable=False, index=True)
    total_value = Column(Float, nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())

class Budget(Base):
    __tablename__ = 'budgets'
    id = Column(Integer, primary_key=True, index=True)
    category = Column(String(128), nullable=True, index=True)   # NULL => total monthly budget
    amount = Column(Float, nullable=False)
    period = Column(String(32), default='monthly')              # 'monthly' or 'yearly'
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())

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

def init_db(auto_repair_safe: bool = True):
    """Initialize DB schema and optionally validate and auto-repair."""
    # 1. Create tables if not exist
    Base.metadata.create_all(bind=engine, checkfirst=True)

    # 2. Ensure migrations table exists
    try:
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS migrations (
                    id SERIAL PRIMARY KEY,
                    filename TEXT NOT NULL,
                    applied_at TIMESTAMP DEFAULT now()
                );
            """))
            conn.commit()
    except Exception as e:
        print("⚠ Failed to ensure migrations table:", e)

    # 3. Schema validation
    try:
        from app.schema_validator import validate_and_repair_schema
        report = validate_and_repair_schema(engine, Base.metadata, auto_repair=auto_repair_safe)
        print("🔍 Schema validator report:", report)
    except Exception as e:
        print("⚠ Schema validator error (ignored):", e)

    # 4. Seed default accounts using built-in helper (NO finance imports!)
    try:
        created = seed_default_accounts()
        if created:
            print("✔ Default accounts created:", created)
    except Exception as e:
        print("⚠ Failed to seed default accounts:", e)



def get_session():
    """
    Return a new SQLAlchemy session.
    Caller should close() the session when done.
    """
    return SessionLocal()

def seed_default_accounts():
    """
    Create Main, Cash, and Credit Card accounts ONLY if missing.
    (Safe for circular imports because it uses Account directly.)
    """
    sess = SessionLocal()
    try:
        existing = {a.name.lower(): a for a in sess.query(Account).all()}
        created = []

        if "main" not in existing:
            a = Account(name="Main", currency="INR", balance=0.0, kind="bank")
            sess.add(a); sess.flush()
            created.append(("Main", a.id))

        if "cash" not in existing:
            a = Account(name="Cash", currency="INR", balance=0.0, kind="cash")
            sess.add(a); sess.flush()
            created.append(("Cash", a.id))

        if "credit card" not in existing:
            a = Account(name="Credit Card", currency="INR", balance=0.0, kind="card")
            sess.add(a); sess.flush()
            created.append(("Credit Card", a.id))

        sess.commit()
        return created

    except Exception as e:
        sess.rollback()
        print("⚠ Account seeding failed:", e)
        return []

    finally:
        sess.close()

