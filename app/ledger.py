# app/ledger.py
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db import get_session, LedgerPerson, Ledger, init_db
from app.finance import adjust_balance, get_account_by_id

# ensure tables exist
init_db()

# Helper to get column references safely (fallbacks)
def _col_remaining_amount():
    return getattr(Ledger, 'remaining_amount', Ledger.amount)

def _get_remaining_from_row(row):
    return float(getattr(row, 'remaining_amount', row.amount))

# -----------------------
# Person CRUD
# -----------------------
def create_person(name: str, contact: Optional[str] = None, note: Optional[str] = None) -> int:
    name = name.strip()
    if not name:
        raise ValueError("Person name cannot be empty")
    sess: Session = get_session()
    try:
        existing = sess.query(LedgerPerson).filter(func.lower(LedgerPerson.name) == name.lower()).first()
        if existing:
            raise ValueError("Person with this name already exists")
        p = LedgerPerson(name=name, contact=contact, note=note)
        sess.add(p)
        sess.commit()
        return p.id
    except Exception:
        sess.rollback()
        raise
    finally:
        sess.close()

def update_person(person_id: int, name: Optional[str]=None, contact: Optional[str]=None, note: Optional[str]=None) -> bool:
    sess = get_session()
    try:
        p = sess.query(LedgerPerson).filter(LedgerPerson.id==person_id).first()
        if not p:
            return False
        if name:
            p.name = name.strip()
        if contact is not None:
            p.contact = contact
        if note is not None:
            p.note = note
        sess.commit()
        return True
    except Exception:
        sess.rollback()
        raise
    finally:
        sess.close()

def delete_person(person_id: int) -> bool:
    sess = get_session()
    try:
        p = sess.query(LedgerPerson).filter(LedgerPerson.id==person_id).first()
        if not p:
            return False
        entries_count = sess.query(func.count(Ledger.id)).filter(Ledger.person_id==person_id).scalar()
        if entries_count and entries_count > 0:
            raise ValueError("Cannot delete person with existing ledger entries")
        sess.delete(p)
        sess.commit()
        return True
    except Exception:
        sess.rollback()
        raise
    finally:
        sess.close()

def list_persons() -> List[Dict[str,Any]]:
    sess = get_session()
    try:
        rows = sess.query(LedgerPerson).order_by(LedgerPerson.name).all()
        out = []
        for r in rows:
            out.append({
                'id': r.id,
                'name': r.name,
                'contact': r.contact,
                'note': r.note,
                'created_at': r.created_at.isoformat() if r.created_at else None
            })
        return out
    finally:
        sess.close()

# -----------------------
# Ledger entries (create, query, settle)
# -----------------------
def add_entry_for_person(person_id: Optional[int],
                         amount: float,
                         direction: str,   # 'lent' or 'borrowed' or 'transfer'
                         date_val: Optional[date] = None,
                         due_date: Optional[date] = None,
                         purpose: Optional[str] = None,
                         contact: Optional[str] = None,
                         notes: Optional[str] = None,
                         affects_balance: bool = False,
                         account_id: Optional[int] = None,
                         interest_rate: Optional[float] = 0.0) -> int:
    if direction not in ('lent','borrowed','transfer'):
        raise ValueError("direction must be 'lent' or 'borrowed' or 'transfer'")

    if date_val is None:
        date_val = datetime.now().date()

    sess = get_session()
    try:
        e = Ledger(
            account_id = account_id,
            date = date_val,
            amount = float(amount),
            # remaining_amount may or may not exist in DB; set attribute when creating
            remaining_amount = float(amount) if hasattr(Ledger, 'remaining_amount') else None,
            direction = direction,
            party = None,
            person_id = person_id,
            due_date = due_date,
            purpose = purpose,
            contact = contact,
            notes = notes,
            affects_balance = bool(affects_balance),
            interest_rate = float(interest_rate) if hasattr(Ledger, 'interest_rate') else None,
            status = 'active'
        )
        sess.add(e)
        sess.commit()
        eid = e.id
    except Exception:
        sess.rollback()
        raise
    finally:
        sess.close()

    # Immediate account adjustment if requested
    if affects_balance and account_id:
        acct = get_account_by_id(account_id)
        if acct:
            kind = acct.get('kind','bank')
            if direction == 'lent':
                if kind in ('bank','cash'):
                    adjust_balance(account_id, -float(amount))
                else:
                    adjust_balance(account_id, float(amount))
            elif direction == 'borrowed':
                if kind in ('bank','cash'):
                    adjust_balance(account_id, float(amount))
                else:
                    adjust_balance(account_id, -float(amount))
    return eid

