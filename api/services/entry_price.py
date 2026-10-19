"""Resolve fee-exclusive fills only when recorded opening fills reconcile to holdings."""
import math
import sqlite3
from pathlib import Path


def recorded_entry_price(db_path, account, con_id, quantity, *, symbol=None, expiration=None, strike=None, option_type=None):
    if not db_path or not account or not con_id or not quantity:
        return None
    try:
        with sqlite3.connect(Path(db_path).resolve().as_uri() + '?mode=ro', uri=True) as db:
            if all(value is not None for value in (symbol, expiration, strike, option_type)):
                # Include old records without conId, but reject conflicting identities.
                matches = db.execute("""SELECT action, filled, avg_fill_price, intent, con_id FROM orders
                    WHERE account_id=? AND filled>0 AND COALESCE(is_mock,0)=0
                    AND (con_id=? OR (UPPER(ticker)=? AND REPLACE(expiration,'-','')=?
                         AND strike=? AND UPPER(option_type) IN (?,?)))""",
                    (account, con_id, symbol.upper(), expiration.replace('-', ''), strike,
                     option_type.upper(), 'P' if option_type.upper() in ('PUT', 'P') else 'C')).fetchall()
                if any(row[4] not in (None, 0, con_id) for row in matches):
                    return None
                rows = [row[:4] for row in matches]
            else:
                rows = db.execute('''SELECT action, filled, avg_fill_price, intent FROM orders
                    WHERE account_id=? AND con_id=? AND filled>0 AND COALESCE(is_mock,0)=0''',
                    (account, con_id)).fetchall()
            if not rows:
                # Chart orders need not exist in the legacy orders table. These
                # persisted marks retain exact broker fills across reconnects.
                # Use one source, never add duplicated order/mark quantities.
                rows = db.execute('''SELECT side, quantity, price, 'OPEN' FROM chart_execution_marks
                    WHERE account=? AND con_id=?''', (account, con_id)).fetchall()
        # Never infer a historical entry from a limit price or fee-adjusted IB cost.
        # Partial closes/reopened contracts require lot history, so leave them unknown.
        side = 'SELL' if quantity < 0 else 'BUY'
        if not rows or any(action != side or intent != 'OPEN' for action, _, _, intent in rows):
            return None
        if any(not math.isfinite(float(q)) or not math.isfinite(float(p or 0)) or q <= 0 or not p or p <= 0
               for _, q, p, _ in rows):
            return None
        total = sum(q for _, q, _, _ in rows)
        if not math.isclose(total, abs(quantity), rel_tol=0, abs_tol=1e-8):
            return None
        return sum(q * p for _, q, p, _ in rows) / total
    except (sqlite3.Error, ValueError, TypeError, OSError):
        return None


def broker_entry_price(rows, quantity):
    """Reconcile chronological broker fills to the remaining average entry basis."""
    position = basis = 0.0
    try:
        for row in sorted(rows, key=lambda r: r['time']):
            amount, price = float(row['quantity']), float(row['price'])
            if row['side'] not in ('BUY', 'SELL') or not all(map(math.isfinite, (amount, price))) or min(amount, price) <= 0:
                return None
            signed = amount if row['side'] == 'BUY' else -amount
            if position * signed >= 0:
                basis = (abs(position) * basis + amount * price) / (abs(position) + amount)
            elif amount > abs(position):
                basis = price
            position += signed
            if abs(position) < 1e-8:
                position = basis = 0.0
        if quantity and math.isclose(position, quantity, rel_tol=0, abs_tol=1e-8):
            return basis
    except (KeyError, TypeError, ValueError, OverflowError):
        pass
    return None
