"""Opt-in loopback-only acceptance host; never imported by the normal app.
Uses unchanged Wheel HTTP routes, dispatcher, PaperChart and IBConnection recovery.
A new private directory is mandatory. No production configuration is inherited.
"""
import argparse
import json
import os
from pathlib import Path
import secrets
import sys
import time
from uuid import uuid4

class OrderFence:
    def __init__(self, account, client_id, con_id, reference, audit):
        self.account, self.client_id, self.con_id, self.reference = account, client_id, con_id, reference
        self.identities = {}; self.audit = audit

    def check(self, contract, order, cancel=False):
        oid = order.orderId
        if (order.account != self.account or order.orderRef != self.reference or
            getattr(order, 'clientId', 0) not in (0, self.client_id)):
            raise ValueError('Acceptance fence: foreign order identity')
        if contract is not None and contract.conId != self.con_id:
            raise ValueError('Acceptance fence: foreign contract')
        if cancel and oid not in self.identities:
            raise ValueError('Acceptance fence: unknown cancellation')
        if not cancel and oid not in self.identities:
            if len(self.identities) >= 3 or float(order.totalQuantity) != 1:
                raise ValueError('Acceptance fence: only one one-contract bracket')
        old = self.identities.get(oid)
        perm = getattr(order, 'permId', 0)
        if old and old != perm:
            raise ValueError('Acceptance fence: changed permanent identity')
        if not cancel: self.identities[oid] = perm
        self.audit('cancel' if cancel else 'place', order_id=oid, perm_id=perm, ref=order.orderRef)

    def install(self, ib):
        place, cancel = ib.placeOrder, ib.cancelOrder
        def place_order(contract, order):
            self.check(contract, order)
            return place(contract, order)
        def cancel_order(order, *args, **kwargs):
            self.check(None, order, True)
            return cancel(order, *args, **kwargs)
        def forbidden(*args, **kwargs):
            raise ValueError('Acceptance fence: global operations disabled')
        ib.placeOrder, ib.cancelOrder = place_order, cancel_order
        ib.reqGlobalCancel = forbidden
        ib.reqAutoOpenOrders = forbidden


class TwoGroupFence(OrderFence):
    def __init__(self, account, client_id, con_id, references, audit):
        if len(set(references))!=2:raise ValueError('Exactly two distinct references required')
        super().__init__(account,client_id,con_id,references[0],audit)
        self.children={ref:OrderFence(account,client_id,con_id,ref,audit) for ref in references}
    def check(self, contract, order, cancel=False):
        owner=self.children.get(order.orderRef)
        if owner is None:raise ValueError('Foreign group')
        if any(order.orderId in child.identities for ref,child in self.children.items() if ref!=order.orderRef):
            raise ValueError('Cross-group identity reuse')
        owner.check(contract,order,cancel)