def get_entries_by_person(person_id: int, include_settled: bool = False, limit: int = 500) -> List[Dict[str,Any]]:
    sess = get_session()
    try:
        q = sess.query(Ledger).filter(Ledger.person_id == person_id)
        if not include_settled:
            q = q.filter(Ledger.status != 'settled')
        q = q.order_by(Ledger.date.desc()).limit(limit)
        rows = q.all()
        out = []
        for r in rows:
            out.append({
                'id': r.id,
                'date': r.date.isoformat() if r.date else None,
                'amount': float(r.amount),
                'remaining_amount': _get_remaining_from_row(r),
                'direction': r.direction,
                'due_date': r.due_date.isoformat() if r.due_date else None,
                'purpose': r.purpose,
                'contact': r.contact,
                'notes': r.notes,
                'affects_balance': bool(r.affects_balance),
                'account_id': r.account_id,
                'status': r.status,
                'interest_rate': float(getattr(r, 'interest_rate', 0.0) or 0.0)
            })
        return out
    finally:
        sess.close()

def mark_entry_settled(entry_id: int, settled: bool = True) -> bool:
    sess = get_session()
    try:
        e = sess.query(Ledger).filter(Ledger.id == entry_id).first()
        if not e:
            return False
        e.status = 'settled' if settled else 'active'
        if settled:
            # set remaining_amount if supported
            if hasattr(e, 'remaining_amount'):
                e.remaining_amount = 0.0
        sess.commit()
        return True
    except Exception:
        sess.rollback()
        raise
    finally:
        sess.close()

def settle_entry(entry_id: int, settle_amount: float, account_id: Optional[int] = None, note: Optional[str] = None) -> bool:
    """
    Partially or fully settle a ledger entry.
    - settle_amount must be > 0 and <= remaining_amount.
    - account_id: account used for the settlement (affects balances).
    """
    if settle_amount <= 0:
        raise ValueError("settle_amount must be > 0")

    # We'll read necessary fields inside the session to avoid detached-instance errors
    sess = get_session()
    try:
        e = sess.query(Ledger).filter(Ledger.id == entry_id).with_for_update().first()
        if not e:
            raise ValueError("Entry not found")
        # get direction & remaining locally
        direction_local = e.direction
        remaining_local = float(getattr(e, 'remaining_amount', e.amount))
        if settle_amount > remaining_local + 1e-9:
            raise ValueError("Settle amount cannot exceed remaining amount")

        # update DB fields
        if hasattr(e, 'remaining_amount'):
            e.remaining_amount = remaining_local - float(settle_amount)
            if e.remaining_amount <= 1e-9:
                e.remaining_amount = 0.0
                e.status = 'settled'
        else:
            # if remaining_amount column doesn't exist, mark settled only when full settlement
            if abs(settle_amount - e.amount) <= 1e-9:
                e.status = 'settled'
        if note:
            e.notes = (e.notes or "") + f"\n[settle:{datetime.now().isoformat()}] {note}"
        sess.commit()
    except Exception:
        sess.rollback()
        raise
    finally:
        sess.close()

    # Adjust account AFTER commit, using direction_local
    if account_id:
        acct = get_account_by_id(account_id)
        if not acct:
            raise ValueError("Account not found")
        kind = acct.get('kind','bank')

        if direction_local == 'lent':
            # person paid you: bank/cash +, card -
            if kind in ('bank','cash'):
                adjust_balance(account_id, float(settle_amount))
            else:
                adjust_balance(account_id, -float(settle_amount))
        elif direction_local == 'borrowed':
            # you repaid: bank/cash -, card +
            if kind in ('bank','cash'):
                adjust_balance(account_id, -float(settle_amount))
            else:
                adjust_balance(account_id, float(settle_amount))
    return True

