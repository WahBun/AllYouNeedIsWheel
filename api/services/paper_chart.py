"""Paper-only chart brackets. All calls run on the serialized IB owner.

The journal claims each request before a broker write. Unknown outcomes are
never automatically replayed. Real accounts cannot use this execution path.
"""
import json
import hashlib
import math
import time
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
    def __init__(self, path, group_id=None):
        self.path = path
        self.group_id = str(UUID(group_id)) if group_id else None

    def database(self):
        db = sqlite3.connect(self.path)
        db.execute('CREATE TABLE IF NOT EXISTS chart_paper_requests (id TEXT PRIMARY KEY, account TEXT NOT NULL, body TEXT NOT NULL, result TEXT)')
        db.execute('CREATE TABLE IF NOT EXISTS chart_paper_groups (account TEXT, con_id INTEGER, orders TEXT NOT NULL, PRIMARY KEY(account,con_id))')
        db.execute('CREATE TABLE IF NOT EXISTS chart_paper_independent (account TEXT, con_id INTEGER, group_id TEXT, orders TEXT NOT NULL, PRIMARY KEY(account,con_id,group_id))')
        db.commit()
        return db

    def group(self, account, cid):
        with self.database() as db:
            if self.group_id:
                row = db.execute('SELECT orders FROM chart_paper_independent WHERE account=? AND con_id=? AND group_id=?',(account,cid,self.group_id)).fetchone()
            else:
                row = db.execute('SELECT orders FROM chart_paper_groups WHERE account=? AND con_id=?',(account,cid)).fetchone()
        return json.loads(row[0]) if row else None

    def group_choices(self, account, cid):
        with self.database() as db:
            records = db.execute('SELECT group_id,orders FROM chart_paper_independent WHERE account=? AND con_id=? ORDER BY rowid',(account,cid)).fetchall()
            original = db.execute('SELECT orders FROM chart_paper_groups WHERE account=? AND con_id=?',(account,cid)).fetchone()
        return ([dict(id='',ref=json.loads(original[0]).get('ref'))] if original else []) + [dict(id=k,ref=json.loads(v).get('ref')) for k,v in records]

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
                      active=False, known=True, orders=[], entry=0, tp=0, sl=0, side=1, status='idle', group_id=self.group_id or '', group_choices=self.group_choices(account,cid))
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
        if not group:
            self._resolved_trades = trades
            if position and result['position']:
                size=result['position']
                try:
                    multiplier=float(position.contract.multiplier or (1 if position.contract.secType=='STK' else 0))
                    basis=abs(float(position.avgCost))/multiplier if multiplier>0 else 0
                except (AttributeError,TypeError,ValueError,ZeroDivisionError): basis=0
                working=any(t.order.account==account and t.contract.conId==cid for t in conn.ib.openTrades())
                valid=math.isfinite(size) and size==int(size) and math.isfinite(basis) and basis>0
                snapshot=dict(position=size,entry=basis)
                signature=hashlib.sha256(json.dumps([account,cid,snapshot],sort_keys=True).encode()).hexdigest()[:32]
                result.update(active=True,position_only=True,status='filled',side=1 if size>0 else -1,entry=basis,
                    order_ref='WheelPaper:position:'+signature,edit_snapshot=[snapshot],
                    protection_manageable=valid and not working and not result['group_choices'],requested_protection=[],
                    protection=self.protection_progress([],size),
                    protection_block_reason='Use the existing order group to manage this position' if result['group_choices'] else 'Existing working orders need reconciliation' if working else '' if valid else 'Wait for a valid whole position and cost basis')
                result['protection']['status']='not_requested'
            return result
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
            self.save_group(account,cid,group)
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
        for row in rows:
            if row['role'].split('_')[0] == 'entry':
                row['entry_kind'] = group.get('entry_kinds', {}).get(str(row['order_id']), 'unknown')
        confirmed = {r['role']:r for r in rows if r['status'] in ('Filled','Cancelled','ApiCancelled','Inactive')}
        if confirmed != group.get('terminal'):
            group['terminal'] = confirmed
            self.save_group(account,cid,group)
        result.update(orders=rows, side=group['side'], known=all(r['status']!='Unknown' for r in rows))
        result['active']=any(r['status'] not in ('Filled','Cancelled','ApiCancelled','Inactive') for r in rows) or result['position']!=0
        result['status']='working' if result['active'] else 'done'
        for row in rows:
            if row['role'] in ('entry','tp','sl'): result[row['role']]=row['price']
        if group.get('lots'):
            for role in ('tp','sl'):
                live_rows=[r for r in rows if r['role'].split('_')[0]==role and r['status'] not in ('Filled','Cancelled','ApiCancelled','Inactive')]
                if role=='tp':
                    ordinary=[r for r in live_rows if not any(l.get('closing') and l.get('tp')==r['order_id'] for l in group['lots'])]
                    result[role]=ordinary[-1]['price'] if ordinary else 0
                    result['add_tp']=result[role] or group.get('ordinary_tp') or next((l.get('original_tp') for l in group['lots'] if l.get('original_tp')),0)
                elif live_rows: result[role]=live_rows[-1]['price']
            result['scalable']=all('tp' in lot and 'sl' in lot for lot in group['lots'])
            result['quantity']=sum(max(0,r['quantity']-r['filled']) for r in rows if r['role'].split('_')[0]=='entry' and r['status'] not in ('Filled','Cancelled','ApiCancelled','Inactive'))
        parent=trades.get(group['ids'].get('entry'))
        if parent and parent.orderStatus.avgFillPrice>0: result['entry']=parent.orderStatus.avgFillPrice
        elif parent and trade_fills(parent):
            fills = trade_fills(parent)
            total = sum(float(f.execution.shares) for f in fills)
            if total > 0: result['entry'] = sum(float(f.execution.shares)*float(f.execution.price) for f in fills)/total
        if group.get('origin_position'):
            result['entry']=group['origin_entry']
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
            size = abs(group.get('origin_position',0)); cost = size*group.get('origin_entry',0)
            for _, _, action, quantity, fill_price in sorted(events.values()):
                if action == ('BUY' if group['side'] == 1 else 'SELL'):
                    size += quantity; cost += quantity * fill_price
                elif size and quantity <= size:
                    cost -= cost * quantity / size; size -= quantity
            if size and abs(size - abs(result['position'])) < .000001: result['entry'] = cost / size
        result['be_applied']=bool(result['position'] and result['sl']>0 and result['side']*(result['sl']-result['entry'])>0)
        result['rejected']=any(r['status']=='Inactive' and '_retired_' not in r['role'] for r in rows)
        result['protection'] = self.protection_progress(rows, result['position'], group.get('lots'))
        protective = [r for r in rows if r['role'].split('_')[0] in ('tp', 'sl')]
        result['protection_cancelable'] = bool(result['known'] and result['position'] and protective
            and all(r['status'] in ('Filled','Cancelled','ApiCancelled','Inactive') for r in rows if r['role'].split('_')[0]=='entry')
            and any(r['status'] in ('Submitted','PreSubmitted') for r in protective))
        for role in ('tp', 'sl'):
            if not any(r['role'].split('_')[0] == role and r['status'] not in ('Filled','Cancelled','ApiCancelled','Inactive') for r in rows):
                result[role] = 0
        if result['position'] and protective and all(r['status'] in ('Filled','Cancelled','ApiCancelled','Inactive') for r in protective):
            result['protection']['status'] = 'unprotected'
            result['scalable'] = False
            result['be_applied'] = False

        requested = group.get('requested_protection', ['tp', 'sl'])
        result['requested_protection'] = requested
        coverage = result['protection']
        if result['known'] and result['position'] and all(coverage[r] == (abs(result['position']) if r in requested else 0) for r in ('tp','sl')):
            coverage['status'] = 'covered' if len(requested)==2 else 'tp_only' if requested==['tp'] else 'sl_only' if requested==['sl'] else ('unprotected' if protective else 'not_requested')
        result['protection_manageable'] = bool(result['known'] and result['position'] and not group.get('pending_protection')
            and all(r['status'] in ('Filled','Cancelled','ApiCancelled','Inactive') for r in rows if r['role'].split('_')[0] in ('entry','close')))
        if coverage['status'] != 'covered': result['scalable'] = False

        if group.get('origin_position'):
            owned=group['origin_position']+group['side']*sum((1 if r['role'].split('_')[0]=='entry' else -1)*r['filled'] for r in rows)
            result['protection_manageable'] = result['protection_manageable'] and abs(owned-result['position'])<.000001
            if abs(owned-result['position'])>=.000001:
                result['protection_block_reason']='Position changed outside this protection group; reconcile orders'

        if group.get('lots'):
            projection=dict(realized=0.0,known=True,targets=[])
            stop_targets=[];stop_known=True
            multiplier=float(next(iter(trades.values())).contract.multiplier or 1) if trades else 1
            def execution_totals(trade):
                if not trade: return 0.0, 0.0
                fills=trade_fills(trade)
                shares=sum(float(f.execution.shares) for f in fills)
                quantity=max(float(trade.orderStatus.filled or 0),shares)
                average=float(trade.orderStatus.avgFillPrice or 0)
                if shares and shares>=quantity:
                    average=sum(float(f.execution.shares)*float(f.execution.price) for f in fills)/shares
                return quantity,average
            for lot in group['lots']:
                parent=trades.get(lot['entry'])
                parent_filled,basis=execution_totals(parent)
                if not parent: projection['known']=False; continue
                if not parent_filled:
                    if parent.orderStatus.status=='Filled': projection['known']=False
                    continue
                if basis<=0: projection['known']=False; continue
                for role in ('tp','sl'):
                    if role not in lot: continue
                    trade=trades.get(lot[role])
                    if not trade: projection['known']=False; continue
                    filled,actual=execution_totals(trade)
                    if filled:
                        if actual<=0: projection['known']=False
                        else: projection['realized']+=(actual-basis)*group['side']*filled*multiplier
                    if role=='tp' and not trade.isDone():
                        stop=trades.get(lot.get('sl'))
                        remaining=max(0,parent_filled-filled-execution_totals(stop)[0])
                        if remaining: projection['targets'].append(dict(order_id=trade.order.orderId,price=trade.order.lmtPrice,
                            quantity=remaining,entry=basis,side=group['side'],multiplier=multiplier,trim=bool(lot.get('closing'))))
                take=trades.get(lot.get('tp'));stop=trades.get(lot.get('sl'))
                remaining=max(0,parent_filled-execution_totals(take)[0]-execution_totals(stop)[0])
                if remaining:
                    if not stop or stop.isDone() or stop.order.orderType!='STP' or not (0<float(stop.order.auxPrice)<1e100):
                        stop_known=False
                    else:
                        stop_targets.append(dict(order_id=stop.order.orderId,price=stop.order.auxPrice,
                            quantity=remaining,entry=basis,side=group['side'],multiplier=multiplier))
            result['tp_projection']=projection
            result['sl_projection']=dict(realized=projection['realized'],known=projection['known'] and stop_known
                and abs(sum(r['quantity'] for r in stop_targets)-abs(result['position']))<.000001,targets=stop_targets)

        adjustment = group.get('adjustment')
        if adjustment:
            by_id = {r['order_id']: r for r in rows}
            selected = [by_id.get(oid, dict(status='Unknown', filled=0)) for oid in adjustment['orders']]
            filled = sum(min(1, r['filled'] + by_id.get(sl, {}).get('filled', 0)) for r, sl in zip(selected, adjustment.get('stops', [None]*len(selected))))
            result['pending_exits'] = [dict(order_id=r['order_id'], price=r['price'],
                quantity=max(0,r['quantity']-r['filled']), status=r['status'], action=adjustment['action'])
                for r in selected if r.get('order_id') in adjustment.get('acknowledged', [])
                and r['status'] in ('Submitted','PreSubmitted','PendingCancel') and r.get('quantity',0)>r['filled']]
            for pending in result['pending_exits']:
                lot=next((lot for lot in group.get('lots',[]) if lot.get('tp')==pending['order_id']),{})
                pending['action']=lot.get('exit_action',adjustment['action'])
                pending['plan_id']=lot.get('plan_id',str(pending['order_id']))
                ordinary=[r['price'] for r in rows if r['role'].split('_')[0]=='tp' and r['status'] in ('Submitted','PreSubmitted')
                          and not any(l.get('tp')==r['order_id'] and l.get('closing') for l in group.get('lots',[]))]
                pending['restore_price']=ordinary[-1] if ordinary else group.get('ordinary_tp') or lot.get('original_tp')
            result['adjustment'] = dict(action=adjustment['action'], requested=len(selected), filled=filled,
                remaining=max(0, len(selected)-filled), pending=sum(max(0, 1-r['filled']) for r in selected if r.get('order_id') in adjustment.get('acknowledged', []) and r['status'] in ('Submitted','PreSubmitted')), position=result['position'],
                status='filled' if filled == len(selected) else 'unknown' if any(r['status']=='Unknown' for r in selected) or adjustment.get('outcome') == 'unknown'
                else 'rejected' if adjustment.get('outcome') == 'rejected' or any(r['status']=='Inactive' for r in selected)
                else 'canceled' if any(r['status'] in ('Cancelled','ApiCancelled') for r in selected)
                else 'working')
        if adjustment and adjustment.get('action')=='close':
            closing_ids=set(adjustment.get('latest_orders',[]))
            closing_pairs=[(oid,sl) for oid,sl in zip(adjustment['orders'],adjustment.get('stops',[])) if oid in closing_ids]
            closed=sum(min(1,by_id.get(oid,{}).get('filled',0)+by_id.get(sl,{}).get('filled',0)) for oid,sl in closing_pairs)
            pending_entries=any(r['role'].split('_')[0]=='entry' and r['status'] not in ('Filled','Cancelled','ApiCancelled','Inactive') for r in rows)
            result['close_progress']=dict(requested=len(closing_pairs),filled=closed,remaining=abs(result['position']),
                status='completed' if result['known'] and not result['active'] and not pending_entries
                else 'unknown' if not result['known'] else 'working' if result['adjustment']['status'] in ('working','filled') else result['adjustment']['status'])
        close_row=next((r for r in rows if r['role']=='close'),None)
        if close_row:
            result['close_progress']=dict(requested=close_row['quantity'],filled=close_row['filled'],remaining=abs(result['position']),
                status='completed' if result['known'] and not result['position'] and not result['active']
                else 'unknown' if not result['known'] else close_row['status'])
        if group.get('lots'):
            reserved=sum(r['quantity'] for r in result.get('pending_exits',[]))
            result['trim_available']=max(0,abs(result['position'])-reserved)
        if group.get('mode') == 'overnight_entry':
            result['broker_messages'] = [entry.message for t in trades.values()
                if t.order.orderId in group['ids'].values() for entry in t.log if entry.message]
            result.update(mode='overnight_entry', scalable=False, tif='OVERNIGHT' if parent and parent.contract.exchange == 'OVERNIGHT' else parent.order.tif if parent else 'DAY',
                          route=parent.contract.exchange if parent else '', protection=dict(status='not_requested'))
            errors = [entry for t in trades.values() if t.order.orderId in group['ids'].values()
                      for entry in t.log if entry.errorCode and entry.errorCode != 399 and
                      (200 <= entry.errorCode < 2100 or entry.errorCode >= 10000)]
            statuses = {r['status'] for r in rows}
            result['rejected'] = result['rejected'] or bool(errors and statuses <= {'Cancelled', 'ApiCancelled', 'Inactive'})
            result['status'] = ('rejected' if result['rejected'] else 'unknown' if not result['known']
                else 'filled' if statuses == {'Filled'} else 'canceled' if statuses <= {'Cancelled', 'ApiCancelled'}
                else 'working' if statuses <= {'Submitted', 'PreSubmitted'} else 'pending')
        closing = next((r for r in rows if r['role'] == 'close'), None)
        if closing:
            result['closing'] = closing['status'] in ('Submitted', 'PreSubmitted', 'PendingSubmit', 'PendingCancel')
            result['close_status'] = closing['status']
            if group.get('mode') == 'overnight_entry':
                if closing['status'] in ('Submitted', 'PreSubmitted'): result['status'] = 'working'
                elif closing['status'] == 'Filled' and not result['position']: result['status'] = 'done'
        parents = [r for r in rows if r['role'].split('_')[0] == 'entry']
        result['order_ref'] = group.get('ref')
        result['tif'] = result.get('tif') or (parent.order.tif if parent else 'DAY')
        result['entry_type'] = parent.order.orderType if parent else 'LMT'
        result['allowed_tifs'] = ['DAY', 'GTC']
        if parent and parent.contract.secType == 'STK' and parent.contract.currency == 'USD' and parent.order.action in ('BUY', 'SELL') and parent.order.orderType == 'LMT':
            result['allowed_tifs'].append('OVERNIGHT')
        result['entry_editable'] = bool(parents and result['known'] and not result['position']
            and not group.get('pending_edit') and all(r['filled'] == 0 and
            r['status'] in ('Submitted', 'PreSubmitted') for r in rows))
        result['edit_snapshot'] = [dict(order_id=r['order_id'], price=r['price'], quantity=r['quantity'],
            filled=r['filled'], status=r['status'], tif=trades[r['order_id']].order.tif if r['order_id'] in trades else '') for r in rows]
        if group.get('pending_resize'):
            result['sync_error']=True
            result['scalable']=False
            for key in ('tp_projection','sl_projection'):
                if key in result: result[key]['known']=False
        return result

    @staticmethod
    def protection_progress(rows, position, lots=None):
        contingent = {'tp': 0, 'sl': 0}
        if lots:
            by_id = {r['order_id']: r for r in rows}
            held = set()
            for lot in lots:
                parent = by_id.get(lot['entry'])
                if parent and parent['filled'] == 0:
                    held.update(lot[r] for r in ('tp', 'sl') if r in lot)
            for row in rows:
                role = row['role'].split('_')[0]
                if row['order_id'] in held and role in contingent and row['status'] in ('Submitted', 'PreSubmitted'):
                    contingent[role] += max(0, row['quantity'] - row['filled'])
            rows = [r for r in rows if r['order_id'] not in held]
        quantities = {role: sum(max(0, r['quantity']-r['filled']) for r in rows
            if r['role'].split('_')[0] == role and r['status'] in ('Submitted','PreSubmitted')) for role in ('tp','sl')}
        size = abs(position)
        return dict(**quantities, pending_entry_tp=contingent['tp'], pending_entry_sl=contingent['sl'], remaining_position=size,
                    status='flat' if size == 0 else 'unknown' if any(r['status']=='Unknown' for r in rows)
                    else 'covered' if quantities['tp'] == size and quantities['sl'] == size else 'needs_review')

    def request_status(self, conn, cid, request_id):
        """Read-only reconciliation. Never replay a broker write."""
        account = paper_account(conn)
        request_id = str(UUID(request_id))
        with self.database() as db:
            row = db.execute('SELECT body,result FROM chart_paper_requests WHERE id=? AND account=?', (request_id, account)).fetchone()
        if not row:
            # Serialized with execute(): no ledger row means no broker write started.
            # Reserve the UUID as rejected so a delayed HTTP submission cannot run later.
            tombstone = json.dumps(dict(con_id=cid, group_id=self.group_id, not_started=True), sort_keys=True)
            result = json.dumps(dict(success=False, status='rejected', message='Request did not start; no order was sent'))
            with self.database() as db:
                inserted = db.execute('INSERT OR IGNORE INTO chart_paper_requests VALUES(?,?,?,?)',
                                      (request_id, account, tombstone, result)).rowcount
            return dict(confirmed=bool(inserted), status='rejected' if inserted else 'unknown')
        body = json.loads(row[0])
        if body.get('group_id') != self.group_id: raise ValueError('Request order group mismatch')
        if body.get('con_id') != cid: raise ValueError('Request contract mismatch')
        result = json.loads(row[1]) if row[1] else {}
        if result.get('status') in ('acknowledged','rejected','working','filled','canceled','pending','done','reconciled'):
            return dict(confirmed=True, status=result['status'])
        authoritative = conn._bounded_order_read(conn.ib.reqOpenOrders, timeout_seconds=3)
        state = self.state(conn, cid)
        group = self.group(account, cid) or {}
        def resolved(status):
            # Persist reconciliation: a later read/restart must not resurrect the lock.
            if group.get('pending_edit') == request_id:
                group.pop('pending_edit'); self.save_group(account, cid, group)
            with self.database() as db:
                db.execute('UPDATE chart_paper_requests SET result=? WHERE id=? AND account=?',
                    (json.dumps(dict(success=status != 'rejected', status=status)), request_id, account))
            return dict(confirmed=True, status=status)
        if body.get('action')=='close' and state['known']:
            cancellation=group.get('close_cancellation',{})
            if cancellation.get('request_id')==request_id:
                rows={r['order_id']:r for r in state['orders']}
                if all(rows.get(oid,{}).get('status') in ('Filled','Cancelled','ApiCancelled')
                       for oid in cancellation['parents']):
                    # Only the cancellation phase ran. Release the uncertainty lock;
                    # never send the remaining close writes from a status read.
                    group.pop('close_cancellation',None);self.save_group(account,cid,group)
                    return resolved('reconciled')
        if body.get('action')=='resize_trim' and state['known'] and group.get('ref')==body.get('expected_ref'):
            operation=group.get('pending_resize',{})
            if operation.get('id')==request_id:
                working={t.order.orderId:t for t in authoritative if t.order.account==account and t.contract.conId==cid and t.order.orderRef==group['ref']}
                rows={r['order_id']:r for r in state['orders']}
                changes=operation['changes']
                if all(rows.get(c['order_id'],{}).get('status')=='Filled' or c['order_id'] in working
                       and working[c['order_id']].orderStatus.status in ('Submitted','PreSubmitted')
                       and working[c['order_id']].order.lmtPrice==c['price'] for c in changes):
                    for change in changes:self.finish_resize_change(account,cid,change,operation['plan_id'])
                    group=self.group(account,cid);group.pop('pending_resize',None);self.save_group(account,cid,group)
                    return resolved('reconciled')
        if body.get('action') == 'cancel_protection' and state['known'] and group.get('ref') == body.get('expected_ref'):
            rows = self.protection_cancel_rows(state,group,body.get('role'))
            if rows and all(r['status'] in ('Filled', 'Cancelled', 'ApiCancelled', 'Inactive') for r in rows):
                group['requested_protection']=[r for r in group.get('requested_protection',['tp','sl']) if body.get('role') and r!=body['role']]
                self.save_group(account,cid,group)
                return resolved('canceled')
        if body.get('action') == 'set_protection' and state['known'] and group.get('ref') == body.get('expected_ref'):
            operation=group.get('protection_request', {})
            if operation.get('id')==request_id:
                targets=[r for r in state['orders'] if r['order_id'] in operation['ids'].values()]
                if len(targets)==len(operation['ids']) and all(r['status'] in ('Submitted','PreSubmitted','Filled','Cancelled','ApiCancelled','Inactive') for r in targets):
                    group.pop('pending_protection',None); self.save_group(account,cid,group)
                    return resolved('reconciled')
            elif all(r['status'] in ('Filled','Cancelled','ApiCancelled','Inactive') for r in state['orders'] if r['role'].split('_')[0] in ('tp','sl')):
                group.pop('pending_protection',None); self.save_group(account,cid,group)
                return resolved('canceled')
        if body.get('action') in ('trim','close') and state['known']:
            adjustment=group.get('adjustment',{})
            ids=set(adjustment.get('latest_orders',[]))
            if adjustment.get('request_id')==request_id and ids:
                working={t.order.orderId:t for t in authoritative if t.order.account==account and t.contract.conId==cid and t.order.orderRef==group.get('ref')}
                rows={r['order_id']:r for r in state['orders']}
                if all(rows.get(oid,{}).get('status')=='Filled' or oid in working and working[oid].orderStatus.status in ('Submitted','PreSubmitted') and working[oid].order.lmtPrice==adjustment.get('target_price') for oid in ids):
                    adjustment['acknowledged']=list(set(adjustment.get('acknowledged',[]))|ids)
                    adjustment['outcome']='acknowledged';self.save_group(account,cid,group)
                    return resolved('reconciled')
        if body.get('action')=='amend_add' and state['known'] and group.get('ref')==body.get('expected_ref'):
            oid=body.get('order_id')
            lot=next((l for l in group.get('lots',[]) if l['entry']==oid),None)
            row=next((r for r in state['orders'] if r['order_id']==oid),None)
            if lot and row:
                if row['filled'] or row['status']=='Filled': return resolved('filled')
                if row['status'] in ('Cancelled','ApiCancelled'): return resolved('canceled')
                matches=[t for t in authoritative if t.order.orderId==oid and t.order.account==account
                         and t.contract.conId==cid and t.order.orderRef==group['ref']
                         and t.orderStatus.status in ('Submitted','PreSubmitted') and t.order.orderType in ('LMT','STP')]
                if len(matches)==1 and getattr(matches[0].order,'lmtPrice' if matches[0].order.orderType=='LMT' else 'auxPrice')==body.get('price'):
                    return resolved('reconciled')
        if body.get('action') == 'cancel_add' and state['known'] and group.get('ref') == body.get('expected_ref'):
            lot = next((lot for lot in group.get('lots', []) if lot['entry'] == body.get('order_id')), None)
            rows = {r['order_id']: r for r in state['orders']}
            parent = rows.get(body.get('order_id'))
            if lot and parent:
                if parent['filled'] or parent['status'] == 'Filled':
                    return resolved('filled')
                if parent['status'] in ('Cancelled','ApiCancelled') and all(
                        rows.get(lot[r], {}).get('status') in ('Cancelled','ApiCancelled','Inactive') for r in ('tp','sl') if r in lot):
                    return resolved('canceled')
        if body.get('action') in ('amend','be') and state['known'] and group.get('ref') == body.get('expected_ref'):
            role='sl' if body['action']=='be' else body.get('role')
            target_ids={oid for key,oid in group.get('ids',{}).items() if key.split('_')[0]==role}
            if body.get('order_id') is not None: target_ids &= {body['order_id']}
            elif role=='tp': target_ids -= {lot['tp'] for lot in group.get('lots',[]) if lot.get('closing')}

            rows=[r for r in state['orders'] if r['order_id'] in target_ids]
            if body.get('restore_trim') and rows and all(r['status']=='Filled' for r in rows):
                self.finish_trim_restore(account,cid,group,body['order_id'])
                return resolved('filled')
            if rows and not state['active'] and not state['position']:
                return resolved('done')
            # Only actual broker snapshot rows can release an uncertain amendment.
            working=[t for t in authoritative if t.order.orderId in target_ids and t.order.account==account
                     and t.contract.conId==cid and t.order.orderRef==group.get('ref')]
            live_rows=[r for r in rows if r['status'] not in ('Filled','Cancelled','ApiCancelled','Inactive')]
            if body['action']=='amend' and live_rows and {t.order.orderId for t in working}=={r['order_id'] for r in live_rows} and all(
                    t.orderStatus.status in ('Submitted','PreSubmitted') and getattr(t.order,'auxPrice' if role=='sl' else 'lmtPrice')==body.get('price') for t in working):
                if body.get('restore_trim'):
                    self.finish_trim_restore(account,cid,group,body['order_id'])
                return resolved('reconciled')
        if body.get('action') == 'edit_entry' and state['known']:
            original = group.get('ref') == body.get('expected_ref')
            if original and state['orders'] and not state['position'] and all(
                    r['status'] in ('Cancelled', 'ApiCancelled') and not r['filled'] for r in state['orders']):
                # A delayed cancellation can finish after the replacement timed out.
                # Release the old request, but never submit its replacement on a GET.
                return resolved('canceled')
            # For a price-only edit, a fresh broker snapshot of that same order
            # resolves uncertainty even if IB retained the old price. Never resend.
            price_only = 'price' in body and not any(k in body for k in ('quantity','tif','cancel'))
            parent_ids = [oid for role, oid in group.get('ids', {}).items() if role.split('_')[0] == 'entry']
            confirmed_parent = [t for t in authoritative if t.order.orderId in parent_ids
                and t.order.account == account and t.contract.conId == cid and t.order.orderRef == body.get('expected_ref')
                and t.orderStatus.status in ('Submitted','PreSubmitted')]
            if group.get('pending_edit') == request_id and price_only and len(parent_ids) == len(confirmed_parent) == 1:
                return resolved('reconciled')
            parents = [r for r in state['orders'] if r['role'].split('_')[0] == 'entry']
            identity = group.get('ref') in (body.get('expected_ref'), 'WheelPaper:' + request_id)
            matches = identity and bool(parents) and all(r['status'] in ('Submitted','PreSubmitted') and not r['filled'] for r in parents)
            if 'price' in body: matches = matches and all(r['price'] == body['price'] for r in parents)
            if 'quantity' in body: matches = matches and sum(r['quantity'] for r in parents) == body['quantity']
            if 'tif' in body: matches = matches and state['tif'] == body['tif']
            if body.get('cancel'): matches = identity and all(r['status'] in ('Cancelled','ApiCancelled') and not r['filled'] for r in state['orders'])
            if matches:
                if group.get('pending_edit') == request_id:
                    return resolved('reconciled')
        return dict(confirmed=False,status='unknown')

    def execute(self, conn, cid, body):
        account=paper_account(conn,True)
        request_id=str(UUID(str(body.get('request_id',''))))
        if self.group_id: body=dict(body,group_id=self.group_id)
        encoded=json.dumps(dict(body,con_id=cid),sort_keys=True,allow_nan=False)
        with self.database() as db:
            old=db.execute('SELECT account,body,result FROM chart_paper_requests WHERE id=?',(request_id,)).fetchone()
            if old:
                if old[:2]!=(account,encoded): raise ValueError('Request identifier already used')
                return json.loads(old[2]) if old[2] else dict(success=False,status='unknown',message='Previous request needs broker reconciliation; not replayed')
            db.execute('INSERT INTO chart_paper_requests VALUES(?,?,?,NULL)',(request_id,account,encoded))
        try:
            self.perform(conn,account,cid,body,request_id)
            confirmed_price_edit = body.get('action') in ('amend', 'be', 'amend_add') or (body.get('action') == 'edit_entry'
                and 'price' in body and not any(k in body for k in ('quantity', 'tif', 'cancel')))
            if body.get('cancel') is not True and not confirmed_price_edit: conn.ib.sleep(.2)
            group = self.group(account, cid)
            if group and group.get('adjustment', {}).get('request_id') == request_id:
                group['adjustment']['outcome'] = 'acknowledged'
                self.save_group(account, cid, group)
            state=self.state(conn,cid)
            result=dict(success=not state.get('rejected',False),status='rejected' if state.get('rejected') else 'acknowledged',message='IB rejected a paper order; review Gateway' if state.get('rejected') else 'Paper request sent; broker status shown on chart',state=state)
            if body.get('action') == 'cancel_protection':
                result.update(success=True, status='canceled', message='Requested protection cancellation confirmed; position and remaining protection reflect broker state')
            if body.get('action') == 'cancel_add':
                parent = next((r for r in state['orders'] if r['order_id'] == body.get('order_id')), {})
                filled = bool(parent.get('filled') or parent.get('status') == 'Filled')
                result.update(success=True, status='filled' if filled else 'canceled',
                              message='Add filled before cancellation; position and protection retained' if filled else 'Add order canceled; existing position and protection retained')
            if state.get('mode') == 'overnight_entry':
                status = state['status']
                cancel_requested = (body.get('cancel') is True or body.get('action') == 'cancel_entry'
                    or (body.get('action') == 'manage_entry' and body.get('operation') == 'cancel'))
                result.update(success=status in ('working', 'filled', 'done') or (cancel_requested and status == 'canceled'), status=status,
                    message=(('Paper close order is ' if body.get('action') == 'close' else 'Paper limit order is ') + status +
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
            if self.group_id:
                db.execute('INSERT OR REPLACE INTO chart_paper_independent VALUES(?,?,?,?)',(account,cid,self.group_id,json.dumps(group)))
            else:
                db.execute('INSERT OR REPLACE INTO chart_paper_groups VALUES(?,?,?)',(account,cid,json.dumps(group)))

    def add_lots(self, conn, account, cid, contract, group, qty, kind, entry, tp, sl, entry_kind="entry"):
        for _ in range(qty):
            index = len(group['lots'])
            values = {r:v for r,v in (('tp',tp),('sl',sl)) if v is not None}
            group['requested_protection'] = list(values)
            ids = {role:conn.ib.client.getReqId() for role in ('entry', *values)}
            for role, oid in ids.items(): group['ids'][role if index==0 else f'{role}_{index}'] = oid
            group.setdefault('entry_kinds', {})[str(ids['entry'])] = entry_kind
            group['lots'].append(ids); self.save_group(account,cid,group)
            buy = 'BUY' if group['side']==1 else 'SELL'; sell = 'SELL' if group['side']==1 else 'BUY'
            parent = MarketOrder(buy,1) if kind=='MKT' else (LimitOrder if kind=='LMT' else StopOrder)(buy,1,entry)
            parent.orderId=ids['entry']; parent.transmit=not values
            orders=[parent]+[(LimitOrder if r=='tp' else StopOrder)(sell,1,v,orderId=ids[r],parentId=ids['entry'],transmit=False) for r,v in values.items()]
            orders[-1].transmit=True
            for order in orders:
                order.account=account;order.tif=group.get('tif', 'DAY') if order is parent else 'GTC';order.orderRef=group['ref']
                order.outsideRth = contract.secType == 'FUT'
                conn.ib.placeOrder(contract,order)

    def exit_lots(self, conn, account, cid, group, lots, trades, price, action, request_id, limit_target=None):
        import copy
        if limit_target is None:
            state=stock_chart.active
            if not state or state['con_id']!=cid: raise ValueError('Wait for a current quote')
            # Use the chart's quote freshness rules, independently of its interval.
            contract = trades[lots[0]['tp']].contract
            packet=stock_chart.packet(state,5,'all' if contract.secType == 'FUT' else 'rth')
            if not packet: raise ValueError('Fresh exit quote unavailable')
            quote=packet.get('bid' if group['side']==1 else 'ask')
            # packet() only exposes current, non-delayed Bid/Ask. Its status instead
            # tracks Last trades, which can pause during a quiet ETH market.
            if not quote: raise ValueError('Wait for a live bid/ask')
            target=price(quote)
        else:
            target=price(limit_target)
        old=group.get('adjustment',{})
        for previous in group['lots']:
            if previous.get('closing'): previous.setdefault('exit_action',old.get('action','trim'))
        pairs=dict(zip(old.get('orders',[]),old.get('stops',[])))
        pairs.update({lot['tp']:lot['sl'] for lot in lots})
        group['adjustment'] = dict(action=action, request_id=request_id, orders=list(pairs), stops=list(pairs.values()),
            acknowledged=[oid for oid in old.get('acknowledged',[]) if oid not in {lot['tp'] for lot in lots}],
            latest_orders=[lot['tp'] for lot in lots],target_price=target,outcome='unknown')
        ordinary=next((trades[l['tp']].order.lmtPrice for l in group['lots'] if not l.get('closing') and l.get('tp') in trades and not trades[l['tp']].isDone()),0)
        if ordinary: group['ordinary_tp']=ordinary
        self.save_group(account, cid, group)
        for lot in lots:
            take=trades[lot['tp']];stop=trades[lot['sl']]
            if take.isDone() or stop.isDone(): raise ValueError('Exit changed before adjustment')
            lot.setdefault('original_tp',take.order.lmtPrice)
            lot['closing']=True;lot['exit_action']=action;lot['plan_id']=request_id;self.save_group(account,cid,group)
            order=copy.copy(take.order);order.lmtPrice=target;order.transmit=True
            self.modify_exit(conn,take,order,'lmtPrice')
            group['adjustment']['acknowledged'].append(lot['tp'])
            self.save_group(account, cid, group)

    def finish_trim_restore(self, account, cid, group, oid):
        for lot in group.get('lots',[]):
            if lot.get('tp')==oid:
                lot.pop('closing',None);lot.pop('original_tp',None);lot.pop('exit_action',None);lot.pop('plan_id',None)
        adjustment=group.get('adjustment',{})
        pairs=[(o,stop) for o,stop in zip(adjustment.get('orders',[]),adjustment.get('stops',[])) if o!=oid]
        if pairs:
            adjustment['orders']=[o for o,_ in pairs];adjustment['stops']=[stop for _,stop in pairs]
            adjustment['acknowledged']=[o for o in adjustment.get('acknowledged',[]) if o!=oid]
        else: group.pop('adjustment',None)
        self.save_group(account,cid,group)

    def modify_exit(self, conn, trade, order, field):
        # Keep the broker's parent/OCA fields verbatim. Clearing or rebuilding
        # them during a price amendment causes IB 10326/10327 rejections.
        start=len(trade.log)
        if trade.contract.exchange == 'OVERNIGHT': order.tif = 'DAY'
        # Capture immutable intent: ib_async mutates Trade/Order on local writes
        # and broker callbacks. Their current price alone is not an acknowledgement.
        requested=getattr(order,field)
        identity=(order.orderId,order.account,trade.contract.conId,order.orderRef)
        conn.ib.placeOrder(trade.contract,order)
        import time
        deadline=time.monotonic()+3
        while True:
            # A first snapshot can precede the amendment acknowledgement. Wait
            # for subsequent broker events and re-read; never repeat placeOrder.
            confirmed=conn._bounded_order_read(conn.ib.reqOpenOrders,timeout_seconds=max(.05,deadline-time.monotonic()))
            errors=[e.errorCode for e in trade.log[start:] if e.errorCode and e.errorCode not in (399,2109)]
            if errors: raise ValueError(f'IB rejected the order amendment ({errors[-1]}); broker state will be refreshed')
            if trade.orderStatus.status=='Filled': return
            matches=[t for t in confirmed if (t.order.orderId,t.order.account,t.contract.conId,t.order.orderRef)==identity]
            if any(t.orderStatus.status in ('Submitted','PreSubmitted') and getattr(t.order,field)==requested for t in matches): return
            if time.monotonic()>=deadline: raise RuntimeError('Broker amendment not confirmed')
            conn.ib.sleep(.05)

    def submit_overnight_entry(self, conn, account, cid, contract, current, body, request_id):
        """Standalone Paper stock entry; venue controls the overnight session, never SMART fallback."""
        import copy
        if contract.secType != 'STK' or contract.currency != 'USD':
            raise ValueError('Overnight entry requires a USD stock')
        if isinstance(body.get('side'), bool) or body.get('side') not in (-1, 1) or body.get('entry_type') != 'LMT':
            raise ValueError('Standalone overnight entry supports BUY or SELL limit orders only')
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
        if not self.group_id and any(t.contract.conId == cid and t.order.account == account for t in conn.ib.openTrades()):
            raise ValueError('A working order already exists for this contract')
        tif = body.get('tif', 'OVERNIGHT')
        if tif not in ('DAY', 'GTC', 'OVERNIGHT'): raise ValueError('Unsupported stock TIF')
        routed = copy.copy(contract)
        routed.exchange = 'OVERNIGHT' if tif == 'OVERNIGHT' else 'SMART'
        self.validate_entry_route_price(conn, routed, cid, amount)
        oid = conn.ib.client.getReqId()
        ref = 'WheelPaper:' + request_id
        # Persist ownership before sending. Unknown outcomes remain blocked, never replayed.
        self.save_group(account, cid, dict(ids=dict(entry=oid), side=body['side'], ref=ref,
                                          mode='overnight_entry'))
        order = LimitOrder('BUY' if body['side'] == 1 else 'SELL', int(qty), float(amount), orderId=oid, account=account,
                           tif='DAY' if tif == 'OVERNIGHT' else tif, outsideRth=tif == 'OVERNIGHT', transmit=True, orderRef=ref)
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

    def validate_entry_route_price(self, conn, routed, cid, amount):
        if routed.exchange == 'OVERNIGHT':
            return self.validate_overnight_price(conn, routed, cid, amount)
        active = stock_chart.active
        rules = active.get('price_rules', []) if active and active['con_id'] == cid else []
        ticks = [r['increment'] for r in rules if Decimal(str(r['low'])) <= amount]
        if not ticks or amount % Decimal(str(ticks[-1])):
            raise ValueError('Wait for a valid contract price increment')

    def edit_entry(self, conn, account, cid, contract, current, group, body, request_id):
        """Edit only a wholly unfilled, exactly identified Paper order group."""
        import copy
        import time
        if not current.get('entry_editable') or body.get('expected_ref') != group.get('ref'):
            raise ValueError('Entry is no longer editable; refresh chart')
        if body.get('expected_snapshot') != current.get('edit_snapshot'):
            raise ValueError('Order changed; refresh chart before editing')
        trades = self._resolved_trades
        owned = [trades[oid] for oid in group['ids'].values()]
        if any(t.order.account != account or t.contract.conId != cid or
               t.order.orderRef != group['ref'] for t in owned):
            raise ValueError('Order ownership mismatch')
        parents = [trades[oid] for role, oid in group['ids'].items() if role.split('_')[0] == 'entry']
        quantity = body.get('quantity', sum(t.order.totalQuantity for t in parents))
        if body.get('cancel') is not True:
            limit = 1000 if contract.secType == 'STK' else 10
            if isinstance(quantity, bool) or not isinstance(quantity, (int, float)) or not math.isfinite(quantity) or quantity != int(quantity) or not 1 <= quantity <= limit:
                raise ValueError('Invalid order quantity')
            tif = body.get('tif', current['tif'])
            overnight = group.get('mode') == 'overnight_entry'
            if tif not in current.get('allowed_tifs', ['DAY', 'GTC']):
                raise ValueError('OVT requires a USD stock limit entry')
            to_overnight = tif == 'OVERNIGHT'
            if to_overnight and not overnight and body.get('confirm_remove_protection') is not True:
                raise ValueError('Confirm replacing the bracket with an OVT entry without TP/SL')
            try: amount = Decimal(str(body.get('price', current['entry'])))
            except Exception: raise ValueError('Invalid entry price')
            if not amount.is_finite() or amount <= 0: raise ValueError('Invalid entry price')
            if to_overnight:
                routed = copy.copy(contract); routed.exchange = 'OVERNIGHT'
                self.validate_overnight_price(conn, routed, cid, amount)
            else:
                active = stock_chart.active
                rules = active.get('price_rules', []) if active and active['con_id'] == cid else []
                ticks = [r['increment'] for r in rules if Decimal(str(r['low'])) <= amount]
                if not ticks or amount % Decimal(str(ticks[-1])): raise ValueError('Invalid contract tick size')
                if not overnight and ((current['tp'] and group['side'] * (current['tp'] - float(amount)) <= 0) or (current['sl'] and group['side'] * (current['sl'] - float(amount)) >= 0)):
                    raise ValueError('Entry must stay between TP and SL; adjust protection first')
        # Contract validation pumps broker events. Recheck all fills before any write.
        fresh = self.state(conn, cid)
        if not fresh.get('entry_editable') or fresh['edit_snapshot'] != current['edit_snapshot']:
            raise ValueError('Order changed while validating; refresh chart')
        group['pending_edit'] = request_id
        self.save_group(account, cid, group)
        try:
            structural = (body.get('cancel') is True or quantity != sum(t.order.totalQuantity for t in parents) or tif != current['tif']
                or (current['tif'] == 'OVERNIGHT' and float(amount) != current['entry']))
            if not structural:
                for trade in parents:
                    if trade.isDone() or trade.orderStatus.filled or trade.fills:
                        raise RuntimeError('Entry filled during amendment')
                    amended = copy.copy(trade.order)
                    field = 'auxPrice' if amended.orderType == 'STP' else 'lmtPrice'
                    setattr(amended, field, float(amount)); amended.transmit = True
                    self.modify_exit(conn, trade, amended, field)

            else:
                # Quantity/TIF changes replace the entire unfilled bracket. Cancel parents
                # first; never remove protection if a fill races with cancellation.
                for trade in parents: conn.ib.cancelOrder(trade.order)
                deadline = time.monotonic() + 4
                while any(not t.isDone() for t in parents) and time.monotonic() < deadline: conn.ib.sleep(.05)
                fresh = self.state(conn, cid)
                if any(t.orderStatus.status not in ('Cancelled', 'ApiCancelled') for t in parents) or fresh['position'] or any(r['filled'] for r in fresh['orders']):
                    raise RuntimeError('Cancellation/fill needs reconciliation; protection retained')
                for trade in owned:
                    if trade not in parents and not trade.isDone(): conn.ib.cancelOrder(trade.order)
                deadline = time.monotonic() + 4
                while any(not t.isDone() for t in owned) and time.monotonic() < deadline: conn.ib.sleep(.05)
                fresh = self.state(conn, cid)
                if any(t.orderStatus.status not in ('Cancelled', 'ApiCancelled') for t in owned) or fresh['position'] or any(r['filled'] for r in fresh['orders']):
                    raise RuntimeError('Original bracket not fully canceled; replacement blocked')
                if body.get('cancel') is True:
                    group.pop('pending_edit', None)
                    self.save_group(account, cid, group)
                    return
                if overnight or to_overnight:
                    replacement = dict(action='submit', mode='overnight_entry', side=group['side'],
                        entry_type='LMT', entry=float(amount), quantity=int(quantity), tif=tif)
                else:
                    replacement = dict(action='submit', side=group['side'], entry_type=current['entry_type'],
                        entry=float(amount), quantity=int(quantity), tp=current['tp'] or None, sl=current['sl'] or None, tif=tif)
                self.perform(conn, account, cid, replacement, request_id)
            latest = self.group(account, cid)
            latest.pop('pending_edit', None)
            self.save_group(account, cid, latest)
        except Exception as error:
            latest = self.group(account, cid)
            if isinstance(error, ValueError) and not structural and len(parents) == 1:
                confirmed = conn._bounded_order_read(conn.ib.reqOpenOrders, timeout_seconds=3)
                if any(t.order.account == account and t.contract.conId == cid and t.order.orderId == parents[0].order.orderId for t in confirmed):
                    latest.pop('pending_edit', None); self.save_group(account,cid,latest)
                    raise ValueError(str(error)) from error
            latest['pending_edit'] = request_id
            self.save_group(account, cid, latest)
            # At least one broker write may have happened. Do not offer a blind retry.
            raise RuntimeError('Entry amendment needs broker reconciliation') from error

    def cancel_add(self, conn, account, cid, body):
        """Cancel one owned, unfilled unit parent; never cancel its protection directly."""
        conn._bounded_order_read(conn.ib.reqOpenOrders, timeout_seconds=3)
        current = self.state(conn, cid)
        group = self.group(account, cid) or {}
        if not current['known'] or body.get('expected_ref') != group.get('ref'):
            raise ValueError('Order identity/status changed; refresh before canceling the add')
        oid = body.get('order_id')
        if isinstance(oid, bool) or not isinstance(oid, int):
            raise ValueError('Exact add order ID required')
        lot = next((lot for lot in group.get('lots', []) if lot['entry'] == oid), None)
        if not lot:
            raise ValueError('This is not an owned add order')
        trades = getattr(self, '_resolved_trades', {})
        parent = trades.get(oid)
        if (not parent or parent.contract.conId != cid or parent.order.account != account
                or parent.order.orderRef != group.get('ref')):
            raise ValueError('Exact add order unavailable')
        if group.get('entry_kinds',{}).get(str(oid))=='entry' and (parent.orderStatus.filled or parent.orderStatus.status=='Filled'):
            raise ValueError('Original entry is already filled; protection retained')
        if parent.orderStatus.filled or parent.orderStatus.status == 'Filled':
            return  # Fill won the race; never remove filled-unit protection.
        if parent.orderStatus.status not in ('Cancelled', 'ApiCancelled', 'PendingCancel'):
            if parent.orderStatus.status not in ('Submitted', 'PreSubmitted'):
                raise ValueError('Add order is not currently cancelable')
            conn.ib.cancelOrder(parent.order)
        import time
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            if parent.orderStatus.filled or parent.orderStatus.status == 'Filled':
                return
            children = [trades.get(lot[r]) for r in ('tp', 'sl') if r in lot]
            if parent.orderStatus.status in ('Cancelled', 'ApiCancelled') and all(
                    t and t.orderStatus.status in ('Cancelled', 'ApiCancelled', 'Inactive') for t in children):
                return
            conn.ib.sleep(.05)
        raise RuntimeError('Add cancellation is awaiting broker confirmation')

    @staticmethod
    def protection_cancel_rows(state, group, role):
        planned={lot.get('tp') for lot in group.get('lots',[]) if lot.get('closing')}
        return [r for r in state['orders']
                if r['role'].split('_')[0] in ((role,) if role else ('tp','sl'))
                and not (role=='tp' and r['order_id'] in planned)]

    def cancel_protection(self, conn, account, cid, body):
        conn._bounded_order_read(conn.ib.reqOpenOrders, timeout_seconds=3)
        current = self.state(conn, cid)
        group = self.group(account, cid)
        if not group or body.get('expected_ref') != group.get('ref') or not current['known']:
            raise ValueError('Protection identity/status changed; refresh before canceling')
        role = body.get('role')
        if role not in (None, 'tp', 'sl'): raise ValueError('Invalid protection role')
        if body.get('confirm_remove_protection') is not True:
            raise ValueError('Confirm removal of both TP and SL; the position will be unprotected')
        terminal = ('Filled', 'Cancelled', 'ApiCancelled', 'Inactive')
        if any(r['role'].split('_')[0] == 'entry' and r['status'] not in terminal for r in current['orders']):
            raise ValueError('Finish or cancel pending entries before removing protection')
        rows = self.protection_cancel_rows(current,group,role)
        if not rows: raise ValueError('No owned protection orders')
        trades = getattr(self, '_resolved_trades', {})
        targets = []
        for row in rows:
            if row['status'] in terminal: continue
            trade = trades.get(row['order_id'])
            if (not trade or trade.order.account != account or trade.contract.conId != cid
                    or trade.order.orderRef != group['ref']):
                raise ValueError('Exact protection order unavailable')
            targets.append(trade)
        for trade in targets:
            if not trade.isDone(): conn.ib.cancelOrder(trade.order)
        deadline = time.monotonic() + 4
        while any(not t.isDone() for t in targets) and time.monotonic() < deadline:
            conn.ib.sleep(.05)
        fresh = self.state(conn, cid)
        if not fresh['known'] or any(r['status'] not in terminal for r in self.protection_cancel_rows(fresh,group,role)):
            raise RuntimeError('Protection cancellation awaiting broker confirmation; do not resubmit')
        group=self.group(account,cid)
        group['requested_protection']=[r for r in group.get('requested_protection',['tp','sl']) if role and r!=role]
        self.save_group(account,cid,group)

    def set_protection(self, conn, account, cid, contract, current, group, body, request_id, price):
        """Explicit replacement for a settled, fully owned position. Never replay writes.

        Existing exits are canceled and reconciled before fresh standalone GTC
        exits are sent. The user confirms this cancellation gap in the editor.
        """
        terminal = ('Filled','Cancelled','ApiCancelled','Inactive')
        if not group and current.get('position_only'):
            # User explicitly requests exits for the current broker holding. Check
            # every API client's open orders before claiming this position.
            others=conn._bounded_order_read(conn.ib.reqAllOpenOrders,timeout_seconds=3)
            if any(t.order.account==account and t.contract.conId==cid for t in others):
                raise ValueError('Existing working orders must be reconciled before adding TP/SL')
            fresh=self.state(conn,cid)
            if fresh.get('order_ref')!=current.get('order_ref') or fresh.get('edit_snapshot')!=current.get('edit_snapshot'):
                raise ValueError('Position changed; reopen TP/SL')
            if self.group(account,cid): raise ValueError('Protection group changed; refresh')
            group=dict(ids={},side=current['side'],ref=current['order_ref'],origin_position=current['position'],origin_entry=current['entry'],requested_protection=[])
        if not group or body.get('expected_ref') != group.get('ref') or not current.get('protection_manageable'):
            raise ValueError('Wait for settled entries and a known owned position')
        if body.get('expected_snapshot') != current['edit_snapshot']:
            raise ValueError('Orders changed; reopen protection settings')
        if body.get('confirm_replace_protection') is not True:
            raise ValueError('Confirm replacing existing exits; protection may be interrupted')
        values = {r:price(body[r]) for r in ('tp','sl') if body.get(r) is not None}
        if 'tp' in values and group['side']*(values['tp']-current['entry']) <= 0:
            raise ValueError('TP must be on the profitable side of entry')
        if len(values)==2 and group['side']*(values['tp']-values['sl']) <= 0:
            raise ValueError('TP and SL cannot cross')
        owned = group.get('origin_position',0)+sum((1 if r['role'].split('_')[0]=='entry' else -1)*r['filled'] for r in current['orders'])*group['side']
        if abs(owned-current['position']) > .000001 or owned*group['side'] <= 0:
            raise ValueError('Position differs from owned fills; reconcile before protecting')
        trades = self._resolved_trades
        if any(t.order.orderId not in group['ids'].values() for t in conn.ib.openTrades() if t.order.account==account and t.contract.conId==cid):
            raise ValueError('Other working orders exist; reconcile before protecting')
        if any(t.order.account!=account or t.contract.conId!=cid or t.order.orderRef!=group['ref'] for oid,t in trades.items() if oid in group['ids'].values()):
            raise ValueError('Protection ownership mismatch')
        fresh=self.state(conn,cid)
        if fresh['edit_snapshot']!=current['edit_snapshot'] or fresh['position']!=current['position']:
            raise ValueError('Position changed while validating')
        group['pending_protection'] = request_id
        self.save_group(account,cid,group)
        try:
            targets=[trades[r['order_id']] for r in current['orders'] if r['role'].split('_')[0] in ('tp','sl') and r['status'] not in terminal]
            for t in targets:
                if not t.isDone(): conn.ib.cancelOrder(t.order)
            deadline=time.monotonic()+4
            while any(not t.isDone() for t in targets) and time.monotonic()<deadline: conn.ib.sleep(.05)
            fresh=self.state(conn,cid)
            if not fresh['known'] or any(not t.isDone() for t in targets): raise RuntimeError('Cancellation unconfirmed')
            # A fill during cancellation invalidates the requested quantity. Do not replace.
            if fresh['position']!=current['position'] or any(r['filled']!=old['filled'] for r,old in zip(fresh['orders'],current['orders'])):
                raise RuntimeError('Fill raced protection replacement; reconcile before another action')
            positions=conn._bounded_order_read(conn.ib.reqPositions,timeout_seconds=3)
            actual=next((float(p.position) for p in positions if p.account==account and p.contract.conId==cid),0)
            if actual!=fresh['position']: raise RuntimeError('Position reconciliation incomplete')
            verified=self.state(conn,cid)
            if verified['edit_snapshot']!=fresh['edit_snapshot'] or verified['position']!=actual:
                raise RuntimeError('Orders changed during position reconciliation')
            if any(t.order.orderId not in group['ids'].values() for t in conn.ib.openTrades() if t.order.account==account and t.contract.conId==cid):
                raise RuntimeError('Other working orders appeared during reconciliation')
            # Archive old IDs to retain fills and reconnect history; new roles own the new exits.
            for role in list(group['ids']):
                if role.split('_')[0] in ('tp','sl') and '_retired_' not in role:
                    archived=role+'_retired_'+str(group['ids'][role])
                    group['ids'][archived]=group['ids'].pop(role)
                    if role in group.get('perms',{}): group['perms'][archived]=group['perms'].pop(role)
                    if role in group.get('terminal',{}):
                        group['terminal'][archived]=dict(group['terminal'].pop(role),role=archived)
            group.pop('lots',None); group.pop('adjustment',None); group.pop('mode',None)
            group['requested_protection']=list(values)
            ids={r:conn.ib.client.getReqId() for r in values}
            group['ids'].update(ids)
            group['protection_request']=dict(id=request_id,ids=ids)
            self.save_group(account,cid,group)
            for role,value in values.items():
                order=(LimitOrder if role=='tp' else StopOrder)('SELL' if actual>0 else 'BUY',abs(actual),value,
                    orderId=ids[role],account=account,tif='GTC',orderRef=group['ref'],transmit=role==next(reversed(values)),
                    ocaGroup=('WheelExit:'+request_id) if len(values)==2 else '',ocaType=2 if len(values)==2 else 0)
                order.outsideRth=contract.secType=='FUT'
                conn.ib.placeOrder(contract,order)
            deadline=time.monotonic()+3
            while ids:
                snapshot=conn._bounded_order_read(conn.ib.reqOpenOrders,timeout_seconds=max(.05,deadline-time.monotonic()))
                confirmed={t.order.orderId for t in snapshot if t.order.account==account and t.contract.conId==cid and t.order.orderRef==group['ref'] and t.orderStatus.status in ('Submitted','PreSubmitted')}
                fresh=self.state(conn,cid)
                done={r['order_id'] for r in fresh['orders'] if r['status'] in terminal}
                if set(ids.values()) <= confirmed | done: break
                if time.monotonic()>=deadline: raise RuntimeError('New exits not yet confirmed')
                conn.ib.sleep(.05)
            group.pop('pending_protection',None); self.save_group(account,cid,group)
        except Exception as error:
            raise RuntimeError('Protection replacement needs broker reconciliation; do not resubmit') from error

    def resize_trim(self, conn, account, cid, current, group, body, request_id, price):
        import copy
        if not group or not current['known'] or not current.get('scalable') or body.get('expected_ref')!=group['ref']:
            raise ValueError('Trim ownership/protection changed; refresh')
        if body.get('expected_position')!=current['position']:
            raise ValueError('Position changed; reopen quantity editor')
        expected=body.get('expected_orders')
        if not isinstance(expected,list) or not expected: raise ValueError('Exact trim orders required')
        ids=[r.get('order_id') for r in expected if isinstance(r,dict)]
        if len(ids)!=len(expected) or len(set(ids))!=len(ids): raise ValueError('Invalid trim selection')
        rows={r['order_id']:r for r in current.get('pending_exits',[])}
        if any(oid not in rows or rows[oid]['action']!='trim' or rows[oid]['status'] not in ('Submitted','PreSubmitted')
               or item.get('price')!=rows[oid]['price'] or item.get('quantity')!=rows[oid]['quantity']
               for oid,item in zip(ids,expected)): raise ValueError('Trim plan changed; reopen editor')
        if any(rows[oid]['quantity']!=1 for oid in ids): raise ValueError('Wait for partial fills to reconcile before changing quantity')
        plans={rows[oid]['plan_id'] for oid in ids}
        if len(plans)!=1 or {r['order_id'] for r in rows.values() if r['plan_id'] in plans and r['price']==rows[ids[0]]['price']}!=set(ids):
            raise ValueError('Select the complete trim plan')
        qty=body.get('quantity')
        if isinstance(qty,bool) or not isinstance(qty,int) or not 0<=qty<=len(ids)+current.get('trim_available',0):
            raise ValueError('Quantity exceeds unreserved filled position')
        if len({rows[oid]['price'] for oid in ids})!=1: raise ValueError('Plan prices differ; manage the individual orders')
        target=price(rows[ids[0]]['price'])
        if any(r['status'] in ('PendingSubmit','PendingCancel','Unknown') for r in current['orders']):
            raise ValueError('Wait for stable broker order status')
        if group.get('adjustment',{}).get('outcome') in ('unknown','rejected'):
            raise ValueError('Previous exit needs reconciliation')
        trades=getattr(self,'_resolved_trades',{})
        owned=sum(group['side']*(1 if r['role'].split('_')[0]=='entry' else -1)*r['filled'] for r in current['orders'])
        if abs(owned-current['position'])>.000001: raise ValueError('Position differs from owned fills')
        free=[]
        for lot in group['lots']:
            parent,take,stop=(trades.get(lot.get(r)) for r in ('entry','tp','sl'))
            if parent and take and stop and parent.orderStatus.status=='Filled' and not lot.get('closing') and all(t.orderStatus.status in ('Submitted','PreSubmitted') for t in (take,stop)):
                free.append(lot)
        if qty>len(ids)+len(free): raise ValueError('Filled quantity changed')
        changes=[]
        for oid in ids[qty:]:
            changes.append(dict(order_id=oid,price=price(rows[oid]['restore_price']),restore=True))
        additions=free[:max(0,qty-len(ids))]
        for lot in additions: changes.append(dict(order_id=lot['tp'],price=target,restore=False,original_price=trades[lot['tp']].order.lmtPrice))
        if not changes:return
        for change in changes:
            t=trades.get(change['order_id'])
            if not t or t.order.account!=account or t.contract.conId!=cid or t.order.orderRef!=group['ref']:
                raise ValueError('Exact owned exit unavailable')
            lot=next(l for l in group['lots'] if l.get('tp')==change['order_id'])
            stop=trades.get(lot['sl'])
            if not stop or stop.orderStatus.status not in ('Submitted','PreSubmitted') or group['side']*(change['price']-stop.order.auxPrice)<=0:
                raise ValueError('Trim target cannot cross its protective stop')
        group['pending_resize']=dict(id=request_id,changes=changes,plan_id=next(iter(plans)))
        self.save_group(account,cid,group)
        try:
            for change in changes:
                t=trades[change['order_id']]
                lot=next(l for l in group['lots'] if l.get('tp')==change['order_id'])
                stop=trades.get(lot['sl'])
                if t.orderStatus.status not in ('Submitted','PreSubmitted') or t.orderStatus.filled or not stop or stop.orderStatus.status not in ('Submitted','PreSubmitted') or stop.orderStatus.filled:
                    raise RuntimeError('Exit filled during quantity change')
                order=copy.copy(t.order);order.lmtPrice=change['price'];order.transmit=True
                self.modify_exit(conn,t,order,'lmtPrice')
                self.finish_resize_change(account,cid,change,next(iter(plans)))
            fresh=self.group(account,cid);fresh.pop('pending_resize',None);self.save_group(account,cid,fresh)
        except Exception as error:
            raise RuntimeError('Quantity change needs reconciliation; do not replay') from error

    def finish_resize_change(self, account, cid, change, plan_id):
        group=self.group(account,cid);oid=change['order_id']
        if change['restore']:
            self.finish_trim_restore(account,cid,group,oid)
        else:
            lot=next(l for l in group['lots'] if l.get('tp')==oid)
            lot.setdefault('original_tp',change.get('original_price') or group.get('ordinary_tp'))
            lot.update(closing=True,exit_action='trim',plan_id=plan_id)
            adjustment=group['adjustment']
            if oid not in adjustment['orders']:
                adjustment['orders'].append(oid);adjustment['stops'].append(lot['sl'])
            if oid not in adjustment['acknowledged']:adjustment['acknowledged'].append(oid)
            self.save_group(account,cid,group)

    def perform(self, conn, account, cid, body, request_id):
        pending=self.group(account,cid) or {}
        if pending.get('pending_resize'): raise ValueError('Previous quantity change needs broker reconciliation')
        if body.get('action') == 'cancel_protection':
            return self.cancel_protection(conn, account, cid, body)
        if body.get('action') == 'cancel_add':
            return self.cancel_add(conn, account, cid, body)
        if body.get('action') in ('close','be','add','trim','resize_trim') and any(t.contract.conId==cid and t.order.account==account and t.order.orderRef in {g['ref'] for g in self.group_choices(account,cid) if g['id'] != (self.group_id or '')} for t in conn.ib.openTrades()):
            raise ValueError('Multiple order groups: manage each order separately; position actions require reconciliation')
        if body.get('action') == 'edit_entry' and body.get('cancel') is True:
            # A pure cancellation needs exact broker identity, not new contract/price rules.
            conn._bounded_order_read(conn.ib.reqOpenOrders, timeout_seconds=3)
            current = self.state(conn, cid)
            group = self.group(account, cid)
            if not group: raise ValueError('No owned entry')
            owned = getattr(self, '_resolved_trades', {})
            parent = next((owned.get(oid) for role, oid in group['ids'].items()
                           if role.split('_')[0] == 'entry' and owned.get(oid)), None)
            if not parent or parent.order.account != account or parent.contract.conId != cid or parent.order.orderRef != group.get('ref'):
                raise ValueError('Exact owned order unavailable')
            return self.edit_entry(conn, account, cid, parent.contract, current, group, body, request_id)
        if body.get('entry_type') == 'STP' and (body.get('tif') == 'OVERNIGHT' or body.get('mode') == 'overnight_entry'):
            raise ValueError('OVT supports limit orders only; STP is unavailable')
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
        if action == 'edit_entry':
            if not group: raise ValueError('No owned entry')
            return self.edit_entry(conn, account, cid, contract, current, group, body, request_id)
        if group and group.get('mode') == 'overnight_entry' and action == 'close':
            if not current['position'] or body.get('expected_ref') != group.get('ref'):
                raise ValueError('Explicit filled-position reference required; cancel an unfilled entry instead')
        # Fresh submissions use their own mode after checking the prior order is resolved.
        if group and group.get('mode') == 'overnight_entry' and action not in ('close', 'submit', 'set_protection'):
            if action == 'manage_entry':
                import copy
                if not current['known'] or body.get('expected_ref') != group.get('ref'):
                    raise ValueError('Order identity changed; refresh Orders')
                trade = getattr(self, '_resolved_trades', {}).get(group['ids']['entry'])
                if not trade or trade.order.account != account or trade.contract.conId != cid or trade.order.orderRef != group['ref']:
                    raise ValueError('Exact owned order unavailable')
                if trade.orderStatus.status not in ('Submitted', 'PreSubmitted'):
                    raise ValueError('Wait for a confirmed working order')
                if trade.contract.exchange not in ('OVERNIGHT', 'SMART') or trade.order.orderType != 'LMT':
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
                self.validate_entry_route_price(conn, trade.contract, cid, amount)
                # Validation can pump broker events; recheck before the write.
                if trade.isDone() or trade.orderStatus.filled or trade.fills or trade.orderStatus.status not in ('Submitted','PreSubmitted'):
                    raise ValueError('Order changed while validating; refresh Orders')
                if trade.contract.exchange == 'OVERNIGHT':
                    return self.edit_entry(conn, account, cid, contract, current, group,
                        dict(price=float(amount), expected_ref=group['ref'], expected_snapshot=current['edit_snapshot']), request_id)
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
            if isinstance(value,bool): raise ValueError('Invalid price')
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
        if action=='resize_trim':
            return self.resize_trim(conn,account,cid,current,group,body,request_id,price)
        if action=='amend_add':
            if not group or not current['known'] or body.get('expected_ref')!=group.get('ref'):
                raise ValueError('Add identity/status changed; refresh before amending')
            oid=body.get('order_id')
            lot=next((l for l in group.get('lots',[]) if l['entry']==oid),None)
            row=next((r for r in current['orders'] if r['order_id']==oid),None)
            trades=getattr(self,'_resolved_trades',{})
            parent=trades.get(oid)
            if not lot or not row or not parent or parent.contract.conId!=cid or parent.order.account!=account or parent.order.orderRef!=group['ref']:
                raise ValueError('Exact owned add order required')
            if row['filled'] or row['status'] not in ('Submitted','PreSubmitted') or parent.order.orderType not in ('LMT','STP'):
                raise ValueError('Add filled or is no longer amendable')
            if body.get('expected_price')!=row['price'] or body.get('expected_quantity')!=row['quantity']:
                raise ValueError('Add changed; refresh before moving')
            target=price(body.get('price'))
            take,stop=trades.get(lot.get('tp')),trades.get(lot.get('sl'))
            if not take or not stop or any(t.isDone() or t.orderStatus.status not in ('Submitted','PreSubmitted') for t in (take,stop)):
                raise ValueError('Add protection needs reconciliation')
            if group['side']*(take.order.lmtPrice-target)<=0 or group['side']*(stop.order.auxPrice-target)>=0:
                raise ValueError('Add price must lie between its TP and SL')
            import copy
            order=copy.copy(parent.order)
            field='lmtPrice' if order.orderType=='LMT' else 'auxPrice'
            setattr(order,field,target);order.transmit=True
            self.modify_exit(conn,parent,order,field)
            return
        if action=='set_protection':
            return self.set_protection(conn,account,cid,contract,current,group,body,request_id,price)
        if action=='submit':
            if current['active'] or not current['known']: raise ValueError('An existing chart order needs resolution first')
            if current['position'] or (not self.group_id and any(t.contract.conId==cid and t.order.account==account for t in conn.ib.openTrades())):
                raise ValueError('Close existing position/orders for this contract before starting a new bracket')
            tif=body.get('tif', 'DAY')
            if tif not in ('DAY', 'GTC'): raise ValueError('Unsupported bracket TIF')
            side=body.get('side'); qty=body.get('quantity')
            if isinstance(side,bool) or isinstance(qty,bool) or side not in (-1,1) or not isinstance(qty,(int,float)) or not math.isfinite(qty) or qty!=int(qty) or not 1<=qty<=(10 if contract.secType in ('FUT','OPT') else 1000): raise ValueError('Invalid paper order size or side')
            entry=price(body.get('entry')); tp=price(body['tp']) if body.get('tp') is not None else None; sl=price(body['sl']) if body.get('sl') is not None else None
            if (tp is not None and side*(tp-entry)<=0) or (sl is not None and side*(sl-entry)>=0): raise ValueError('TP and SL must be on opposite sides of entry')
            if body.get('entry_type') not in ('LMT','STP'): raise ValueError('Unsupported entry type')
            if contract.secType in ('FUT','OPT'):
                group=dict(ids={},lots=[],side=side,ref='WheelPaper:'+request_id,tif=tif)
                self.add_lots(conn,account,cid,contract,group,int(qty),body['entry_type'],entry,tp,sl)
                return
            buy='BUY' if side==1 else 'SELL'; sell='SELL' if side==1 else 'BUY'
            values = {r:v for r,v in (('tp',tp),('sl',sl)) if v is not None}
            ids={role:conn.ib.client.getReqId() for role in ('entry', *values)}
            parent=(LimitOrder if body['entry_type']=='LMT' else StopOrder)(buy,qty,entry,orderId=ids['entry'],transmit=not values)
            orders=[parent]+[(LimitOrder if r=='tp' else StopOrder)(sell,qty,v,orderId=ids[r],parentId=ids['entry'],transmit=False) for r,v in values.items()]
            orders[-1].transmit=True
            self.save_group(account,cid,dict(ids=ids,side=side,ref='WheelPaper:'+request_id,requested_protection=list(values)))
            for order in orders:
                order.account=account;order.tif=tif if order is parent else 'GTC';order.orderRef='WheelPaper:'+request_id
                conn.ib.placeOrder(contract,order)
            return
        if not current['known']: raise ValueError('Orders need Gateway reconciliation before another action')
        group=self.group(account,cid)
        if not group: raise ValueError('No chart bracket for this contract')
        trades=getattr(self,'_resolved_trades',{})
        if action in ('add','trim'):
            if body.get('expected_ref') is not None and body['expected_ref'] != group.get('ref'):
                raise ValueError('Order identity changed; refresh before adjusting')
            if not current.get('scalable'): raise ValueError('Add/Trim requires active paired protection; use an independent order or Close')
            if not group.get('lots'):
                raise ValueError('This older bracket cannot be scaled without replacing protection; start a new protected futures bracket')
            qty = body.get('quantity')
            if isinstance(qty,bool) or not isinstance(qty,(int,float)) or not math.isfinite(qty) or qty != int(qty) or qty < 1:
                raise ValueError('Invalid adjustment quantity')
            size = abs(current['position'])
            if not size or current['position'] * group['side'] <= 0: raise ValueError('No filled chart position')
            priced_trim = action == 'trim' and 'exit_price' in body
            if priced_trim:
                if body.get('expected_ref') != group.get('ref') or body.get('expected_position') != current['position']:
                    raise ValueError('Position changed; reopen the priced exit')
                if body.get('exit_type') != 'LMT': raise ValueError('Priced trim supports limit orders only')
                target=price(body.get('exit_price'))
                if group['side']*(target-current['sl']) <= 0:
                    raise ValueError('Exit limit cannot cross the protective stop')
                if qty > size: raise ValueError('Exit quantity exceeds remaining position')
            elif action == 'trim' and qty >= size: raise ValueError('Trim must leave a position; use Close Position')
            owned = sum(group['side'] * (1 if row['role'].split('_')[0] == 'entry' else -1) * row['filled']
                        for row in current['orders'])
            if abs(owned-current['position']) > .000001: raise ValueError('Position differs from chart fills; reconcile Gateway')
            if any(t.order.orderId not in group['ids'].values() for t in conn.ib.openTrades() if t.contract.conId==cid and t.order.account==account):
                raise ValueError('Other working orders exist; review Gateway')
            if group.get('adjustment',{}).get('outcome') in ('unknown','rejected'):
                raise ValueError('Previous exit needs reconciliation before another adjustment')
            live = []
            reserved=[]
            for lot in group['lots']:
                parent, take, stop = [trades.get(lot[r]) for r in ('entry','tp','sl')]
                if not all((parent,take,stop)): raise ValueError('Lot status needs reconciliation')
                if (parent.orderStatus.status in ('Cancelled','ApiCancelled') and not parent.orderStatus.filled
                        and all(t.orderStatus.status in ('Cancelled','ApiCancelled','Inactive') and not t.orderStatus.filled for t in (take,stop))):
                    continue
                if (parent.orderStatus.status in ('Submitted','PreSubmitted') and not parent.orderStatus.filled
                        and all(t.orderStatus.status in ('Submitted','PreSubmitted') and not t.orderStatus.filled for t in (take,stop))):
                    continue
                if parent.orderStatus.status != 'Filled': raise ValueError('Wait for all entry orders to finish')
                if take.orderStatus.status == 'Filled' or stop.orderStatus.status == 'Filled': continue
                if take.isDone() or stop.isDone() or take.orderStatus.status not in ('Submitted','PreSubmitted') or stop.orderStatus.status not in ('Submitted','PreSubmitted'):
                    raise ValueError('An exit needs reconciliation before another adjustment')
                if lot.get('closing'):
                    if lot['tp'] not in group.get('adjustment',{}).get('acknowledged',[]): raise ValueError('Trim outcome needs reconciliation')
                    reserved.append(lot)
                else: live.append(lot)
            if len(live)+len(reserved) != size: raise ValueError('Protected lot count differs from position')
            if action=='trim' and qty>len(live):
                raise ValueError('Trim quantity exceeds unreserved position')
            if action == 'add':
                if body.get('expected_ref') is not None and body['expected_ref'] != group.get('ref'):
                    raise ValueError('Order identity changed; refresh before adding')
                kind = body.get('entry_type', 'MKT')
                if kind not in ('MKT', 'LMT', 'STP'):
                    raise ValueError('Unsupported add order type')
                target = 0 if kind == 'MKT' else price(body.get('entry'))
                tp, sl = price(current.get('add_tp') or current['tp']), price(current['sl'])
                if kind != 'MKT':
                    if body.get('expected_ref') != group.get('ref') or body.get('side') != group['side']:
                        raise ValueError('Priced add must match the current position and order identity')
                    if body.get('expected_tp') != tp or body.get('expected_sl') != sl:
                        raise ValueError('Protection prices changed; reopen the add order')
                    if group['side'] * (tp-target) <= 0 or group['side'] * (sl-target) >= 0:
                        raise ValueError('Add price must lie between the current TP and SL')
                self.add_lots(conn,account,cid,contract,group,int(qty),kind,target,tp,sl,entry_kind='add')
            else:
                self.exit_lots(conn,account,cid,group,live[:int(qty)],trades,price,action,request_id,limit_target=target if priced_trim else None)
            return
        if action in ('amend','be'):
            if body.get('expected_ref') is not None and body['expected_ref'] != group.get('ref'):
                raise ValueError('Order identity changed; refresh before amending protection')
            if body.get('restore_trim') and (action!='amend' or body.get('role')!='tp' or not isinstance(body.get('order_id'),int)):
                raise ValueError('Exact trim order required')
            role='sl' if action=='be' else body.get('role')
            if role not in ('tp','sl'): raise ValueError('Only TP and SL can be amended')
            trade=next((trades.get(lot.get(role)) for lot in group.get('lots',[]) if trades.get(lot.get(role)) and not trades[lot[role]].isDone()),None) if group.get('lots') else trades.get(group['ids'].get(role))
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
            if body.get('order_id') is not None:
                wanted=body['order_id']
                row=next((r for r in current.get('pending_exits',[]) if r['order_id']==wanted),None)
                if role!='tp' or not row or row['status'] not in ('Submitted','PreSubmitted') or body.get('expected_ref')!=group.get('ref'):
                    raise ValueError('Exact working trim exit required')
                if body.get('expected_price')!=row['price'] or body.get('expected_quantity')!=row['quantity']:
                    raise ValueError('Trim changed; refresh before moving')
                if body.get('restore_trim') and (not row.get('restore_price') or new_price!=row['restore_price']):
                    raise ValueError('Original TP changed; refresh before canceling trim')
                targets=[trades.get(wanted)]
            else:
                targets=[trades.get(lot.get(role)) for lot in group['lots'] if role!='tp' or not lot.get('closing')] if group.get('lots') else [trade]
            if not any(t and not t.isDone() for t in targets): raise ValueError('No remaining exit at this level')
            for target in targets:
                if not target or target.isDone(): continue
                if action=='be' and group['side']*(target.order.auxPrice-new_price)>=0: continue
                import copy
                amended=copy.copy(target.order)
                if role=='sl': amended.auxPrice=new_price
                else: amended.lmtPrice=new_price
                amended.transmit=True;self.modify_exit(conn,target,amended,'auxPrice' if role=='sl' else 'lmtPrice')
            if role=='tp' and body.get('order_id') is None:
                group['ordinary_tp']=new_price;self.save_group(account,cid,group)
            if body.get('restore_trim'):
                self.finish_trim_restore(account,cid,group,body['order_id'])
            return
        if action == 'close' and body.get('expected_ref') is not None and body['expected_ref'] != group.get('ref'):
            raise ValueError('Order identity changed; refresh before closing')
        if action=='close' and group.get('lots') and current.get('scalable') and current.get('protection', {}).get('status') == 'covered':
            import time
            pending_parents=[trades[lot['entry']] for lot in group['lots']
                             if lot['entry'] in trades and not trades[lot['entry']].isDone()]
            if pending_parents:
                group['close_cancellation']=dict(request_id=request_id,parents=[t.order.orderId for t in pending_parents])
                self.save_group(account,cid,group)
            for parent in pending_parents:
                conn.ib.cancelOrder(parent.order)
            if pending_parents:
                deadline=time.monotonic()+4
                while any(not t.isDone() for t in pending_parents) and time.monotonic()<deadline:
                    conn.ib.sleep(.05)
                if any(t.orderStatus.status not in ('Filled','Cancelled','ApiCancelled') for t in pending_parents):
                    raise RuntimeError('Entry cancellation needs reconciliation; protection retained')
                # A pending Add can fill while its cancellation is in flight.
                # Re-read the position and protect/exit that unit in this same request.
                current=self.state(conn,cid)
                trades=self._resolved_trades
                if not current['known']:
                    raise RuntimeError('Entry outcome needs reconciliation; protection retained')
                group.pop('close_cancellation',None);self.save_group(account,cid,group)
            live=[]
            for lot in group['lots']:
                parent,take,stop=[trades.get(lot[r]) for r in ('entry','tp','sl')]
                if not all((parent,take,stop)): raise RuntimeError('Lot status needs reconciliation')
                if take.orderStatus.status=='Filled' or stop.orderStatus.status=='Filled': continue
                if parent.orderStatus.status=='Filled':
                    if take.isDone() or stop.isDone(): raise RuntimeError('Protection needs reconciliation')
                    live.append(lot)
                elif not parent.isDone():
                    raise RuntimeError('Entry cancellation needs reconciliation')
            if len(live)!=abs(current['position']):
                raise RuntimeError('Position changed during close; protection retained')
            if live: self.exit_lots(conn,account,cid,group,live,trades,price,action,request_id)
            return
        if action=='close':
            pending_close = trades.get(group['ids'].get('close'))
            if pending_close and not pending_close.isDone(): raise ValueError('Close order already working')
            working=[t for t in trades.values() if t.order.orderId in group['ids'].values() and not t.isDone()]
            for trade in working: conn.ib.cancelOrder(trade.order)
            import time
            deadline=time.monotonic()+4
            while any(not t.isDone() for t in working) and time.monotonic()<deadline: conn.ib.sleep(.05)
            if any(not t.isDone() for t in working): raise RuntimeError('Cancellation not confirmed')
            positions=conn._bounded_order_read(conn.ib.reqPositions,timeout_seconds=3)
            position=next((p for p in positions if p.account==account and p.contract.conId==cid),None)
            expected = group.get('origin_position',0)+sum((1 if t.order.action == 'BUY' else -1) * max(float(t.orderStatus.filled),
                           sum(float(f.execution.shares) for f in t.fills)) for t in trades.values()
                           if t.order.orderId in group['ids'].values())
            actual = float(position.position) if position else 0
            if abs(expected - actual) > .000001:
                raise ValueError('Position and executions are not synchronized; review before closing')
            if position and position.position:
                if any(t.contract.conId==cid and t.order.account==account for t in conn.ib.openTrades()): raise ValueError('Other working orders exist; review Gateway')
                order=MarketOrder('SELL' if position.position>0 else 'BUY',abs(position.position),account=account,tif='DAY',orderRef=group.get('ref','WheelPaper:'+request_id))
                order.orderId=conn.ib.client.getReqId();group['ids']['close']=order.orderId
                self.save_group(account,cid,group)
                if group.get('mode') == 'overnight_entry':
                    import copy
                    contract = copy.copy(contract); contract.exchange = 'SMART'
                conn.ib.placeOrder(contract,order)
            return
        raise ValueError('Unsupported paper chart action')