def resume_manifest(root, account, client_id, port):
    """Only resume the exact isolated journal; never import production state."""
    import sqlite3
    root = root.resolve()
    m=json.loads((root/'manifest.json').read_text())
    config=json.loads((root/'connection.json').read_text())
    if (m['client_id']!=client_id or m['port']!=port or config['account_id']!=account or
        config['client_id']!=client_id or config['port']!=4002 or config['host']!='127.0.0.1' or
        Path(config['db_path']).resolve()!=root/'test.sqlite' or
        Path(m['database']).resolve()!=root/'test.sqlite'):
        raise ValueError('Resume identity/configuration mismatch')
    if not (root/'test.sqlite').is_file():raise ValueError('Test database missing')
    with sqlite3.connect(root/'test.sqlite') as db:
        db.execute('PRAGMA query_only=ON')
        rows=db.execute('SELECT orders FROM chart_paper_independent WHERE account=? AND con_id=? AND group_id=?',
                        (account,m['con_id'],m['group'])).fetchall()
    if len(rows)!=1:raise ValueError('Exact isolated group required')
    group=json.loads(rows[0][0])
    if group['ref']!='WheelPaper:'+m['submit'] or set(group['ids'])!={'entry','tp','sl'}:
        raise ValueError('Not the original one-contract bracket')
    ids={oid:group.get('perms',{}).get(role,0) for role,oid in group['ids'].items()}
    if len(ids)!=3 or not all(ids.values()):raise ValueError('Confirmed permanent identities required')
    return m,config,ids


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--two-groups', action='store_true')
    parser.add_argument('--account', required=True)
    parser.add_argument('--client-id', type=int, required=True)
    parser.add_argument('--port', type=int, default=18081)
    args = parser.parse_args()
    if not args.account.startswith('DU') or args.client_id in (0, 71) or args.client_id < 1 or not 1024 <= args.port <= 65535:
        parser.error('Explicit Paper account, nonzero non-71 client and unprivileged port required')
    if args.two_groups and args.resume:parser.error('Two-group process restart not enabled in this acceptance scope')
    root = Path(args.root).resolve()
    import fcntl
    os.umask(0o077)
    if not args.resume:root.mkdir(mode=0o700)
    lock=(root/'instance.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    restored={}
    if args.resume:
        manifest,config,restored=resume_manifest(root,args.account,args.client_id,args.port)
        token,group,submit,cid=(manifest[k] for k in ('token','group','submit','con_id'))
        manifest['pid']=os.getpid()
    else:
        token, group, submit = secrets.token_hex(32), str(uuid4()), str(uuid4())
        cid = 815824267
        manifest = dict(pid=os.getpid(), client_id=args.client_id, port=args.port, group=group,
                        submit=submit, con_id=cid, token=token, database=str(root/'test.sqlite'))
        config = dict(host='127.0.0.1', port=4002, client_id=args.client_id, account_id=args.account,
                      readonly=False, db_path=str(root/'test.sqlite'), timeout=8)
        (root/'connection.json').write_text(json.dumps(config))
    test_groups={group:submit}
    if args.two_groups:test_groups[str(uuid4())]=str(uuid4())
    manifest['test_groups']=test_groups
    (root/'manifest.json').write_text(json.dumps(manifest))
    os.environ.update(CONNECTION_CONFIG=str(root/'connection.json'), LOG_DIR=str(root/'logs'),
                      WHEEL_ACCOUNT_PROFILES=str(root/'disabled-account-profiles'),
                      WHEEL_GATEWAY_PROFILES=str(root/'disabled-gateway'))
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    def audit(event, **values):
        with (root/'audit.jsonl').open('a') as f:
            f.write(json.dumps(dict(time=time.time(), event=event, **values))+'\n')
    from core.connection import IBConnection
    from api.services.connection_manager import connection_manager
    fence = OrderFence(args.account, args.client_id, cid, 'WheelPaper:'+submit, audit)
    if args.two_groups:fence=TwoGroupFence(args.account,args.client_id,cid,['WheelPaper:'+r for r in test_groups.values()],audit)
    fence.identities.update(restored)
    class IsolatedConnection(IBConnection):
        checked = False
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            fence.install(self.ib)
        def connect(self):
            result = super().connect()
            if not result: return False
            if self.ib.managedAccounts() != [args.account] or self.ib.client.clientId != args.client_id:
                self.disconnect(); raise ValueError('Actual Paper/client mismatch')
            if not self.checked:
                opened = self._bounded_order_read(self.ib.reqAllOpenOrders, timeout_seconds=3)
                unexpected=[t for t in opened if (t.order.clientId == args.client_id or t.contract.conId == cid) and not (args.resume and t.order.clientId==args.client_id and t.order.account==args.account and t.contract.conId==cid and t.order.orderRef==fence.reference and restored.get(t.order.orderId)==t.order.permId)]
                if unexpected:
                    self.disconnect(); raise ValueError('Client already owns orders or MNQ orders exist')
                if any(p.contract.conId == cid and p.position and not (args.resume and p.account==args.account and p.position==1) for p in self.ib.positions()):
                    self.disconnect(); raise ValueError('MNQ position exists')
                self.checked = True
            audit('connected', client_id=self.ib.client.clientId, paper_verified=True)
            return True
    connection_manager._connection_factory = IsolatedConnection
    from api import create_app
    from flask import request, jsonify
    app = create_app()
    chart_path = f'/api/portfolio/paper-chart/{cid}'
    read_paths = {'/health', '/api/account/profiles', chart_path,
                  f'/api/portfolio/stock-chart/{cid}', f'/api/portfolio/chart-executions/{cid}'}
    @app.before_request
    def fence_http():
        if request.remote_addr != '127.0.0.1' or not secrets.compare_digest(request.headers.get('X-Acceptance-Token',''),token):
            return jsonify(error='Acceptance authorization required'),403
        if request.method=='GET' and request.path in read_paths:
            if request.path==chart_path and request.args.get('group_id') not in test_groups:
                return jsonify(error='Exact test group required'),403
            return None
        if not args.two_groups and request.method=='POST' and request.path=='/api/acceptance/disconnect': return None
        if request.method=='POST' and request.path==chart_path and request.args.get('group_id') in test_groups:
            selected_submit=test_groups[request.args['group_id']]
            selected_ref='WheelPaper:'+selected_submit
            body=request.get_json(silent=True) or {}
            action=body.get('action')
            if not args.resume and action=='submit' and body.get('request_id')==selected_submit and body.get('quantity')==1 and body.get('side')==1 and body.get('tp') and body.get('sl'):
                return None
            if args.two_groups and action=='amend' and body.get('expected_ref')==selected_ref and body.get('role') in ('tp','sl'):return None
            if action=='close' and body.get('expected_ref')==selected_ref and body.get('expected_position')==1: return None
            if action=='edit_entry' and body.get('cancel') is True and body.get('expected_ref')==selected_ref: return None
        return jsonify(error='Operation outside isolated acceptance scope'),403
    @app.post('/api/acceptance/disconnect')
    def disconnect():
        # This /api route runs inside the normal single-thread IB dispatcher.
        conn=connection_manager._connection
        if not conn or conn.client_id!=args.client_id or not conn.is_connected():
            return jsonify(error='No isolated connected session'),409
        from api.services.paper_chart import PaperChart
        s=PaperChart(config['db_path'],group).state(conn,cid)
        if not s.get('known') or s.get('position')!=1 or s.get('protection',{}).get('tp')!=1 or s.get('protection',{}).get('sl')!=1:
            return jsonify(error='Accepted one-contract protection required'),409
        conn.disconnect()
        audit('disconnected', client_id=args.client_id, state=s)
        return jsonify(disconnected=True,client_id=args.client_id)
    audit('resumed' if args.resume else 'started', client_id=args.client_id, port=args.port, pid=os.getpid())
    from werkzeug.serving import make_server
    server=make_server('127.0.0.1',args.port,app,threaded=True)
    try: server.serve_forever()
    finally:
        app.extensions['ib_background_stop'].set()
        server.server_close()

if __name__=='__main__': main()
