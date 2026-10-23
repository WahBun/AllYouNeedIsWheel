# Read-queue investigation — 2026-10-23

## Evidence and attribution

Investigated the 40 `ib_queue_full` events from the ETH Paper acceptance, on deployed `Ben/wheel-1.8` commit `7b310cf4a94ff7f2547f2e4f3ab4e614f9224cda`. The current dedicated Wheel target was inspected again with REA. Investigation used existing Mini logs read-only; no new broker order, deployment, or restart was performed.

Joined diagnostic request IDs to their API route, IB job start/end and arrival timestamps. All 40 rejected requests were GETs. Cold latest-snapshot 503s were excluded.

| Running HTTP job at rejection | Rejections |
| --- | ---: |
| Order POST | 9 |
| Order-state GET | 16 |
| P&L GET | 4 |
| Pending-orders GET | 3 |
| EMA GET | 2 |
| Account profiles GET | 1 |
| No running HTTP job identifiable at that instant | 5 |

The dispatcher admits three read jobs and reserves a fourth slot for writes. In the identified cases, running/queued reads occupied the read allowance. For the remaining five, HTTP logs show queued reads but do not individually timestamp the background synchronization job or slot-release callback; attributing each to a particular background function would exceed the evidence.

The longest measured order POST occupied the serialized worker for 5.584 seconds. Subsequent reads waited as long as 6.103 seconds in that burst. These operations ultimately reconciled in the earlier broker acceptance. The investigation does not establish that the order waits themselves are erroneous, and does not shorten them, change the reservation, add concurrency, or enlarge the queue.

## Confirmed defect and narrow repair

`chart-layout.js` used the same 500 ms pause for a successful background-history `loading` response and for a queue-busy rejection. The dispatcher explicitly returns `Retry-After: 2` for queue admission failures. The history client therefore retried four times as often as intended while the queue remained busy.

Access-log context distinguishes simultaneous panes from actual retries: the 15-minute request at 13:50:28 was a different context, while the 5-minute requests at 13:50:28.582 and 13:50:29.122 had the same contract, ETH session and `before` value. The latter is a confirmed repeat after about 540 ms. The four history rejections are not all claimed to be repeats of one request.

Repair: wait 2 seconds only after `retryableReadBusy` in the shared historical-page reader. Keep successful loading polls at 500 ms and retain the existing abort signal, account/context checks and overall timeout. Both active and companion panes use this reader. No quote delivery, layout, indicator calculation, order write/reconciliation, backend admission, or iOS code changes.

## Validation

- Same offline 1.8-second busy window: baseline produced four busy responses at approximately 0/503/1006/1510 ms. The repaired page produces one busy response and retries after approximately 2 seconds.
- The focused real-browser fixture covers single/four-pane pages, unchanged successful-loading polling, continuing synthetic SSE updates on every pane, and cancellation of the obsolete history context during backoff. All API writes are forbidden by the fixture.
- Existing slow-history test: a 17-second loading response remains polled and applied without a new 30-second gap.
- Existing four-pane RTH history admission test: exactly three recent seeds, preserved viewport and manual earlier-history loading.
- `git diff --check` passes. Local pre-existing translation-catalog changes are excluded.

These are offline regression results, not deployed performance measurements. The change reduces one proven source of avoidable retry pressure; it does not claim to eliminate all 40 busy responses. Remaining transient read contention and actual deployed behavior require later observation after an authorized update.

## Deployment scope

No deployment or restart performed. For this JavaScript-only fix, use **Deploy only** when authorized, then reload the web page. No backend/Gateway restart or iPhone Run is required for this fix. The separate iOS version-label PR has its own user-operated Run requirement.
