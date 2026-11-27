"""Explicit stock timing; overnight is one session routed separately from SMART."""
import copy
from datetime import datetime, timezone

# IB retires this venue at 02:00 New York time, before the first new session.
OVERNIGHT_END = datetime(2026, 12, 6, 7, tzinfo=timezone.utc)


def require_legacy_venue():
    if datetime.now(timezone.utc) >= OVERNIGHT_END:
        raise ValueError('The OVERNIGHT venue is retired. Review a new order and its trading hours.')


def stock_session(value, security_type, currency, tif):
    if value is None:
        return None
    if security_type != 'STK' or currency != 'USD' or tif not in ('DAY', 'GTC'):
        raise ValueError('Trading hours require a USD stock order with DAY or GTC')
    if value not in ('RTH', 'EXTENDED'):
        raise ValueError('Unknown stock trading hours')
    return value


def broker_stock_session(contract, order):
    if contract.secType != 'STK' or contract.exchange != 'SMART':
        return None
    outside = getattr(order, 'outsideRth', None)
    if isinstance(outside, bool):
        return 'EXTENDED' if outside else 'RTH'
    return None

STOCK_TIFS = ('DAY', 'GTC', 'OVERNIGHT')


def order_tif(order):
    default = 'GTC' if order.get('intent') == 'CLOSE' else 'DAY'
    value = order.get('tif')
    value = default if value is None else str(value).strip().upper()
    if order.get('option_type') == 'STOCK':
        if value not in STOCK_TIFS:
            raise ValueError('Stock time in force must be DAY, GTC or OVERNIGHT')
        if value == 'OVERNIGHT' and order.get('currency', 'USD') != 'USD':
            raise ValueError('Overnight trading requires a USD stock contract')
    elif value != default:
        raise ValueError('Custom time in force is supported only for stock orders')
    return value


def routed_contract(contract, tif):
    if tif != 'OVERNIGHT':
        return contract
    if getattr(contract, 'secType', '') != 'STK' or getattr(contract, 'currency', '') != 'USD':
        raise ValueError('Overnight trading requires a USD stock contract')
    if not getattr(contract, 'conId', 0):
        raise ValueError('An exact stock contract is required for overnight trading')
    require_legacy_venue()
    routed = copy.copy(contract)
    routed.exchange = 'OVERNIGHT'
    return routed
