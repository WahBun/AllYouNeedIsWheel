"""Paper-only chart brackets. All calls run on the serialized IB owner.

The journal claims each request before a broker write. Unknown outcomes are
never automatically replayed. Real accounts cannot use this execution path.
"""
import json
import math
import sqlite3
from decimal import Decimal, ROUND_CEILING
from uuid import UUID
from ib_async import LimitOrder, StopOrder, MarketOrder
from api.services.chart_contracts import contracts
from api.services.stock_chart import stock_chart
from api.services.futures_orders import completed_trades


def paper_account(conn, write=False):
    if not conn or not conn.is_connected(): raise ValueError('Gateway disconnected')
    account = conn.account_id
    accounts = conn.ib.managedAccounts()
    if not account or not account.startswith('DU') or accounts != [account] or conn.port != 4002:
        raise ValueError('Chart execution requires the configured single paper account on port 4002')
    if write and conn.readonly is not False: raise ValueError('Paper trading is read-only')
    return account


class PaperChart:
    def __init__(self, path):
        self.path = path

    def database(self):
        db = sqlite3.connect(self.path)
        db.execute('CREATE TABLE IF NOT EXISTS chart_paper_requests (id TEXT PRIMARY KEY, account TEXT NOT NULL, body TEXT NOT NULL, result TEXT)')
        db.execute('CREATE TABLE IF NOT EXISTS chart_paper_groups (account TEXT, con_id INTEGER, orders TEXT NOT NULL, PRIMARY KEY(account,con_id))')
        db.commit()
        return db

    def group(self, account, cid):
        with self.database() as db:
            row = db.execute('SELECT orders FROM chart_paper_groups WHERE account=? AND con_id=?',(account,cid)).fetchone()
        return json.loads(row[0]) if row else None

    def execution_groups(self, account, cid):
        """Recover logical user orders from the write journal, not candle time.

        One futures request can own several unit brackets. Separate Add/Trim
        requests must remain distinct, even on the same candle. No broker order
        fields or protective linkage are changed for display grouping.
        """
        with self.database() as db:
            signature=db.execute('SELECT rowid,result IS NOT NULL FROM chart_paper_requests WHERE account=? ORDER BY rowid DESC LIMIT 1',(account,)).fetchone()
            cache=getattr(self,'_execution_group_cache',None)
            if cache and cache[:3]==(account,cid,signature): return cache[3]
            records=db.execute('SELECT id,body,result FROM chart_paper_requests WHERE account=? AND result IS NOT NULL ORDER BY rowid',(account,)).fetchall()
        groups={};reference=None;previous={}
        for request_id,body,encoded in records:
            request=json.loads(body)
            if request.get('con_id')!=cid: continue
            result=json.loads(encoded);rows=result.get('state',{}).get('orders',[])
            if not rows: continue
            action=request.get('action')
            if action=='submit': reference='WheelPaper:'+request_id;previous={}
            if not reference: continue
            for row in rows:
                oid=row['order_id'];role=row['role'].split('_')[0];old=previous.get(oid)
                key=(reference,oid)
                if old is None and action in ('submit','add','close'):
                    groups[key]=request_id+':'+role
                elif action in ('trim','close') and result.get('success') and role=='tp' and old and (
                    row['price']!=old['price'] or row.get('filled',0)>old.get('filled',0)):
                    groups[key]=request_id+':exit'
                previous[oid]=row
        self._execution_group_cache=(account,cid,signature,groups)
        return groups

    def state(self, conn, cid):
        account = paper_account(conn)
        # Read broker events even when no chart SSE subscriber is pumping the loop.
        # Runs only on the serialized IB owner, never an HTTP thread.
        conn.ib.sleep(.005)
        group = self.group(account,cid)
        trades = {t.order.orderId:t for t in conn.ib.trades() if t.order.account==account and t.contract.conId==cid}
        position = next((p for p in conn.ib.positions() if p.account==account and p.contract.conId==cid),None)
        result = dict(paper=True, enabled=conn.readonly is False, position=float(position.position) if position else 0,
                      active=False, known=True, orders=[], entry=0, tp=0, sl=0, side=1, status='idle')
        executions = {}
        execution_groups=self.execution_groups(account,cid)
        for fill in conn.ib.fills():
            e = fill.execution
            if e.acctNumber != account or fill.contract.conId != cid: continue
            if e.side not in ('BOT','SLD') or not e.execId or e.shares <= 0: continue
            broker_id=getattr(e,'permId',0) or getattr(e,'orderId',0) or e.execId
            batch=execution_groups.get((getattr(e,'orderRef',''),getattr(e,'orderId',0)))
            executions[e.execId] = dict(id=e.execId,group=batch or f'broker:{getattr(e,"clientId",0)}:{broker_id}',time=fill.time.timestamp(),price=float(e.price),
                quantity=float(e.shares),side='BUY' if e.side=='BOT' else 'SELL')
        result['executions'] = sorted(executions.values(), key=lambda e:e['time'])
        if not group: return result
        # Completed IB orders can lose their temporary orderId after reconnect.
        # Recover only by exact recorded permId or a unique bracket reference/role.
        missing = [role for role, oid in group['ids'].items() if oid not in trades]
        if missing:
            ref = group.get('ref')
            if not ref:
                refs = {f.execution.orderRef for f in conn.ib.fills()
                        if f.execution.acctNumber == account and f.contract.conId == cid
                        and f.execution.clientId == conn.ib.client.clientId
                        and f.execution.orderId == group['ids']['entry']
                        and f.execution.orderRef.startswith('WheelPaper:')}
                if len(refs) == 1: ref = next(iter(refs))
            for role in missing:
                perm = group.get('perms', {}).get(role)
                candidates = []
                if perm or ref:
                    for t in completed_trades(conn, account):
                        if t.order.account != account or t.contract.conId != cid: continue
                        if perm:
                            matches = (t.order.permId or t.orderStatus.permId) == perm
                        else:
                            entry_action = 'BUY' if group['side'] == 1 else 'SELL'
                            matches = t.order.orderRef == ref and (
                                role == 'entry' and t.order.action == entry_action or
                                role == 'tp' and t.order.action != entry_action and t.order.orderType == 'LMT' or
                                role == 'sl' and t.order.action != entry_action and t.order.orderType == 'STP')
                        if matches: candidates.append(t)
                if len(candidates) == 1: trades[group['ids'][role]] = candidates[0]
        self._resolved_trades = trades
        perms = {role:int(trades[oid].order.permId or trades[oid].orderStatus.permId)
                 for role,oid in group['ids'].items() if oid in trades and (trades[oid].order.permId or trades[oid].orderStatus.permId)}
        if perms and perms != group.get('perms'):
            group['perms'] = {**group.get('perms', {}), **perms}
            with self.database() as db:
                db.execute('UPDATE chart_paper_groups SET orders=? WHERE account=? AND con_id=?',(json.dumps(group),account,cid))
        def trade_fills(t):
            perm = t.order.permId or t.orderStatus.permId
            fills = list(t.fills)
            if perm:
                fills += [f for f in conn.ib.fills() if f.execution.acctNumber == account
                          and f.contract.conId == cid and f.execution.permId == perm]
            return list({f.execution.execId:f for f in fills}.values())
        terminal = group.get('terminal', {})
        if missing:
            # A locally held, subsequently canceled order has no broker permId
            # and disappears on reconnect. Recover only its confirmed journal state.
            with self.database() as db:
                snapshots = db.execute('SELECT result FROM chart_paper_requests WHERE account=? AND result IS NOT NULL', (account,)).fetchall()
            for (encoded,) in snapshots:
                snapshot = json.loads(encoded).get('state', {}).get('orders', [])
                if {r['order_id'] for r in snapshot} != set(group['ids'].values()): continue
                for row in snapshot:
                    if row['status'] in ('Filled','Cancelled','ApiCancelled','Inactive'): terminal[row['role']] = row
        rows=[]
        for role, oid in group['ids'].items():
            t=trades.get(oid)
            if not t and role in terminal and terminal[role]['order_id'] == oid:
                rows.append(terminal[role]); continue
            rows.append(dict(role=role, order_id=oid, status=t.orderStatus.status if t else 'Unknown',
                price=(t.order.auxPrice if role.split('_')[0]=='sl' or (role.split('_')[0]=='entry' and t.order.orderType=='STP') else t.order.lmtPrice) if t and role!='close' else 0,
                quantity=max(float(t.order.totalQuantity),float(t.orderStatus.filled),sum(float(f.execution.shares) for f in trade_fills(t))) if t else 0,
                filled=max(float(t.orderStatus.filled),sum(float(f.execution.shares) for f in trade_fills(t))) if t else 0))
        confirmed = {r['role']:r for r in rows if r['status'] in ('Filled','Cancelled','ApiCancelled','Inactive')}
        if confirmed != group.get('terminal'):
            group['terminal'] = confirmed
            with self.database() as db:
                db.execute('UPDATE chart_paper_groups SET orders=? WHERE account=? AND con_id=?',(json.dumps(group),account,cid))
        result.update(orders=rows, side=group['side'], known=all(r['status']!='Unknown' for r in rows))
        result['active']=any(r['status'] not in ('Filled','Cancelled','ApiCancelled','Inactive') for r in rows) or result['position']!=0
        result['status']='working' if result['active'] else 'done'
        for row in rows:
            if row['role'] in ('entry','tp','sl'): result[row['role']]=row['price']
        if group.get('lots'):
            for role in ('tp','sl'):
                live_rows=[r for r in rows if r['role'].split('_')[0]==role and r['status'] not in ('Filled','Cancelled','ApiCancelled','Inactive')]
                if live_rows: result[role]=live_rows[-1]['price']
            result['scalable']=True
            result['quantity']=sum(max(0,r['quantity']-r['filled']) for r in rows if r['role'].split('_')[0]=='entry' and r['status'] not in ('Filled','Cancelled','ApiCancelled','Inactive'))
        parent=trades.get(group['ids']['entry'])
        if parent and parent.orderStatus.avgFillPrice>0: result['entry']=parent.orderStatus.avgFillPrice
        elif parent and trade_fills(parent):
            fills = trade_fills(parent)
            total = sum(float(f.execution.shares) for f in fills)
            if total > 0: result['entry'] = sum(float(f.execution.shares)*float(f.execution.price) for f in fills)/total
        if not result['known']: result['status']='unknown'
        if result['position']:
            # Broker avgCost includes commission for futures. Use actual fills for
            # the chart's price basis, retaining average cost through trims.
            events = {}
            for oid in group['ids'].values():
                trade = trades.get(oid)
                if not trade: continue
                for f in trade_fills(trade):
                    events[f.execution.execId] = (f.time, f.execution.execId, trade.order.action, float(f.execution.shares), float(f.execution.price))
            size = cost = 0.0
            for _, _, action, quantity, fill_price in sorted(events.values()):
                if action == ('BUY' if group['side'] == 1 else 'SELL'):
                    size += quantity; cost += quantity * fill_price
                elif size and quantity <= size:
                    cost -= cost * quantity / size; size -= quantity
            if size and abs(size - abs(result['position'])) < .000001: result['entry'] = cost / size
        result['be_applied']=bool(result['position'] and result['sl']>0 and result['side']*(result['sl']-result['entry'])>0)
        result['rejected']=any(r['status']=='Inactive' for r in rows)
        result['protection'] = self.protection_progress(rows, result['position'])
        adjustment = group.get('adjustment')
        if adjustment:
            by_id = {r['order_id']: r for r in rows}
            selected = [by_id.get(oid, dict(status='Unknown', filled=0)) for oid in adjustment['orders']]
            filled = sum(min(1, r['filled'] + by_id.get(sl, {}).get('filled', 0)) for r, sl in zip(selected, adjustment.get('stops', [None]*len(selected))))
            result['adjustment'] = dict(action=adjustment['action'], requested=len(selected), filled=filled,
                remaining=max(0, len(selected)-filled), pending=sum(max(0, 1-r['filled']) for r in selected if r.get('order_id') in adjustment.get('acknowledged', []) and r['status'] in ('Submitted','PreSubmitted')), position=result['position'],
                status='filled' if filled == len(selected) else 'unknown' if any(r['status']=='Unknown' for r in selected) or adjustment.get('outcome') == 'unknown'
                else 'rejected' if adjustment.get('outcome') == 'rejected' or any(r['status']=='Inactive' for r in selected)
                else 'canceled' if any(r['status'] in ('Cancelled','ApiCancelled') for r in selected)
                else 'working')
        if group.get('mode') == 'overnight_entry':
            result['broker_messages'] = [entry.message for t in trades.values()
                if t.order.orderId in group['ids'].values() for entry in t.log if entry.message]
            result.update(mode='overnight_entry', scalable=False, tif='OVERNIGHT',
                          route='OVERNIGHT', protection=dict(status='not_requested'))
            errors = [entry for t in trades.values() if t.order.orderId in group['ids'].values()
                      for entry in t.log if entry.errorCode and entry.errorCode != 399 and
                      (200 <= entry.errorCode < 2100 or entry.errorCode >= 10000)]
            statuses = {r['status'] for r in rows}
            result['rejected'] = result['rejected'] or bool(errors and statuses <= {'Cancelled', 'ApiCancelled', 'Inactive'})
            result['status'] = ('rejected' if result['rejected'] else 'unknown' if not result['known']
                else 'filled' if statuses == {'Filled'} else 'canceled' if statuses <= {'Cancelled', 'ApiCancelled'}
                else 'working' if statuses <= {'Submitted', 'PreSubmitted'} else 'pending')
        return result

    @staticmethod
    def protection_progress(rows, position):
        quantities = {role: sum(max(0, r['quantity']-r['filled']) for r in rows
            if r['role'].split('_')[0] == role and r['status'] in ('Submitted','PreSubmitted')) for role in ('tp','sl')}
        size = abs(position)
        return dict(**quantities, remaining_position=size,
                    status='flat' if size == 0 else 'unknown' if any(r['status']=='Unknown' for r in rows)
                    else 'covered' if quantities['tp'] == size and quantities['sl'] == size else 'needs_review')

    def execute(self, conn, cid, body):
        account=paper_account(conn,True)
        request_id=str(UUID(str(body.get('request_id',''))))
        encoded=json.dumps(dict(body,con_id=cid),sort_keys=True,allow_nan=False)
        with self.database() as db:
            old=db.execute('SELECT account,body,result FROM chart_paper_requests WHERE id=?',(request_id,)).fetchone()
            if old:
                if old[:2]!=(account,encoded): raise ValueError('Request identifier already used')
                return json.loads(old[2]) if old[2] else dict(success=False,status='unknown',message='Previous request needs broker reconciliation; not replayed')
            db.execute('INSERT INTO chart_paper_requests VALUES(?,?,?,NULL)',(request_id,account,encoded))
        try:
            self.perform(conn,account,cid,body,request_id)
            conn.ib.sleep(.2)
            group = self.group(account, cid)
            if group and group.get('adjustment', {}).get('request_id') == request_id:
                group['adjustment']['outcome'] = 'acknowledged'
                self.save_group(account, cid, group)
            state=self.state(conn,cid)
            result=dict(success=not state.get('rejected',False),status='rejected' if state.get('rejected') else 'acknowledged',message='IB rejected a paper order; review Gateway' if state.get('rejected') else 'Paper request sent; broker status shown on chart',state=state)
            if state.get('mode') == 'overnight_entry':
                status = state['status']
                result.update(success=status in ('working', 'filled'), status=status,
                    message=('Overnight Paper limit order is ' + status +
                             ('. ' + '; '.join(state.get('broker_messages', [])) if status == 'rejected'
                              else '; verify broker status before any further action')))
        except ValueError as error:
            result=dict(success=False,status='rejected',message=str(error))
        except Exception:
            result=dict(success=False,status='unknown',message='Broker outcome uncertain. Check Gateway; do not resubmit.')
        group = self.group(account, cid)
        if group and group.get('adjustment', {}).get('request_id') == request_id:
            group['adjustment']['outcome'] = result['status']
            self.save_group(account, cid, group)
        with self.database() as db:
            db.execute('UPDATE chart_paper_requests SET result=? WHERE id=?',(json.dumps(result),request_id))
        return result

    def save_group(self, account, cid, group):
        with self.database() as db:
            db.execute('INSERT OR REPLACE INTO chart_paper_groups VALUES(?,?,?)',(account,cid,json.dumps(group)))

    def add_lots(self, conn, account, cid, contract, group, qty, kind, entry, tp, sl):
        for _ in range(qty):
            index = len(group['lots'])
            ids = {role:conn.ib.client.getReqId() for role in ('entry','tp','sl')}
            for role, oid in ids.items(): group['ids'][role if index==0 else f'{role}_{index}'] = oid
            group['lots'].append(ids); self.save_group(account,cid,group)
            buy = 'BUY' if group['side']==1 else 'SELL'; sell = 'SELL' if group['side']==1 else 'BUY'
            parent = MarketOrder(buy,1) if kind=='MKT' else (LimitOrder if kind=='LMT' else StopOrder)(buy,1,entry)
            parent.orderId=ids['entry']; parent.transmit=False
            take=LimitOrder(sell,1,tp,orderId=ids['tp'],parentId=ids['entry'],transmit=False)
            stop=StopOrder(sell,1,sl,orderId=ids['sl'],parentId=ids['entry'],transmit=True)
            for order in (parent,take,stop):
                order.account=account;order.tif='DAY';order.orderRef=group['ref']
                conn.ib.placeOrder(contract,order)

    def exit_lots(self, conn, account, cid, group, lots, trades, price, action, request_id):
        import copy
        state=stock_chart.active
        if not state or state['con_id']!=cid: raise ValueError('Wait for a current quote')
        # Use the chart's quote freshness rules, independently of its interval.
        packet=stock_chart.packet(state,5,'rth')
        if not packet: raise ValueError('Fresh exit quote unavailable')
        quote=packet.get('bid' if group['side']==1 else 'ask')
        if packet.get('status')!='live' or not quote: raise ValueError('Wait for a live bid/ask')
        target=price(quote)
        group['adjustment'] = dict(action=action, request_id=request_id, orders=[lot['tp'] for lot in lots], stops=[lot['sl'] for lot in lots], acknowledged=[], outcome='unknown')
        self.save_group(account, cid, group)
        for lot in lots:
            take=trades[lot['tp']];stop=trades[lot['sl']]
            if take.isDone() or stop.isDone(): raise ValueError('Exit changed before adjustment')
            lot['closing']=True;self.save_group(account,cid,group)
            order=copy.copy(take.order);order.lmtPrice=target;order.transmit=True
            self.modify_exit(conn,take,order,'lmtPrice')
            group['adjustment']['acknowledged'].append(lot['tp'])
            self.save_group(account, cid, group)

    def modify_exit(self, conn, trade, order, field):
        # Keep the broker's parent/OCA fields verbatim. Clearing or rebuilding
        # them during a price amendment causes IB 10326/10327 rejections.
        import time
        start=len(trade.log)
        conn.ib.placeOrder(trade.contract,order)
        deadline=time.monotonic()+3
        while True:
            conn.ib.sleep(.05)
            errors=[e.errorCode for e in trade.log[start:] if e.errorCode]
            if errors: raise ValueError(f'IB rejected the exit amendment ({errors[-1]}); original protection needs review')
            if trade.orderStatus.status=='Filled': return
            if trade.orderStatus.status in ('Submitted','PreSubmitted') and getattr(trade.order,field)==getattr(order,field): return
            if time.monotonic()>=deadline: raise RuntimeError('Exit amendment not confirmed')

    def submit_overnight_entry(self, conn, account, cid, contract, current, body, request_id):
        """Standalone Paper BUY; venue controls the overnight session, never SMART fallback."""
        from core.order_timing import routed_contract
        if contract.secType != 'STK' or contract.currency != 'USD':
            raise ValueError('Overnight entry requires a USD stock')
        if body.get('side') != 1 or body.get('entry_type') != 'LMT':
            raise ValueError('Standalone overnight entry supports BUY limit orders only')
        qty = body.get('quantity')
        if isinstance(qty, bool) or not isinstance(qty, (int, float)) or not math.isfinite(qty) or qty != int(qty) or not 1 <= qty <= 1000:
            raise ValueError('Quantity must be 1–1000 whole shares')
        if any(body.get(k) is not None for k in ('tp', 'sl')):
            raise ValueError('Standalone overnight entry must not contain TP/SL')
        try: amount = Decimal(str(body.get('entry')))
        except Exception: raise ValueError('Invalid entry price')
        if not amount.is_finite() or amount <= 0: raise ValueError('Invalid entry price')
        conn._bounded_order_read(conn.ib.reqOpenOrders, timeout_seconds=3)
        if not current['known'] or current['active'] or current['position']:
            raise ValueError('Resolve existing chart orders/position before a standalone entry')
        if any(t.contract.conId == cid and t.order.account == account for t in conn.ib.openTrades()):
            raise ValueError('A working order already exists for this contract')
        routed = routed_contract(contract, 'OVERNIGHT')
        self.validate_overnight_price(conn, routed, cid, amount)
        oid = conn.ib.client.getReqId()
        ref = 'WheelPaper:' + request_id
        # Persist ownership before sending. Unknown outcomes remain blocked, never replayed.
        self.save_group(account, cid, dict(ids=dict(entry=oid), side=1, ref=ref,
                                          mode='overnight_entry'))
        order = LimitOrder('BUY', int(qty), float(amount), orderId=oid, account=account,
                           tif='DAY', outsideRth=True, transmit=True, orderRef=ref)
        conn.ib.placeOrder(routed, order)

    def validate_overnight_price(self, conn, routed, cid, amount):
        details = conn._bounded_order_read(conn.ib.reqContractDetails, routed, timeout_seconds=3)
        matches = [d for d in details if d.contract.conId == cid and d.contract.secType == 'STK'
                   and d.contract.currency == 'USD']
        if len(matches) != 1: raise ValueError('Exact overnight contract details unavailable')
        detail = matches[0]
        venues = detail.validExchanges.split(',')
        if 'OVERNIGHT' not in venues: raise ValueError('IB does not advertise OVERNIGHT for this contract')
        ids = detail.marketRuleIds.split(',')
        try: rule_id = int(ids[venues.index('OVERNIGHT')])
        except (IndexError, ValueError): raise ValueError('Overnight price rule unavailable')
        rules = conn._bounded_order_read(conn.ib.reqMarketRule, rule_id, timeout_seconds=3)
        ticks = [r for r in rules if Decimal(str(r.lowEdge)) <= amount and r.increment > 0]
        if not ticks: raise ValueError('Overnight price increment unavailable')
        tick = Decimal(str(max(ticks, key=lambda r:r.lowEdge).increment))
        if amount % tick: raise ValueError('Price does not match overnight tick size')

    def perform(self, conn, account, cid, body, request_id):
        contract=contracts.resolve(conn,cid)
        if contract.secType not in ('STK','FUT','OPT'): raise ValueError('This contract supports chart viewing only')
        if body.get('action')!='submit':
            # Refresh canonical broker fields before copying an active order.
            conn._bounded_order_read(conn.ib.reqOpenOrders,timeout_seconds=3)
        current=self.state(conn,cid)
        action=body.get('action')
        if body.get('mode') == 'overnight_entry':
            if action != 'submit': raise ValueError('Overnight entry mode only supports submit')
            return self.submit_overnight_entry(conn, account, cid, contract, current, body, request_id)
        group = self.group(account, cid)
        if group and group.get('mode') == 'overnight_entry':
            if action == 'manage_entry':
                import copy
                if not current['known'] or body.get('expected_ref') != group.get('ref'):
                    raise ValueError('Order identity changed; refresh Orders')
                trade = getattr(self, '_resolved_trades', {}).get(group['ids']['entry'])
                if not trade or trade.order.account != account or trade.contract.conId != cid or trade.order.orderRef != group['ref']:
                    raise ValueError('Exact owned order unavailable')
                if trade.orderStatus.status not in ('Submitted', 'PreSubmitted'):
                    raise ValueError('Wait for a confirmed working order')
                if trade.contract.exchange != 'OVERNIGHT' or trade.order.orderType != 'LMT':
                    raise ValueError('Order route/type changed; verify Gateway')
                if body.get('operation') == 'cancel':
                    conn.ib.cancelOrder(trade.order)
                    return
                if body.get('operation') != 'amend': raise ValueError('Unsupported entry operation')
                if trade.orderStatus.filled or trade.fills:
                    raise ValueError('Entry has fills; refresh before changing it')
                if body.get('expected_price') != trade.order.lmtPrice:
                    raise ValueError('Order price changed; refresh Orders')
                try: amount = Decimal(str(body.get('price')))
                except Exception: raise ValueError('Invalid entry price')
                if not amount.is_finite() or amount <= 0: raise ValueError('Invalid entry price')
                self.validate_overnight_price(conn, trade.contract, cid, amount)
                # Validation can pump broker events; recheck before the write.
                if trade.isDone() or trade.orderStatus.filled or trade.fills or trade.orderStatus.status not in ('Submitted','PreSubmitted'):
                    raise ValueError('Order changed while validating; refresh Orders')
                amended = copy.copy(trade.order)
                amended.lmtPrice = float(amount)
                self.modify_exit(conn, trade, amended, 'lmtPrice')
                return
            if action != 'cancel_entry':
                raise ValueError('Standalone overnight entry has no TP/SL; only explicit entry cancellation is supported')
            trade = getattr(self, '_resolved_trades', {}).get(group['ids']['entry'])
            if not trade: raise ValueError('Entry status needs Gateway reconciliation')
            if trade.isDone(): raise ValueError('Entry is already finished')
            conn.ib.cancelOrder(trade.order)
            return
        def price(value):
            try: number=float(value)
            except (TypeError,ValueError): raise ValueError('Invalid price')
            if not math.isfinite(number) or number<=0: raise ValueError('Invalid price')
            state=stock_chart.active
            rules=state.get('price_rules',[]) if state and state['con_id']==cid else []
            increments=[r['increment'] for r in rules if r['low']<=number]
            if not increments: raise ValueError('Wait for contract price increments')
            tick=Decimal(str(increments[-1])); amount=Decimal(str(number))
            if abs(amount/tick-(amount/tick).to_integral_value())>Decimal('0.000001'): raise ValueError('Price does not match contract tick size')
            return number
        if action=='submit':
            if current['active'] or not current['known']: raise ValueError('An existing chart order needs resolution first')
            if current['position'] or any(t.contract.conId==cid and t.order.account==account for t in conn.ib.openTrades()):
                raise ValueError('Close existing position/orders for this contract before starting a new bracket')
            side=body.get('side'); qty=body.get('quantity')
            if side not in (-1,1) or not isinstance(qty,(int,float)) or not math.isfinite(qty) or qty!=int(qty) or not 1<=qty<=(10 if contract.secType in ('FUT','OPT') else 1000): raise ValueError('Invalid paper order size or side')
            entry=price(body.get('entry')); tp=price(body.get('tp')); sl=price(body.get('sl'))
            if side*(tp-entry)<=0 or side*(sl-entry)>=0: raise ValueError('TP and SL must be on opposite sides of entry')
            if body.get('entry_type') not in ('LMT','STP'): raise ValueError('Unsupported entry type')
            if contract.secType in ('FUT','OPT'):
                group=dict(ids={},lots=[],side=side,ref='WheelPaper:'+request_id)
                self.add_lots(conn,account,cid,contract,group,int(qty),body['entry_type'],entry,tp,sl)
                return
            buy='BUY' if side==1 else 'SELL'; sell='SELL' if side==1 else 'BUY'
            ids={role:conn.ib.client.getReqId() for role in ('entry','tp','sl')}
            parent=(LimitOrder if body['entry_type']=='LMT' else StopOrder)(buy,qty,entry,orderId=ids['entry'],transmit=False)
            take=LimitOrder(sell,qty,tp,orderId=ids['tp'],parentId=ids['entry'],transmit=False)
            stop=StopOrder(sell,qty,sl,orderId=ids['sl'],parentId=ids['entry'],transmit=True)
            with self.database() as db:
                db.execute('INSERT OR REPLACE INTO chart_paper_groups VALUES(?,?,?)',(account,cid,json.dumps(dict(ids=ids,side=side,ref='WheelPaper:'+request_id))))
            for order in (parent,take,stop):
                order.account=account;order.tif='DAY';order.orderRef='WheelPaper:'+request_id
                conn.ib.placeOrder(contract,order)
            return
        if not current['known']: raise ValueError('Orders need Gateway reconciliation before another action')
        group=self.group(account,cid)
        if not group: raise ValueError('No chart bracket for this contract')
        trades=getattr(self,'_resolved_trades',{})
        if action in ('add','trim'):
            if not group.get('lots'):
                raise ValueError('This older bracket cannot be scaled without replacing protection; start a new protected futures bracket')
            qty = body.get('quantity')
            if isinstance(qty,bool) or not isinstance(qty,(int,float)) or not math.isfinite(qty) or qty != int(qty) or qty < 1:
                raise ValueError('Invalid adjustment quantity')
            size = abs(current['position'])
            if not size or current['position'] * group['side'] <= 0: raise ValueError('No filled chart position')
            if action == 'trim' and qty >= size: raise ValueError('Trim must leave a position; use Close Position')
            if action == 'add' and size + qty > 10: raise ValueError('Resulting position exceeds the chart quantity limit')
            owned = sum((1 if t.order.action == 'BUY' else -1) * max(float(t.orderStatus.filled),sum(float(f.execution.shares) for f in t.fills))
                        for oid,t in trades.items() if oid in group['ids'].values())
            if abs(owned-current['position']) > .000001: raise ValueError('Position differs from chart fills; reconcile Gateway')
            if any(t.order.orderId not in group['ids'].values() for t in conn.ib.openTrades() if t.contract.conId==cid and t.order.account==account):
                raise ValueError('Other working orders exist; review Gateway')
            live = []
            for lot in group['lots']:
                parent, take, stop = [trades.get(lot[r]) for r in ('entry','tp','sl')]
                if not all((parent,take,stop)): raise ValueError('Lot status needs reconciliation')
                if parent.orderStatus.status != 'Filled': raise ValueError('Wait for all entry orders to finish')
                if take.orderStatus.status == 'Filled' or stop.orderStatus.status == 'Filled': continue
                if lot.get('closing') or take.isDone() or stop.isDone(): raise ValueError('An exit needs reconciliation before another adjustment')
                live.append(lot)
            if len(live) != size: raise ValueError('Protected lot count differs from position')
            if action == 'add':
                self.add_lots(conn,account,cid,contract,group,int(qty),'MKT',0,price(current['tp']),price(current['sl']))
            else:
                self.exit_lots(conn,account,cid,group,live[:int(qty)],trades,price,action,request_id)
            return
        if action in ('amend','be'):
            role='sl' if action=='be' else body.get('role')
            if role not in ('tp','sl'): raise ValueError('Only TP and SL can be amended')
            trade=next((trades.get(lot[role]) for lot in group.get('lots',[]) if trades.get(lot[role]) and not trades[lot[role]].isDone()),None) if group.get('lots') else trades.get(group['ids'][role])
            if not trade or trade.isDone(): raise ValueError('Exit order is no longer working')
            if action=='be':
                if not current['position']: raise ValueError('BE requires a filled position')
                base=current['entry']; rules=stock_chart.active.get('price_rules',[]) if stock_chart.active and stock_chart.active['con_id']==cid else []
                ticks=[r['increment'] for r in rules if r['low']<=base]
                if not ticks: raise ValueError('Wait for contract tick size')
                tick=Decimal(str(ticks[-1])); sign=1 if current['position']>0 else -1
                from decimal import ROUND_FLOOR
                rounded=(Decimal(str(base))/tick).to_integral_value(rounding=ROUND_CEILING if sign>0 else ROUND_FLOOR)*tick
                new_price=price(float(rounded+sign*tick))
            else: new_price=price(body.get('price'))
            if action=='be' and not group.get('lots') and group['side']*(current['sl']-new_price)>=0: return
            other=current['tp'] if role=='sl' else current['sl']
            if other>0 and group['side']*((other-new_price) if role=='sl' else (new_price-other))<=0: raise ValueError('TP and SL cannot cross')
            # Initial TP is held (transmit=False) until the last bracket leg.
            # A later amendment must be transmitted on its own.
            targets=[trades.get(lot[role]) for lot in group['lots']] if group.get('lots') else [trade]
            for target in targets:
                if not target or target.isDone(): continue
                if action=='be' and group['side']*(target.order.auxPrice-new_price)>=0: continue
                import copy
                amended=copy.copy(target.order)
                if role=='sl': amended.auxPrice=new_price
                else: amended.lmtPrice=new_price
                amended.transmit=True;self.modify_exit(conn,target,amended,'auxPrice' if role=='sl' else 'lmtPrice')
            return
        if action=='close' and group.get('lots'):
            live=[]
            for lot in group['lots']:
                parent,take,stop=[trades.get(lot[r]) for r in ('entry','tp','sl')]
                if not all((parent,take,stop)): raise ValueError('Lot status needs reconciliation')
                if take.orderStatus.status=='Filled' or stop.orderStatus.status=='Filled': continue
                if parent.orderStatus.status=='Filled':
                    live.append(lot)
                elif not parent.isDone():
                    # Cancel only an unfilled unit; never remove filled-unit protection.
                    conn.ib.cancelOrder(parent.order)
            if live: self.exit_lots(conn,account,cid,group,live,trades,price,action,request_id)
            return
        if action=='close':
            working=[t for t in trades.values() if t.order.orderId in group['ids'].values() and not t.isDone()]
            for trade in working: conn.ib.cancelOrder(trade.order)
            import time
            deadline=time.monotonic()+4
            while any(not t.isDone() for t in working) and time.monotonic()<deadline: conn.ib.sleep(.05)
            if any(not t.isDone() for t in working): raise RuntimeError('Cancellation not confirmed')
            positions=conn._bounded_order_read(conn.ib.reqPositions,timeout_seconds=3)
            position=next((p for p in positions if p.account==account and p.contract.conId==cid),None)
            expected = sum((1 if t.order.action == 'BUY' else -1) * max(float(t.orderStatus.filled),
                           sum(float(f.execution.shares) for f in t.fills)) for t in trades.values()
                           if t.order.orderId in group['ids'].values())
            actual = float(position.position) if position else 0
            if abs(expected - actual) > .000001:
                raise ValueError('Position and executions are not synchronized; review before closing')
            if position and position.position:
                if any(t.contract.conId==cid and t.order.account==account for t in conn.ib.openTrades()): raise ValueError('Other working orders exist; review Gateway')
                order=MarketOrder('SELL' if position.position>0 else 'BUY',abs(position.position),account=account,tif='DAY',orderRef=group.get('ref','WheelPaper:'+request_id))
                order.orderId=conn.ib.client.getReqId();group['ids']['close']=order.orderId
                with self.database() as db: db.execute('UPDATE chart_paper_groups SET orders=? WHERE account=? AND con_id=?',(json.dumps(group),account,cid))
                conn.ib.placeOrder(contract,order)
            return
        raise ValueError('Unsupported paper chart action')
