# app/db.py
import os
from datetime import datetime
from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Date, DateTime, Text, Boolean,
    ForeignKey, Index
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from sqlalchemy.sql import func

DB_PATH = os.getenv('EXPENX_DB', 'data/expenses.db')
DB_URL = f"sqlite:///{DB_PATH}"

# ensure directory exists
db_dir = os.path.dirname(DB_PATH)
if db_dir and not os.path.exists(db_dir):
    os.makedirs(db_dir, exist_ok=True)

engine = create_engine(DB_URL, echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

class Account(Base):
    __tablename__ = 'accounts'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), unique=True, nullable=False)
    currency = Column(String(8), default='INR')
    balance = Column(Float, default=0.0)
    created_at = Column(DateTime, default=func.now())

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

    # NEW: payment source (Account name / Cash / Credit Card). Default 'Main'.
    payment_source = Column(String(128), default='Main', nullable=False, index=True)

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
    direction = Column(String(16), nullable=False)  # 'lent' or 'borrowed'
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
    amount = Column(Float, nullable=False)
    description = Column(Text, nullable=True)
    type = Column(String(64), nullable=True)
    risk = Column(String(32), nullable=True)
    mature_period_months = Column(Integer, nullable=True)
    maturity_date = Column(Date, nullable=True)
    expected_return_percent = Column(Float, nullable=True)
    status = Column(String(32), default='active')
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())

    account = relationship("Account", back_populates="investments")

# Indexes
Index('idx_accounts_name', Account.name)
Index('idx_expenses_date', Expense.date)
Index('idx_expenses_payment_source', Expense.payment_source)
Index('idx_income_date', Income.date)
Index('idx_ledger_date', Ledger.date)
Index('idx_investments_date', Investment.date)

def init_db():
    Base.metadata.create_all(bind=engine)

def get_session():
    return SessionLocal()
