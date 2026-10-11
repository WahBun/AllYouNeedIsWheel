# Next stage: IB order workflow acceptance

Goal: clear, responsive order status with recoverable failures and fewer repeated user actions, using the existing layout. Public Tradesea evidence establishes a separate trading Worker and client reconnect handling; it does not establish server-side idempotency, reconciliation or transaction guarantees. Reuse openly licensed components only after identifying their license. REA static evidence is not a license or access to proprietary backend code.

No Live enablement or real order is authorized by these mock tests. A target date is not an acceptance result.

| Workflow | Required behavior | Offline fault cases | Remaining broker/device acceptance |
|---|---|---|---|
| Submit | Stable UUID/payload identity; queued, sent and confirmed distinguishable | Duplicate tap/request; timeout before start; crash after claim, partial bracket send and final send; same UUID/different payload | Paper submit and acknowledged state, then app restart |
| Modify | Same broker identity or explicit replacement relationship; original terms remain visible until confirmed | Stale edit, partial fill during edit, changed quantity/price/TIF, late ack, missing ack | Exact contract/quantity/price/TIF, replacement ownership |
| Cancel | Pending cancel remains nonterminal until broker confirms; fill wins when observed | Duplicate cancel, fill/cancel race, disconnection after request | Working and partially filled order cancellation in bounded Paper scope |
| Partial fill | Cumulative quantity and remaining size are consistent; execution IDs deduplicate | Duplicate/out-of-order execId, repeated status snapshots, missing fill history | Multiple fills, fees and positions reconcile |
| Unknown | Lock uncertain action; preserve original UUID; never silently re-send | Lost response; persistent journal recovery; operator read-only status query; late request tombstone | Reconnect recovers actual broker result without extra order |
| Reconnect/status | Authoritative reads update state and stale indicators; no write retry | Network drops at each boundary, process SIGKILL/restart, old account epoch, concurrent status callbacks | Gateway reconnect and device foreground/background |
| UI feedback | Status remains explicit; action availability follows evidence; layout retained | Double tap, slow response, stale panel, close/reopen | Web/iOS interaction and Paper/Live isolation gates |

Already present: serialized IB owner, stable orderRef, atomic claim, chart request journal, unknown/no-replay paths, execId matching and pending-request recovery. Earlier tests simulated SystemExit. `tests/test_order_process_faults.py` now also terminates owned fake-broker child processes with SIGKILL after claim, after the first bracket write, and after all three writes before result persistence. Reopening the temporary SQLite journal returns unknown without broker replay; integrity checks pass. SQLite trigger-injected claim/result write failures verify no send before a durable claim and no resend after an unpersisted result. These are process/SQL-failure checks, not a power-loss/fsync/hardware disk-failure certification.

A regression test reproduced duplicate execId records falsely turning a partial fill into Filled. The execution-history fallback in core/connection.py now counts an exact execId once; conflicting duplicate quantities/prices cannot confirm a full fill. Existing ID-less compatibility remains; it does not prove replay safety for data lacking IDs. Broker execution corrections (different suffix IDs), combo-leg semantics, commissions, and actual read-after-reconnect remain separate acceptance gaps.

Priority gaps before a Live-readiness recommendation:
1. Unify the documented state-transition/action matrix across submission, amendments, cancellation and grouped/bracket paths; prove the existing implementations agree.
2. Extend the now-passing SIGKILL and SQLite-failure checks to amendment/cancel boundaries and real broker reconciliation; test corrected executions and true storage failures separately.
3. Cover partial-fill/cancel/replacement races and identity retention end to end, then visible status recovery without duplicate user confirmations.
4. Run separately authorized bounded Paper acceptance and applicable physical-device gates. Record unresolved market-open fill, partial-fill and TP/SL evidence explicitly.
5. Re-run the protected market-data matrix under simulated pending order work so new status features do not block current-price rendering.

Do not infer Live readiness from compilation, mock tests, a calendar target or resemblance to another product. Present any remaining gaps for a user decision without changing the trading environment.


## Second isolated fault batch — 2026-10-11

`test_order_action_crashes.py` covers six chart amendment/cancellation boundaries
(before request claim, after claim, before send, after send, before result commit,
and after result commit), partial-fill state and a fill winning during the write.
All use owned SIGKILL children and a durable fake-broker reply ledger. Read-only
reconciliation resolves observed outcomes across another service restart; an
unobserved/unsent action remains uncertain, without replay.

