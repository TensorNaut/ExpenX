# app/db.py
from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Date, DateTime, Text, func, Index
)
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.exc import SQLAlchemyError
import os

DB_PATH = os.getenv('EXPENX_DB', 'data/expenses.db')
DB_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(DB_URL, echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

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

# create indexes (if desired, SQLAlchemy creates simple indexes above)
Index('idx_expenses_date', Expense.date)
Index('idx_expenses_category', Expense.category)

def init_db():
    Base.metadata.create_all(bind=engine)

# Small helper to get sessions
def get_session():
    return SessionLocal()
