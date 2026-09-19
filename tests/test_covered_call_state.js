import test from 'node:test';
import assert from 'node:assert/strict';

import {
    getCoveredCallContracts,
    getCoveredCallOrderQuantity,
    mergeOptionResponse
} from '../frontend/static/js/utils/covered-call.js';

test('CALL refresh preserves the server covered-call capacity', () => {
    const current = { stock_price: 0, position: 0, calls: [], puts: [] };
    const quote = { strike: 105, bid: 3.9, ask: 4.15 };

    mergeOptionResponse(current, 'CALL', {
        stock_price: 92,
        position: 100,
        covered_call_capacity: 0,
        calls: [quote]
    });

    assert.equal(current.covered_call_capacity, 0);
    assert.deepEqual(current.calls, [quote]);
    assert.equal(getCoveredCallContracts(current), 0);
});

test('PUT refresh does not overwrite covered-call capacity', () => {
    const current = { covered_call_capacity: 0, calls: [{ strike: 105 }], puts: [] };

    mergeOptionResponse(current, 'PUT', {
        stock_price: 92,
        position: 100,
        puts: [{ strike: 80 }]
    });

    assert.equal(current.covered_call_capacity, 0);
    assert.deepEqual(current.calls, [{ strike: 105 }]);
    assert.deepEqual(current.puts, [{ strike: 80 }]);
});

test('covered-call capacity never exceeds owned shares', () => {
    assert.equal(getCoveredCallContracts({ position: 300, covered_call_capacity: 2 }), 2);
    assert.equal(getCoveredCallContracts({ position: 100, covered_call_capacity: 3 }), 1);
    assert.equal(getCoveredCallContracts({ position: 300, covered_call_capacity: 0 }), 0);
});

test('covered-call order quantity defaults to capacity and clamps user input', () => {
    const optionData = { position: 300, covered_call_capacity: 3 };

    assert.equal(getCoveredCallOrderQuantity(optionData), 3);
    assert.equal(getCoveredCallOrderQuantity(optionData, 2), 2);
    assert.equal(getCoveredCallOrderQuantity(optionData, 9), 3);
    assert.equal(getCoveredCallOrderQuantity(optionData, 0), 3);
    assert.equal(
        getCoveredCallOrderQuantity({ position: 300, covered_call_capacity: 0 }, 1),
        0
    );
});
