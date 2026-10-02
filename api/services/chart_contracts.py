"""Exact chart contract discovery on the existing IB owner thread."""
import re
import copy
from datetime import datetime, timezone
from ib_async import Contract, Future

class ChartContracts:
    def __init__(self):
        self.contracts = {}

    def search(self, conn, query):
        symbol = str(query).strip().upper()
        if not re.fullmatch(r'[A-Z][A-Z0-9.]{0,11}', symbol):
            raise ValueError('Enter a stock symbol, ES, NQ, MES or MNQ')
        if symbol in ('ES', 'NQ', 'MES', 'MNQ'):
            details = conn._bounded_order_read(conn.ib.reqContractDetails,
                Future(symbol=symbol, exchange='CME', currency='USD'), timeout_seconds=6)
            today = datetime.now(timezone.utc).strftime('%Y%m%d')
            found = [d.contract for d in details if d.contract.secType == 'FUT'
                     and d.contract.symbol == symbol and d.contract.currency == 'USD'
                     and d.contract.lastTradeDateOrContractMonth >= today]
            found.sort(key=lambda c: c.lastTradeDateOrContractMonth)
            found = found[:6]
        else:
            contract = conn.get_qualified_stock_contract(symbol)
            found = [contract] if contract else []
        results = []
        for c in found:
            if not c.conId or c.secType not in ('STK', 'FUT') or c.currency != 'USD': continue
            self.contracts[c.conId] = c
            results.append(dict(con_id=c.conId, symbol=c.symbol, security_type=c.secType,
                local_symbol=c.localSymbol or c.symbol, exchange=c.exchange,
                expiration=c.lastTradeDateOrContractMonth, multiplier=c.multiplier or '1'))
        return results

    def resolve(self, conn, con_id):
        if con_id in self.contracts: return self.contracts[con_id]
        held = conn.get_option_position_by_con_id(con_id)
        if held and held['contract'].conId == con_id and held['contract'].secType in ('STK','FUT','OPT') and held['contract'].currency == 'USD':
            contract=held['contract']
            if contract.secType=='OPT':
                contract=copy.copy(contract)
                if not contract.exchange: contract.exchange='SMART'
                self.contracts[con_id]=contract
            return contract
        if held:
            raise ValueError('Unsupported chart contract')
        # The phone persists a conId across backend restarts; the search cache does not.
        # Resolve that exact ID with IB instead of substituting a symbol/front month.
        details = conn._bounded_order_read(conn.ib.reqContractDetails,
            Contract(conId=con_id), timeout_seconds=3)
        matches = [d.contract for d in details if d.contract.conId == con_id
                   and d.contract.secType in ('STK', 'FUT', 'OPT') and d.contract.currency == 'USD']
        if len(matches) != 1:
            raise ValueError('Exact chart contract unavailable; select it using search')
        contract = matches[0]
        if not contract.exchange:
            raise ValueError('Exact chart contract exchange unavailable; select it using search')
        self.contracts[con_id] = contract
        return contract

contracts = ChartContracts()
