import test from 'node:test';
import assert from 'node:assert/strict';

import { isOrderConfirmationEnabled } from '../frontend/static/js/utils/order-preferences.js';

test('order confirmation stays enabled by default', () => {
    assert.equal(isOrderConfirmationEnabled(null), true);
    assert.equal(isOrderConfirmationEnabled('true'), true);
});

test('only an explicit false value enables direct execution', () => {
    assert.equal(isOrderConfirmationEnabled('false'), false);
    assert.equal(isOrderConfirmationEnabled('0'), true);
});
