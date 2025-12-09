# app/finance.py
from datetime import datetime, date
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy.orm import Session
from app.db import get_session, Account, Income, Ledger, Expense, Budget
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError


def create_account(name: str, initial_balance: float = 0.0, currency: str = 'INR', kind: str = 'bank') -> int:
    """
    Create account. name must be unique (case-insensitive).
    kind: 'bank'|'cash'|'card'
    """
    name = str(name).strip()
    if not name:
        raise ValueError("Account name cannot be empty")
    kind = kind if kind in ('bank','cash','card') else 'bank'
    sess: Session = get_session()
    try:
        # check duplicate (case-insensitive)
        exists = sess.query(Account).filter(func.lower(Account.name) == name.lower()).first()
        if exists:
            raise ValueError(f"Account with name '{name}' already exists")
        acct = Account(name=name, balance=float(initial_balance), currency=currency, kind=kind)
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
        rows = sess.query(Account).order_by(Account.id).all()
        out = []
        for r in rows:
            kind = getattr(r, 'kind', 'bank')  # fallback if column missing
            out.append({
                'id': r.id,
                'name': r.name,
                'balance': float(r.balance),
                'currency': r.currency,
                'kind': kind
            })
        return out
    finally:
        sess.close()

def get_account_by_id(account_id: int) -> Optional[Dict[str,Any]]:
    sess = get_session()
    try:
        a = sess.query(Account).filter(Account.id == account_id).first()
        if not a:
            return None
        return {
            'id': a.id,
            'name': a.name,
            'balance': float(a.balance),
            'currency': a.currency,
            'kind': getattr(a, 'kind', 'bank')
        }
    finally:
        sess.close()

def get_account_by_name(name: str) -> Optional[Dict[str,Any]]:
    sess = get_session()
    try:
        a = sess.query(Account).filter(func.lower(Account.name) == name.lower()).first()
        if not a:
            return None
        return {
            'id': a.id,
            'name': a.name,
            'balance': float(a.balance),
            'currency': a.currency,
            'kind': getattr(a, 'kind', 'bank')
        }
    finally:
        sess.close()
    

def adjust_balance(account_id: int, delta: float, sess: Optional[Session] = None) -> bool:
    """
    Adjust balance by delta. For bank/cash: positive increases assets.
    For card: we use balance field to store outstanding amount (positive = owed).

    If `sess` is provided, the update happens in that session (no commit/close).
    If `sess` is None, this function manages its own session (commit/close).
    """
    own_session = False
    if sess is None:
        sess = get_session()
        own_session = True

    try:
        acct = sess.query(Account).filter(Account.id == account_id).with_for_update().first()
        if not acct:
            if own_session:
                sess.rollback()
            return False
        acct.balance = float(acct.balance or 0.0) + float(delta)
        # commit only if we own the session
        if own_session:
            sess.commit()
        return True
    except Exception:
        if own_session:
            sess.rollback()
        raise
    finally:
        if own_session:
            sess.close()

def add_income(account_id: int, amount: float, source: str, date_val: date = None, description: str = '') -> int:
    if date_val is None:
        date_val = datetime.now().date()
    sess = get_session()
    try:
        acct = sess.query(Account).filter(Account.id == account_id).first()
        if not acct:
            raise ValueError("Account not found")
        inc = Income(account_id=account_id, amount=float(amount), source=source, date=date_val, description=description)
        sess.add(inc)
        # For income, always increase account balance for bank/cash.
        # If account is card and you record income into card, it will reduce outstanding (uncommon).
        if acct.kind in ('bank','cash'):
            acct.balance = float(acct.balance or 0.0) + float(amount)
        else:
            # treating income to card as a payment: reduce outstanding
            acct.balance = float(acct.balance or 0.0) - float(amount)
        sess.commit()
        return inc.id
    except Exception:
        sess.rollback()
        raise
    finally:
        sess.close()

