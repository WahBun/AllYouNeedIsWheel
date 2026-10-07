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

Post-fix actual TCP-cut verification PASSED on 6e704b4. The relay forwarded the
single order, withheld broker replies for 150ms, then closed both TCP directions
while execute was still waiting. execute returned unknown; reconnecting client179
and request_status (GET-equivalent read path) returned confirmed/reconciled against
exactly one original broker order. No resubmit. Exact test order canceled, no
pending orders or option position; QQQ400/SGOV1000 retained. Evidence on Mini:
/tmp/wheel-gateway-cut-ea38f9d2-b5be-4c12-9602-0ab0bfa914fe.
An earlier immediate-cut repetition returned no matching open order; it stayed
unknown with no replay and no position/open orders, correctly not claimed as an
accepted-order recovery pass. Evidence /tmp/wheel-gateway-cut-1349aaa9-0ede-45b3-954e-c1b9485b0a57.
Scope: real isolated client-to-Gateway transport interruption using production
PaperChart code/private journal, not a full Gateway process kill or every action
(amend/cancel/partial bracket transmission). Main backend remained connected.

## CURRENT retained test position (02:00 Beijing)

Do not start another flat-position test or deploy over active order management.
QQQ call conId867924875 now has -2 test contracts, average execution 1.50,
ref WheelPaper:eac5a507-84a2-4384-bf74-6c224bbe3924. Entry IDs1658/1659
both filled one. These are TWO separate parents, not a single parent's partial
fill; partial-fill acceptance is NOT passed. Initial response uncertainty resolved
by read-only request status. No original request was replayed.
Retained for protected aggregate Trim work, as authorized. TP1660 BUY2 at0.50,
SL1661 BUY2 at3.50, both PreSubmitted and state covered at last read. QQQ400 shares
cover both calls; user stocks preserved. Re-read broker state before any mutation.
Next: implement safe protected aggregate Trim accounting, then verify against this
exact group; do not generate more entries just to recreate it. Private evidence:
/tmp/wheel-partial-observe.jsonl and /tmp/wheel-partial-observe-retained.json on Pro.

## 02:07 Beijing: latest state supersedes retained-position note

User requested immediate real partial-fill acceptance. Used existing aggregate
BUY2 TP1660 instead of adding exposure. At1.49 it remained unfilled; new explicit
amendment to current bid1.66 filled both. Observations never showed filled1 /
remaining1, so single-order partial acceptance remains NOT passed. TP1660 Filled2,
SL1661 Cancelled, option position0. Pending-order read and stock preservation were
checked separately. No retained test option position now; do not assume -2 remains.
Evidence on Pro /tmp/wheel-partial-exit.jsonl and /tmp/wheel-partial-exit-latest.json.
Automation wheel-paper was deleted at user request; continue only in this thread.
