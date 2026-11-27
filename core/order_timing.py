"""Explicit stock timing; overnight is one session routed separately from SMART."""
import copy
from datetime import datetime, timezone

# The client notice says not to route directly to OVERNIGHT on December 6.
# Stop Wheel writes at midnight ET, ahead of the API's 02:00 ET venue retirement.
LEGACY_ROUTE_CUTOFF = datetime(2026, 12, 6, 5, tzinfo=timezone.utc)


def legacy_venue_available():
    return datetime.now(timezone.utc) < LEGACY_ROUTE_CUTOFF


def require_legacy_venue():
    if not legacy_venue_available():
        raise ValueError('Wheel no longer routes to OVERNIGHT. Review a new order and its trading hours.')


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
