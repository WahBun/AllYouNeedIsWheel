# MNQ tick refresh investigation — local 1.5

Scope: passive Tradesea observation through REA/CDP, existing IB market-data reads, local frontend changes and mocked/replay tests. No deployment, orders, broker configuration changes or Mini restart.

## Findings

REA identified four MNQZ6 charts and a dedicated market-data worker. Public worker source uses a 48 ms bounded message coalescing window. Temporary CDP measurement of that worker observed 105 total market batches and 59 bar-containing batches in a 20-second comparison window. Total batch gaps had median 152 ms and p95 450 ms. These are worker deliveries, not physical screen paint times or guaranteed exchange ticks. Instrumentation was restored after measurement.

Wheel's same-window browser sample received roughly 31–33 events per pane, with median gaps around 537–551 ms and p95 around 1.2 seconds. Events include heartbeats/snapshots, so they are not equivalent to candle changes. IB tick counts increased by 116 while only about 19 single-bar price increments were delivered. Most receive-to-packet deltas were 0–10 ms. This places the dominant observed delay before browser rendering; it does not distinguish broker-side batching from owner-loop scheduling. Cross-host absolute timestamps are not calibrated latency measurements. Tradesea and IB are different feeds.

Read-only SSH confirmed Mini clean at 9f0f6002. Recent logs (597 jobs) had queue median/p95/max 1.4/15.8/1499.5 ms and work median/p95/max 3.3/16.1/1481.2 ms. Logs have no per-tick arrival instrumentation; occasional long jobs are plausible contributors but cannot establish the cause of every slow update. The existing 120-second stream renewal can also produce a reconnect gap. Neither backend behavior was changed.

## Local change

Cache immutable New York calendar-day identities used by EMA and FVG calculations in the shared chart asset, bounded to 24,000 timestamps per iframe. No changes to indicator formulas, OHLC aggregation, subscriptions, SSE pacing or trading logic.

An isolated, network-disabled replay of identical captured MNQ history and 100 tail updates reduced per-pane calculation p95 from 0.6–2.3 ms to 0.2–0.6 ms, with matching final OHLC. This reduces browser work but does not solve upstream half-second delivery cadence.

## Validation

- Frontend unit suite: 53 passed, including timezone/DST, bounded cache, EMA/FVG parity and historical correction coverage.
- Offline backend regression: 168 passed.
- Same-load 1–4 panes, two pages of four panes, 6,000-bar history: passed before/after.
- 100 Hz stress, distinct symbols, stream lifecycle, volatility, ATR, chart interactions and disconnect recovery: passed.
- EMA browser test fails its collapse bridge assertion on both baseline and changed versions. Numeric EMA parity passes; this existing UI assertion remains unresolved.
- git diff whitespace check passed.

Optimized local preview opened in Chrome with four live MNQZ6 market-data panes, preserving 5/1/15/60-minute periods. Local proxy blocks all writes and only forwards allowlisted market-data reads. Old preview tab closed. Production remains unchanged.

## Evidence

REA Tradesea evidence: ev_cd27f893fc64150e172d8570bc45c68ff69352a878512c9c3d30f6e308feff8a.
Temporary local evidence: /tmp/wheel15-tradesea-rea.json, /tmp/tradesea-worker-measure.json, /tmp/wheel15-ib-preview/refresh-before.json, /tmp/wheel15-ib-preview/render-replay-comparison.json. Temporary files are not durable release artifacts.

## Follow-up: locating the upstream delay and removing lease-renewal backoff

This follow-up supersedes the earlier uncertainty between Mini processing and upstream delivery for the sampled periods. It does not prove that IB intentionally imposes a fixed update interval.

### Passive runtime observations

No deployed code, Gateway configuration, account setting, broker identity or running service was changed. Existing Gateway packets were observed through a bounded passive packet socket inside its container. Only packet timing/length and tick-by-tick market fields were retained; no raw payload, credentials or order/account messages were stored. A separate read-only SSE observer reused the existing MNQ subscription. No additional IB client was constructed.

- First 35-second capture: Gateway outgoing Last-trade bursts had median spacing **530 ms**, p95 **1,223 ms**, maximum **5,782 ms**. A burst is an analysis grouping separated by more than 20 ms, not a product throttle. This batching was already present before Wheel's API owner received it.
- Approximate matched Gateway-to-Wheel receipt delays: median **6.4 ms**, p95 **30.6 ms** (36 matches). Mini-side publication-to-local-SSE-reader: median **4.3 ms**, p95 **10.9 ms**. Later clock checks placed container time about 1.37 ms behind Mini, with best calibration round trips about 0.28 ms; these are approximate cross-clock correlations, not exact per-trade latency guarantees.
- A second 25-second capture reproduced outgoing Last-trade burst spacing: median **502 ms**, p95 **955 ms**. Of 51 trade bursts, 49 followed a packet on the active encrypted IB upstream flow within 20 ms (median 1.6 ms, p95 12.8 ms). The upstream flow's complete sample had packet-gap median **386 ms**; it carries more than just trade messages, so this must not be equated to a trade cadence. The earlier roughly 500 ms upstream packet estimate was from a partial sample.
- Encrypted upstream traffic was not decoded. Nearest-packet association is timing correlation, not proof of its contents. Capture reassembly reported gaps, so this is not a completeness/count audit. Bursts and price timing remain useful evidence; missing records must not be interpreted as missing broker trades.
- Container CPU had no configured quota and zero throttled periods. Its TCP receive queues were empty at inspection. The Mini code remained clean at `9f0f6002`; the original service processes remained running.

