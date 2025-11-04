# app/tracker.py
from datetime import date as _date, datetime
from typing import Optional, List, Dict, Any
import os
import pickle
from sentence_transformers import SentenceTransformer
import pandas as pd

from app.db import get_session, Expense, engine, init_db

# Default model and classifier paths (change as needed)
DEFAULT_MODEL_PATH = os.getenv('EXPENX_BERT_PATH', 'models/new_bert_model')
DEFAULT_CLF_PATH = os.getenv('EXPENX_CLF_PATH', 'models/new_bert_classifier.pkl')

# Lazy-loaded globals
_MODEL = None
_CLF = None

def _load_model_and_clf(model_path=DEFAULT_MODEL_PATH, clf_path=DEFAULT_CLF_PATH):
    """
    Load & cache SentenceTransformer model and classifier (pickle).
    This is lazy-loaded to avoid reloading model for each call.
    """
    global _MODEL, _CLF
    if _MODEL is None:
        # load model
        _MODEL = SentenceTransformer(model_path)
    if _CLF is None:
        with open(clf_path, 'rb') as f:
            _CLF = pickle.load(f)
    return _MODEL, _CLF

# ensure DB/tables exist
init_db()

def add_expense(amount: float,
                description: str,
                date: Optional[str|_date|datetime]=None,
                category: Optional[str]=None,
                source: str = 'manual',
                ocr_confidence: Optional[float]=None,
                use_model: bool = True) -> int:
    """
    Add an expense to the SQLite DB.
    - amount: float
    - description: text
    - date: ISO string (YYYY-MM-DD) or datetime.date or datetime; defaults to today
    - category: if provided, it will be used; otherwise, auto-predict if model available and use_model=True
    - returns: inserted expense id
    """
    # parse date input
    if date is None:
        date_val = datetime.now().date()
    elif isinstance(date, (datetime,)):
        date_val = date.date()
    elif isinstance(date, _date):
        date_val = date
    else:
        # assume string
        date_val = datetime.fromisoformat(str(date)).date()

    # If no category provided, try to predict using local model
    final_category = category or 'Uncategorized'
    if (not category) and use_model:
        try:
            model, clf = _load_model_and_clf()
            emb = model.encode([description])
            pred = clf.predict(emb)[0]
            final_category = str(pred)
        except Exception as ex:
            # If model loading/prediction fails, fallback gracefully
            # Optionally log exception to a logger
            final_category = 'Uncategorized'

    sess = get_session()
    try:
        e = Expense(
            date = date_val,
            amount = float(amount),
            description = description,
            category = final_category,
            source = source,
            ocr_confidence = ocr_confidence
        )
        sess.add(e)
        sess.commit()
        eid = e.id
        return eid
    except Exception as ex:
        sess.rollback()
        raise
    finally:
        sess.close()

def get_expenses(limit: int = 1000, offset: int = 0) -> pd.DataFrame:
    """
    Return expenses as a pandas DataFrame with columns:
    id, Date, Amount, Description, Category, Source, ocr_confidence, created_at
    Sorted by Date desc, then id desc.
    """
    # Use pandas read_sql for convenience
    query = "SELECT id, date as Date, amount as Amount, description as Description, category as Category, source, ocr_confidence, created_at FROM expenses ORDER BY date DESC, id DESC LIMIT ? OFFSET ?"
    df = pd.read_sql_query(query, engine, params=(limit, offset), parse_dates=['Date','created_at'])
    return df

def get_expense_by_id(eid: int) -> Optional[Dict[str, Any]]:
    sess = get_session()
    try:
        r = sess.query(Expense).filter(Expense.id == eid).first()
        if not r:
            return None
        return {
            'id': r.id,
            'Date': r.date.isoformat() if r.date else None,
            'Amount': float(r.amount) if r.amount is not None else None,
            'Description': r.description,
            'Category': r.category,
            'Source': r.source,
            'ocr_confidence': float(r.ocr_confidence) if r.ocr_confidence is not None else None,
            'created_at': r.created_at.isoformat() if r.created_at else None
        }
    finally:
        sess.close()

def delete_expense_by_id(eid: int) -> bool:
    sess = get_session()
    try:
        r = sess.query(Expense).filter(Expense.id == eid).first()
        if not r:
            return False
        sess.delete(r)
        sess.commit()
        return True
    except Exception:
        sess.rollback()
        raise
    finally:
        sess.close()
