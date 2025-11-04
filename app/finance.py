# app/finance.py
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from app.db import get_session, Account, Income, Ledger, Expense, init_db
from sqlalchemy import func

# Ensure DB created
init_db()

def create_account(name: str, initial_balance: float = 0.0, currency: str = 'INR') -> int:
    sess: Session = get_session()
    try:
        acct = Account(name=name, balance=float(initial_balance), currency=currency)
        sess.add(acct)
        sess.commit()
        return acct.id
    except Exception:
        sess.rollback()
        raise
    finally:
        sess.close()

def get_accounts() -> List[Dict[str,Any]]:
    sess = get_session()
    try:
        rows = sess.query(Account).order_by(Account.name).all()
        return [{'id': r.id, 'name': r.name, 'balance': float(r.balance), 'currency': r.currency} for r in rows]
    finally:
        sess.close()

def get_account_by_id(account_id: int) -> Optional[Dict[str,Any]]:
    sess = get_session()
    try:
        a = sess.query(Account).filter(Account.id == account_id).first()
        if not a:
            return None
        return {'id': a.id, 'name': a.name, 'balance': float(a.balance), 'currency': a.currency}
    finally:
        sess.close()

def adjust_balance(account_id: int, delta: float) -> bool:
    """
    Atomically adjust account balance by delta (positive or negative).
    """
    sess = get_session()
    try:
        acct = sess.query(Account).filter(Account.id == account_id).with_for_update().first()
        if not acct:
            return False
        acct.balance = float(acct.balance or 0.0) + float(delta)
        sess.commit()
        return True
    except Exception:
        sess.rollback()
        raise
    finally:
        sess.close()

def add_income(account_id: int, amount: float, source: str, date_val: date = None, description: str = '') -> int:
    """
    Insert an income record and add amount to account balance atomically.
    """
    if date_val is None:
        date_val = datetime.now().date()
    sess = get_session()
    try:
        # validate account
        acct = sess.query(Account).filter(Account.id == account_id).first()
        if not acct:
            raise ValueError("Account not found")
        inc = Income(account_id=account_id, amount=float(amount), source=source, date=date_val, description=description)
        sess.add(inc)
        acct.balance = float(acct.balance or 0.0) + float(amount)
        sess.commit()
        return inc.id
    except Exception:
        sess.rollback()
        raise
    finally:
        sess.close()

def add_ledger_entry(account_id: Optional[int], amount: float, direction: str, party: str, date_val: date = None, due_date: Optional[date] = None, purpose: str = '', contact: str = '', notes: str = '', affects_balance: bool = False) -> int:
    """
    Add ledger entry. If affects_balance True and account_id provided, adjusts account balance:
      - direction == 'lent'  -> you gave money to someone => balance decreases by amount
      - direction == 'borrowed' -> you borrowed money => balance increases by amount
    """
    if direction not in ('lent','borrowed'):
        raise ValueError("direction must be 'lent' or 'borrowed'")
    if date_val is None:
        date_val = datetime.now().date()
    sess = get_session()
    try:
        if account_id:
            acct = sess.query(Account).filter(Account.id == account_id).first()
            if not acct:
                raise ValueError("Account not found")
        entry = Ledger(account_id=account_id, amount=float(amount), direction=direction, party=party, date=date_val, due_date=due_date, purpose=purpose, contact=contact, notes=notes, affects_balance=bool(affects_balance))
        sess.add(entry)
        # adjust balance if requested
        if affects_balance and account_id:
            if direction == 'lent':
                acct.balance = float(acct.balance or 0.0) - float(amount)
            else:  # borrowed
                acct.balance = float(acct.balance or 0.0) + float(amount)
        sess.commit()
        return entry.id
    except Exception:
        sess.rollback()
        raise
    finally:
        sess.close()

def get_ledger(account_id: Optional[int]=None, limit:int=200) -> List[Dict[str,Any]]:
    sess = get_session()
    try:
        q = sess.query(Ledger).order_by(Ledger.date.desc())
        if account_id:
            q = q.filter(Ledger.account_id == account_id)
        rows = q.limit(limit).all()
        return [{
            'id': r.id,
            'date': r.date.isoformat(),
            'amount': float(r.amount),
            'direction': r.direction,
            'party': r.party,
            'due_date': r.due_date.isoformat() if r.due_date else None,
            'purpose': r.purpose,
            'contact': r.contact,
            'notes': r.notes,
            'affects_balance': bool(r.affects_balance),
            'account_id': r.account_id
        } for r in rows]
    finally:
        sess.close()

def get_account_transactions(account_id: int, limit:int=200) -> List[Dict[str,Any]]:
    """
    Combine income + expenses + ledger-affecting entries for a simple account ledger view.
    """
    sess = get_session()
    try:
        # incomes
        incs = sess.query(Income).filter(Income.account_id == account_id).all()
        exps = sess.query(Expense).filter(Expense.account_id == account_id).all()
        led = sess.query(Ledger).filter(Ledger.account_id == account_id, Ledger.affects_balance == True).all()

        events = []
        for r in incs:
            events.append({'type':'income', 'date': r.date, 'amount': float(r.amount), 'desc': r.source or r.description})
        for r in exps:
            events.append({'type':'expense', 'date': r.date, 'amount': -float(r.amount), 'desc': r.description})
        for r in led:
            amt = float(r.amount) if r.direction == 'borrowed' else -float(r.amount)
            events.append({'type':'ledger', 'date': r.date, 'amount': amt, 'desc': f"{r.direction} - {r.party}"})
        # sort desc by date
        events.sort(key=lambda x: x['date'], reverse=True)
        # limit
        return events[:limit]
    finally:
        sess.close()
