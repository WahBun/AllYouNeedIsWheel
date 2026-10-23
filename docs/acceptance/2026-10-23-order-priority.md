# Order admission and execution priority — 2026-10-23

## Evidence and problem

The deployed Mini and GitHub target `Ben/wheel-1.8` were verified at `7b310cf4a94ff7f2547f2e4f3ab4e614f9224cda`. REA inspected the existing dedicated Wheel page, without navigating or changing reference tabs (evidence `ev_ad046eeb85a8e1626694cbf20ea7396f3faa5b77f71278a163914c50e0d9223c`). Passive browser evidence confirms the current page/context; it does not reveal backend scheduling. Source inspection and an offline Flask reproduction establish that scheduling behavior.

The backend reserved one admission slot for writes but used a FIFO executor. A running read plus two waiting reads allowed an order write to enter, yet executed `GET, GET, GET, POST`. Reserving space therefore did not provide execution priority over already-queued history/status reads.

## Narrow change and guarantees

Keep the existing one-thread IB owner and existing admission limits (four jobs, at most three reads). Its executor now selects admitted state-changing HTTP requests before HTTP reads that have not started. The same reproduction executes `GET, POST, GET, GET`.

- Never interrupt the running job or execute IB work on another thread.
- Preserve FIFO among writes, including placement, amendment and cancellation. No automatic replay or write deduplication.
- Preserve the relative order of ordinary owner tasks and writes. Chart pumps, stream setup and background fill synchronization already ahead of a write remain ahead of it; they are not demoted behind a burst of orders. With no waiting write, the entire queue keeps FIFO behavior.
- Keep response futures, account/epoch guards, same-read sharing, admission rejection, unstarted-job expiry/cancellation and running-write acknowledgement behavior.
- Do not change price aggregation, SSE publication, chart layout, broker order logic, retry cadence or queue capacity.

The guarantee is limited to **admitted writes versus unstarted HTTP reads**. It is not immediate execution, preemption of an active broker request, guaranteed admission when writes fill all slots, or a broker acknowledgement deadline. An already-running history read or earlier owner synchronization may still delay a write.

## Verification

The pre-change Flask regression fails because the write runs fourth. After the change, it runs immediately after the in-progress read. Five additional executor tests cover write/owner ordering, unchanged FIFO without writes, canceled-write omission, exception recovery and shutdown cancellation. All execution uses one owner thread.

The broader offline run completed 77 tests: 73 passed. The four failures are existing `test_chart_history.BackgroundHistoryTests` cases (capacity, failed-read cooldown, late-page context and slow-page completion). Replacing the dispatcher with the exact unmodified formal version reproduced all four failures; no production history code changed here. They remain disclosed, not counted as passes. Dispatcher, request diagnostics, immutable latest quotes, stream capacity, initial history, request crash and order process-fault checks passed.

A controlled FIFO/current comparison queued the same two 100 ms reads, a chart pump and a write behind a held job. After release, FIFO write wait was 207–210 ms; the new scheduler's was 0.12–0.62 ms across 1/2/3/4/8 subscriber cases. Both preserved a 200-tick burst's high/low/close (120/80/100.199). These are synthetic scheduling measurements, not deployed trading latency promises.

The existing browser market-feed suites passed:

- `latency-matrix.cjs`: 1–4 panes, two four-pane pages, 5/10 Hz, 6,000-bar history and burst integrity.
- `interactions.cjs`: repeated layouts, symbol/period changes, disconnect/recovery, close/reopen and context isolation.
- `stress.cjs`: dense input for single/four/dual-four pages.
- `distinct-symbols.cjs`: eight distinct symbols across two four-pane pages.

Browser fixtures had zero trading writes, page errors or stream-capacity rejections. Their HTTP harness does not use the production Flask dispatcher; the separate Flask/executor checks cover that boundary. All test resources closed. No real broker order, deployed latency comparison or physical-device acceptance was performed in this task.

## Delivery boundary

No merge, deployment, service restart, Gateway restart or Release. After approval to deploy, choose **Deploy & Restart Backend** because the owner executor is instantiated at backend startup. No Gateway restart, web-asset refresh or iPhone Run is required for this backend-only change; clients must reconnect to the restarted backend normally. The independent history-retry and iOS-version PRs retain their own deployment requirements.
