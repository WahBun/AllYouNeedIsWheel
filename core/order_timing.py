"""Explicit stock timing; overnight is one session routed separately from SMART."""
import copy

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
    routed = copy.copy(contract)
    routed.exchange = 'OVERNIGHT'
    return routed
