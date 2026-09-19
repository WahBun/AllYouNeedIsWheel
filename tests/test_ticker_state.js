import test from 'node:test';
import assert from 'node:assert/strict';

import { ensureTickerState } from '../frontend/static/js/utils/ticker-state.js';

test('saved OTM preferences are expanded into a complete ticker state', () => {
    const store = {
        TSLL: {
            callOtmPercentage: 20,
            putOtmPercentage: 15,
            putQuantity: 2
        }
    };

    const state = ensureTickerState(store, 'TSLL');

    assert.equal(state.callOtmPercentage, 20);
    assert.equal(state.putOtmPercentage, 15);
    assert.equal(state.putQuantity, 2);
    assert.deepEqual(state.data.data.TSLL, {
        stock_price: 0,
        position: 0,
        calls: [],
        puts: []
    });
});

test('new ticker state receives safe defaults', () => {
    const store = {};

    const state = ensureTickerState(store, 'CRCL');

    assert.equal(state.callOtmPercentage, 10);
    assert.equal(state.putOtmPercentage, 10);
    assert.equal(state.putQuantity, 1);
    assert.deepEqual(state.data.data.CRCL.calls, []);
    assert.deepEqual(state.data.data.CRCL.puts, []);
});
