# Account / P&L / Join recovery candidate (2026-10-12)

Baseline: Mini ca8a2f2, verified Paper, same server epoch as deployment. Only read-only Mini profile inspection in this round; no broker writes or restarts.

## Causes
- Account-change feedback was a persistent trading log, with no identity-scoped recovery completion. Same Paper mode did not prove the selected account identity.
- Quote snapshots without include_pnl did not carry account epoch. The host also overwrote quote epoch with the previous P&L epoch. Identity of two separate data lifecycles was conflated.
- P&L returning from background waited behind the price priority window/polling cadence and an older in-flight read. A stale value rendered unavailable without distinguishing recovery loading. Late/context-mismatched results needed explicit rejection.
- Actual Mini Join block was known=false from historical group attribution, NOT missing bid/ask. Keep that protection. Existing buttons lacked precise reasons and their handler did not force LMT or check asynchronous Join callback identity.

## Changes
- Exact configured/connected account match plus opaque identity in profile status; reject wrong epoch market packets, stamp finite snapshots without requiring P&L.
- Clear only the owned synchronization notice once profile, quote epoch and order read are synchronized. Other rejection/unknown notices remain.
- Context-bound, abortable P&L reads; foreground refresh; distinct loading/unavailable/zero; reject late, wrong-account/contract responses. No price aggregation or stream scheduler changes.
- Explicit Join reason for unconfirmed group/account, stale/missing/crossed quotes and invalid ticks/quantity. Buy bid / Sell ask force LMT, keep existing template and request UUID flow. Revalidate quote/context/quantity/TIF/template before dispatch; no chasing or close-price substitution.

## Validation
- 29 targeted Python tests passed: account profiles, ChartPnL, chart realized P&L, realized P&L; exact-account mismatch and quote snapshot epoch regression added.
- Node VM runs actual host functions and shared chart template/submitPreview, not a second order implementation: epoch preservation, wrong/late P&L, zero/missing, notice recovery, missing/stale quotes, increments, sides/LMT, quantity2, Bracket on/off, duplicate guard passed.
- Actual Chrome local fixture (127.0.0.1:8769), no broker connection: first load, reload, account unavailable/recovered, tab away/return, unavailable P&L recovered to +33.50, stale quote disabled and known=false explicit reason observed. Buy100 / TP102 / SL99 and Sell100.25 / TP98.25 / SL101.25 requests intercepted by fixture; no broker submission.
- Runtime disconnection was SIMULATED in fixture, not Gateway disconnect. Live current data after deployment, physical iPhone, and full tick performance baseline not rerun. Native iOS bundle unchanged.

## Deployment gate
Mini remains ca8a2f2. Need user authorization for a brief Wheel-only restart (client71 and charts reconnect), after backup and GitHub version verification. Gateway/Docker/QQQ/Live untouched. This candidate intentionally does not remove historical group ownership restrictions.
