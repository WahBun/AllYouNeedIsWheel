# Project Handoff

## Workflow

The native iOS app is the primary user interface and the MacBook Pro is the
primary Xcode development host. Mac mini runs the backend and IB Gateway.
See the root README for the current end-to-end setup and ios/README.md for native
behavior. The web workflow notes below describe the retained auxiliary interface;
browser and app preferences are separate. Desktop App/DMG releases remain separate
and require an explicit request.

Keep code updates local unless the user explicitly requests a GitHub push.

For explicit successful workflow actions, prefer navigating to the resulting
record and back to its source, on both desktop and phone. Dashboard Add/Add All
now refresh Pending and reveal the saved order; confirmed cancellation returns
to the matching opportunity and CALL/PUT tab if it still exists on that page.
`utils/workflow-navigation.js` provides reusable reveal/highlight behavior with
reduced-motion support. Execute and background polling never navigate; failed
or unconfirmed cancellations stay in Pending. Mocked browser tests covered
successful and failed Add/Cancel at 393 and 1440 pixels without broker writes.

Portfolio close staging waits for the modal to finish hiding, then reveals the
saved Pending row. Confirmed close cancellation returns to the exact conId's
held-position row. Rollover Roll reveals suggestions; staging reveals the closing
leg in Pending and confirmed cancellation returns to suggestions. Open/close
cancellations from another page use a one-shot sessionStorage destination, wait
up to 15 seconds for rendered rows, and never change quote selection or submit.
Global mocked click tests covered Portfolio and Rollover staging/cancellation
plus both directions of Dashboard/Portfolio returns at 393 and 1440 pixels.

The deployment model is one always-on Mac mini running the web application and
IB Gateway, accessed locally or from trusted devices through Tailscale Serve.
Do not assume another computer has the same paths, Python environment, credentials
or uncommitted changes. Pull Git updates and inspect the current host first.

## Architecture Invariants

- Flask/Jinja frontend with JavaScript modules; Python `ib_async` backend and SQLite.
- One Gunicorn process, eight HTTP threads, one dedicated API execution thread.
  `api/request_dispatcher.py` owns serialized API dispatch and preserves IB event-loop
  thread ownership. Identical in-flight GET requests share work. Writes never do.
- Four concurrent API waiters are admitted; excess requests receive 503 and
  Retry-After. HTML, static assets and health checks do not enter the IB queue.
- Order staging is separate from Execute. Execution confirmation is configurable.
- Unknown submissions without an IB ID are reconciled by local order reference;
  unknown broker statuses remain unknown and preserve confirmed partial fills.
- An atomic database claim guards duplicate execution of the same staged order.
  Execution rechecks the configured account, contract and position capacity.
- Readonly is enforced by both service and connection code, not just the IB library.
- Portfolio reads target a two-second start-to-start cadence, without overlapping
  requests or catch-up bursts. Failed reads back off; hidden tabs pause.
- Quote selection serializes work per row and discards superseded results. Old
  prices are removed while loading. Invalid manual prices cannot fall back silently.
- Expiration checks use the New York date, not the host's local calendar date.

## Verification

```sh
python -m unittest discover -s tests
node --test tests/*.js
git diff --check
```

The September 20, 2026 verification passed 99 Python and 39 JavaScript tests.
Browser checks covered Dashboard, Portfolio, Rollover, rapid expiry changes,
failed quotes, invalid manual prices, mobile table scrolling, settings and dialogs.
Widths tested: 320, 390, 430 and 1440 pixels, including English/Chinese and
light/dark combinations. These checks are not live-trade or real-iPhone certification.

No real order was submitted or canceled during verification. Use mocked broker
responses for order tests; a populated portfolio alone does not prove a paper account.

Phone layouts below 576 CSS pixels reuse original table cells and trading controls
as labeled two-column records. `mobile-tables.js` refreshes labels after dynamic
renders and language changes; `mobile-trading.css` is phone-only. Mocked browser
checks covered all three pages at 320, 393, 402 and 1440 pixels, populated pending
orders, price edits, both languages/themes, and no overflowing cells. The desktop
option table screenshot was pixel-identical with the phone stylesheet disabled.
This is browser viewport testing, not physical iPhone/Safari certification.

