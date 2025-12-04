# app/investments.py
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db import get_session, Investment, InvestmentSettlement, init_db
# from app.finance import get_account_by_id, adjust_balance

# ensure metadata / tables exist
# init_db()

# unit mapping
UNIT_LABELS = {
    'Stock': ('shares', True),
    'Mutual Fund': ('units', True),
    'MF': ('units', True),
    'Bond': ('units', True),
    'FD': ('₹', False),
    'Gold': ('grams', True),
    'Silver': ('kg', True),
    'Commodity': ('units', True),
    'Crypto': ('coins', True),
    'SIP': ('units', True),
    'Other': ('units', False)
}

def _unit_label_for_type(inv_type: str):
    if not inv_type:
        return (None, False)
    inv_type = inv_type.strip()
    for k, v in UNIT_LABELS.items():
        if inv_type.lower() == k.lower():
            return v
    return ('units', True)

# -------------------------
# Create investment (ORM)
# -------------------------
def create_investment(amount: float,
                      inv_type: str = "Other",
                      date_val: Optional[date] = None,
                      account_id: Optional[int] = None,
                      description: Optional[str] = None,
                      risk: Optional[str] = None,
                      mature_period_months: Optional[int] = None,
                      expected_return_percent: Optional[float] = None,
                      debit_account: bool = False,
                      maturity_date: Optional[date] = None,
                      notes: Optional[str] = None,
                      quantity: Optional[float] = None,
                      purchase_price_per_unit: Optional[float] = None,
                      currency: str = "INR") -> int:
    from app.finance import get_account_by_id, adjust_balance
    if date_val is None:
        date_val = datetime.now().date()
    unit_label, has_unit = _unit_label_for_type(inv_type)

    sess: Session = get_session()
    try:
        inv = Investment(
            account_id = account_id,
            date = date_val,
            amount = float(amount),
            principal_remaining = float(amount),
            type = inv_type,
            risk = risk,
            mature_period_months = mature_period_months,
            maturity_date = maturity_date,
            expected_return_percent = expected_return_percent,
            status = 'active',
            notes = notes,
            currency = currency,
            quantity = float(quantity) if quantity is not None else None,
            unit_label = unit_label,
            purchase_price_per_unit = float(purchase_price_per_unit) if purchase_price_per_unit is not None else None,
            current_price_per_unit = None,
            current_value = None
        )
        sess.add(inv)
        sess.commit()
        inv_id = inv.id
    except Exception:
        sess.rollback()
        raise
    finally:
        sess.close()

    # debit account if requested
    if debit_account and account_id is not None:
        acct = get_account_by_id(account_id)
        if acct:
            kind = acct.get('kind','bank')
            if kind in ('bank','cash'):
                adjust_balance(account_id, -float(amount))
            else:
                adjust_balance(account_id, float(amount))
    return inv_id

# -------------------------
# List / Get investments
# -------------------------
def list_investments(status: Optional[str] = None, include_zero_remaining: bool = False) -> List[Dict[str,Any]]:
    sess: Session = get_session()
    try:
        q = sess.query(Investment)
        if status:
            q = q.filter(Investment.status == status)
        rows = q.order_by(Investment.date.desc()).all()
        out = []
        for r in rows:
            pr = r.principal_remaining if r.principal_remaining is not None else r.amount
            if not include_zero_remaining and pr is not None and float(pr) <= 0:
                continue
            out.append({
                'id': r.id,
                'account_id': r.account_id,
                'date': r.date.isoformat() if r.date else None,
                'amount': float(r.amount),
                'principal_remaining': float(pr),
                'type': r.type,
                'risk': r.risk,
                'maturity_date': r.maturity_date.isoformat() if r.maturity_date else None,
                'expected_return_percent': r.expected_return_percent,
                'status': r.status,
                'notes': r.notes,
                'currency': r.currency,
                'quantity': float(r.quantity) if r.quantity is not None else None,
                'unit_label': r.unit_label,
                'purchase_price_per_unit': float(r.purchase_price_per_unit) if r.purchase_price_per_unit is not None else None,
                'current_price_per_unit': float(r.current_price_per_unit) if r.current_price_per_unit is not None else None,
                'current_value': float(r.current_value) if r.current_value is not None else None,
            })
        return out
    finally:
        sess.close()

def get_investment_by_id(investment_id: int) -> Optional[Dict[str,Any]]:
    sess: Session = get_session()
    try:
        r = sess.query(Investment).filter(Investment.id == investment_id).first()
        if not r:
            return None
        pr = r.principal_remaining if r.principal_remaining is not None else r.amount
        return {
            'id': r.id,
            'account_id': r.account_id,
            'date': r.date.isoformat() if r.date else None,
            'amount': float(r.amount),
            'principal_remaining': float(pr),
            'type': r.type,
            'risk': r.risk,
            'maturity_date': r.maturity_date.isoformat() if r.maturity_date else None,
            'expected_return_percent': r.expected_return_percent,
            'status': r.status,
            'notes': r.notes,
            'currency': r.currency,
            'quantity': float(r.quantity) if r.quantity is not None else None,
            'unit_label': r.unit_label,
            'purchase_price_per_unit': float(r.purchase_price_per_unit) if r.purchase_price_per_unit is not None else None,
            'current_price_per_unit': float(r.current_price_per_unit) if r.current_price_per_unit is not None else None,
            'current_value': float(r.current_value) if r.current_value is not None else None,
        }
    finally:
        sess.close()

