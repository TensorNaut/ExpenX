# app/ledger.py
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any
from app.db import get_session, LedgerPerson, Ledger, init_db
from app.finance import adjust_balance, get_account_by_id
from sqlalchemy import func, desc
from sqlalchemy.orm import Session

init_db()

def create_person(name: str, contact: Optional[str]=None, note: Optional[str]=None) -> int:
    name = name.strip()
    if not name:
        raise ValueError("Person name cannot be empty")
    sess: Session = get_session()
    try:
        # ensure unique name (case-insensitive)
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
        # Option: prevent deletion if person has entries (safer)
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

def add_entry_for_person(person_id: Optional[int],
                         amount: float,
                         direction: str,   # 'lent' or 'borrowed'
                         date_val: Optional[date] = None,
                         due_date: Optional[date] = None,
                         purpose: Optional[str] = None,
                         contact: Optional[str] = None,
                         notes: Optional[str] = None,
                         affects_balance: bool = False,
                         account_id: Optional[int] = None) -> int:
    """
    Creates a ledger entry linked to a person (person_id can be None, and party free-text used).
    If affects_balance True and account_id provided, adjusts account via adjust_balance:
      - direction 'lent' -> you gave money to someone -> balance decreases (bank/cash: -amount; card: +amount)
      - direction 'borrowed' -> you received money from someone -> balance increases (bank/cash: +amount; card: -amount)
    """
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
            direction = direction,
            party = None,
            person_id = person_id,
            due_date = due_date,
            purpose = purpose,
            contact = contact,
            notes = notes,
            affects_balance = bool(affects_balance),
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

    # adjust linked account if requested (outside session to reuse adjust_balance)
    if affects_balance and account_id:
        # fetch account kind via get_account_by_id
        acct = get_account_by_id(account_id)
        if acct:
            kind = acct.get('kind','bank')
            # semantics:
            # - if direction == 'lent': you gave money -> bank/cash balance -= amount ; card outstanding += amount
            # - if direction == 'borrowed': you received money -> bank/cash balance += amount ; card outstanding -= amount
            if direction == 'lent':
                if kind in ('bank','cash'):
                    adjust_balance(account_id, -float(amount))
                else:  # card
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
                'direction': r.direction,
                'due_date': r.due_date.isoformat() if r.due_date else None,
                'purpose': r.purpose,
                'contact': r.contact,
                'notes': r.notes,
                'affects_balance': bool(r.affects_balance),
                'account_id': r.account_id,
                'status': r.status
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
        if settled:
            e.status = 'settled'
        else:
            e.status = 'active'
        sess.commit()
        return True
    except Exception:
        sess.rollback()
        raise
    finally:
        sess.close()

def get_person_summary(person_id: int) -> Dict[str,Any]:
    """
    Returns totals for a person (lent_sum, borrowed_sum, net, open_dues_count)
    """
    sess = get_session()
    try:
        lent = sess.query(func.coalesce(func.sum(Ledger.amount), 0.0)).filter(Ledger.person_id==person_id, Ledger.direction=='lent').scalar() or 0.0
        borrowed = sess.query(func.coalesce(func.sum(Ledger.amount), 0.0)).filter(Ledger.person_id==person_id, Ledger.direction=='borrowed').scalar() or 0.0
        open_dues = sess.query(func.count(Ledger.id)).filter(Ledger.person_id==person_id, Ledger.status != 'settled').scalar() or 0
        last_activity = sess.query(Ledger).filter(Ledger.person_id==person_id).order_by(Ledger.date.desc()).first()
        last_date = last_activity.date.isoformat() if last_activity and last_activity.date else None
        return {
            'person_id': person_id,
            'lent': float(lent),
            'borrowed': float(borrowed),
            'net': float(lent - borrowed),
            'open_dues_count': int(open_dues),
            'last_activity': last_date
        }
    finally:
        sess.close()

def overall_summary() -> Dict[str,Any]:
    """
    Returns totals across all ledger entries.
    """
    sess = get_session()
    try:
        total_lent = sess.query(func.coalesce(func.sum(Ledger.amount), 0.0)).filter(Ledger.direction=='lent').scalar() or 0.0
        total_borrowed = sess.query(func.coalesce(func.sum(Ledger.amount), 0.0)).filter(Ledger.direction=='borrowed').scalar() or 0.0
        net = float(total_lent - total_borrowed)
        open_dues = sess.query(func.count(Ledger.id)).filter(Ledger.status != 'settled').scalar() or 0
        return {'total_lent': float(total_lent), 'total_borrowed': float(total_borrowed), 'net': net, 'open_dues': int(open_dues)}
    finally:
        sess.close()

def due_reminders(days_ahead: int = 7) -> Dict[str, List[Dict[str,Any]]]:
    """
    Returns two lists: incoming (lent -> people owe you) and outgoing (borrowed -> you owe others) due within days_ahead.
    """
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
    """
    Returns list of persons with lent, borrowed and net sorted by net descending.
    """
    sess = get_session()
    try:
        persons = sess.query(LedgerPerson).all()
        out=[]
        for p in persons:
            s = get_person_summary(p.id)
            out.append({'id': p.id, 'name': p.name, 'contact': p.contact, 'lent': s['lent'], 'borrowed': s['borrowed'], 'net': s['net'], 'open_dues': s['open_dues_count'], 'last_activity': s['last_activity']})
        out.sort(key=lambda x: x['net'], reverse=True)
        return out[:limit]
    finally:
        sess.close()
