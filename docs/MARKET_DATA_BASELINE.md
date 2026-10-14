# Protected market-data baseline

The price/OHLC path is a foundation of the trading chart. Feature work should leave it alone by default. A necessary change must compare the same synthetic input against the prior baseline and run the matrix below. Preserve the current UI layout; do not add confirmation prompts to protect this path.

## Contract

- With incoming data, every visible pane in 1, 2, 3 and 4 pane layouts must update naturally several times per second. Visible inactive panes must not silently fall back to multi-second polling under the supported load.
- Test two pages with four panes each. Each page/account epoch shares one SSE transport with at most four distinct contexts. The process admits at most four transports, with eight queued packets per context. Excess capacity is explicitly rejected; do not remove bounds. Legacy single-context SSE clients remain supported. The underlying contract pool is separately capped at eight; an actively streamed contract must not be evicted to open a ninth. Closed/unsubscribed sources can be reclaimed.
- Aggregation consumes the accepted source ticks before display coalescing. Preserve open/high/low/close, supplied volume fields, historical corrections and the final value. Display frames may skip intermediate prices at input rates above the display cadence; aggregation may not skip their extremes.
- Send validated price deltas immediately to Lightweight Charts `series.update`; its own invalidation/rAF scheduler owns price drawing. Batch auxiliary configuration only, avoiding an extra animation-frame wait before price delivery.
- Never add a fixed quote throttle to meet a throughput target. The synthetic 5Hz, 10Hz and 100Hz cases are test inputs, not product refresh limits.
- Keep per-context sequence/snapshot recovery and account-epoch isolation. Late packets retain the epoch captured at subscription creation. A changed view may rebuild the bounded page transport and resnapshot; retained panes must stay visibly current in the interaction test.
- Keep IB operations on the existing serialized owner. SSE socket threads only drain bounded queues. A tick wakes the sender immediately; the idle heartbeat timeout is not a quote polling interval.
- Measure generated event → Python receipt → aggregation/packet → queue publication → socket push → browser event → chart apply → frame opportunity separately. Do not equate fewer render calls with lower latency, or requestAnimationFrame with physical screen presentation.

## Repeatable checks

