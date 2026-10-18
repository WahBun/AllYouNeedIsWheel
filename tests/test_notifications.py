import tempfile
import time
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from api.services.notifications import NotificationStore, account_scope
from api.services.notification_runtime import NotificationRuntime
from api.services.push_delivery import deliver_once
from api.services.chart_drawings import exchange


class NotificationsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)/'notifications.db'
        self.store = NotificationStore(self.path)
        self.scope = account_scope('DU_TEST')
        self.other = account_scope('U_TEST')
        self.runtime = NotificationRuntime(self.store)
        self.start = time.time()
    def tearDown(self): self.temp.cleanup()
    def alert(self, **kw):
        body = dict(id=str(uuid.uuid4()), price=100, condition='crossing', repeat='once', **kw)
        row = self.store.create_alert(self.scope, 7, 'TEST', body)
        self.runtime.active = self.store.alerts(active=True)
        return row
    def prices(self, *prices, scope=None, start=None):
        for index, price in enumerate(prices):
            self.runtime.process(('price', scope or self.scope, 7, price, 'IB Paper', (start or self.start)+index+1))
    def events(self, scope=None): return self.store.events(scope or self.scope, 0)['events']
    def test_crossing_once_replay_and_scope(self):
        a = self.alert(); self.prices(99, 101, 99, 101, scope=self.other)
        self.assertEqual(self.events(), [])
        self.prices(99, 100, 101, 99, 101)
        self.assertEqual(len(self.events()), 1)
        restored = NotificationStore(self.path)
        self.assertEqual(restored.alerts(self.scope)[0]['state'], 'triggered')
        self.assertFalse(restored.fire(a, 101, 'IB Paper'))
    def test_no_initial_or_stale_crossing(self):
        self.alert(); self.prices(101)
        self.assertFalse(self.events())
        self.runtime.process(('reset',)); self.prices(99)
        self.prices(101, start=self.start+100)
        self.assertFalse(self.events())
    def test_every_crossing_cooldown(self):
        a = self.store.create_alert(self.scope, 7, 'TEST', dict(id=str(uuid.uuid4()), price=100, condition='up', repeat='every'))
        self.runtime.active = [a]; self.prices(99, 101, 99, 101)
        self.assertEqual(len(self.events()), 1)
        self.prices(99,101,start=self.start+65)
        self.assertEqual(len(self.events()),2)
    def test_only_live_last_tick(self):
        self.alert(); self.runtime.conn=SimpleNamespace(is_connected=lambda:True); self.runtime.scope=self.scope;self.runtime.mode='IB Paper'
        ticker=SimpleNamespace(marketDataType=3,ticks=[SimpleNamespace(tickType=4,price=99)])
        self.runtime.tick(7,ticker);self.assertEqual(self.runtime.queue.get_nowait(),('reset',7))
        ticker.marketDataType=1;ticker.ticks=[SimpleNamespace(tickType=x,price=99) for x in [1,2,9,68,4]]
        self.runtime.tick(7,ticker);event=self.runtime.queue.get_nowait();self.assertEqual(event[:4],('price',self.scope,7,99));self.assertTrue(self.runtime.queue.empty())
    def test_ray_follows_saved_value_and_delete_is_terminal(self):
        drawing=Path(self.temp.name)/'drawings.db'
        def op(key,price,base=0,kind='put'):
            return dict(op=key,id='ray',kind=kind,base=base,value=dict(id='ray',type='hray',p=[dict(time=1,price=price)]))
        exchange(7,[op('create',100)],drawing);a=self.alert(drawing='ray');self.prices(99)
        exchange(7,[op('move',105,1)],drawing);self.store.sync_rays(drawing)
        moved=self.store.alerts(self.scope)[0];self.assertEqual(moved['price'],105);self.assertFalse(self.store.fire(a,106,'IB Paper'))
        self.runtime.active=[moved];self.prices(106);self.assertFalse(self.events())
        exchange(7,[op('delete',105,2,'delete')],drawing);self.store.sync_rays(drawing)
        exchange(7,[op('stale',100,1)],drawing);self.store.sync_rays(drawing)
        self.assertEqual(self.store.alerts(self.scope)[0]['state'],'drawing_removed')
    def test_confirmed_cancel_only_and_restart_dedup(self):
        self.store.observe_order(self.scope,'10','Cancelled','OLD','IB Paper')
        self.store.observe_order(self.scope,'11','Submitted','TEST','IB Paper')
        self.store.observe_order(self.scope,'11','PendingCancel','TEST','IB Paper');self.assertFalse(self.events())
        NotificationStore(self.path).observe_order(self.scope,'11','Cancelled','TEST','IB Paper')
        self.store.observe_order(self.scope,'11','Cancelled','TEST','IB Paper');self.assertEqual(len(self.events()),1)
    def test_fill_history_replay_and_delivery_retry(self):
        self.store.begin_orders(self.scope)
        with self.store.connect() as db: since=db.execute('SELECT since FROM order_scopes').fetchone()[0]
        self.store.observe_fill(self.scope,'historical',since-1,'OLD','IB Paper');self.assertFalse(self.events())
        device=dict(id=str(uuid.uuid4()),token='ab'*32,environment='sandbox',enabled=True)
        self.store.register(self.scope,device)
        for _ in range(3):self.store.observe_fill(self.scope,'execution.1',since+1,'TEST 1 @ 100','IB Paper')
        self.assertEqual(len(self.events()),1)
        sender=SimpleNamespace(send=lambda d,e:(503,''));deliver_once(self.store,sender)
        with self.store.connect() as db:
            row=db.execute('SELECT * FROM deliveries').fetchone();self.assertEqual(row['state'],'pending');self.assertEqual(row['attempts'],1)
            db.execute('UPDATE deliveries SET next_try=0')
        sender.send=lambda d,e:(200,'');deliver_once(self.store,sender);deliver_once(self.store,sender)
        with self.store.connect() as db:self.assertEqual(db.execute('SELECT state,attempts FROM deliveries').fetchone()[:],('sent',2))
    def test_token_rotation_scope_disable_and_invalid_device(self):
        device=dict(id=str(uuid.uuid4()),token='ab'*32,environment='sandbox',enabled=True)
        self.store.register(self.scope,device);self.store.register(self.other,device)
        self.store.register(self.scope,{**device,'token':'cd'*32})
        with self.store.connect() as db:self.assertEqual({r[0] for r in db.execute('SELECT token FROM devices')},{'cd'*32})
        self.store.register(self.other,dict(id=device['id'],enabled=False))
        self.alert();self.prices(99,101)
        deliver_once(self.store,SimpleNamespace(send=lambda d,e:(410,'Unregistered')))
        with self.store.connect() as db:self.assertFalse(any(r[0] for r in db.execute('SELECT enabled FROM devices')))
    def test_idempotency_limits_and_invalid_input(self):
        a=self.alert();b=self.store.create_alert(self.scope,7,'TEST',dict(id=a['id'],price=100));self.assertEqual(a,b)
        for price in [0,-1,float('nan'),True]:
            with self.assertRaises(ValueError):self.store.create_alert(self.scope,7,'TEST',dict(id=str(uuid.uuid4()),price=price))
        with self.assertRaises(ValueError):self.store.create_alert(self.other,7,'TEST',dict(id=a['id'],price=100))
    def test_owner_pump_without_chart_and_reconnect(self):
        from eventkit import Event
        self.alert(); self.runtime.enabled=True
        ticker=SimpleNamespace(updateEvent=Event(),marketDataType=1,ticks=[])
        connected=[True]; sleeps=[]
        ib=SimpleNamespace(orderStatusEvent=Event(),execDetailsEvent=Event(),fills=lambda:[],sleep=sleeps.append)
        conn=SimpleNamespace(ib=ib,account_id='DU_TEST',is_connected=lambda:connected[0],
            get_market_ticker=lambda c:ticker,has_market_subscription=lambda c:True,refresh_execution_history=lambda:None,get_order_status_snapshot=lambda:{'trades':[]})
        service=SimpleNamespace(_ensure_connection=lambda:conn,config={'account_id':'DU_TEST'},connection_status=lambda c:{'mode':'paper'})
        with patch('api.services.chart_contracts.contracts.resolve',return_value=object()):
            self.runtime.pulse(service)
            self.assertEqual(len(ticker.updateEvent),1);self.assertEqual(sleeps,[.005])
            for price in (99,101):
                ticker.ticks=[SimpleNamespace(tickType=4,price=price)];ticker.updateEvent.emit(ticker)
            while not self.runtime.queue.empty():self.runtime.process(self.runtime.queue.get_nowait())
            self.assertEqual(len(self.events()),1)
            connected[0]=False;self.runtime.pulse(service);self.assertEqual(len(ticker.updateEvent),0)
            connected[0]=True;self.runtime.next_refresh=0;self.runtime.pulse(service);self.assertEqual(len(ticker.updateEvent),1)
            self.runtime.enabled=False;self.runtime.pulse(service);self.assertEqual(len(ticker.updateEvent),0)

    def test_routes_keep_epoch_and_same_origin_guards(self):
        from api import create_app
        app=create_app({'TESTING':True,'NOTIFICATION_DB':str(self.path)})
        conn=SimpleNamespace(account_id='DU_TEST',is_connected=lambda:True)
        service=SimpleNamespace(config={'account_id':'DU_TEST'},connection=conn,_ensure_connection=lambda:conn,connection_status=lambda c:{'mode':'paper'})
        try:
            with patch('api.routes.portfolio.portfolio_service',service),patch('api.routes.account.epoch',return_value='current'),patch('api.services.chart_contracts.contracts.describe',return_value={'local_symbol':'TEST'}):
                client=app.test_client();body=dict(id=str(uuid.uuid4()),price=100)
                endpoint='/api/notifications/alerts/7'
                self.assertEqual(client.post(endpoint,json=body).status_code,403)
                self.assertEqual(client.post(endpoint,json=body,headers={'X-All-You-Need-Is-Wheel':'1'}).status_code,409)
                headers={'X-All-You-Need-Is-Wheel':'1','X-Wheel-Account-Epoch':'current'}
                response=client.post(endpoint,json=body,headers=headers);self.assertEqual(response.status_code,200,response.json)
                self.assertEqual(len(response.json['alerts']),1)
                self.assertEqual(client.post(endpoint,json=body,headers=headers).status_code,200)
                self.assertEqual(client.get('/api/notifications/events').status_code,200)
                self.assertEqual(client.post('/api/notifications/alerts/'+body['id']+'/stop',json={},headers=headers).status_code,200)
                self.assertEqual(self.store.alerts()[0]['state'],'stopped')
        finally:
            app.extensions['ib_background_stop'].set();app.extensions['ib_api_executor'].shutdown(wait=True)

    def test_apns_headers_payload_and_signature(self):
        import httpx, jwt, os
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives import serialization
        from api.services.push_delivery import APNs
        key=ec.generate_private_key(ec.SECP256R1())
        path=Path(self.temp.name)/'temporary-test-key.p8'
        path.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
        requests=[]
        client=httpx.Client(transport=httpx.MockTransport(lambda request: requests.append(request) or httpx.Response(200)))
        sender=APNs();sender.client=client
        try:
            with patch.dict(os.environ,dict(WHEEL_APNS_KEY_ID='TESTKEY',WHEEL_APNS_TEAM_ID='TESTTEAM',WHEEL_APNS_KEY_PATH=str(path),WHEEL_APNS_TOPIC='test.wheel')):
                for ident in ['fill:'+self.scope+':one','fill:'+self.scope+':two']:
                    self.assertEqual(sender.send({'environment':'sandbox','token':'ab'*32},dict(id=ident,kind='fill',title='IB Paper',body='TEST',created=time.time()))[0],200)
            claims=jwt.decode(requests[0].headers['authorization'].split(' ')[1],key.public_key(),algorithms=['ES256'])
            self.assertEqual(claims['iss'],'TESTTEAM')
            self.assertEqual(requests[0].url.host,'api.sandbox.push.apple.com')
            self.assertEqual(requests[0].headers['apns-topic'],'test.wheel')
            self.assertNotEqual(requests[0].headers['apns-collapse-id'],requests[1].headers['apns-collapse-id'])
            import json
            self.assertEqual(json.loads(requests[0].content)['wheel_kind'],'fill')
        finally: client.close()

    def test_terminal_orders_do_not_regress(self):
        for status in ['Submitted','Filled','Submitted','Cancelled']:
            self.store.observe_order(self.scope,'100',status,'TEST','IB Paper')
        self.assertFalse(self.events())
        with self.store.connect() as db:self.assertEqual(db.execute('SELECT status FROM broker_orders').fetchone()[0],'Filled')

    def test_events_initial_snapshot_and_cursor(self):
        self.alert();self.prices(99,101)
        first=self.store.events(self.scope);self.assertFalse(first['events']);self.assertGreater(first['cursor'],0)
        self.assertFalse(self.store.events(self.scope,first['cursor'])['events'])
        self.assertFalse(self.store.events(self.other,0)['events'])

if __name__ == '__main__': unittest.main()
