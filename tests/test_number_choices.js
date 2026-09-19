import test from 'node:test';
import assert from 'node:assert/strict';
import { numberChoices } from '../frontend/static/js/utils/number-choices.js';

test('integer choices respect OTM and covered quantity limits', () => {
    assert.deepEqual(numberChoices(1, 1, 3), ['1', '2', '3']);
    assert.deepEqual(numberChoices(0, 0, 0), ['0']);
    assert.equal(numberChoices(10, 1, 50).length, 50);
});
test('price choices advance in exact cents around the current price', () => {
    const choices = numberChoices(0.62, 0.01, Infinity, true);
    assert.equal(choices[0], '0.42');
    assert.equal(choices.at(-1), '0.82');
    assert(choices.includes('0.62'));
    assert(!numberChoices(0.01, 0.01, Infinity, true).includes('0.00'));
    assert.deepEqual(numberChoices('', 0.01, Infinity, true), []);
    assert.deepEqual(numberChoices('NaN', 0.01, Infinity, true), []);
});
