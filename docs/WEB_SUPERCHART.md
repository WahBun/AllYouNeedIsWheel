# Web Superchart

`/superchart` hosts the same HTML, chart library and drawing JavaScript used by
iOS. The Flask frame route reads those files directly; do not copy them into a
second web implementation. `frontend/static/js/superchart.js` replaces native
bridge callbacks with browser controls and the existing Paper chart API.

The desktop view includes symbol/contract selection, intervals, RTH/ETH,
shared drawing tools, visible High/Low, preview and explicit Buy/Sell submission,
direct Join, price drag, quantity/TIF editor, TP/SL, cancel/Close, BE and scalable
position adjustments. Pending Orders and positions open the exact conId.
The sidebar shows operation outcomes and can copy a short diagnostic record.

Only a fresh verified Paper state enables writes. Account epoch and existing
backend checks remain authoritative. A UUID is persisted before sending a write;
uncertain outcomes are reconciled by GET, including after browser reload, never
replayed. Live is viewing-only. Native-only settings not yet represented by the
web settings dialog remain at chart defaults. Drawings/settings are browser-local
and do not replace the user's iPhone preferences.

## Local Pro preview

Run `ops/chart_preview.py --backend <Mini API base URL>` using the project Python
environment. It binds localhost:8765 and forwards only the required APIs. For a
Mini API bound to loopback, use an SSH local forward first. This starts no IB
connection, copies no database and changes no account configuration. Keep both
processes running while reviewing `http://127.0.0.1:8765/superchart`.

The preview uses two-second, non-overlapping snapshot polling. Broker fills and
actual market-session behavior still require Paper acceptance; browser fixtures
are not broker tests. iPhone installation remains deferred. The user approved GitHub publication and
Mini deployment after this round of verification.

## Verification

- `python -m unittest discover -s tests`
- `node tests/chart/web-superchart.cjs` (localhost preview required; all API calls mocked)
- `node tests/chart/drawing-timeframes.cjs`
- `node tests/chart/visible-extrema.cjs`

Browser tests cover explicit submit, edits with expected order identity, cancel,
Orders refresh, lost write response/reload with no replay, Live isolation and
393/850/1440px layouts. No broker writes are sent by these tests.


The interval menu supports star favorites persisted in the browser. Shift+F
switches fullscreen, and Cmd+Shift+S (Ctrl+Shift+S on other platforms) copies a
PNG of the chart with a success toast. Input fields do not trigger shortcuts.
The desktop context menu resets the viewport, stages price-aware Buy/Sell orders,
removes drawings, and copies the chart image; it does not submit orders itself.

Earlier bars load when the viewport approaches the left edge, using the existing
serialized IB connection and a bounded read-only history endpoint. Successful
pages are cached; recent polling is merged without discarding older bars. Empty
or failed pages can be retried after cooldown, rather than claiming the contract
has no more history. Browser caches hold at most 12 contexts / 20,000 bars each;
the backend keeps four active contract states with idle expiry and 64 cached
history pages. Live subscriptions and order configuration are not recreated on
Pro. Real broker history depth still depends on the contract and IB response.
