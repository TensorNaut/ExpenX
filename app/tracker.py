# app/tracker.py
from datetime import date as _date, datetime
from typing import Optional, List, Dict, Any
import os
import pickle
from sentence_transformers import SentenceTransformer
import pandas as pd

from sqlalchemy import distinct
from app.db import get_session, Expense, engine, init_db

# Default model and classifier paths (change via env vars if needed)
DEFAULT_MODEL_PATH = os.getenv('EXPENX_BERT_PATH', 'models/new_bert_model')
DEFAULT_CLF_PATH = os.getenv('EXPENX_CLF_PATH', 'models/new_bert_classifier.pkl')

# Lazy-loaded globals
_MODEL = None
_CLF = None

def _load_model_and_clf(model_path=DEFAULT_MODEL_PATH, clf_path=DEFAULT_CLF_PATH):
    """
    Internal loader — caches the model and classifier in module globals.
    Returns (model, clf) where either may be None on failure.
    """
    global _MODEL, _CLF
    if _MODEL is None:
        try:
            _MODEL = SentenceTransformer(model_path)
        except Exception:
            _MODEL = None
    if _CLF is None:
        try:
            with open(clf_path, 'rb') as f:
                _CLF = pickle.load(f)
        except Exception:
            _CLF = None
    return _MODEL, _CLF

def load_model(model_path=DEFAULT_MODEL_PATH, clf_path=DEFAULT_CLF_PATH) -> bool:
    """
    Public function to eagerly load and cache the model+classifier.
    Returns True if at least one of model or classifier loaded successfully.
    """
    try:
        m, c = _load_model_and_clf(model_path=model_path, clf_path=clf_path)
        return (m is not None) and (c is not None)
    except Exception:
        return False

# ensure DB/tables exist
init_db()

def predict_category(description: str) -> Optional[str]:
    """
    Predict a category string for the given description using the local model.
    Returns predicted label or None if prediction not possible.
    This lazy-loads the model and classifier on first call, but you may call load_model()
    from the app to pre-warm the model.
    """
    if not description or not description.strip():
        return None
    try:
        model, clf = _load_model_and_clf()
        if model is None or clf is None:
            return None
        emb = model.encode([description])
        pred = clf.predict(emb)[0]
        return str(pred)
    except Exception:
        return None

def get_category_options() -> List[str]:
    """
    Returns category options list. Classifier labels first (if available),
    followed by distinct DB categories, then sensible defaults, and 'Uncategorized'.
    """
    options = []
    try:
        _, clf = _load_model_and_clf()
        if clf is not None:
            classes = getattr(clf, 'classes_', None)
            if classes is not None:
                options = [str(c) for c in classes]
    except Exception:
        options = []

    # get distinct categories from DB
    db_cats = []
    try:
        sess = get_session()
        rows = sess.query(distinct(Expense.category)).all()
        sess.close()
        db_cats = [r[0] for r in rows if r[0]]
    except Exception:
        db_cats = []

    # merge preserving order
    seen = set()
    merged = []
    for c in options:
        if c and c not in seen:
            merged.append(c)
            seen.add(c)
    for c in db_cats:
        if c and c not in seen:
            merged.append(c)
            seen.add(c)

    # sensible defaults
    defaults = ['Food', 'Transport', 'Groceries', 'Bills', 'Entertainment', 'Rent', 'Subscription']
    for d in defaults:
        if d not in seen:
            merged.append(d)
            seen.add(d)

    if 'Uncategorized' not in seen:
        merged.append('Uncategorized')

    return merged

def add_expense(amount: float,
                description: str,
                date: Optional[str|_date|datetime]=None,
                category: Optional[str]=None,
                source: str = 'manual',
                ocr_confidence: Optional[float]=None,
                use_model_when_none: bool = True) -> int:
    """
    Add an expense to the SQLite DB.
    - If `category` is None and `use_model_when_none` is True, the model will predict.
    - If category is provided (including custom string), it will be used as-is.
    Returns inserted expense id.
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

    final_category = category or 'Uncategorized'

    if (not category) and use_model_when_none:
        pred = predict_category(description)
        if pred:
            final_category = pred

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
    except Exception:
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

def update_expense(eid: int, **fields) -> bool:
    """
    Update allowed fields on an existing expense.
    """
    sess = get_session()
    try:
        r = sess.query(Expense).filter(Expense.id == eid).first()
        if not r:
            return False
        # date
        if 'date' in fields and fields['date'] is not None:
            val = fields['date']
            if isinstance(val, str):
                r.date = datetime.fromisoformat(val).date()
            elif isinstance(val, _date):
                r.date = val
            elif isinstance(val, datetime):
                r.date = val.date()
        if 'amount' in fields and fields['amount'] is not None:
            r.amount = float(fields['amount'])
        for k in ('description','category','source','ocr_confidence'):
            if k in fields and fields[k] is not None:
                setattr(r, k, fields[k])
        sess.commit()
        return True
    except Exception:
        sess.rollback()
        raise
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
