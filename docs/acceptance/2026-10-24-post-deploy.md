# Post-deployment acceptance — 2026-10-24

## Verified deployment

The user authorized Mini deployment after merging PR #64. GitHub confirmed
PR #64 merged into `Ben/wheel-1.8` at
`d5bf994e0464df389f0b8d259b76f3834e548f27`. This also includes the earlier
Paper acceptance report from PR #63.

The existing deployment helper verified the clean Mini checkout and GitHub
ancestry, retained a rollback branch at
`dd3777484b49eea2438da566878770cb6b9cfa4c`, fast-forwarded the checkout, and
requested one Backend restart. It confirmed the target SHA, a new Backend PID,
and healthy status. No Gateway restart or physical-phone operation was requested.

Post-restart read-only reconciliation confirmed the verified Paper session,
all six earlier test groups known and flat, zero pending orders, and the
pre-existing QQQ quantity unchanged at 200 shares.

REA inspected the existing dedicated browser and reloaded its QQQ four-pane
RTH page. Across the 40-second sample, all four panes advanced their tick counts
and OHLC values; the one-minute chart also advanced to a new candle. Trading
remained locked. This is deployed recovery evidence, not an A/B speed claim.
Evidence: `ev_58168b20652a61152b1cbd72801cf7b75e94a4550d7cee288809b28516cb8d8b`.

## Full-editor broker check

A fresh Paper test identity used the new Backend epoch. Initial cold quote
reads did not yet supply a valid quote expiry; the test made no trading write
until a subsequent read supplied valid bid, ask, tick rules and freshness.

One unfilled option limit entry was submitted. The actual web editor sent one
price-edit request containing unchanged quantity and TIF, changing 1.19 to 1.20.
The broker retained order ID 1869 and confirmed the new price. The page became
editable without another POST. The subsequent explicit cancellation completed
with no fill, no replacement, and no remaining order in that test group.

Evidence: `ev_c2bd3b994ff9cf1abce938888b54b16ae480f0f288b9cb8b7ff915558d8c6425`.
This validates the deployed normal amendment path. No lost-response timeout was
forced against the broker; the timeout/restart classification regressions remain
local evidence. The earlier slow-cancellation TIF limitation is not claimed fixed.

## Previously failing history checks

The four previously recorded `BackgroundHistoryTests` failures reproduced on
the merged baseline. They assumed one `asyncio.sleep(0)` completed both the
outer page task and the shared budget's shielded SDK task. Some assertions ran
before the mock request had even started.

The tests now wait for explicit mock-start events and the captured page tasks,
with bounded timeouts. The late-account/client case now changes context only
after the old request has actually started. Capacity, deduplication, continuing
tick delivery, cooldown, old-context rejection, and no-order-write assertions
remain intact. No runtime scheduling or market-data source changed.

All 11 history tests and five shared-budget tests pass, including the existing
nine-second slow-response case. `git diff --check` passes. These checks use mocked
broker responses and an isolated offline runner.

The initial follow-up at `80b1a8acd06aa20335f90435fe627d71c15f5e22`
changes tests and acceptance documentation only. That commit needs no
Backend deployment, restart, web refresh, or iPhone Run. If synchronizing these
files after merge, choose **Deploy only**. Unrelated local localization edits
remain excluded.

## Protection observation

A separate one-contract Paper entry filled at 2.79. Its TP at 3.01 and SL at
2.49 were confirmed by the broker, appeared in Orders with the same identities,
and retained matching chart labels. They were left unchanged for approximately
ten minutes. Neither order triggered naturally. The bounded test then explicitly
closed the position; the close filled, both protection orders were canceled,
and the group returned to zero position with no active orders.

This is actual protection creation, display, and manual-close synchronization
evidence. It is not natural TP/SL-trigger, partial-fill, or cancel/fill-race
acceptance. Those market events remain unobserved.

REA observations: `ev_a92d3c165f261dd4d0fc84216369572fcdddf21c976c69f4d0b662ef233758e9`
and `ev_8bd22851b44f9e0c3a00f8f392cf0fcccb6a55c79098cd7b3d7441c0fb0fc4e0`.

## TIF replacement and final reconciliation

A final independent one-contract limit order changed DAY to GTC through the
actual editor. Exactly one modification POST was observed. Original order 1899
was replaced by order 1902 at the same 1.32 limit price and quantity. Fresh
request-status reads confirmed the new reference; the chart and Orders list
both showed the replacement as Submitted/GTC. Its subsequent explicit
cancellation completed with no fill and no remaining order.

Evidence: `ev_db103972a4d88c6eb7a02d6da442f60ef9b2dc253ef03994a06ae2b0b2bef06b`.
This demonstrates successful TIF replacement when cancellation completes within
the existing wait. It does not erase the earlier slow-cancel observations or
attribute this success to PR #64, which did not change the replacement path.
No delayed replacement was automatically submitted.

Final read-only reconciliation confirmed all nine test groups known and flat,
zero pending orders, and only the original QQQ position at 200 shares. The clean
Mini checkout remained on the deployed SHA with no pending deployment marker.
The original locked QQQ four-pane RTH page was restored, evidence
`ev_943a02f7aa11f9417236050c97b98a07bd4277d416bce4d93fe458413d909621`.

A post-deployment diagnostic sample contained 1,186 completed HTTP responses.
Of 30 read 503s, 29 were immutable-latest snapshot misses and one was a history
queue rejection. One stream 400 occurred during startup, followed by successful
streaming recovery. These response counts do not establish an A/B improvement
or justify changing queue capacity. Raw logs, broker journals, account details,
and test manifests remain private and outside Git.
