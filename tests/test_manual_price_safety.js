import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source = fs.readFileSync(new URL('../frontend/static/js/dashboard/options-table.js', import.meta.url), 'utf8');
const context = vm.createContext({});
vm.runInContext('let manualLimitPrices = {};\n' +
    source.slice(source.indexOf('function getOptionPriceKey('), source.indexOf('function formatSpreadBadge(')) +
    source.slice(source.indexOf('function getRowLimitPrice('), source.indexOf('function getOptionFromRow(')), context);

test('cleared or invalid visible prices cannot silently fall back to the old midpoint', () => {
    for (const value of ['', '0', '-1', 'invalid']) {
        assert.equal(context.getRowLimitPrice({ querySelector: () => ({value}) }, 1.25), 0);
    }
    assert.equal(context.getRowLimitPrice({querySelector: () => ({value: '1.30'})}, 1.25), 1.30);
});

test('invalid manual edit remains explicit for Add All until reset', () => {
    const option = {strike: 10, expiration: '20261218'};
    context.setManualLimitPrice('TSLL', 'PUT', option, 0);
    assert.equal(context.getManualLimitPrice('TSLL', 'PUT', option), 0);
    context.clearManualLimitPrice('TSLL', 'PUT');
    assert.equal(context.getManualLimitPrice('TSLL', 'PUT', option), null);
});
