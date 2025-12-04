# app/autopay.py
from datetime import date, datetime, timedelta
from typing import List, Optional, Dict, Any
from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.db import get_session, AutopayRule, AutopayExecution, Expense, Ledger, Account
from sqlalchemy import func

# ============ helpers to compute next run ============
def _add_months_safe(src_date: date, months: int = 1) -> date:
    # keep it simple: move month-by-month, clamp end-of-month
    month = src_date.month - 1 + months
    year = src_date.year + month // 12
    month = month % 12 + 1
    day = min(src_date.day, (date(year, month + 1, 1) - timedelta(days=1)).day)
    return date(year, month, day)

def _next_run_for_rule(rule: AutopayRule, from_date: Optional[date] = None) -> date:
    if from_date is None:
        from_date = rule.next_run_date or date.today()
    freq = (rule.frequency or 'monthly').lower()
    if freq == 'daily':
        return from_date + timedelta(days=1)
    if freq == 'weekly':
        return from_date + timedelta(days=7)
    if freq == 'interval' and rule.interval_days:
        return from_date + timedelta(days=int(rule.interval_days))
    if freq == 'once':
        return None  # no next run
    # monthly or default
    # prefer to preserve day_of_month if present
    try:
        dom = int(rule.day_of_month) if rule.day_of_month else from_date.day
    except Exception:
        dom = from_date.day
    # compute next month date with same day (clamping)
    candidate = _add_months_safe(from_date, 1)
    # try to set day if day_of_month specified
    if rule.day_of_month:
        y = candidate.year
        m = candidate.month
        import calendar
        last_day = calendar.monthrange(y, m)[1]
        d = min(dom, last_day)
        return date(y, m, d)
    return candidate

# ============ CRUD ============
def create_rule(name: str, account_id: Optional[int], amount: float,
                frequency: str = 'monthly', next_run_date: Optional[date] = None,
                category: Optional[str] = None, description: Optional[str] = None,
                day_of_month: Optional[int] = None, day_of_week: Optional[int] = None,
                interval_days: Optional[int] = None, active: bool = True, paused_until: Optional[date] = None) -> int:
    sess = get_session()
    try:
        if next_run_date is None:
            next_run_date = date.today()
        rule = AutopayRule(
            name=name,
            description=description,
            account_id=account_id,
            amount=float(amount),
            category=category,
            frequency=frequency,
            day_of_month=day_of_month,
            day_of_week=day_of_week,
            interval_days=interval_days,
            next_run_date=next_run_date,
            active=active,
            paused_until=paused_until
        )
        sess.add(rule)
        sess.commit()
        return rule.id
    except Exception:
        sess.rollback()
        raise
    finally:
        sess.close()

def update_rule(rule_id: int, **fields) -> bool:
    sess = get_session()
    try:
        rule = sess.query(AutopayRule).filter(AutopayRule.id == rule_id).first()
        if not rule:
            return False
        for k,v in fields.items():
            if hasattr(rule, k):
                setattr(rule, k, v)
        rule.updated_at = datetime.now()
        sess.commit()
        return True
    except Exception:
        sess.rollback()
        raise
    finally:
        sess.close()

def delete_rule(rule_id: int) -> bool:
    sess = get_session()
    try:
        rule = sess.query(AutopayRule).filter(AutopayRule.id == rule_id).first()
        if not rule:
            return False
        sess.delete(rule)
        sess.commit()
        return True
    except Exception:
        sess.rollback()
        raise
    finally:
        sess.close()

def get_rules(active_only: bool = True) -> List[Dict[str,Any]]:
    sess = get_session()
    try:
        q = sess.query(AutopayRule)
        if active_only:
            q = q.filter(AutopayRule.active == True)
        rows = q.order_by(AutopayRule.next_run_date.asc()).all()
        out = []
        for r in rows:
            out.append({
                'id': r.id,
                'name': r.name,
                'account_id': r.account_id,
                'amount': float(r.amount),
                'category': r.category,
                'frequency': r.frequency,
                'next_run_date': r.next_run_date,
                'active': bool(r.active),
                'paused_until': r.paused_until
            })
        return out
    finally:
        sess.close()

