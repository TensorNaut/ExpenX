# app/tracker.py
from datetime import date as _date, datetime
from typing import Optional, List, Dict, Any
import os
import pickle
from sentence_transformers import SentenceTransformer
import pandas as pd

from app.db import get_session, Expense, engine, init_db
from app.finance import adjust_balance, get_accounts
from sqlalchemy import text

# Model paths (env / defaults)
DEFAULT_MODEL_PATH = os.getenv('EXPENX_BERT_PATH', 'models/new_bert_model')
DEFAULT_CLF_PATH = os.getenv('EXPENX_CLF_PATH', 'models/new_bert_classifier.pkl')

# Lazy-loaded model & clf
_MODEL = None
_CLF = None

def _load_model_and_clf(model_path=DEFAULT_MODEL_PATH, clf_path=DEFAULT_CLF_PATH):
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
    try:
        m, c = _load_model_and_clf(model_path=model_path, clf_path=clf_path)
        return (m is not None) and (c is not None)
    except Exception:
        return False

init_db()

def predict_category(description: str) -> Optional[str]:
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

def _map_payment_source_to_account_id(payment_source: Optional[str]) -> Optional[int]:
    """
    Map a payment_source string (account name) to account_id.
    Returns None for Cash / Credit Card / other non-account values.
    """
    if not payment_source:
        return None
    ps = payment_source.strip()
    if ps.lower() in ('cash', 'credit card', 'creditcard', 'card'):
        return None
    # map account name -> id via finance.get_accounts()
    try:
        accounts = get_accounts()
        for a in accounts:
            if a['name'].lower() == ps.lower():
                return a['id']
    except Exception:
        return None
    return None

def add_expense(amount: float,
                description: str,
                date: Optional[str|_date|datetime]=None,
                category: Optional[str]=None,
                source: str = 'manual',
                payment_source: Optional[str] = None,
                account_id: Optional[int] = None,
                ocr_confidence: Optional[float]=None,
                use_model_when_none: bool = True) -> int:
    """
    Add an expense and optionally debit a linked account.
    If category is None and use_model_when_none True => try predict.
    payment_source: string (account name / Cash / Credit Card). If it matches an account name and account_id not provided, we map it.
    """
    # parse date
    if date is None:
        date_val = datetime.now().date()
    elif isinstance(date, (datetime,)):
        date_val = date.date()
    elif isinstance(date, _date):
        date_val = date
    else:
        date_val = datetime.fromisoformat(str(date)).date()

    # category prediction
    final_category = category or 'Uncategorized'
    if (not category) and use_model_when_none:
        pred = predict_category(description)
        if pred:
            final_category = pred

    # resolve account_id from payment_source if needed
    resolved_account_id = account_id
    if not resolved_account_id:
        resolved_account_id = _map_payment_source_to_account_id(payment_source)

    sess = get_session()
    try:
        e = Expense(
            date=date_val,
            amount=float(amount),
            description=description,
            category=final_category,
            source=source,
            payment_source=payment_source or 'Main',
            ocr_confidence=ocr_confidence,
            account_id=resolved_account_id
        )
        sess.add(e)
        sess.commit()
        eid = e.id
    except Exception:
        sess.rollback()
        raise
    finally:
        sess.close()

    # debit linked account (if any). Use finance.adjust_balance helper.
    if resolved_account_id:
        # fetch account kind
        from app.finance import get_account_by_id
        acct = get_account_by_id(resolved_account_id)
        if acct:
            if acct['kind'] in ('bank','cash'):
                # debit
                adjust_balance(resolved_account_id, -float(amount))
            else:  # card
                # increase card outstanding (liability) instead of debit
                adjust_balance(resolved_account_id, float(amount))
    return eid

def get_expenses(limit: int = 1000, offset: int = 0) -> pd.DataFrame:
    query = "SELECT id, date as Date, amount as Amount, description as Description, category as Category, source, payment_source, account_id, ocr_confidence, created_at FROM expenses ORDER BY date DESC, id DESC LIMIT ? OFFSET ?"
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
            'PaymentSource': r.payment_source,
            'AccountId': r.account_id,
            'ocr_confidence': float(r.ocr_confidence) if r.ocr_confidence is not None else None,
            'created_at': r.created_at.isoformat() if r.created_at else None
        }
    finally:
        sess.close()

def update_expense(eid: int, **fields) -> bool:
    """
    Update an expense.
    This implementation will reconcile account balances if account_id or amount changes:
      - refund the old amount to old account (if any)
      - debit the new account with new amount (if any)
    """
    sess = get_session()
    try:
        r = sess.query(Expense).filter(Expense.id == eid).first()
        if not r:
            return False

        old_amount = float(r.amount or 0.0)
        old_account = r.account_id

        # parse & apply updates
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
        for k in ('description','category','source','ocr_confidence','payment_source','account_id'):
            if k in fields and fields[k] is not None:
                # If payment_source string is provided, also map account_id if account not explicitly passed
                if k == 'payment_source' and not fields.get('account_id'):
                    # attempt to resolve
                    mapped = _map_payment_source_to_account_id(fields['payment_source'])
                    if mapped:
                        r.account_id = mapped
                    else:
                        r.payment_source = fields['payment_source']
                else:
                    setattr(r, k, fields[k])
        # commit the updated expense
        sess.commit()

        # reconcile balances if needed (do outside of previous session for simplicity)
        new_amount = float(r.amount or 0.0)
        new_account = r.account_id

        # refund old_account by old_amount if old_account exists and differs from new_account or amount changed
        # then debit new_account by new_amount if needed
        # Only perform reconciliation if something changed
        if (old_account != new_account) or (old_amount != new_amount):
            # refund old
            if old_account:
                adjust_balance(old_account, float(old_amount))
            # debit new
            if new_account:
                adjust_balance(new_account, -float(new_amount))

        return True
    except Exception:
        sess.rollback()
        raise
    finally:
        sess.close()

def delete_expense_by_id(eid: int) -> bool:
    """
    Delete expense. As a conservative approach, when deleting, refund the amount back to the linked account (if any).
    """
    sess = get_session()
    try:
        r = sess.query(Expense).filter(Expense.id == eid).first()
        if not r:
            return False
        acct_id = r.account_id
        amt = float(r.amount or 0.0)
        sess.delete(r)
        sess.commit()
        # refund if account linked
        if acct_id:
            adjust_balance(acct_id, float(amt))
        return True
    except Exception:
        sess.rollback()
        raise
    finally:
        sess.close()

def get_category_options() -> list[str]:
    """
    Returns category options for dropdowns.
    Tries to read classifier labels (if available),
    then distinct categories from DB, plus defaults.
    """
    from sqlalchemy import distinct
    sess = get_session()
    try:
        options = []

        # try classifier labels
        _, clf = _load_model_and_clf()
        if clf is not None:
            classes = getattr(clf, 'classes_', None)
            if classes is not None:
                options = [str(c) for c in classes]

        # fetch distinct DB categories
        db_cats = []
        rows = sess.query(distinct(Expense.category)).all()
        db_cats = [r[0] for r in rows if r[0]]

        # merge + defaults
        seen = set(options)
        for c in db_cats:
            if c not in seen:
                options.append(c)
                seen.add(c)

        defaults = ['Food', 'Transport', 'Groceries', 'Bills', 'Entertainment',
                    'Rent', 'Subscription', 'Shopping', 'Uncategorized']
        for d in defaults:
            if d not in seen:
                options.append(d)
                seen.add(d)
        return options
    finally:
        sess.close()



