import test from 'node:test';
import assert from 'node:assert/strict';

import {
    getPositionKey,
    haveSamePositionSet,
    getPriceDirection
} from '../frontend/static/js/utils/live-positions.js';

test('position keys stay stable across quote changes', () => {
    const stock = { security_type: 'STK', symbol: 'TSLL', market_price: 9.5 };
    const option = { security_type: 'OPT', symbol: 'TSLL', con_id: 846598113, market_price: 0.16 };

    assert.equal(getPositionKey(stock), 'STK:TSLL');
    assert.equal(getPositionKey(option), 'OPT:846598113');
});

test('position set changes trigger a structural table refresh', () => {
    const current = [
        { security_type: 'STK', symbol: 'TSLL' },
        { security_type: 'OPT', symbol: 'TSLL', con_id: 2 }
    ];
    const repriced = [
        { security_type: 'OPT', symbol: 'TSLL', con_id: 2, market_price: 0.17 },
        { security_type: 'STK', symbol: 'TSLL', market_price: 9.52 }
    ];
    const closed = [{ security_type: 'STK', symbol: 'TSLL' }];

    assert.equal(haveSamePositionSet(current, repriced), true);
    assert.equal(haveSamePositionSet(current, closed), false);
});

test('price direction ignores missing and unchanged values', () => {
    assert.equal(getPriceDirection(9.5, 9.51), 'up');
    assert.equal(getPriceDirection(9.5, 9.49), 'down');
    assert.equal(getPriceDirection(9.5, 9.5), null);
    assert.equal(getPriceDirection(null, 9.5), null);
});
