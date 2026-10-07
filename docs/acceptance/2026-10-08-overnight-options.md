# Tonight options Paper acceptance continuation

User permits retained test positions and resting orders; do not flatten after every
phase merely to finish a turn. At Beijing 01:21 actual Paper reads confirmed QQQ
400 shares, SGOV 1000, option flat and no pending orders. Preserve these stocks.
Maximum actual short calls plus pending sells is four, subject to fresh server
coverage validation. Preferred QQQ Oct 16 2026 775 Call, conId 867924875. No CSP,
no naked calls, no Live writes or gate activation, no phone Run/install.

See options-live-readiness.md for completed tests and blockers. Remaining: protected
aggregate Trim implementation and verification; sustained partial fills of one
broker order; external actual fills/ownership races; isolated in-flight Gateway
interruption. Do not re-label already-tested client response loss or idle restart
as those cases. Never replay unknown writes. No test orders currently retained.

Automation wheel-paper checks this thread every 15 minutes through Beijing 04:00
2026-10-08. Check running scripts and journals first; never overlap trading tests.
At cutoff stop new tests, read and record any test holdings/orders/protection and
remove the automation. Retained test positions are permitted, but record their
exact broker identity and next step. Notify only substantive failures, required
user action, or stage completion; do not send routine progress notifications.

Current steering: native chart Add/Trim still used legacy scalable gate. Source has been updated to honor separate add_allowed / trim_allowed, with expected position
and captured group/contract identity. Simulator build passed; this is not device acceptance and no installation is authorized.

User reported stale stock average after adds: confirmed QQQ 400 shares while
entry remained the first 100-share price. Old completed parent has broker totals
but historical execution details are absent from the current session. When
complete execution reconstruction is unavailable, use IB position avgCost divided
by contract multiplier (includes fees), expose entry_source, and never silently
reuse the first fill. Invalid broker basis yields unknown/zero and rejects BE.
591 backend tests passed, including stock fallback, option multiplier, and invalid
cost. Mini deployed GitHub commit 5aa3c02; actual read-only Paper verification returned
QQQ position 400, entry 756.680103, entry_source broker_average_cost, exactly
matching portfolio avg_cost. No pending orders and no trading writes for this fix. Existing protection projections
with incomplete execution history remain unknown; no fabricated group P/L.

## External actual fill, 01:40 Beijing continuation

Isolated Paper client 178 sold one covered call and bought that exact one back;
both were confirmed Filled, all option orders terminal and no option position.
QQQ 400 / SGOV 1000 retained. Main backend correctly disabled Add/Trim against
the foreign position, but incorrectly advertised protection_manageable=true on
an old completed group. Existing write-side ownership validation already rejects
this mismatch; fixed the state/UI capability to apply ownership checks to all
groups, not only imported-position groups. 593 backend regressions passed.
Private evidence on Mini: /tmp/wheel-external-fill-evidence.jsonl. Deployed 449c3bc and repeated actual one-call foreign sale/buyback. Main state
now reports Add=false, Trim=false, protection_manageable=false with an explicit
position-outside-group reason. Both test executions filled, final option flat,
no pending orders; QQQ 400 and SGOV 1000 unchanged. This does not certify every
external fill race. Protected aggregate Trim, sustained partial fills and isolated
in-flight Gateway interruption remain outstanding.

## In-flight Gateway API TCP interruption

An isolated real Paper client 179 used the production PaperChart service and a
private journal. A loopback TCP relay forwarded the placeOrder frame to port4002,
then closed both socket directions before delivering the broker reply. Main
backend/client71 and Gateway session remained running. One covered far-limit call
was actually accepted; execute returned unknown as required. After reconnecting
client179, IB returned exactly one matching order, but request_status incorrectly
remained unknown: submit lacked a reconciliation branch for transport exceptions.
The test order was canceled by exact UUID ref, option flat and QQQ400/SGOV1000
unchanged. No replay. Evidence /tmp/wheel-gateway-cut-4743b670-034d-49e9-961b-1a7fa9685fc9 on Mini.

Fix resolves only a complete fresh working-order snapshot matching stored IDs,
request ref, account, contract, sides, types, quantities, prices and TIF. Missing
legs or changed prices remain unknown and no write is sent by recovery. 597
backend tests passed. Actual post-fix TCP-cut repetition pending.
