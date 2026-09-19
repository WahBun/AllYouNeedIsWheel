import test from 'node:test';
import assert from 'node:assert/strict';
import { annualizedPremium, daysToExpiration } from '../frontend/static/js/utils/earnings.js';

const now = new Date('2026-09-20T12:00:00Z');
test('monthly premium uses actual days instead of 52 repetitions', () => {
    assert.equal(daysToExpiration('20261016', now), 26);
    assert.equal(annualizedPremium([{ premium: 100, expiration: '2026-10-16' }], now), 100 * 365 / 26);
});
test('mixed expirations are annualized individually', () => {
    assert.equal(annualizedPremium([
        { premium: 100, expiration: '20260927' },
        { premium: 200, expiration: '20261016' }
    ], now), 100 * 365 / 7 + 200 * 365 / 26);
});
test('invalid, expired, same-day and missing expirations do not manufacture annual returns', () => {
    for (const expiration of ['20260230', '20260919', '20260920', '', null]) {
        assert.equal(annualizedPremium([{ premium: 100, expiration }], now), null);
    }
    assert.equal(annualizedPremium([], now), 0);
    assert.equal(annualizedPremium([{ premium: 0, expiration: '' }], now), 0);
});
test('exchange date remains correct at Asian midnight and across DST', () => {
    assert.equal(daysToExpiration('20260920', new Date('2026-09-20T01:00:00Z')), 1);
    assert.equal(daysToExpiration('20261102', new Date('2026-10-31T12:00:00Z')), 2);
});
