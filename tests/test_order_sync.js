import test from 'node:test';
import assert from 'node:assert/strict';

import {
    getActiveExternalOrders,
    getCancelableWebOrders,
    getOrderTimeInForce,
    getOrderSyncInterval,
    hasTrackedOrders,
    ORDER_DISCOVERY_INTERVAL_MS,
    ORDER_STATUS_SYNC_INTERVAL_MS,
    shouldForceOrderDiscovery
} from '../frontend/static/js/utils/order-sync.js';

test('active IB states keep order synchronization running', () => {
    for (const status of ['submitting', 'processing', 'canceling', 'unknown']) {
        assert.equal(hasTrackedOrders([{ status }]), true);
    }
});

test('local and terminal states do not keep polling IB', () => {
    for (const status of ['pending', 'executed', 'canceled', 'rejected']) {
        assert.equal(hasTrackedOrders([{ status }]), false);
    }
});

test('foreground order synchronization uses a short bounded interval', () => {
    assert.equal(ORDER_STATUS_SYNC_INTERVAL_MS, 1000);
});

test('time in force matches the order intent shown before execution', () => {
    assert.equal(getOrderTimeInForce({ intent: 'CLOSE' }), 'GTC');
    assert.equal(getOrderTimeInForce({ intent: 'OPEN' }), 'DAY');
    assert.equal(getOrderTimeInForce({ intent: 'CLOSE', tif: 'DAY' }), 'DAY');
    assert.equal(getOrderTimeInForce({}), 'DAY');
});

test('empty tables keep a slower discovery loop for orders entered in IB', () => {
    assert.equal(getOrderSyncInterval([]), ORDER_DISCOVERY_INTERVAL_MS);
    assert.equal(
        getOrderSyncInterval([{ status: 'processing', external_ib: true }]),
        ORDER_STATUS_SYNC_INTERVAL_MS
    );
    assert.ok(ORDER_DISCOVERY_INTERVAL_MS > ORDER_STATUS_SYNC_INTERVAL_MS);
});

test('external IB orders force authoritative refreshes until they disappear', () => {
    assert.equal(shouldForceOrderDiscovery([]), true);
    assert.equal(shouldForceOrderDiscovery([{ status: 'processing' }]), false);
    assert.equal(
        shouldForceOrderDiscovery([{ status: 'processing', external_ib: true }]),
        true
    );
});

test('cancel all separates web-owned and externally managed orders', () => {
    const orders = [
        { id: 1, status: 'pending' },
        { id: 2, status: 'processing' },
        { id: 'ib-3', status: 'processing', external_ib: true },
        { id: 4, status: 'executed' }
    ];

    assert.deepEqual(getCancelableWebOrders(orders).map(order => order.id), [1, 2]);
    assert.deepEqual(getActiveExternalOrders(orders).map(order => order.id), ['ib-3']);
});
