"""A new Paper lifecycle from fresh broker-flat evidence, preserving old unknowns.

A checkpoint does not cancel an order, assert a historical fill, or waive an
unresolved write. Old groups remain inspectable and cannot be traded. Only a
new independent group can start from the broker-confirmed empty boundary.
"""
import json
import math
import time
from types import SimpleNamespace
from core.execution_evidence import groups as execution_groups

FIELDS = ('execId', 'acctNumber', 'clientId', 'orderId', 'permId', 'orderRef', 'side', 'shares', 'price')
TERMINAL = ('Filled', 'Cancelled', 'ApiCancelled')


def latest(service, account, cid):
    with service.database() as db:
        row = db.execute('SELECT request_id,payload FROM chart_flat_checkpoints WHERE account=? AND con_id=? ORDER BY rowid DESC LIMIT 1', (account, cid)).fetchone()
    return dict(json.loads(row[1]), request_id=row[0]) if row else None


def records(conn, account, cid):
    fills = list(conn.ib.fills()) + [f for t in conn.ib.trades() for f in t.fills]
    return sorted({json.dumps({k: getattr(f.execution, k, None) for k in FIELDS}, sort_keys=True)
                   for f in fills if f.execution.acctNumber == account and f.contract.conId == cid})


def active_old_order(checkpoint, trades, account, cid):
    refs = set(checkpoint['references'])
    perms = {p for g in checkpoint['groups'] for p in g.get('perms', {}).values() if p}
    return any(t.order.account == account and t.contract.conId == cid
               and (t.order.orderRef in refs or (t.order.permId or t.orderStatus.permId) in perms)
               and t.orderStatus.status not in TERMINAL for t in trades)


def reconcile(service, conn, account, cid, body, request_id):
    if not account.startswith('DU') or conn.port != 4002 or conn.ib.managedAccounts() != [account]:
        raise ValueError('Flat history recovery is available only in the configured Paper account')
    if not service.group_id or service.group(account, cid):
        raise ValueError('Choose a new independent order group for flat history recovery')
    choices = service.group_choices(account, cid)
    from api.services.paper_chart import PaperChart
    groups = [PaperChart(service.path, c['id'] or None).group(account, cid) for c in choices]
    groups += service.historical_groups(account, cid, {c['ref'] for c in choices})
    refs = sorted(g['ref'] for g in groups)
    if not refs or sorted(body.get('expected_refs', [])) != refs:
        raise ValueError('Order groups changed; refresh before starting a new group')
    if any(any(v for k, v in g.items() if k.startswith('pending_')) or g.get('close_cancellation')
           or g.get('stock_adjustment', {}).get('pending') or g.get('adjustment', {}).get('outcome') == 'unknown'
           for g in groups):
        raise ValueError('An existing order change needs broker reconciliation first')
    with service.database() as db:
        for rid, encoded, result in db.execute('SELECT id,body,result FROM chart_paper_requests WHERE account=?', (account,)):
            if rid == request_id or json.loads(encoded).get('con_id') != cid:
                continue
            outcome = json.loads(result) if result else {}
            if not outcome or outcome.get('status') in ('unknown', 'pending', 'submitting') or outcome.get('awaiting_broker'):
                raise ValueError('An unresolved request remains; no new lifecycle is allowed')
        has_conflicts = db.execute("SELECT 1 FROM sqlite_master WHERE name='group_ledger_conflicts'").fetchone()
        if has_conflicts and db.execute('SELECT 1 FROM group_ledger_conflicts WHERE account=? AND con_id=?', (account, cid)).fetchone():
            raise ValueError('Conflicting execution or ownership evidence needs reconciliation first')
    before = records(conn, account, cid)
    client = conn.ib.client
    client_id = client.clientId

    def unchanged():
        if (not conn.is_connected() or conn.account_id != account or conn.ib.client is not client
                or conn.port != 4002 or client.clientId != client_id or conn.ib.managedAccounts() != [account]):
            raise ValueError('Broker connection changed during recovery')
        if any(p.account == account and p.contract.conId == cid and p.position != 0 for p in conn.ib.positions()):
            raise ValueError('A position remains; no flat checkpoint is possible')
        if any(t.order.account == account and t.contract.conId == cid for t in conn.ib.openTrades()):
            raise ValueError('An active order remains; no flat checkpoint is possible')
        if records(conn, account, cid) != before:
            raise ValueError('An execution arrived during recovery; refresh before retrying')

    # Complete all-client snapshots, followed by callback checks. Empty cached
    # positions or a history timeout alone can never establish this boundary.
    for _ in range(2):
        opened = conn._bounded_order_read(conn.ib.reqAllOpenOrders, timeout_seconds=3)
        positions = conn._bounded_order_read(conn.ib.reqPositions, timeout_seconds=3)
        if not isinstance(opened, (list, tuple)) or not isinstance(positions, (list, tuple)):
            raise ValueError('Complete broker order and position snapshots are required')
        if any(t.order.account == account and t.contract.conId == cid for t in opened):
            raise ValueError('An order remains in the broker open-order snapshot')
        if any(p.account == account and p.contract.conId == cid and
               (not math.isfinite(float(p.position)) or p.position != 0) for p in positions):
            raise ValueError('Broker position is not confirmed flat')
        unchanged()
    baseline = [json.loads(r) for r in before]
    with service.database() as db:
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='group_execution_evidence'").fetchone():
            baseline += [{k: json.loads(row[0]).get(k) for k in FIELDS} for row in db.execute(
                'SELECT payload FROM group_execution_evidence WHERE account=? AND con_id=?', (account, cid))]
    _, unambiguous = execution_groups([SimpleNamespace(**r) for r in baseline])
    if not unambiguous:
        raise ValueError('Conflicting historical executions cannot establish a new lifecycle')
    unchanged()
    current = [PaperChart(service.path, c['id'] or None).group(account, cid) for c in service.group_choices(account, cid)]
    current += service.historical_groups(account, cid, {g['ref'] for g in current})
    if sorted(current, key=lambda g: g['ref']) != sorted(groups, key=lambda g: g['ref']):
        raise ValueError('Order history changed during recovery; refresh before retrying')
    checkpoint = dict(references=refs, groups=groups, baseline=baseline, group_id=service.group_id,
                      observed_at=time.time(), position=0, open_order_count=0)
    with service.database() as db:
        db.execute('INSERT INTO chart_flat_checkpoints VALUES(?,?,?,?)',
                   (request_id, account, cid, json.dumps(checkpoint, sort_keys=True)))
    return dict(success=True, status='acknowledged',
                message='Broker confirmed no position or open orders. New group ready; unresolved history is retained.')
