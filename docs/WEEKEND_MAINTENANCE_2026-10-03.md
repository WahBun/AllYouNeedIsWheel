# Weekend maintenance — 2026-10-03

This pass uses fixtures and read-only verification. The connected live account is
not a test execution account. No order is submitted, amended, or canceled.

## Changes

- Portfolio bootstrap and live refresh return selected-account mode and separate
  submission permissions. A verified managed DU account is Paper; a verified U
  account is Live. Missing/mismatched identity stays Unknown. Port alone never
  identifies an account. Chart execution retains its single-paper-account guard.
- iOS status, account settings and chart footer use that mode. Trading permission
  and data freshness remain distinct. Old backends without metadata fail closed.
- Trim/Close records the requested exit units before amendments. Progress reports
  requested, filled, awaiting fill, remaining unfinished, remaining position and
  confirmed working TP/SL quantities. Partial rejection/cancellation does not
  turn unfinished units into completed fills. A selected unit's SL fill also
  counts as an exit. Existing protection is not rebuilt by these changes.
- Chart writes now persist the same unresolved-write lock as ordinary orders.
  Timeout/app restart cannot silently unlock a second submission. Fresh reads
  and broker acknowledgement are different events; reads do not clear that lock.
- Paper controls require a fresh order snapshot and verified connection. Native
  and chart bridge entry points share the checks. Live accounts no longer poll
  the paper-only state endpoint once per second.
- A chart stream with no valid packets for eight seconds is canceled and read
  again; foreground/context cancellation still closes transport immediately.
  Actionable stream setup errors are preserved instead of replaced by a generic
  unavailable message.
- Option chart notices distinguish delayed/frozen data, short history and no
  bars in the selected session. A permission notice requires an explicit,
  contract-matching broker error; an empty history response alone does not prove
  missing permissions. History retry cooldown retains the useful explanation.

## Verification

- Python suite: 312 tests passed, including paper/live identity, mismatched
  account, read-only mode, partial exit, cancellation, partial rejection,
  unknown outcome, duplicate request and option permission fixtures.
- Native suite: 109 tests passed, including a timed-out chart write surviving a
  new TradingSession, duplicate suppression, missing account metadata and option
  stream diagnostics.
- JavaScript suite: 39 tests passed. Chart resume and paper-order browser suites
  also passed.
- Native progress rendering: 320, 393 and 1024 point widths, English, simplified
  and traditional Chinese, light/dark. Representative narrow English/dark and
  Chinese/light renders inspected. Phone build succeeded.

## Remaining acceptance

- Physical iPhone Wi-Fi/cellular switching and a real brief network outage are
  not certified by the fixture/render tests. Verify read-only refresh of chart,
  positions and orders after foreground, network change and chart reopen.
- At next market open, use IB Paper to exercise at least four units: partial
  entry, Add, Trim, BE, Close, rejected/canceled exits and disconnect with working
  orders. Check actual fills, remaining TP/SL, and absence of duplicate writes.
- Real option quote entitlement remains broker/account specific. Verify existing
  holdings read-only; do not open options merely to manufacture test data.
