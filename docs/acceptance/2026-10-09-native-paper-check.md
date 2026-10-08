# Native simulator Paper check — 2026-10-09

## Observed on running iPhone 18 Pro simulator

- PASS: Portfolio identifies Paper; backend account/profiles selected Paper and verified, bootstrap account prefix DU.
- Baseline: QQQ 400 shares, SGOV 1000 shares, no option positions. Pending-orders returned an empty list.
- PASS: native Trade > Covered calls > QQQ detail navigation.
- FAIL: expiration 20261016 strike picker failed twice with HTTP 503. Entering 775 could not be confirmed while the strike list was unavailable.
- Server evidence: GET /api/options/strikes, request 98510d20852d4ed3870f4513a4007150, 2026-10-09 00:36:10–00:36:20 Beijing time; dispatcher work 10006 ms, response 503. The implementation requests all contract details for that expiry with the 10-second preflight timeout. This identifies the failing read, not a proven broker root cause.
- Further native quote refresh showed “No options data available”.
- NOT OBSERVED this run: entry submission/fill, amendments, BE/SL, Trim, independent cancellation, stop-trigger cleanup, same-parent partial fill, and reconnect/race outcomes.
- No test order was submitted; no cancellation or position change was requested. Live configuration was not changed.

This is an incomplete/failed acceptance, not Live release approval. Existing mocked/regression results do not replace these missing native-to-broker cases.

## Overnight continuation authorized

User explicitly authorized autonomous fixes and repeated acceptance until US/Eastern 2026-10-08 16:00 / Asia/Shanghai 2026-10-09 04:00. Heartbeat `wheel-rth-paper` updated to every 10 minutes with this cutoff and mandatory final reconciliation/deletion. No further routine confirmations needed for bounded Paper work.

Further diagnosis at 00:41: both wildcard expiry strikes (`reqContractDetails`, 10 s) AND individual option qualification (`qualifyContracts`, 5 s) time out; pending-orders and bootstrap still respond. Do not assume increasing the strike-list timeout fixes the root issue or replace exact-expiry validation with an unverified union of strikes. Investigate IB contract-details service/read path next. Gateway has not been restarted.

Computer-use target is `com.apple.dt.Devices` (Device Hub), window iPhone 18 Pro, not app name Simulator. Current UI is QQQ Covered call 20261016 830 Call detail; selecting 775 was NOT confirmed because the strikes list failed. No paper order was sent. CUA must be used for UI input. Existing simulation and native code tests are not native-to-broker acceptance.

## Update 00:51 Beijing time — supersedes earlier no-order baseline

- IB exact strike list recovered without a code/config change around 00:45. Native 775 Call selection and quote now succeeded. The intermittent timeout remains unresolved, not marked fixed.
- Native stage of 1 QQQ 20261016 775 CALL at 0.68 DAY created local draft 52; native automatically navigated to Orders. This was verified as a local database write only.
- Computer-use automatic approval rejected final Confirm Execute even after verified Paper routing and user authorization. Do not bypass that rejection through API/shell or another UI route. User personally confirmed execution and explicitly said “confirm了”.
- Read-only post-confirmation reconciliation: IB order 2054, permanent ID 2052563195, PreSubmitted, filled 0, remaining 1, quantity 1, limit 0.68, DAY. Native detail matches those identifiers and status. Exactly one pending order present.
- At 00:51 still PreSubmitted/unfilled; QQQ400 and SGOV1000 stocks unchanged, no option holding. Do not claim fill/BE/Trim acceptance. Monitor read-only until fill or cutoff; broker-affecting UI actions remain subject to the hand-off restriction. Do not automatically amend price to force a fill.
- Current simulator is Orders > QQQ test-order detail, not the earlier option picker.


## Update 01:13 Beijing — cross-surface pending-order gap

- User manually amended the native entry; read-only IB execution now confirms SELL 1 at 0.44, with position -1. Broker per-share average cost is 0.429809336; it is not the raw fill price.
- Current account profile remains verified Paper. Chart shows no working orders. Its previous canceled entry group (zero filled) still owns the chart selection, causing Add/Trim/BE capability restrictions on this new native holding. This is a separate confirmed defect; not yet fixed.
- Local pending-order synchronization repair now adds native-order chart visibility and existing-service amendment/cancellation controls. Exact account, client, permanent ID, contract, order reference and expected terms are checked. Unknown outcomes stay pending and are not replayed. CC opening quantity remains locked by the existing amendment service; the UI states this limitation rather than advertising an unsupported edit.
- Backend regression at 01:09: 675 passed. New local chart fixture passed display, price/quantity edit message, exact cancellation message, and contract-switch removal. These are mock tests only, not IB amendment/cancellation acceptance. Further reconciliation tests are in progress; patch is not deployed yet.
- Automated final IB submission remains blocked by automatic approval review. User has reiterated Paper authorization, but no alternate-path submission was attempted.

## Delivered 01:26 Beijing — synchronized chart management

- User canceled the scheduled acceptance. Automation was deleted and has not been recreated. User then separately authorized finishing the synchronization repair and installing/running it on the physical iPhone.
- GitHub main and the development branch contain 96d272f (following 3f3bcdb). Mini pulled the same code; only Wheel API restarted, not Gateway.
- Actual post-deployment read-only state: Paper short 1 remains; no pending orders. Add allowed, capacity 3; BE allowed; protection manageable; the old outside-group warning is gone. Trim remains disabled for the one-contract holding under the existing partial-Trim rule; Close is available.
- The original canceled zero-fill chart group is archived, not erased. Adoption requires complete matching native position evidence, exact account/client/permanent IDs and canonical contracts; missing conId in old native rows is handled by exact contract fields. Previously explicitly released history is respected; unacknowledged unknown writes still prevent adoption.
- Pending native orders now expose chart edit/cancel controls through the existing profile-aware order service. Pending quantities represent remaining quantity, while the quantity editor edits total quantity including fills. Existing covered-call opening quantity and rollover locks remain visibly explained.
- Local evidence: full backend regression 682 passed before the final profile-adapter test; the profile adapter's 9 tests and native-group recovery's 5 tests passed afterward. Native simulator suite 138 passed. Local chart fixtures passed pending visibility, price/quantity amendments, exact cancellation messages, contract-switch removal, Chinese phone viewport, and the existing Trim/SL interaction suite.
- Physical iPhone signing build succeeded. Device installation reported success, and process launch succeeded. No real-device order submission was performed. Final broker pending/amend/cancel lifecycle remains unobserved for this new patch; mock UI messages are not broker acceptance. No Live execution enabled and no broker writes performed in this delivery.
