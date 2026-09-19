import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source = fs.readFileSync(new URL('../frontend/static/js/dashboard/account.js', import.meta.url), 'utf8');
const polling = source.slice(source.indexOf('async function refreshLivePositions()'), source.indexOf('/**\n * Load portfolio data'));

function setup() {
    let now = 0;
    let calls = 0;
    let finish;
    const timers = new Map();
    let id = 0;
    const document = { hidden: false, getElementById: () => ({}) };
    const context = vm.createContext({
        document, performance: { now: () => now }, console: { error() {} },
        window: {
            setTimeout(fn, delay) { timers.set(++id, { fn, delay }); return id; },
            clearTimeout(key) { timers.delete(key); }
        },
        fetchLivePositions() { calls++; return new Promise((resolve, reject) => { finish = { resolve, reject }; }); },
        applyLivePositions: () => true, updateLivePositionStatus() {}
    });
    vm.runInContext(`let liveRefreshTimer = null, liveRefreshPromise = null;
        let liveRefreshEnabled = false, liveRefreshStartedAt = 0, liveRefreshFailures = 0;
        const LIVE_REFRESH_INTERVAL_MS = 2000;\n${polling}`, context);
    return {
        context, timers, document, calls: () => calls,
        async complete(at, fail = false) {
            now = at;
            fail ? finish.reject(new Error('offline')) : finish.resolve({ positions: [] });
            await new Promise(resolve => setImmediate(resolve));
        },
        fire() { const [key, timer] = timers.entries().next().value; timers.delete(key); now += timer.delay; void timer.fn(); }
    };
}

test('subtracts request time and repeated focus does not start extra requests', async () => {
    const s = setup();
    s.context.startLivePositionUpdates();
    s.context.startLivePositionUpdates();
    assert.equal(s.calls(), 1);
    await s.complete(300);
    assert.equal([...s.timers.values()][0].delay, 1700);
    s.context.startLivePositionUpdates();
    assert.equal(s.calls(), 1);
    s.fire();
    assert.equal(s.calls(), 2);
    assert.equal(s.timers.size, 0);
});

test('slow responses skip catch-up and stop during a request cannot restart polling', async () => {
    const s = setup();
    s.context.startLivePositionUpdates();
    await s.complete(2700);
    assert.equal([...s.timers.values()][0].delay, 2000);
    s.fire();
    s.context.stopLivePositionUpdates();
    s.document.hidden = true;
    await s.complete(5000);
    assert.equal(s.timers.size, 0);
    s.document.hidden = false;
    s.context.startLivePositionUpdates();
    assert.equal(s.calls(), 3);
    await s.complete(5200);
    assert.equal(s.timers.size, 1);
});

test('failures back off and successful requests restore the normal cadence', async () => {
    const s = setup();
    s.context.startLivePositionUpdates();
    await s.complete(100, true);
    assert.equal([...s.timers.values()][0].delay, 2000);
    s.fire();
    await s.complete(2200, true);
    assert.equal([...s.timers.values()][0].delay, 4000);
    s.fire();
    await s.complete(6300, true);
    assert.equal([...s.timers.values()][0].delay, 8000);
    s.fire();
    await s.complete(14400);
    assert.equal([...s.timers.values()][0].delay, 1900);
});