**Conclusion:** in these samples, the dominant half-second cadence existed on the Gateway/upstream side, rather than being introduced by Wheel's chart rendering or normal Mini processing. The occasional long API jobs observed earlier are a separate possible contributor to pauses; they do not explain the observed Gateway output cadence.

### Network follow-up — improvement remains possible

The active MNQ upstream flow maps to the higher-latency IB connection. Host-side TCP statistics showed approximately **223–241 ms RTT**. During an 18-second incremental sample it received **82,484 bytes**, with **17,514 bytes recorded out of order**, no duplicate bytes, and no locally retransmitted bytes in that window. Local transmit-retry counters do not establish whether the remote sender retransmitted. Other IB connections had much lower RTT but serve different connections; they are not interchangeable market-data endpoints.

The container's sub-millisecond TCP RTT measures Docker's local TCP boundary and must not be presented as internet RTT. Host socket inspection showed direct IB destination sockets, not connections to the system proxy's loopback ports; this does not exclude interception farther along the network route.

Three no-protocol TCP connection probes to the observed endpoint measured direct connect times of **211–221 ms**. The existing local SOCKS proxy acknowledged connections in **1–4 ms**, which is too early to establish remote end-to-end latency; this is **not evidence that switching Gateway to that proxy will accelerate data**. Probes sent no IB protocol, login or account messages and did not alter the running connection.

Network latency and reordering are plausible contributors. The current evidence cannot separate IB farm batching from the internet/router path with certainty, nor attribute each half-second batch to reordering. Improving the upstream route may help, but must be validated with actual same-feed delivery measurements. No route, proxy, data-farm selection or Gateway setting was changed under the no-deployment scope. Client-side interpolation or replaying old prices would only create an appearance of motion and was not introduced.

### Local repair

The existing server retires each chart transport after 120 seconds. Previously its normal EOF took the same failure/backoff path as a broken network, adding an unnecessary retry wait.

- On planned lease expiry the server now wakes the sender, releases its bounded admission slot, and emits an explicit `renew` control event.
- The page immediately replaces its shared four-context transport. Per-pane sequences reset and the replacement must begin with a snapshot. Late callbacks, old account epochs, malformed packets and genuine failures retain their existing rejection/backoff behavior.
- No price throttle, interpolation, extra IB owner, subscription-cap increase or trading change was introduced. This backend change is **local only**; the real-data preview still reads the unchanged Mini backend and cannot demonstrate the new server renewal event until a separately authorized deployment.

### Validation

- Frontend: **55 tests passed**. Offline backend: **171 tests passed**, with broker construction, real network and persistent database access prohibited.
- Added checks for planned expiry wakeup, admission release before reconnect, exactly-once release, genuine-close behavior, four-context renewal, stale callbacks, stop-during-renewal and snapshot-first validation after renewal.
- Paired four-chart browser fixture: old renewal acquired all replacement snapshots in **1,072–1,075 ms**; repaired runs took **2–5 ms**. These are isolated synthetic loopback results, not claimed real-IB or screen-presentation latency.
- Same-load 1–4 panes, two four-pane pages and 6,000-bar history passed before and after. Price-apply p95 remained in the millisecond range (before 2–8 ms; after 2–9 ms), with no material steady-state throughput improvement claimed.
- 100 Hz stress, eight distinct symbols, repeated layouts, contract/period changes, disconnect/recovery, close/reopen and epoch isolation passed. OHLC extremes and final values were retained; trading POST count remained zero. Stream lifecycle and whitespace checks passed.
- The prior unrelated EMA collapse-bridge browser failure remains documented above; it was not changed in this follow-up.

Evidence files for this follow-up (temporary local files): `/tmp/wheel-gateway-passive.jsonl`, `/tmp/wheel-mini-direct-sse-2.jsonl`, `/tmp/wheel-gateway-upstream.jsonl`, `/tmp/wheel-upstream-summary.json`, `/tmp/wheel-ib-host-network.csv`, `/tmp/wheel-route-probe.json`, `/tmp/wheel-renew-before/after-results.json`, `/tmp/wheel-renew-after/after-results.json` and `/tmp/wheel-renew-*.log`.

Reproduce the isolated renewal comparison with `tests/chart/market-feed/renewal.cjs`; set `WHEEL_EXPECT_SLOW_RENEW=1` only when running it against the saved pre-change baseline. Other required cases use the commands in `docs/MARKET_DATA_BASELINE.md`.
