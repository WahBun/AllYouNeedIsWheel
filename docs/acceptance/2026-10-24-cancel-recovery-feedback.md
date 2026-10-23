# Canceled replacement feedback — 2026-10-24

## Evidence and repair

Continued from deployed `Ben/wheel-1.8` commit
`d5bf994e0464df389f0b8d259b76f3834e548f27` and the post-deployment report.
REA verified the same dedicated Wheel target remained available. The earlier
actual late-cancel observation showed `Reconciled: canceled`; the later normal
TIF replacement succeeded. These are different broker outcomes.

The late-cancel recovery response previously carried only `canceled`. It now
also reports: `Original entry canceled. No replacement order was submitted.`
The message is saved with that exact request's reconciled result and survives
subsequent reads or a Backend restart. Explicit cancellation and successful
replacement responses retain their existing semantics.

Web automatic reconciliation and Check order status display the returned
message. The native chart receives it once from its exact pending request,
checks task/contract/group context, and displays it before the following state
read so a transient read failure cannot swallow the confirmed result.

No broker write, cancellation deadline, replacement continuation, queue,
market-data delivery, One-click or Confirm/Discard behavior changes. Slow
cancellation can still end without a replacement; this repair makes that result
explicit rather than presenting generic recovery as completion of the edit.

## Validation and delivery

The late-cancel regression failed before the repair. The entry-edit,
order-status and process-fault suites pass 45 checks, including restart
persistence, OVT cancellation, exact identity and no automatic replay.
The browser fixture covers normal and late-cancel recovery in Paper and Live
modes at desktop/mobile sizes in light/dark themes, with no broker connectivity or automatic writes.
Six native simulator checks pass, covering pending-request recovery after client restart,
one-time delivery of the message, isolation, and flat-history recovery.

These are local/mock checks. No further Paper orders, deployment, Gateway
restart, or physical-iPhone operation was performed in this supplement.
After merge, choose **Deploy & Restart Backend** and refresh the web page.
The native display change requires a user-operated iPhone Run/install.
iOS remains 1.8.1 (2); the installed phone version was not inspected or changed.
