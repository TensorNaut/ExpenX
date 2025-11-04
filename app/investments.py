# app/investments.py
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any
from app.db import get_session, Investment, Account, init_db
from app.finance import adjust_balance, add_income  # adjust_balance used to debit on creation, add_income can be used on redeem
from sqlalchemy.orm import Session

init_db()

def create_investment(amount: float,
                      inv_type: str,
                      date_val: Optional[date] = None,
                      account_id: Optional[int] = None,
                      description: str = '',
                      risk: Optional[str] = None,
                      mature_period_months: Optional[int] = None,
                      expected_return_percent: Optional[float] = None,
                      debit_account: bool = False,
                      maturity_date: Optional[date] = None,
                      notes: Optional[str] = None) -> int:
    """
    Create an investment entry. If debit_account True and account_id provided,
    the account balance will be decreased by `amount` atomically.
    Returns investment id.
    """
    if date_val is None:
        date_val = datetime.now().date()
    sess: Session = get_session()
    try:
        # validate account
        acct = None
        if account_id:
            acct = sess.query(Account).filter(Account.id == account_id).first()
            if not acct:
                raise ValueError("Account not found")
            if debit_account:
                # ensure sufficient balance? not required but suggested
                # if acct.balance < amount: raise ValueError("Insufficient balance")
                acct.balance = float(acct.balance or 0.0) - float(amount)

        inv = Investment(
            account_id = account_id,
            date = date_val,
            amount = float(amount),
            description = description,
            type = inv_type,
            risk = risk,
            mature_period_months = mature_period_months,
            maturity_date = maturity_date,
            expected_return_percent = expected_return_percent,
            status = 'active',
            notes = notes
        )
        sess.add(inv)
        sess.commit()
        return inv.id
    except Exception:
        sess.rollback()
        raise
    finally:
        sess.close()

def list_investments(status: Optional[str]=None, account_id: Optional[int]=None, limit:int=500) -> List[Dict[str,Any]]:
    sess = get_session()
    try:
        q = sess.query(Investment).order_by(Investment.date.desc())
        if status:
            q = q.filter(Investment.status == status)
        if account_id:
            q = q.filter(Investment.account_id == account_id)
        rows = q.limit(limit).all()
        out = []
        for r in rows:
            out.append({
                'id': r.id,
                'date': r.date.isoformat(),
                'amount': float(r.amount),
                'type': r.type,
                'risk': r.risk,
                'maturity_date': r.maturity_date.isoformat() if r.maturity_date else None,
                'mature_period_months': r.mature_period_months,
                'expected_return_percent': r.expected_return_percent,
                'status': r.status,
                'account_id': r.account_id,
                'description': r.description,
                'notes': r.notes
            })
        return out
    finally:
        sess.close()

def redeem_investment(inv_id: int, redeem_amount: Optional[float] = None, credit_account: Optional[int] = None, create_income_record: bool = True) -> bool:
    """
    Mark investment as redeemed/sold. Optionally credit an account by redeem_amount (defaults to principal).
    If create_income_record True, an Income record is created via add_income (so account balance increases and Income table has record).
    Returns True on success.
    """
    sess = get_session()
    try:
        inv = sess.query(Investment).filter(Investment.id == inv_id).first()
        if not inv:
            return False
        if inv.status != 'active':
            # already redeemed/matured
            return False
        # default redeem amount = principal
        amt = float(redeem_amount) if redeem_amount is not None else float(inv.amount)

        # mark status
        inv.status = 'redeemed'
        # optionally create income/credit
        if credit_account:
            # use add_income to create income + credit account atomically
            # we import locally to avoid circular import at module import time
            from app.finance import add_income
            add_income(account_id=credit_account, amount=amt, source=f"Redeem: {inv.type}", date_val=datetime.now().date(), description=f"Redeemed investment id {inv.id}")
        sess.commit()
        return True
    except Exception:
        sess.rollback()
        raise
    finally:
        sess.close()
