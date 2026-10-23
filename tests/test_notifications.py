import tempfile
import time
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from api.services.notifications import NotificationStore, account_scope, AlertConflict
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

    def test_clear_history_keeps_active_new_other_scopes_and_retry_identity(self):
        active = self.alert()
        stopped = self.alert(); self.store.stop_alert(self.scope, stopped['id'])
        fired = self.alert(); self.store.fire(fired, 101, 'IB Paper')
        removed = self.alert(drawing='old-ray')
        with self.store.connect() as db:
            db.execute("UPDATE alerts SET state='drawing_removed' WHERE id=?", (removed['id'],))
        other = self.store.create_alert(self.other, 7, 'OTHER', dict(id=str(uuid.uuid4()), price=100))
        self.store.stop_alert(self.other, other['id'])
        contract = self.store.create_alert(self.scope, 8, 'ANOTHER', dict(id=str(uuid.uuid4()), price=100))
        self.store.stop_alert(self.scope, contract['id'])
        seen = [a['id'] for a in [stopped, fired, removed, active, other, contract]]
        newer = self.alert(); self.store.stop_alert(self.scope, newer['id'])
        events = self.events()
        self.assertEqual(self.store.clear_alert_history(self.scope, 7, seen), 3)
        self.assertEqual({a['id'] for a in self.store.alerts(self.scope, 7)}, {active['id'], newer['id']})
        self.assertEqual(self.store.clear_alert_history(self.scope, 7, seen), 0)
        self.assertEqual(self.store.alerts(self.other, 7)[0]['id'], other['id'])
        self.assertEqual(self.store.alerts(self.scope, 8)[0]['id'], contract['id'])
        self.assertEqual(self.events(), events)
        replay = self.store.create_alert(self.scope, 7, 'TEST', dict(id=stopped['id'], price=100))
        self.assertEqual(replay['state'], 'stopped')
        self.assertFalse(self.store.fire(fired, 101, 'IB Paper'))
        restored = NotificationStore(self.path)
        self.assertEqual({a['id'] for a in restored.alerts(self.scope, 7)}, {active['id'], newer['id']})
        for invalid in [None, 'all', [False], [newer['id'], 'bad-id']]:
            with self.assertRaises(ValueError): restored.clear_alert_history(self.scope, 7, invalid)
        self.assertEqual({a['id'] for a in restored.alerts(self.scope, 7)}, {active['id'], newer['id']})
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

    def test_sound_persists_per_alert_and_is_snapshotted_on_event(self):
        first = self.alert(sound='hand-bell')
        second = self.alert(sound='none')
        self.assertEqual(NotificationStore(self.path).alerts(self.scope)[0]['sound'], 'none')
        changed = self.store.amend_alert(self.scope, first['id'],
                                        dict(cid=7, version=1, price=100, sound='chirpy'))
        self.assertEqual((changed['sound'], changed['version']), ('chirpy', 2))
        self.assertEqual(self.store.amend_alert(self.scope, first['id'],
                         dict(cid=7, version=1, price=100, sound='chirpy')), changed)
        self.assertFalse(self.store.fire(first, 101, 'IB Paper'))
        self.assertTrue(self.store.fire(changed, 101, 'IB Paper'))
        self.assertTrue(self.store.fire(second, 101, 'IB Paper'))
        self.assertEqual([e['sound'] for e in self.events()], ['chirpy', 'none'])
        self.assertFalse(self.store.fire(changed, 101, 'IB Paper'))
        self.assertEqual(self.store.events(self.other, 0)['events'], [])
        self.assertEqual(self.store.events(self.scope)['events'], [], 'Initial history stays silent')

    def test_sound_validation_drag_preservation_and_legacy_default(self):
        alert = self.alert(sound='three-notes')
        for invalid in ['missing', '../filled', None, [], True]:
            with self.assertRaises(ValueError): self.alert(sound=invalid)
            with self.assertRaises(ValueError):
                self.store.amend_alert(self.scope, alert['id'], dict(cid=7, version=1, price=100, sound=invalid))
        with self.assertRaises(AlertConflict):
            self.store.amend_alert(self.other, alert['id'], dict(cid=7, version=1, price=100, sound='none'))
        changed = self.store.amend_alert(self.scope, alert['id'], dict(cid=7, version=1, price=105))
        self.assertEqual(changed['sound'], 'three-notes', 'Dragging preserves the chosen sound')
        with self.store.connect() as db:
            db.execute('DELETE FROM alert_sounds WHERE id=?', (alert['id'],))
        self.assertEqual(NotificationStore(self.path).alerts(self.scope)[0]['sound'], 'alarm-clock')

    def test_price_amend_is_scoped_versioned_and_replay_safe(self):
        alert = self.alert()
        body = dict(price=105, version=1, cid=7)
        for scope, request in [(self.other, body), (self.scope, {**body, 'cid': 8}), (self.scope, {**body, 'version': 2})]:
            with self.assertRaises(AlertConflict): self.store.amend_alert(scope, alert['id'], request)
        updated = self.store.amend_alert(self.scope, alert['id'], body)
        self.assertEqual((updated['price'], updated['version']), (105, 2))
        self.assertEqual(self.store.amend_alert(self.scope, alert['id'], body), updated)
        self.store.stop_alert(self.scope, alert['id'])
        with self.assertRaises(AlertConflict): self.store.amend_alert(self.scope, alert['id'], dict(price=110, version=2, cid=7))
        self.assertEqual(self.store.alerts(self.scope)[0]['state'], 'stopped')
        ray = self.alert(drawing='saved-ray')
        with self.assertRaises(AlertConflict): self.store.amend_alert(self.scope, ray['id'], body)

    def test_price_amend_discards_pre_amend_ticks_and_requires_new_baseline(self):
        alert = self.alert()
        self.prices(99)
        with patch('api.services.notifications.time.time', return_value=self.start+10):
            updated = self.store.amend_alert(self.scope, alert['id'], dict(price=105, version=1, cid=7))
        self.assertFalse(self.store.fire(alert, 110, 'IB Paper'))
        self.runtime.active = [updated]
        self.prices(104, 106, start=self.start+2)
        self.assertFalse(self.events(), 'Queued old samples cannot cross a newly edited threshold')
        self.prices(106, start=self.start+11)
        self.assertFalse(self.events(), 'First live sample after the edit is only a baseline')
        self.prices(104, start=self.start+13)
        self.assertEqual(len(self.events()), 1)
        self.assertEqual(self.store.amend_alert(self.scope, alert['id'], dict(price=105, version=1, cid=7))['state'], 'triggered')

    def test_alert_schema_remains_compatible_with_previous_release(self):
        ident=str(uuid.uuid4());created=time.time()
        with self.store.connect() as db:
            # The previous release uses this positional insert during a rollback.
            db.execute('INSERT INTO alerts VALUES (?,?,?,?,?,?,?,?,?,?,?,0)',
                       (ident,self.scope,7,'TEST',100,'crossing','once',None,'active',1,created))
        row=self.store.alerts(self.scope)[0]
        self.assertEqual(row['id'],ident);self.assertEqual(row['monitor_since'],created)

    def test_bark_setup_is_private_scoped_and_does_not_replay_old_events(self):
        key = 'temporaryDeviceKey123'
        self.alert(); self.prices(99, 101)
        self.store.register_bark(self.scope, dict(url='https://api.day.app/'+key+'/example', enabled=True))
        status = self.store.bark_status(self.scope)
        self.assertTrue(status['enabled']); self.assertNotIn(key, str(status))
        self.assertFalse(self.store.bark_status(self.other)['enabled'])
        with self.store.connect() as db: self.assertEqual(db.execute('SELECT COUNT(*) FROM deliveries').fetchone()[0], 0)
        for url in ['http://api.day.app/'+key, 'https://example.com/'+key, 'https://api.day.app.evil.test/'+key, 'https://name:password@api.day.app/'+key]:
            with self.assertRaises(ValueError): self.store.register_bark(self.scope, dict(url=url, enabled=True))
        test_id = str(uuid.uuid4())
        self.store.test_bark(self.scope, test_id); self.store.test_bark(self.scope, test_id)
        with self.store.connect() as db: self.assertEqual(db.execute('SELECT COUNT(*) FROM deliveries').fetchone()[0], 1)
        self.store.register_bark(self.scope, dict(enabled=False))
        self.assertFalse(self.store.bark_status(self.scope)['configured'])
        with self.store.connect() as db: self.assertEqual(db.execute('SELECT state FROM deliveries').fetchone()[0], 'disabled')

    def test_bark_transport_and_delivery_without_apns_credentials(self):
        import io, json, os
        from api.services.push_delivery import Bark, NotificationSender
        requests = []
        def response(request, timeout):
            requests.append(request)
            value = io.BytesIO(b'{"code":200,"message":"success"}'); value.status = 200
            return value
        sender = NotificationSender(); sender.bark.opener = SimpleNamespace(open=response)
        key = 'temporaryDeviceKey123'
        self.store.register_bark(self.scope, dict(url=key, enabled=True))
        self.store.register(self.scope, dict(id=str(uuid.uuid4()), token='ab'*32, environment='sandbox', enabled=True))
        self.alert(); self.prices(99,101)
        with patch.dict(os.environ, {}, clear=True): deliver_once(self.store, sender)
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0].full_url, 'https://api.day.app/push')
        payload = json.loads(requests[0].data)
        self.assertEqual(payload['device_key'], key); self.assertEqual(payload['group'], 'Wheel · Paper')
        self.assertNotIn(key, requests[0].full_url); self.assertEqual(payload['level'], 'active')
        with self.store.connect() as db:
            states = {row['environment']: row['state'] for row in db.execute('SELECT v.environment,d.state FROM deliveries d JOIN devices v ON v.id=d.device AND v.scope=d.scope')}
        self.assertEqual(states, {'bark': 'sent', 'sandbox': 'pending'})
        # HTTP success without Bark application-level acceptance must not claim delivery.
        sender.bark.opener = SimpleNamespace(open=lambda *args, **kwargs: type('Response', (io.BytesIO,), {'status':200})(b'{"code":400,"message":"bad key"}'))
        self.assertEqual(sender.bark.send({'token':key},dict(id='test',title='Test',body='Test')),(400,'BadDeviceToken'))

    def test_bark_does_not_wait_behind_unconfigured_apns_and_disable_wins(self):
        import os
        from api.services.push_delivery import NotificationSender
        self.store.register(self.scope, dict(id=str(uuid.uuid4()), token='ab'*32, environment='sandbox', enabled=True))
        with self.store.connect() as db:
            for i in range(25): self.store._event(db, 'native-only-'+str(i), self.scope, 'price', 'IB Paper', 'TEST', time.time())
        self.store.register_bark(self.scope, dict(url='temporaryDeviceKey123', enabled=True))
        self.store.test_bark(self.scope, str(uuid.uuid4()))
        sends=[]
        def disable_while_sending(device,event):
            sends.append(event)
            self.store.register_bark(self.scope, dict(enabled=False))
            return 200,''
        sender=NotificationSender();sender.bark=SimpleNamespace(send=disable_while_sending)
        with patch.dict(os.environ, {}, clear=True): deliver_once(self.store,sender)
        self.assertEqual(len(sends),1)
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT state FROM deliveries WHERE device LIKE 'bark-%'").fetchone()[0],'disabled')
            self.assertEqual(db.execute("SELECT COUNT(*) FROM deliveries WHERE state='pending'").fetchone()[0],25)
    def test_owner_pump_without_chart_and_reconnect(self):
        from eventkit import Event
        self.alert(); self.runtime.enabled=True
        ticker=SimpleNamespace(updateEvent=Event(),marketDataType=1,ticks=[])
        connected=[True]; sleeps=[]
        ib=SimpleNamespace(orderStatusEvent=Event(),execDetailsEvent=Event(),fills=lambda:[],sleep=sleeps.append)
        conn=SimpleNamespace(ib=ib,account_id='DU_TEST',is_connected=lambda:connected[0],
            get_market_ticker=lambda c:ticker,has_market_subscription=lambda c:True,refresh_execution_history=lambda:None,get_order_status_snapshot=lambda:{'trades':[]})
        service=SimpleNamespace(_ensure_connection=lambda:conn,config={'account_id':'DU_TEST'},connection_status=lambda c:{'mode':'paper'})
        with patch('api.services.chart_contracts.contracts.resolve',return_value=object()), patch.object(self.runtime.moonshine, 'pulse', return_value={}):
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
                self.assertEqual(client.get(endpoint,headers=headers).json['epoch'],'current')
                self.assertEqual(client.get(endpoint).status_code,409)
                price_url='/api/notifications/alerts/'+body['id']+'/price'
                amendment=dict(cid=7,version=1,price=105)
                self.assertEqual(client.post(price_url,json=amendment).status_code,403)
                self.assertEqual(client.post(price_url,json=amendment,headers={'X-All-You-Need-Is-Wheel':'1'}).status_code,409)
                self.assertEqual(client.post(price_url,json=amendment,headers=headers).json['alert']['price'],105)
                self.assertEqual(client.post(price_url,json={**amendment,'price':106},headers=headers).status_code,409)
                self.assertEqual(client.post('/api/notifications/bark',json=[],headers=headers).status_code,400)
                bark=client.post('/api/notifications/bark',json={'url':'temporaryDeviceKey123','enabled':True},headers=headers)
                self.assertEqual(bark.status_code,200,bark.json);self.assertNotIn('temporaryDeviceKey123',str(bark.json))
                self.assertEqual(client.get('/api/notifications/bark',headers=headers).json['enabled'],True)
                self.assertEqual(client.get('/api/notifications/bark').status_code,409)
                self.assertEqual(client.get('/api/notifications/bark',headers={**headers,'X-Wheel-Account-Epoch':'old'}).status_code,409)
                with patch('api.routes.account.epoch',side_effect=['current','current','changed']):
                    self.assertEqual(client.get('/api/notifications/bark',headers=headers).status_code,409)
                self.assertEqual(client.post('/api/notifications/bark/test',json={'id':str(uuid.uuid4())},headers=headers).status_code,200)
                self.assertEqual(client.get('/api/notifications/events',headers=headers).status_code,200)
                self.assertEqual(client.post('/api/notifications/alerts/'+body['id']+'/stop',json={},headers=headers).status_code,200)
                self.assertEqual(self.store.alerts()[0]['state'],'stopped')
                clear_url=endpoint+'/clear-history'; clear_body={'ids':[body['id']]}
                self.assertEqual(client.post(clear_url,json=clear_body).status_code,403)
                self.assertEqual(client.post(clear_url,json=clear_body,headers={'X-All-You-Need-Is-Wheel':'1'}).status_code,409)
                self.assertEqual(client.post(clear_url,json=[],headers=headers).status_code,400)
                self.assertEqual(client.post(clear_url,json=clear_body,headers=headers).json['cleared'],1)
                self.assertEqual(client.get(endpoint,headers=headers).json['alerts'],[])
                self.assertEqual(client.post(clear_url,json=clear_body,headers=headers).json['cleared'],0)
        finally:
            app.extensions['ib_background_stop'].set();app.extensions['ib_api_executor'].shutdown(wait=True)

    def test_events_reject_stale_epoch_before_and_after_storage_read(self):
        from api import create_app
        app = create_app({'TESTING': True, 'NOTIFICATION_DB': str(self.path)})
        service = SimpleNamespace(config={'account_id': 'DU_TEST'}, connection=None)
        token = ['current']
        try:
            with patch('api.routes.portfolio.portfolio_service', service), \
                 patch('api.routes.account.epoch', side_effect=lambda: token[0]):
                client = app.test_client()
                headers = {'X-Wheel-Account-Epoch': 'current'}
                endpoint = '/api/notifications/events?after=0'
                self.assertEqual(client.get(endpoint).status_code, 409)
                self.assertEqual(client.get(endpoint, headers={'X-Wheel-Account-Epoch': 'stale'}).status_code, 409)
                self.assertEqual(client.get(endpoint, headers=headers).status_code, 200)
                def switch_during_read(*args):
                    token[0] = 'changed'
                    return {'events': [{'body': 'Previous account event'}], 'cursor': 1}
                with patch.object(app.extensions['notifications'].store, 'events', side_effect=switch_during_read):
                    response = client.get(endpoint, headers=headers)
                self.assertEqual(response.status_code, 409)
                self.assertNotIn('events', response.json)
                # Installations without account profiles retain the existing read path.
                token[0] = None
                self.assertEqual(client.get(endpoint).status_code, 200)
        finally:
            app.extensions['ib_background_stop'].set()
            app.extensions['ib_api_executor'].shutdown(wait=True)

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

    def test_sdk_local_cancel_waits_for_broker_completed_evidence(self):
        self.store.observe_order(self.scope,'42','Submitted','TEST','IB Paper')
        self.runtime.conn=SimpleNamespace(account_id='DU_TEST')
        self.runtime.scope=self.scope;self.runtime.mode='IB Paper'
        trade=SimpleNamespace(order=SimpleNamespace(account='DU_TEST',permId=42,action='BUY',totalQuantity=1,transmit=False),
            orderStatus=SimpleNamespace(status='Cancelled'),contract=SimpleNamespace(localSymbol='TEST',symbol='TEST'))
        self.runtime.order(trade)
        self.assertTrue(self.runtime.queue.empty());self.assertFalse(self.events())
        self.assertIn('42',self.runtime.cancel_candidates)
        self.runtime.order(trade,confirmed=True)
        self.runtime.process(self.runtime.queue.get_nowait())
        self.assertEqual(len(self.events()),1)
        self.runtime.order(trade);self.runtime.order(trade,confirmed=True)
        self.assertTrue(self.runtime.queue.empty());self.assertFalse(self.runtime.cancel_candidates)

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