`test_order_service_crashes.py` separately covers five in-place amendment boundaries
and five cancellation boundaries, with both canceled and filled terminal replies.
This reproduced an unjournaled cancellation in the Orders service. A new nullable
`orders.cancellation_pending` field now fences the action before the broker call.
The claim is atomic and mutually exclusive with a pending amendment. Missing or
still-working broker replies cannot release it. Confirmed terminal states clear
it; restarting or repeated cancel calls do not resend. The schema migration has
only run on temporary databases. Deployment must preserve/back up the real DB
before the ordinary migration; no production database was opened here.

`core/execution_evidence.py` groups exact execId records by account and permanent
order identity (or client/order/reference fallback). Status matching also filters
the selected account and, for numeric order-ID fallback, the selected client.
Conflicting duplicates and four-segment correction families are not resolved by
arrival order or guessed suffix chronology. They remain Unknown and are excluded
from the confirmed subtotal; ID-less records cannot prove full fill. Five-segment
combo execution identifiers remain separate; this does not add combo trading.
`test_execution_evidence.py` independently covers identity collisions, duplicates,
corrections, no IDs, late/missing fees and conflicting fees. Valid fee reports
survive missing duplicate reports; conflicting fee totals and correction-family
fees remain unknown. Existing fee persistence/late-report tests also pass.

Remaining: real broker correction/bust semantics and device display; retrospective
fee corrections after an already-complete terminal DB record (the periodic metadata
query currently focuses on missing fields) need a separate bounded refresh design.
No claim is made that this batch certifies all terminal fee corrections. Partial
execution evidence must not unlock writes or be displayed as an authoritative
complete quantity. Unknown actions that cannot be resolved stay locked; no automatic
release or replacement order is added.

Minimal future Paper acceptance, not executed or authorized by these tests:
1. Approve a Paper-only session, exact contract, quantity/risk bound, allowed
   submit/amend/cancel actions and cleanup. First perform read-only account identity,
   connection and outstanding-order checks; a port number alone is not proof of Paper.
2. Use the existing serialized owner and verified Paper account. Keep Live disabled;
   do not introduce another running server or parallel client identity.
3. Back up DB/config, review this local diff, apply the nullable-field migration
   under a separately authorized deployment, then verify the stored state.
4. In the approved scope, check working-order identity, amendment, pending cancel,
   partial fill/cancel race, disconnect/restart reconciliation and no duplicate writes.
   Market-open fills, TP/SL and fees require actual observed evidence; mock results
   do not replace it. Finish by reconciling all test orders/positions and recording
   any unresolved state. An uncertain result stops further writes.


## Final offline fee and cancel review — 2026-10-11

The earlier retrospective terminal-fee gap above is now covered locally:
`get_fills_for_reconciliation` rotates through at most 100 filled rows per sync,
including complete terminal records. The existing single IB owner retains its
account-scoped 60-second execution-history throttle. A changed cached complete
fee updates SQLite; exact duplicates do not accumulate; conflicting duplicate
fees or ambiguous correction families invalidate stored fee/PnL metadata without
changing executed quantity or order terminal state. Empty/missing cache evidence
preserves previously confirmed metadata. Broker historical availability still
limits what can be refreshed; this is not an archive of every old execution.

Independent follow-up reproduced stale realized PnL after a fee or currency
correction without replacement PnL. Database persistence now clears that older
PnL when a changed fee/currency arrives without authoritative new PnL. Both
background synchronization and completed-order responses have regression coverage.

Cancellation review covers Submitted/PendingCancel/Unknown/NotFound staying
fenced, confirmed Filled/Cancelled/ApiCancelled/Inactive releasing the intent,
terminal requests never resending, stale broker identity failing the atomic claim,
and idempotent nullable-column migration preserving old rows. Submitted after a
pending cancel correctly remains canceling; one inherited test expectation was
corrected, not the production state transition. Migration was only on temp DBs.

No market-data/UI path changed in this final review. Prior browser latency evidence
is retained, not presented as a fresh measurement of full dispatcher plus broker
history reads. No broker, real DB, Mini, deployment, Git push or device install
was used. Actual correction/bust semantics, market-open/partial fills, TP/SL,
Gateway recovery and physical-device acceptance remain unverified.

Paper deployment should keep the existing Mini service as the only owner, first
privately verify its actual state, back up code/config/Paper DB, apply reviewed
changes and the nullable migration while stopped, then restart Wheel once using
its existing client identity. Do not start Pro against the shared Gateway. No
Gateway restart is required by these source changes. Any account switch that
would recreate the shared Gateway requires separate approval. Verify real 1–4
pane and two-page market delivery before separately authorized quantity-1 Paper
submit/amend/cancel acceptance; partial fills and TP/SL require distinct observed
evidence and approved limits. Unknown outcomes stop further writes.