Phone opportunity inputs also offer native selects alongside manual entry: OTM
and quantity use integer steps within the input bounds (quantity capped at 100),
and price offers cent increments within +/- $0.20 of the current value. Disabled
inputs remain disabled. Picks dispatch the original input/change handlers, never
submit orders. Pickers are removed at desktop widths. Browser mocks verified
price selection, summary updates, disabled state, and unchanged desktop pixels.

## Known Limitations

- The iOS Trade polling gate uses the NYSE calendar, including holidays and early closes.
  This is not a universal trading-session model; older web helpers and intraday
  performance estimates have separate, narrower behavior.
- Earnings estimates annualize each quoted selection by 365 / calendar days to
  expiry using the New York date, then sum. Same-day/invalid expiries show N/A.
  These are repeat-premium estimates, not executed income or profit; they exclude
  compounding, fees and losses, and mixed expiries cover different horizons.
- Cold IB contract qualification and unavailable quotes can take seconds. API
  operations still serialize for consistency, although navigation is independent.
- Tailnet membership is the access boundary; there is no separate per-user web
  login. Limit device/user access with Tailnet policy. Do not publish via Funnel.
- Live fills, upstream outages and every broker-side rejection cannot be proven
  by local regression tests. Unknown submission outcomes require reconciliation.

See `MAC_MINI_TAILSCALE.md` for installation, access and restart procedures.
The web frontend supports iPhone standalone Home Screen launch via a manifest
and Apple metadata. It adds no service worker or offline trading cache. Prefer
private Tailscale HTTPS; remove the optional remote TCP 8000 forward only after
validating HTTPS, while retaining the loopback server and unrelated forwards.
See `WORKFLOW_NAVIGATION.md` for the single/batch action navigation checklist.

## iOS completed order details (2026-10-02)

Order details retain confirmed terminal records from the existing order history
response and confirmed cancellation acknowledgements. Disappearing from Pending
alone is never treated as a fill or cancellation; an unresolved result remains
read-only and explicitly requires verification. Partial fills remain visible after
cancellation. The in-memory cache clears on backend/demo context changes.
Verification: 98 iOS tests passed using mocks; no live orders were changed.

## iOS safe diagnostic copy (2026-10-02)

The Portfolio/Orders data-status sheet includes a preview and Copy diagnostics.
Only fixed status fields, numeric versions, response age, HTTP code and the
app-generated request reference are exported. Raw errors, URLs, account and
position data are excluded. Copy is local-only and expires after five minutes.
99 iOS tests passed, including adversarial sensitive-error redaction checks.

## Held-stock chart pilot (2026-10-02)

Long USD stock details now link to a bundled Lightweight Charts 5.2.0 preview.
RTH is the default; all-hours and 1/5/15/60-minute periods reuse one IB Last
subscription and one day of historical 1-minute TRADES bars. RTH filtering uses
the NYSE calendar (including holidays, early close, DST), and hourly RTH bars
anchor at session open. The iPhone polls accumulated OHLC at about 250ms plus
request latency when recent Last ticks are available (one second while waiting).
This is batched transport of tick data, not a guaranteed per-tick frame or SLA.
The existing serialized IB executor owns subscription/event processing; no second
IB client is created. An unused chart lease expires after 30 seconds once the
IB event loop is pumped. Simultaneous different-stock viewers share one slot.
TP/SL lines and P&L are long-stock previews with an editable entry reference and
share quantity, rounded to cents and excluding fees/slippage. They never write
orders. There is no bracket-order execution in this pilot. No options/futures
support or Pine Script runtime is implied. Missing tick permissions/closed
markets show waiting; no snapshot fallback is labeled as tick data.

## Stock chart preview controls

The held-stock chart uses a fixed gray palette in both themes, compact right-side
Entry/TP/SL drag handles, and RTH/ETH session selection. Prices appear in the
handles without duplicate custom axis labels. LMT/STP and Join Bid/Ask change
only the preview; Join copies a recent live quote once. Explanations and required
attribution remain in Chart details. No chart control submits broker orders.
