"""On-demand IB what-if for an exact standard US short put; no order persistence."""
import math
import re
from datetime import datetime, timezone
from ib_async import LimitOrder
from core.utils import market_today


def estimate_put_margin(conn, ticker, expiration, strike, quantity, price):
    ticker = str(ticker).strip().upper()
    if not re.fullmatch(r'[A-Z0-9.-]{1,15}', ticker):
        raise ValueError('Invalid ticker')
    try:
        expiry = datetime.strptime(expiration, '%Y%m%d').date()
        strike, price = float(strike), float(price)
        qty = float(quantity)
    except (ValueError, TypeError):
        raise ValueError('Invalid margin estimate inputs') from None
    if expiry < market_today() or not all(math.isfinite(x) for x in (strike, price, qty)) or strike <= 0 or price <= 0 or not qty.is_integer() or not 1 <= qty <= 100:
        raise ValueError('Invalid margin estimate inputs')
    account = conn._order_account()
    if not account or not conn.is_connected():
        raise ValueError('Configured IB account is unavailable')
    currencies = {v.currency for v in conn.ib.accountSummary(account) if v.account == account and v.tag == 'InitMarginReq'}
    if currencies != {'USD'}:
        raise ValueError('Margin estimate requires a verified USD base account')
    contract = conn.get_qualified_option_contract(ticker, expiration, strike, 'P')
    if not contract or not contract.conId or contract.secType != 'OPT' or contract.symbol != ticker or contract.right != 'P' or contract.lastTradeDateOrContractMonth != expiration or contract.strike != strike or contract.currency != 'USD' or str(contract.multiplier) != '100':
        raise ValueError('Exact standard USD put contract could not be verified')
    order = LimitOrder('SELL', int(qty), price, tif='DAY', account=account, whatIf=True)
    result = conn.what_if_order(contract, order)
    if not result or not result.get('success'):
        raise ValueError('IB margin estimate unavailable; no order was submitted')
    try:
        change = float(result.get('init_margin_change', ''))
    except (ValueError, TypeError):
        raise ValueError('IB did not return a usable initial margin estimate') from None
    if not math.isfinite(change) or abs(change) >= 1e100:
        raise ValueError('IB did not return a usable initial margin estimate')
    return dict(ticker=ticker, expiration=expiration, strike=strike, quantity=int(qty), limit_price=price,
                initial_change=change, currency='USD', estimated=True,
                retrieved_at=datetime.now(timezone.utc).isoformat(), warning=result.get('warning_text') or None)
