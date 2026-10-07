# Options-first Live readiness

User priority (2026-10-07): validate single-leg options first; stocks and futures
remain deferred. This document does not authorize Live execution. The current
chart execution path still requires the exact single Paper account and port 4002.
Future activation needs an explicit option-only server-side product gate, separate
approval, and must not incidentally enable stocks or futures.

## Coverage ledger

| Scenario | Evidence / remaining work |
| --- | --- |
| Long unprotected entry, Add, market Trim, Close | Actual Paper 2 → 3 → 2 → 0 passed |
| Add disabled by protection; restored after confirmed removal | Actual Paper passed |
| Realized plus remaining-position SL amount after Trim | Actual Paper passed; excludes commissions |
| Two-contract protected aggregate entry | Actual Paper passed; parent 2, TP 2, SL 2 |
| Pending entry repricing | Actual Paper passed |
| Pending quantity 2 → 1 → 2, DAY → GTC, cancel bracket | Actual Paper passed; all test orders terminal |
| Immediate edit while broker snapshot changes | Safely rejected; later stable-snapshot edits passed |
| Short-side entry, Add, buy-to-cover Trim, protection, Close | Naked call submission rejected by Paper strategy permissions; no fills. User scopes future sell-side acceptance to CC, not CSP |
| Aggregate protected Trim | Unsupported; release blocker if included in initial feature scope |
| Pending Add amend/cancel and fill/cancel race | Option-specific actual matrix outstanding |
| TP-only, SL-only, OCA counterpart cancellation on actual fill | Complete separate actual verification outstanding |
| BE / profitable SL, amount with prior realized fills | Separate actual verification outstanding |
| Sustained partial fill of one broker order | Not observed; cannot substitute split unit orders or mocks |
| Client response lost after option write | Option-specific isolated test outstanding |
| Backend/Gateway interruption during write | Gateway-wide disruption excluded while user orders share it |
| Stale epoch/ref/snapshot, duplicate request identity, invalid tick/size | Regression coverage; expand option-specific evidence |
| Other clients / external fills / position ownership mismatch | Regression plus isolated actual evidence needed |
| App restart and order-history/chart reconciliation | Web/backend checks do not certify physical iPhone |
| Physical phone acceptance | Deferred by user; no installation authorized |

Use minimum-size, uniquely referenced Paper orders on empty contracts. Record
requests before sending; never replay unknown writes. Reconcile and clean only
test-owned orders and positions. Keep prior holdings/orders untouched. A completed
HTTP request, mock test, or broker acknowledgement is not proof of a fill.

## Latest observations

The attempted TP price amendment on an aggregate two-contract option bracket
returned acknowledgement, but no fill occurred. A subsequent authoritative order
read showed the original TP price again. This is an unresolved amendment outcome,
not a successful TP-trigger test. Explicit close canceled both test exits and
filled two contracts; confirmed position zero, inactive, and no broker-pending
state. No trade write was replayed. During reconciliation, unrelated option
history requests held the serialized queue for about eight seconds and some
reads expired. Record this latency as an acceptance issue, not a completed
in-flight disconnect test.

User now explicitly prioritizes chart favorites before further acceptance and
limits future sell-side testing to covered calls (CC), excluding CSP. Existing
holdings/orders remain out of test scope; establish separate test-owned coverage
before a CC order and retain coverage until the short option is closed.

## Simultaneous web and iPhone idle recovery

On 2026-10-07 the user kept both clients open. IB logged error 322 (maximum
account-summary subscriptions), while synchronous option history calls also
occupied the sole IB owner thread. Version 37d1353 bounds synchronous option
history waits to two seconds and backs off empty cold history for sixty seconds;
stock cold initialization retains its prior timeout. Version 40d8155 explicitly
cancels failed account-summary subscriptions and discards partial summary data.
Completed summaries retain their existing subscription and account filtering.

573 backend regressions passed, plus two focused tests of actual IB adapter
cleanup/account filtering. Following deployment, three consecutive profile reads
were 0.23–0.42 seconds and bootstrap reads 0.21–0.29 seconds. Access logs showed
both desktop browser and native Wheel requests succeeding concurrently. Startup
and initial contention still produced isolated 503s; this is short idle recovery
evidence, not long-duration or concurrent trading acceptance. No trading writes
were sent by this diagnostic run, and no Gateway logout or phone install occurred.

## 2026-10-08 QQQ covered-call acceptance

User explicitly authorized the currently favorited QQQ 2026-10-16 775 Call and
existing 100 QQQ shares as coverage. Verified the selected/favorited exact contract
in the browser and the Paper account before writes. One CC sold and subsequently
bought back, both with actual fills; no second short contract or stock trade was
submitted. Adding both standalone exits exposed an unresolved issue: SL was
PreSubmitted but TP remained PendingSubmit. The replacement response was unknown,
not certified coverage. Both exits were explicitly canceled, Add became available
again, then the single call was closed. All test orders terminal and option flat.
Private evidence: /tmp/wheel-simple-scaling-867924875.jsonl and
/tmp/wheel-rth-20261007.jsonl. CC Add must also be constrained by remaining share
coverage before a CC-only Live rollout; current generic Add capability alone does
not establish that entitlement.

Separately, the two-contract AAPL TP amendment using a fresh near-bid exit price
filled both contracts and canceled the SL counterpart, leaving no test position.
The earlier extreme-price amendment nonfill is not explained by this successful
near-market case; it remains separately recorded rather than erased.

## Retained coverage and successful standalone OCA retest

User authorized buying and retaining another 100 QQQ shares in Paper. One Add
order filled 100; total QQQ coverage is now 200 shares, retained after testing.
Restored terminal entry history now allows unprotected Add only when its signed
confirmed fills reconcile with the current position; mismatch remains blocked.

Standalone OCA exits now explicitly transmit each member with common OCA type 2.
576 backend regressions passed before deployment. Actual QQQ CC test then passed:
one short call filled, Add one filled (two covered by 200 shares), attach TP/SL
with quantities two each, cancel both, Trim by buying one, Close by buying one.
A second one-call CC test attached both exits, amended the TP near current ask,
and actually filled the TP; the OCA SL was canceled. Both tests ended flat with no
working option orders and retained QQQ 200 / SGOV 1000. No Live writes occurred.

Standalone protection amount projection fields were absent in these actual CC
responses; amount display is NOT certified. Protected Trim, actual single-order
partial fills and isolated in-flight disconnection remain outstanding. Stock and
option fresh-ticket protection defaults are off; explicit saved user choices are
preserved. Native source updated only, not built/installed on the phone this run.