# -----------------------
# Summaries & reminders
# -----------------------
def get_person_summary(person_id: int) -> Dict[str,Any]:
    sess = get_session()
    try:
        lent_total = sess.query(func.coalesce(func.sum(Ledger.amount),0.0)).filter(Ledger.person_id==person_id, Ledger.direction=='lent').scalar() or 0.0
        borrowed_total = sess.query(func.coalesce(func.sum(Ledger.amount),0.0)).filter(Ledger.person_id==person_id, Ledger.direction=='borrowed').scalar() or 0.0

        rem_col = _col_remaining_amount()
        lent_rem = sess.query(func.coalesce(func.sum(rem_col),0.0)).filter(Ledger.person_id==person_id, Ledger.direction=='lent', Ledger.status!='settled').scalar() or 0.0
        borrowed_rem = sess.query(func.coalesce(func.sum(rem_col),0.0)).filter(Ledger.person_id==person_id, Ledger.direction=='borrowed', Ledger.status!='settled').scalar() or 0.0

        open_dues = sess.query(func.count(Ledger.id)).filter(Ledger.person_id==person_id, Ledger.status != 'settled').scalar() or 0
        last_activity = sess.query(Ledger).filter(Ledger.person_id==person_id).order_by(Ledger.date.desc()).first()
        last_date = last_activity.date.isoformat() if last_activity and last_activity.date else None
        return {
            'person_id': person_id,
            'lent': float(lent_total),
            'borrowed': float(borrowed_total),
            'lent_open': float(lent_rem),
            'borrowed_open': float(borrowed_rem),
            'net': float(lent_rem - borrowed_rem),
            'open_dues_count': int(open_dues),
            'last_activity': last_date
        }
    finally:
        sess.close()

def overall_summary() -> Dict[str,Any]:
    sess = get_session()
    try:
        rem_col = _col_remaining_amount()
        total_lent_open = sess.query(func.coalesce(func.sum(rem_col),0.0)).filter(Ledger.direction=='lent', Ledger.status!='settled').scalar() or 0.0
        total_borrowed_open = sess.query(func.coalesce(func.sum(rem_col),0.0)).filter(Ledger.direction=='borrowed', Ledger.status!='settled').scalar() or 0.0
        net = float(total_lent_open - total_borrowed_open)
        open_dues = sess.query(func.count(Ledger.id)).filter(Ledger.status != 'settled').scalar() or 0
        return {'total_lent': float(total_lent_open), 'total_borrowed': float(total_borrowed_open), 'net': net, 'open_dues': int(open_dues)}
    finally:
        sess.close()

def due_reminders(days_ahead: int = 7) -> Dict[str, List[Dict[str,Any]]]:
    today = datetime.now().date()
    end = today + timedelta(days=days_ahead)
    sess = get_session()
    try:
        incoming = sess.query(Ledger).filter(Ledger.direction=='lent', Ledger.due_date != None, Ledger.due_date <= end, Ledger.status != 'settled').order_by(Ledger.due_date.asc()).all()
        outgoing = sess.query(Ledger).filter(Ledger.direction=='borrowed', Ledger.due_date != None, Ledger.due_date <= end, Ledger.status != 'settled').order_by(Ledger.due_date.asc()).all()
        def serialize(rows):
            out=[]
            for r in rows:
                out.append({
                    'id': r.id,
                    'person_id': r.person_id,
                    'party': r.party,
                    'amount': float(r.amount),
                    'remaining_amount': _get_remaining_from_row(r),
                    'due_date': r.due_date.isoformat() if r.due_date else None,
                    'days_left': (r.due_date - today).days if r.due_date else None,
                    'purpose': r.purpose,
                    'status': r.status
                })
            return out
        return {'incoming': serialize(incoming), 'outgoing': serialize(outgoing)}
    finally:
        sess.close()

def person_leaderboard(limit:int=100) -> List[Dict[str,Any]]:
    sess = get_session()
    try:
        persons = sess.query(LedgerPerson).all()
        out=[]
        for p in persons:
            s = get_person_summary(p.id)
            out.append({'id': p.id, 'name': p.name, 'contact': p.contact, 'lent_open': s['lent_open'], 'borrowed_open': s['borrowed_open'], 'net': s['net'], 'open_dues': s['open_dues_count'], 'last_activity': s['last_activity']})
        out.sort(key=lambda x: x['net'], reverse=True)
        return out[:limit]
    finally:
        sess.close()