# -------------------------
# Redeem (partial / full) — ORM, updates quantity & current_value, creates InvestmentSettlement rows
# -------------------------
def redeem_investment(investment_id: int, amount: Optional[float] = None, quantity: Optional[float] = None, credit_account: Optional[int] = None, note: Optional[str] = None) -> int:
    from app.finance import get_account_by_id, adjust_balance
    """
    Redeem part/all of an investment. Either specify amount (currency) or quantity (units).
    Decreases principal_remaining, decreases quantity (if quantity-based), updates current_value, creates settlement row, adjusts account.
    Returns settlement id.
    """
    sess: Session = get_session()
    try:
        inv = sess.query(Investment).filter(Investment.id == investment_id).with_for_update().first()
        if not inv:
            raise ValueError("Investment not found")

        pr = float(inv.principal_remaining) if inv.principal_remaining is not None else float(inv.amount)
        if pr <= 0:
            raise ValueError("No principal remaining to redeem")

        redeem_amount = None
        # quantity redemption
        if quantity is not None:
            if inv.current_price_per_unit is not None:
                unit_price = float(inv.current_price_per_unit)
            elif inv.purchase_price_per_unit is not None:
                unit_price = float(inv.purchase_price_per_unit)
            else:
                raise ValueError("No unit price available to compute amount from quantity")
            redeem_amount = float(quantity) * unit_price
            # reduce stored quantity if present
            if inv.quantity is None:
                # if quantity not stored, we can't reduce; but allow redemption by qty if computed from unit price only
                pass
            else:
                if quantity > inv.quantity + 1e-9:
                    raise ValueError("Redeem quantity cannot exceed available quantity")
                inv.quantity = float(inv.quantity) - float(quantity)
        elif amount is not None:
            redeem_amount = float(amount)
        else:
            raise ValueError("Specify amount or quantity to redeem")

        if redeem_amount <= 0:
            raise ValueError("Redeem amount must be > 0")
        if redeem_amount > pr + 1e-9:
            raise ValueError(f"Redeem amount cannot exceed principal remaining ({pr:.2f})")

        # update principal_remaining & status
        new_pr = pr - redeem_amount
        inv.principal_remaining = float(new_pr)
        if new_pr <= 1e-9:
            inv.status = 'redeemed'
            inv.principal_remaining = 0.0
        else:
            inv.status = 'partially_redeemed'

        # update current_value: if we have current_price_per_unit and quantity, use q * price
        if inv.current_price_per_unit is not None and inv.quantity is not None:
            inv.current_value = float(inv.quantity) * float(inv.current_price_per_unit)
        else:
            # fallback: set current_value equal to principal_remaining
            inv.current_value = float(inv.principal_remaining)

        # create settlement row (ORM)
        settlement = InvestmentSettlement(
            investment_id = inv.id,
            date = datetime.now().date(),
            amount = float(redeem_amount),
            account_id = credit_account,
            notes = note
        )
        sess.add(settlement)
        sess.commit()
        settlement_id = settlement.id
    except Exception:
        sess.rollback()
        raise
    finally:
        sess.close()

    # adjust account after commit
    if credit_account:
        acct = get_account_by_id(credit_account)
        if acct:
            kind = acct.get('kind','bank')
            # credit proceeds to your account: bank/cash +, card - (reduces outstanding)
            if kind in ('bank','cash'):
                adjust_balance(credit_account, float(redeem_amount))
            else:
                adjust_balance(credit_account, -float(redeem_amount))
    return settlement_id

# -------------------------
# Settlement history (per-investment)
# -------------------------
def get_settlements_for_investment(investment_id: int) -> List[Dict[str,Any]]:
    sess: Session = get_session()
    try:
        rows = sess.query(InvestmentSettlement).filter(InvestmentSettlement.investment_id == investment_id).order_by(InvestmentSettlement.created_at.desc()).all()
        out = []
        for r in rows:
            out.append({
                'id': r.id,
                'date': r.date.isoformat() if r.date else None,
                'amount': float(r.amount),
                'account_id': r.account_id,
                'notes': r.notes,
                'created_at': r.created_at.isoformat() if r.created_at else None
            })
        return out
    finally:
        sess.close()

# -------------------------
# Simple portfolio summary
# -------------------------
def portfolio_summary() -> Dict[str,Any]:
    sess: Session = get_session()
    try:
        total_principal = sess.query(func.coalesce(func.sum(Investment.amount), 0.0)).scalar() or 0.0
        total_remaining = sess.query(func.coalesce(func.sum(Investment.principal_remaining), 0.0)).scalar() or 0.0
        # compute current_value
        investments = sess.query(Investment).all()
        cur_val = 0.0
        for r in investments:
            if r.current_value is not None:
                cur_val += float(r.current_value)
            else:
                if r.principal_remaining is not None:
                    cur_val += float(r.principal_remaining)
                else:
                    cur_val += float(r.amount)
        return {'total_principal': float(total_principal), 'total_remaining': float(total_remaining), 'current_value': float(cur_val)}
    finally:
        sess.close()
