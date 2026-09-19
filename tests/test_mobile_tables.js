import test from 'node:test';
import assert from 'node:assert/strict';
import { decorateTradingTables } from '../frontend/static/js/mobile-tables.js';

function classes() {
    const values = new Set();
    return { add: value => values.add(value), contains: value => values.has(value),
        toggle: (value, enabled) => enabled ? values.add(value) : values.delete(value) };
}
function fixture() {
    const headers = ['Symbol', 'Limit Price', 'Actions'].map(textContent => ({textContent, dataset: {}}));
    const button = {id: 'existing-execute-button'};
    const cells = headers.map((_, index) => ({
        colSpan: 1, dataset: {}, classList: classes(),
        querySelector: () => index === 2 ? button : null
    }));
    const row = {cells, classList: classes()};
    const table = {tHead: {rows: [{cells: headers}]}, tBodies: [{rows: [row]}], classList: classes()};
    return {root: {querySelectorAll: () => [table]}, cells, headers, row, table, button};
}
test('mobile layout labels original cells without replacing trading controls', () => {
    const f = fixture();
    decorateTradingTables(f.root);
    assert.equal(f.cells[0].dataset.mobileLabel, 'Symbol');
    assert(f.cells[0].classList.contains('mobile-identity'));
    assert(f.cells[2].classList.contains('mobile-actions'));
    assert.equal(f.cells[2].querySelector('button'), f.button);
    assert(f.table.classList.contains('mobile-records'));
});
test('translated headings refresh and spanning empty/group rows have no wrong labels', () => {
    const f = fixture();
    decorateTradingTables(f.root);
    f.headers[0].textContent = '代码';
    decorateTradingTables(f.root);
    assert.equal(f.cells[0].dataset.mobileLabel, '代码');
    assert(f.cells[0].classList.contains('mobile-identity'));
    f.cells[0].colSpan = 3;
    f.row.cells = [f.cells[0]];
    decorateTradingTables(f.root);
    assert(f.row.classList.contains('mobile-spanning-row'));
    assert.equal(f.cells[0].dataset.mobileLabel, '');
    assert(!f.cells[0].classList.contains('mobile-identity'));
});
