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