From the repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python tests/run_chart_offline.py
npm run test:frontend
node tests/chart/stream-lifecycle.cjs
node tests/chart/volatility.cjs
```

Browser tools are installed separately; do not add them to the application environment. The verified baseline used official Playwright 1.64.0 and existing Chrome 154.0.8037.95 on an M5 MacBook Pro. Set the module and evidence directories explicitly:

```sh
export WHEEL_PLAYWRIGHT_MODULE=/absolute/path/to/isolated/node_modules/playwright
export WHEEL_EVIDENCE_DIR=/absolute/path/to/test-evidence
node tests/chart/market-feed/latency-matrix.cjs
node tests/chart/market-feed/interactions.cjs
node tests/chart/market-feed/stress.cjs
node tests/chart/market-feed/distinct-symbols.cjs
```

`WHEEL_CHROME` and `WHEEL_PYTHON` optionally override the existing browser executable and repository `.venv/bin/python`. The fixtures use temporary browser profiles, a loopback-only HTTP server, synthetic read-only endpoints and a fake broker. Browser requests outside that fixture origin are aborted, trading POSTs are rejected, and the Python worker prohibits network sockets and real IB construction. No production application factory is started. The `resources.jsonl` evidence records test ports and worker lifecycle; close all created resources in `finally`.

## Required matrix

| Area | Cases |
|---|---|
| Layout | 1/2/3/4 panes, repeated 1↔2↔3↔4, retained-pane updates, deletion/recreation, duplicate actions |
| Multiple pages | Two pages × four panes, both shared-symbol and eight-distinct-symbol workloads; every pane receives push; distinguish visible panes from hidden documents |
| Input | 5Hz and 10Hz sustained input, denser 100Hz stress, 200 source ticks in one callback with known extremes |
| Recovery | Disconnect/resnapshot, close/reopen, symbol/period changes, hidden/resume, old callback/epoch rejection |
| Bounds | Fifth transport rejected, max four contexts per transport, invalid/duplicate contexts rejected, slow-consumer resnapshot, unstarted/repeated/concurrent close releases once |
| Indicators | Long-history price latency; volatility formula, historical correction, RTH/DST, no lookahead; no repeated formatting of unchanged timestamps |
| Trading boundary | No broker writes or account access; keep UUID and unknown-state recovery tests passing |

## Recorded scope and limitations — 2026-10-11

The local mock/browser baseline passed 1–4 panes, two four-pane pages and interaction recovery. At 10Hz, steady visible-pane applied-update gaps were approximately 100–106ms in the measured dual-page run; no multi-second accumulation was seen. The measurement uses actual StockChart tick callbacks/packet aggregation, Subscriber delta construction and the real chart assets. The browser harness implements the HTTP fixture and is not the deployed Flask/IB queue, real network, exchange feed or physical-screen test. Actual Flask response admission/fairness/wakeup is covered separately by offline tests.

A 6000-bar test isolated repeat volatility date formatting and duplicate synchronous work before price application. The pre-fix source-to-chart-apply p95 was about 27ms; the cache/price-priority fix measured about 7ms on that machine. Keep raw distributions, workload and versions when comparing; these are not universal production guarantees. The earliest inspected introduction is 65572e3 (pre-price volatility work), with duplication added in ceda6f6. This does not prove either commit alone explains every user-observed slowdown.

Volume contract: historical `TRADES` bar volume is preserved in IB-reported units, with `volume_status=historical_snapshot`; zero and fractional values are retained. This is a broker snapshot, not an assertion of exchange completeness or finality. Never multiply by 100 without verifying the connection's volume-unit configuration. Distinct source bars aggregate only when all constituents have known snapshot volume. Unknown constituents produce `volume=null`, `volume_status=unknown`. Historical refreshes replace matching timestamps, not add to them. A price-tick bar or overlapping historical/live merge is explicitly unknown because the current feed has no history/live watermark or stable trade identity. `historical_volume`, when present on an individual bar, is only its prior snapshot, not its current total. Do not combine lastSize, daily cumulative volume, RTVolume and tick-by-tick sizes. Price/OHLC continues independently. This repairs discarded historical volume and false completeness; it does NOT certify complete real-time minute volume. See `tests/test_chart_volume.py` and the IB source links below. Hidden-document tests simulate visibility events; OS background-tab frame scheduling and physical-device behavior remain unverified. Live/Paper broker acceptance is separate and requires its own explicit scope.

## Existing chart engine and reference provenance

Wheel currently embeds TradingView Lightweight Charts 5.2.1 in
`ios/Wheel/ChartAssets/lightweight-charts.standalone.production.js`. Its license
header states Apache 2.0. Keep that license/attribution and the existing
`attributionLogo: true`; the separately authorized 5.2.0 → 5.2.1 patch upgrade preserves this engine and layout. Exact vendor provenance is recorded in `LightweightCharts-version.json`. The
inspected web/iOS code does not use Advanced Charts. `stock-chart.html` uses
`series.update` for tail deltas; `setData` is reserved for initial/new identity,
older-history insertion and historical correction.

Public Tradesea client evidence supports separate market/trading Workers, market
message coalescing, approximately 48ms worker batches, animation-frame state
submission and jittered reconnects. It does not establish its server guarantees
or a reusable software license. Wheel's bounded SSE page multiplexing and epoch
isolation are independently implemented adaptations, not copied Tradesea code.
The fixed 48ms delay was not adopted. Prefer the already licensed chart engine's
existing incremental API over another price-render scheduler.

Additional source-capacity finding: the former four-contract LRU pool (introduced
in 58773f4) silently evicted the first page's sources in an eight-distinct-symbol
mock run. The explicit eight-contract bound and active-subscription protection
fix that case without unlimited expansion. A ninth active source is rejected;
closing an unused chart permits reclamation. This is separate from SSE transport
capacity and must remain covered by the distinct-symbol regression.

Final same-clock paired run (millisecond wall-clock timestamps, 1ms resolution):
6000 bars at 10Hz measured price-apply p50/p95 25/39ms with the saved pre-fix
indicator path, versus 5/6ms after the fix. Volatility calculation p95 changed
from 12ms to 1ms. Earlier mixed-clock absolute timings that produced negative
values are invalid evidence and must not be used. Physical presentation latency
is not certified by these headless measurements.


Volume semantics checked against official IB documentation:
- https://www.interactivebrokers.com/docs/tws-api/doc/market-data-live/available-tick-types/volume-data
- https://www.interactivebrokers.com/docs/tws-api/doc/market-data-live/tick-by-tick-data/receive-tick-by-tick-data
- https://www.interactivebrokers.com/docs/tws-api/doc/market-data-historical/historical-data-limitations/historical-data-filtering
- https://www.interactivebrokers.com/docs/tws-api/doc/market-data-historical/historical-data-limitations/historical-volume-scaling

Local ib_async's wrapper stores receipt `lastTime` in TickByTickAllLast, rather
than the callback's exchange timestamp. No dependency or timestamp behavior was
changed in this batch. This further prevents claiming exact exchange-minute
volume reconstruction. A future implementation needs an explicit time/unit and
reconciliation contract, with separately authorized real-feed evidence.


## Proposed closed-minute volume repair (design only)

Use the existing authorized `TRADES` historical-bar facility for bounded reads of
recent closed minutes, not a new RTVolume or tick-by-tick subscription. Coalesce by
contract/generation on the existing serialized owner; one in-flight request per
contract, limited work per cycle and explicit pacing/backoff. Use asynchronous
owner-loop reads so quote callbacks can run; never insert history work before
immediate price delivery or duplicate an IB client. The current one-off backfill
is not sufficient to keep later closed minutes repaired.

After a grace period, use IB's returned bar timestamp and volume as a replaceable
historical snapshot for that closed minute. Do not sum it with Last sizes, interpolate
empty replies, infer zero, convert lots/shares without verified configuration, or
claim that a closed bar can never be revised. Preserve live OHLC; update volume-only
metadata and invalidate aggregate caches for affected historical buckets. Reject
stale generation/account replies. Missing, overlapping or incompatible-unit evidence
stays unknown. Repeated requests replace the same timestamp; a broker correction may
increase or decrease it. Reconnect must re-establish the source/unit context first.

Before implementing, mock pacing, timeout, duplicate/partial/empty/corrected replies,
old epochs and multiple closed buckets, then compare 1–4 and dual-page latency with
history work pending. Real-feed finality and units require the separately scoped
read-only Paper connection check. This proposal adds no subscription or scheduling
in the current code.

Optional same-owner synthetic reconciliation load is available via
`WHEEL_TEST_PENDING_ORDERS=1` for the browser fixtures. It runs eight cached fake
order-status checks before each tick callback; it does not simulate network waits,
production Flask dispatch, real journal I/O or a broker order write.

## Background browser coverage — 2026-10-14

`node tests/chart/market-feed/background-tabs.cjs` uses a temporary normal Chrome
profile and `connectOverCDP({noDefaults:true})` so Playwright does not force focus
or disable background throttling. It verifies native document visibility, four
panes and browser-title updates while hidden, reconnect/resnapshot while hidden,
foreground recovery and transport release on close. Market streams remain open
while the document is hidden. Browser/OS freezing or process suspension is outside
this short background-tab test; optional non-price work remains foreground-only.
