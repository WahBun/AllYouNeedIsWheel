"""Four on-demand display snapshots. All access is on the existing IB owner."""
import asyncio
import math
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from ib_async import Future, Stock, Ticker

from api.services.contract_labels import contract_label
from api.services.stock_cost_service import reported_costs
from core.currency import CurrencyHelper

SYMBOLS = ('QQQ', 'SPY', 'MES', 'MNQ')
EASTERN = ZoneInfo('America/New_York')


def finite(value):
    return value if isinstance(value, (int, float)) and math.isfinite(value) else None


def holding_average_cost(position):
    cost = finite(getattr(position, 'avgCost', None))
    if cost is None or abs(cost) == sys.float_info.max:
        return None
    contract = position.contract
    if contract.secType not in ('OPT', 'FOP', 'FUT'):
        return None
    try:
        multiplier = float(contract.multiplier)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(multiplier) or multiplier <= 0:
        return None
    return finite(cost / multiplier)


def allocation_snapshot(ib, account, positions, marks):
    def usd(value, currency):
        try:
            value = float(value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(value) or abs(value) == sys.float_info.max:
            return None
        return finite(CurrencyHelper.convert_amount(value, currency or 'USD'))

    totals = {}
    # Summary rows match the iPhone. After a cold start the account update
    # stream can already contain the same tags before a summary is requested.
    for source in (ib.wrapper.acctSummary.values(), ib.accountValues(account)):
        for row in source:
            if (row.account == account and row.tag in ('NetLiquidation', 'TotalCashValue')
                    and not getattr(row, 'modelCode', '') and row.currency not in ('BASE', '')
                    and row.tag not in totals):
                value = usd(row.value, row.currency)
                if value is not None:
                    totals[row.tag] = value
    values = []
    for position in positions:
        contract = position.contract
        mark = marks.get(contract.conId)
        value = usd(mark.marketValue, contract.currency) if mark and mark.position == position.position else None
        values.append(dict(symbol=contract.symbol.upper(), value=value))
    return dict(positions=values, cash=totals.get('TotalCashValue'), net=totals.get('NetLiquidation'))


def holding_page(ib, account, page, symbol=None, *, include_allocation=True):
    # The position stream can be ahead of account-value updates following a fill.
    marks = {p.contract.conId: p for p in ib.portfolio(account) if p.account == account}
    positions = sorted((p for p in ib.positions(account) if p.account == account and p.position),
                       key=lambda p: (p.contract.symbol, p.contract.localSymbol, p.contract.conId))
    allocation = allocation_snapshot(ib, account, positions, marks) if include_allocation else None
    if symbol is not None:
        positions = [p for p in positions if p.contract.symbol.upper() == symbol]
    visible = positions[page * 30:(page + 1) * 30]
    reports = reported_costs(account, refresh=False) if any(p.contract.secType == 'STK' for p in visible) else {}
    rows = []
    for p in visible:
        c = p.contract
        mark = marks.get(c.conId)
        price = finite(mark.marketPrice) if mark and mark.position == p.position else None
        row = dict(id=c.conId, symbol=c.symbol, contract=contract_label(c),
                   quantity=p.position, price=price, currency=c.currency)
        if c.secType == 'STK':
            report = reports.get((c.conId, c.currency))
            row.update(costSource='report', averageCost=report['average'] if report else None)
            if report:
                row.update(reportDate=report['date'], reportedShares=report['quantity'])
        else:
            row.update(costSource='position', averageCost=holding_average_cost(p))
        rows.append(row)
    return dict(positions=rows, total=len(positions), allocation=allocation, symbolFilter=symbol)


class WatchQuotes:
    def __init__(self):
        self.context = None
        self.contracts = {}
        self.rows = {}
        self.job = None
        self.next_batch = 0

    async def contract(self, ib, symbol, today, contracts):
        if symbol in ('QQQ', 'SPY'):
            return Stock(symbol, 'SMART', 'USD', primaryExchange='NASDAQ' if symbol == 'QQQ' else 'ARCA')
        if symbol not in contracts:
            details = await ib.reqContractDetailsAsync(Future(symbol=symbol, exchange='CME', currency='USD'))
            eligible = [d.contract for d in details if d.contract.symbol == symbol and d.contract.secType == 'FUT'
                        and d.contract.exchange == 'CME' and d.contract.currency == 'USD'
                        and len(d.contract.lastTradeDateOrContractMonth) == 8
                        and d.contract.lastTradeDateOrContractMonth > today and d.contract.conId > 0]
            if not eligible:
                return None
            contracts[symbol] = min(eligible, key=lambda c: c.lastTradeDateOrContractMonth)
        return contracts[symbol]

    async def read_one(self, ib, symbol, today, contracts, rows):
        started = time.monotonic()
        tickers = ib.wrapper.reqId2Ticker
        contract = await self.contract(ib, symbol, today, contracts)
        if contract is None or tickers is not ib.wrapper.reqId2Ticker or time.monotonic() - started >= 8:
            return
        # ib_async normally shares a mutable Ticker by contract. Route this finite
        # snapshot by request ID only, so it cannot write into a chart's live Ticker.
        req_id = ib.client.getReqId()
        ticker = Ticker(contract=contract)
        done = ib.wrapper.startReq(req_id, contract)
        tickers[req_id] = ticker
        try:
            sampled_at = time.time()
            ib.client.reqMktData(req_id, contract, '', True, False, [])
            await asyncio.wait_for(asyncio.shield(done), 16)
            if time.monotonic() - started > 24:
                return
            for field in ('last', 'close'):
                value = finite(getattr(ticker, field))
                if value is not None and value > 0:
                    rows[symbol] = dict(symbol=symbol, contract=contract.localSymbol or symbol,
                                        price=value, source=field, dataType=ticker.marketDataType,
                                        sampledAt=sampled_at)
                    break
        finally:
            # IB can reuse request IDs after reconnecting. Only clean up the
            # request registered in this exact wrapper generation.
            if ib.wrapper.reqId2Ticker is tickers and tickers.get(req_id) is ticker:
                if not done.done():
                    if ib.isConnected():
                        ib.client.cancelMktData(req_id)
                    ib.wrapper._endReq(req_id)
                tickers.pop(req_id, None)

    async def batch(self, ib, today, contracts, rows):
        await asyncio.gather(*(asyncio.wait_for(self.read_one(ib, symbol, today, contracts, rows), 24)
                               for symbol in SYMBOLS), return_exceptions=True)

    def read(self, conn, epoch):
        today = datetime.now(EASTERN).strftime('%Y%m%d')
        context = (conn, id(conn.ib.wrapper.reqId2Ticker), epoch, today)
        if self.context != context:
            if self.job and not self.job.done():
                self.job.cancel()
            self.context, self.contracts, self.rows, self.job, self.next_batch = context, {}, {}, None, 0
        # Drain ready callbacks even when Wheel has no chart open. Never wait for
        # qualification or the broker snapshot in the serialized request handler.
        conn.ib.sleep(0)
        now = time.monotonic()
        if (self.job is None or self.job.done()) and now >= self.next_batch:
            self.next_batch = now + 25
            self.job = asyncio.get_event_loop().create_task(self.batch(conn.ib, today, self.contracts, self.rows))
            conn.ib.sleep(0)
        return [self.rows.get(s, dict(symbol=s, contract=s)) for s in SYMBOLS]


watch_quotes = WatchQuotes()
