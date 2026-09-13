import test from 'node:test';
import assert from 'node:assert/strict';

import {
    calculateMidPrice,
    calculateSpreadPercentage,
    positivePrice
} from '../frontend/static/js/utils/option-pricing.js';

test('mid price requires a valid two-sided market', () => {
    assert.equal(calculateMidPrice(0.9, 1.1), 1);
    assert.equal(calculateMidPrice(0.9, 0), null);
    assert.equal(calculateMidPrice(0, 1.1), null);
    assert.equal(calculateMidPrice(1.1, 0.9), null);
});

test('invalid and stale-looking values stay unavailable', () => {
    assert.equal(positivePrice(''), null);
    assert.equal(positivePrice('NaN'), null);
    assert.equal(positivePrice(-1), null);
    assert.equal(calculateMidPrice(null, null), null);
});

test('spread uses the same validated two-sided quote', () => {
    assert.ok(Math.abs(calculateSpreadPercentage(0.95, 1.05) - 10) < 1e-9);
    assert.equal(calculateSpreadPercentage(1, null), null);
});
