import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source = fs.readFileSync(new URL('../frontend/static/js/notifications.js', import.meta.url), 'utf8');
const settle = () => new Promise(resolve => setImmediate(resolve));

function harness() {
    function element() {
        return {
            children: [], dataset: {}, style: {}, setAttribute() {},
            append(...nodes) { this.children.push(...nodes); },
            prepend(node) { this.children.unshift(node); },
            replaceChildren() { this.children = []; },
            get childElementCount() { return this.children.length; },
        };
    }
    const grid = element(), requests = [], heard = [], window = {wheelAlertSounds: {play: sound => heard.push(sound), cancel() {}}};
    const document = { hidden: false, head: element(), getElementById: () => grid,
        createElement: element, addEventListener() {} };
    let poll;
    vm.runInNewContext(source, {
        window, document,
        AbortSignal, setInterval: callback => { poll = callback; }, setTimeout() {}, clearTimeout() {},
        fetch: (url, options) => new Promise(resolve => requests.push({ url, options,
            reply: (data, status = 200) => resolve({ ok: status === 200, json: async () => data }) })),
    });
    return { set: window.WheelNotifications.setContext, poll: () => poll(), requests,
        cards: () => grid.children[0].children, heard, document };
}

test('notification reads carry their originating epoch and reset the cursor on reconnect', async () => {
    const h = harness();
    h.set({ verified: true, account_identity: 'paper', epoch: 'first' });
    assert.equal(h.requests[0].options.headers['X-Wheel-Account-Epoch'], 'first');
    h.requests[0].reply({ scope: 'paper', cursor: 12, events: [] });
    await settle();
    h.set({ verified: true, account_identity: 'paper', epoch: 'second' });
    assert.equal(h.requests[1].url, '/api/notifications/events');
    assert.equal(h.requests[1].options.headers['X-Wheel-Account-Epoch'], 'second');
    h.requests[1].reply({ scope: 'paper', cursor: 20, events: [] });
    await settle();
    h.poll();
    assert.equal(h.requests[2].url, '/api/notifications/events?after=20');
});

test('fresh price events sound once in background; history, old catch-up and order events stay silent', async () => {
    const h = harness();
    const event = (id, kind = 'price', created = 99) => ({ id, kind, created, sound: 'hand-bell', title: id, body: 'Test' });
    h.set({ verified: true, account_identity: 'paper', epoch: 'first' });
    h.requests[0].reply({ scope: 'paper', cursor: 1, server_time: 100, events: [event('initial')] });
    await settle();
    assert.deepEqual(h.heard, []);
    h.document.hidden = true;
    h.poll();
    h.requests[1].reply({ scope: 'paper', cursor: 2, server_time: 100, events: [event('fresh')] });
    await settle();
    assert.deepEqual(h.heard, ['hand-bell']);
    h.poll();
    h.requests[2].reply({ scope: 'paper', cursor: 5, server_time: 100,
        events: [event('fresh'), event('old', 'price', 20), event('fill', 'fill')] });
    await settle();
    assert.deepEqual(h.heard, ['hand-bell']);
});

test('late notification responses cannot survive a reconnect or an account round trip', async () => {
    for (const roundTrip of [false, true]) {
        const h = harness(), profile = { verified: true, account_identity: 'paper', epoch: 'first' };
        h.set(profile);
        h.requests[0].reply({ scope: 'paper', cursor: 1, events: [] });
        await settle();
        h.poll();
        if (roundTrip) {
            h.set({ verified: true, account_identity: 'live', epoch: 'live' });
            h.set(profile);
        } else {
            h.set({ ...profile, epoch: 'second' });
        }
        h.requests[1].reply({ scope: 'paper', cursor: 2,
            events: [{ id: 'late', title: 'Old account', body: 'Must be discarded' }] });
        await settle();
        assert.equal(h.cards().length, 0);
        h.poll();
        assert.equal(h.requests[2].url, '/api/notifications/events');
        h.requests[2].reply({ scope: 'paper', cursor: 3, events: [] });
        await settle();
        h.poll();
        h.requests[3].reply({ scope: 'paper', cursor: 4,
            events: [{ id: 'fresh', title: 'Current account', body: 'New event' }] });
        await settle();
        assert.equal(h.cards()[0].dataset.eventId, 'fresh');
    }
});