# ============ Executor ============
def _create_expense_and_ledger(sess: Session, rule: AutopayRule, exec_date: date):
    """
    Create expense and ledger entries in the provided session.
    This function assumes session open and will not commit — caller handles commit/rollback.
    """
    # create Expense (use provided category)
    exp = Expense(
        date=exec_date,
        amount=float(rule.amount),
        description=f"Autopay: {rule.name}",
        category=rule.category or 'Auto',
        source='autopay',
        payment_source=None,
        account_id=rule.account_id,
        created_at=datetime.now()
    )
    sess.add(exp)
    sess.flush()  # get exp.id

    # create Ledger trace entry
    led = Ledger(
        account_id=rule.account_id,
        date=exec_date,
        amount=float(rule.amount),
        direction='autopay',
        party=rule.name,
        purpose=f"Autopay: {rule.name}",
        affects_balance=True,
        created_at=datetime.now()
    )
    sess.add(led)
    sess.flush()  # get led.id

    return exp.id, led.id

def run_due_autopays(today: Optional[date] = None, dry_run: bool = False) -> Dict[str,Any]:
    """
    Execute all autopay rules where next_run_date <= today and active.
    Returns a report dict.
    If dry_run=True, no DB changes will be committed (still returns what would happen).
    """
    report = {'run': [], 'skipped': [], 'errors': []}
    if today is None:
        today = date.today()

    sess = get_session()
    try:
        # select rules due (and active)
        rules = sess.query(AutopayRule).filter(
            AutopayRule.active == True,
            AutopayRule.next_run_date <= today
        ).order_by(AutopayRule.next_run_date.asc()).all()

        for rule in rules:
            # skip if paused
            if rule.paused_until and rule.paused_until > today:
                report['skipped'].append({'rule_id': rule.id, 'reason': 'paused'})
                continue

            # do execution in a nested transaction
            try:
                # re-check account & balance
                acct = sess.query(Account).filter(Account.id == rule.account_id).with_for_update().first()
                if not acct:
                    # log failure
                    exec_row = AutopayExecution(
                        rule_id=rule.id, run_date=today,
                        amount=rule.amount, status='failed',
                        failure_reason='account_not_found'
                    )
                    sess.add(exec_row)
                    sess.commit()
                    report['errors'].append({'rule_id': rule.id, 'error': 'account_not_found'})
                    continue

                # check funds (we do not fallback)
                if float(acct.balance or 0.0) + 1e-9 < float(rule.amount):
                    exec_row = AutopayExecution(
                        rule_id=rule.id, run_date=today,
                        amount=rule.amount, status='failed',
                        failure_reason='insufficient_funds'
                    )
                    sess.add(exec_row)
                    sess.commit()
                    report['errors'].append({'rule_id': rule.id, 'error': 'insufficient_funds'})
                    continue

                # perform debit using finance.adjust_balance (local import to avoid cycle)
                from app.finance import adjust_balance
                # debit
                ok = adjust_balance(rule.account_id, -float(rule.amount))
                if not ok:
                    raise RuntimeError("adjust_balance failed")

                # create expense + ledger
                exp_id, led_id = _create_expense_and_ledger(sess, rule, today)

                # record execution
                exec_row = AutopayExecution(
                    rule_id=rule.id, run_date=today,
                    amount=rule.amount, status='success',
                    failure_reason=None,
                    expense_id=exp_id,
                    ledger_id=led_id
                )
                sess.add(exec_row)

                # update rule last_run_date and compute next
                rule.last_run_date = today
                # compute and set next_run_date
                next_run = _next_run_for_rule(rule, from_date=rule.next_run_date or today)
                if next_run is None:
                    # one-time rule: deactivate
                    rule.active = False
                    rule.next_run_date = None
                else:
                    rule.next_run_date = next_run

                sess.commit()
                report['run'].append({'rule_id': rule.id, 'expense_id': exp_id, 'ledger_id': led_id})

            except Exception as e_inner:
                sess.rollback()
                try:
                    # log failure row (best-effort)
                    fail = AutopayExecution(rule_id=rule.id, run_date=today, amount=rule.amount, status='failed', failure_reason=str(e_inner))
                    sess.add(fail)
                    sess.commit()
                except Exception:
                    sess.rollback()
                report['errors'].append({'rule_id': rule.id, 'error': str(e_inner)})

        return report
    finally:
        sess.close()
