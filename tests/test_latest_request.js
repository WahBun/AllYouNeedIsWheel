import test from 'node:test';
import assert from 'node:assert/strict';
import { createLatestRequestQueue } from '../frontend/static/js/utils/latest-request.js';

test('rapid selections skip queued obsolete work and discard the old result', async () => {
    const queue = createLatestRequestQueue();
    let finish;
    const first = queue.run('TSLL:CALL', () => new Promise(resolve => { finish = resolve; }));
    await new Promise(resolve => setImmediate(resolve));
    let obsoleteCalls = 0;
    const second = queue.run('TSLL:CALL', () => { obsoleteCalls++; return 'November'; });
    const third = queue.run('TSLL:CALL', () => 'December');
    finish('October');
    assert.deepEqual(await Promise.all([first, second, third]), [null, null, 'December']);
    assert.equal(obsoleteCalls, 0);
});

test('failed obsolete requests do not interrupt the newest selection or another row', async () => {
    const queue = createLatestRequestQueue();
    let fail;
    const old = queue.run('CALL', () => new Promise((_, reject) => { fail = reject; }));
    await new Promise(resolve => setImmediate(resolve));
    const latest = queue.run('CALL', () => 'new');
    assert.equal(await queue.run('PUT', () => 'put'), 'put');
    fail(new Error('timeout'));
    assert.equal(await old, null);
    assert.equal(await latest, 'new');
    await assert.rejects(queue.run('CALL', () => { throw new Error('current failure'); }), /current failure/);
    assert.equal(await queue.run('CALL', () => 'recovered'), 'recovered');
});
