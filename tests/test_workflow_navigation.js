import test from 'node:test';
import assert from 'node:assert/strict';
import { revealPendingOrder, revealWorkflowTarget, batchCancellationConfirmed } from '../frontend/static/js/utils/workflow-navigation.js';

test('batch return requires every cancellation to be explicitly confirmed', () => {
    const confirmed = {status: 'fulfilled', value: {success: true, status: 'canceled'}};
    assert.equal(batchCancellationConfirmed([confirmed, confirmed]), true);
    for (const result of [
        {status: 'rejected', reason: new Error('offline')},
        {status: 'fulfilled', value: {success: true, status: 'canceling'}},
        {status: 'fulfilled', value: {success: false, status: 'canceled'}},
        {status: 'fulfilled', value: {success: true, status: 'unknown'}}
    ]) assert.equal(batchCancellationConfirmed([confirmed, result]), false);
    assert.equal(batchCancellationConfirmed([]), false);
});

test('pending navigation finds exact order in dashboard and rollover bodies', async () => {
    const originals = new Map(['document', 'window', 'matchMedia', 'requestAnimationFrame'].map(key => [key, globalThis[key]]));
    try {
        const visits = [];
        const makeRow = id => ({isConnected: true, dataset: {orderId: id},
            scrollIntoView: options => visits.push({id, options}),
            classList: {add() {}, remove() {}}});
        const rows = [makeRow('12'), makeRow('123')];
        const body = {querySelectorAll: () => rows};
        globalThis.window = {setTimeout: callback => callback()};
        globalThis.matchMedia = () => ({matches: true});
        globalThis.requestAnimationFrame = callback => callback();
        for (const bodyId of ['pending-orders-table', 'pending-orders-table-body']) {
            globalThis.document = {getElementById: id => id === bodyId ? body : null};
            assert.equal(await revealPendingOrder(123), true);
        }
        assert.deepEqual(visits.map(item => item.id), ['123', '123']);
        assert(visits.every(item => item.options.behavior === 'auto'));
        assert.equal(await revealWorkflowTarget(null), false);
        assert.equal(await revealWorkflowTarget({isConnected: false}), false);
    } finally {
        for (const [key, value] of originals) {
            if (value === undefined) delete globalThis[key];
            else globalThis[key] = value;
        }
    }
});