def transfer_between_accounts(from_account_id: int, to_account_id: int, amount: float, description: str = '') -> bool:
    """
    Atomic transfer:
      - from_account: balance decreases if bank/cash; if from_account is card, paying from card is unusual but will increase card outstanding (allowed but logical check recommended)
      - to_account: balance increases if bank/cash; if to_account is card, paying card (i.e., transferring money to card) reduces outstanding (we treat as reduction)
    The function tries to interpret semantics sensibly:
      - subtract from 'from' according to its kind, add to 'to' according to its kind.
    """
    if from_account_id == to_account_id:
        raise ValueError("From and To account must be different")
    if amount <= 0:
        raise ValueError("Amount must be positive")

    sess = get_session()
    try:
        a_from = sess.query(Account).filter(Account.id == from_account_id).with_for_update().first()
        a_to = sess.query(Account).filter(Account.id == to_account_id).with_for_update().first()
        if not a_from or not a_to:
            raise ValueError("Account(s) not found")

        # Determine deltas:
        # From account delta: bank/cash -> -amount, card -> +amount (borrowing on card)
        if a_from.kind in ('bank','cash'):
            delta_from = -float(amount)
        else:  # card
            delta_from = float(amount)  # using card to send money increases outstanding (rare)

        # To account delta: bank/cash -> +amount, card -> -amount (paying card reduces outstanding)
        if a_to.kind in ('bank','cash'):
            delta_to = float(amount)
        else:  # card
            delta_to = -float(amount)

        a_from.balance = float(a_from.balance or 0.0) + delta_from
        a_to.balance = float(a_to.balance or 0.0) + delta_to

        # write a Ledger entry for transparent record (optional)
        entry = Ledger(account_id=from_account_id, amount=float(amount), direction='transfer', party=a_to.name,
                       date=datetime.now().date(), purpose=description or f"Transfer to {a_to.name}",
                       affects_balance=True)
        sess.add(entry)
        sess.commit()
        return True
    except Exception:
        sess.rollback()
        raise
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

def delete_account(account_id: int) -> bool:
    """
    Delete account if it has no associated transactions.
    """
    sess = get_session()
    try:
        acct = sess.query(Account).filter(Account.id == account_id).first()
        if not acct:
            return False
        # Check for associated transactions
        has_income = sess.query(Income).filter(Income.account_id == account_id).first() is not None
        has_expense = sess.query(Expense).filter(Expense.account_id == account_id).first() is not None
        has_ledger = sess.query(Ledger).filter(Ledger.account_id == account_id).first() is not None
        if has_income or has_expense or has_ledger:
            print("Warning: This account has associated transactions and may not be fully deleted.")
            # Optionally, you can still delete the account but keep the transactions
            sess.delete(acct)
            sess.commit()
            return False
        sess.delete(acct)
        sess.commit()
        return True
    except Exception:
        sess.rollback()
        raise
    finally:
        sess.close()

def settle_credit_card(card_account_id: int, from_account_id: int, amount: float, note: Optional[str] = None) -> bool:
    """
    Pay off (partially or fully) a credit card balance using another account.
    - card_account_id: the account with kind='card'
    - from_account_id: the paying account (bank/cash)
    - amount: payment amount
    - note: optional description
    Adjusts balances accordingly:
      - card balance decreases (reduces outstanding)
      - payer account balance decreases (spending cash)
    """
    if amount <= 0:
        raise ValueError("Amount must be positive")
    if card_account_id == from_account_id:
        raise ValueError("Cannot settle using same account")

    sess = get_session()
    try:
        card = sess.query(Account).filter(Account.id == card_account_id).with_for_update().first()
        payer = sess.query(Account).filter(Account.id == from_account_id).with_for_update().first()

        if not card or not payer:
            raise ValueError("Invalid accounts")
        if card.kind != 'card':
            raise ValueError("Target account is not a credit card")
        if payer.kind not in ('bank', 'cash'):
            raise ValueError("Payer account must be bank or cash")

        outstanding = float(card.balance or 0.0)
        if amount > outstanding + 1e-9:
            raise ValueError(f"Cannot pay more than outstanding (₹{outstanding:.2f})")

        # Adjust balances
        payer.balance -= float(amount)
        card.balance -= float(amount)  # reduces outstanding

        # Record a ledger-style entry for transparency
        entry = Ledger(
            account_id=from_account_id,
            amount=float(amount),
            direction='transfer',
            party=card.name,
            date=datetime.now().date(),
            purpose=note or f"Credit Card Payment ({card.name})",
            affects_balance=True,
        )
        sess.add(entry)

        sess.commit()
        return True
    except Exception:
        sess.rollback()
        raise
    finally:
        sess.close()

# -------------------------
# Income read helpers
# -------------------------
def get_income(limit: int = 1000, offset: int = 0) -> list[dict]:
    """
    Return recent income records as a list of dicts:
      id, account_id, date, amount, source, description, created_at
    """
    sess = get_session()
    try:
        rows = sess.query(Income).order_by(Income.date.desc(), Income.id.desc()).limit(limit).offset(offset).all()
        out = []
        for r in rows:
            out.append({
                'id': r.id,
                'account_id': r.account_id,
                'date': r.date.isoformat() if r.date else None,
                'amount': float(r.amount) if r.amount is not None else 0.0,
                'source': r.source,
                'description': r.description,
                'created_at': r.created_at.isoformat() if r.created_at else None
            })
        return out
    finally:
        sess.close()

