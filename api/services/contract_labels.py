"""Compact display names. Broker symbols and contract identities stay unchanged."""
import math
import re
from datetime import datetime


def option_label(symbol, expiry, strike, right):
    expiry = str(expiry or '').replace('-', '')
    code = {'CALL': 'C', 'PUT': 'P', 'C': 'C', 'P': 'P'}.get(str(right or '').upper())
    try:
        if not re.fullmatch(r'\d{8}', expiry): return None
        datetime.strptime(expiry, '%Y%m%d')
        value = float(strike)
        if not symbol or not code or not math.isfinite(value) or value <= 0: return None
    except (ValueError, TypeError):
        return None
    return f'{symbol} · {expiry[4:6]}/{expiry[6:]}/{expiry[2:4]} · {value:.15g}{code}'


def compact_label(value):
    value = str(value or '')
    occ = re.fullmatch(r'([A-Z0-9.]{1,6})\s*(\d{6})([CP])(\d{8})', value)
    if occ:
        root, expiry, right, strike = occ.groups()
        return option_label(root, '20' + expiry, int(strike) / 1000, right) or value
    human = re.fullmatch(r'(\S+)\s+(\d{8}|\d{4}-\d{2}-\d{2})\s+(\d+(?:\.\d+)?)\s+(CALL|PUT|C|P)', value, re.I)
    return (option_label(*human.groups()) or value) if human else value


def contract_label(contract):
    raw = getattr(contract, 'localSymbol', '') or getattr(contract, 'symbol', '')
    if getattr(contract, 'secType', '') != 'OPT': return raw
    label = option_label(getattr(contract, 'symbol', ''), getattr(contract, 'lastTradeDateOrContractMonth', ''),
                         getattr(contract, 'strike', None), getattr(contract, 'right', ''))
    if label is None: return raw
    occ = re.fullmatch(r'([A-Z0-9.]{1,6})\s*(\d{6})([CP])(\d{8})', raw)
    if occ and occ[1].startswith(contract.symbol) and occ[2] == contract.lastTradeDateOrContractMonth[-6:] and occ[3] == contract.right and int(occ[4]) / 1000 == contract.strike:
        return compact_label(raw)
    return label
