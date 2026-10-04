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
- At most four distinct API jobs are admitted. Reads/background sync use at most
  three slots, reserving one for writes during polling saturation. Identical reads
  still share work; writes remain serialized and are never automatically retried.
  Excess requests receive 503 and Retry-After. This is admission reservation, not
  execution priority: an accepted write may still wait behind earlier work. HTML,
  static assets and health checks do not enter the IB queue.
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

Preview direction is inferred when Entry is edited or LMT/STP is changed:
LMT below/above the last chart close selects buy/sell; STP reverses this.
At equality the prior direction is retained. Subsequent quote updates do not
flip direction. TP/SL constraints and preview P&L follow that direction.
The chart close may be historical outside market hours; this is not execution
validation. Actual broker orders remain outside this chart prototype.

Chart favorite intervals persist on-device; the period selector supports
1/3/5/10/15 minutes, 1/8 hours and D/W/M. Calendar periods request native IB
1-year daily, 5-year weekly and 10-year monthly bars on demand, cached for the
active chart lease and canceled with it. Intraday history requests five days of minute bars.
8h RTH shares the native daily history/cache with D; ETH retains 8-hour aggregation. History availability depends on the instrument.

Join Bid explicitly chooses Buy LMT; Join Ask explicitly chooses Sell LMT.
Each tap carries a one-shot revision so polling cannot reapply it after a manual
Entry drag. Quote position relative to the last trade does not override Join.

Chart controls remain preview-only: orange Close Position opens a no-order
explanation, purple BE moves the simulated stop to Entry plus one tick for buys,
minus one tick for sells. Tick increments come from the contract's exchange
market rule and price tier; unknown rules disable BE. This does not manage real
position stops. Overnight data investigation was explicitly deferred by user.

TP/SL distance template is stored on-device in price units. Defaults 0.20/0.10
are editable examples, not instrument-specific risk recommendations. New previews
use it; applying explicitly replaces current preview levels. BE reports applied
state to SwiftUI and disables until the preview no longer has that BE adjustment.
Live chart entry/bracket integration remains unimplemented. User selected Join
Bid/Ask as the eventual direct bracket submission actions in explicit live mode;
existing buttons are still preview-only. Do not test by placing real orders.

## Chart data audit fixes (2026-10-02)

Contract detail reads have a three-second bound; missing rules retry after a
30-second cooldown. Historical backfill replaces stale historical baselines,
merging received live extrema, and the chart accepts older-bar revisions without
resetting its viewport. Bid and ask freshness now requires their own price events;
a Last tick cannot refresh an old quote. Unknown/stale sides disable Join through
the existing nullable quote fields. This remains HTTP polling and preview-only.

## Chart control audit fixes (2026-10-02)

Preview SL dragging permits profit-locking on both sides. Entry edits, dragging,
keyboard stepping, template targets and BE use contract price tiers instead of
hard-coded cents; missing rules defer price edits. Native bridge formatting
preserves sub-cent prices. Invalid template applications show an inline message,
retain existing levels and consume that revision, requiring another Apply after
correction. No broker write integration was added.
Regression: `NODE_PATH=<playwright node_modules> node tests/chart/controls.cjs`
checks long/short profit stops, quarter-point and sub-cent tiers, BE/Join reset,
and invalid-template recovery in Chromium. Device build verified separately.

## Stock chart SSE pilot (2026-10-02)

Intraday charts now use a one-way SSE connection. The existing IB owner executor
is pumped by at most one outstanding job scheduled every 20 ms while viewers are
active; incoming Last ticks retain OHLC extrema, and only changed bars are pushed.
This is bounded display coalescing, not one screen frame per trade or guaranteed
latency. Other serialized IB work can delay delivery. D/W/M and RTH 8h retain the
historical polling path. Two viewers maximum, one active stock; queues are bounded
and overflow emits a complete snapshot. Connections renew after two minutes and
clients reconnect on sequence gaps. No order writes use this transport.
First snapshot precedes deferred history/metadata. iOS reuses an in-memory chart
up to five minutes old while reconnecting, explicitly labeled and with Join disabled
until fresh data arrives. No persistent/offline quote is presented as live.
Dedicated BidAsk tick subscription supplies quotes. A side can persist for up to
30 seconds while actual source activity remains within ten seconds; absent,
frozen, crossed, disconnected or expired quotes disable Join. Client receipt must
also be recent. This is not a promise that buttons always remain enabled.
Full-screen toggle hides navigation, tabs and trade controls while retaining
period/session selection and an exit button. Chart controls remain preview-only.

## Persisted chart history and drawing tools (2026-10-02)

Chart history now survives app process restarts in on-device preferences: up to
12 contexts, 2,500 bars each, 24-hour validity, disk writes throttled to 15 seconds.
Quote fields, countdown eligibility and stream sequence are stripped. Cached
history is labeled until a fresh response arrives; a truly unseen chart still
requires IB history. RTH initial history now requests two days to cover sessions
where one day contains only extended-hours bars.

Independent analysis drawings support the user's 20 starred tools: Trendline,
Info line, Horizontal ray, Parallel channel, Fib retracement, Trend-based fib
extension, Long/Short position, Price range, Highlighter, Arrow, up/down marks,
Rectangle, Path, Triangle, Curve, Text, Note and Price note. This is an original
implementation of basic equivalents, not TradingView's library or all settings.
Tool picker stars determine a scrollable favorite strip; drag its grip to float,
collapse to the left. Analysis drawings are saved per backend/contract; favorites
are global. Select anchor handles to adjust, with delete/undo/lock/hide in picker.
Long/Short takes entry, stop and target anchors and reports price R:R only; it
never submits, amends or cancels broker orders. Free paths finish with checkmark.
Drawing regression: `NODE_PATH=<playwright node_modules> node tests/chart/drawings.cjs`.


## iOS Paper / Live selector (2026-10-03)

Settings selects Demo / IB Paper / Live against private Mini profiles. Separate
account databases and a serialized account epoch prevent stale iOS writes after
a switch. Gateway login remains manual; no credentials are collected. Service
preparation failure leaves the current account intact. See MAC_MINI_TAILSCALE.md
for provisioning and legacy web-client limits. Regression: full Python suite
324 tests passed; device build passed. No broker orders used for verification.


## Gateway login integration (2026-10-03)

Opt-in local credential profiles now let account selection recreate the single
Gateway service for Paper or Live, with bounded asynchronous startup. The iOS app
polls actual account verification and shows IB Key guidance while waiting; Demo
hides backend address/Connect while retaining the saved address. Credentials stay
on Mini, outside Git. Validation: 328 Python tests and iPhone build passed.

## Standalone Paper overnight stock entry (2026-10-03)

POST /api/portfolio/paper-chart/<conId> accepts action=submit,
mode=overnight_entry, side=1, entry_type=LMT, quantity (whole shares, 1–1000),
entry, and a UUID request_id with the current account-epoch header.
This is an explicit USD stock BUY without TP/SL. It uses the existing serialized
IB owner, Paper account/4002/read-only checks and durable request journal.
The exact contract must advertise OVERNIGHT, and the venue market rule must
validate the limit. The broker receives exchange=OVERNIGHT, tif=DAY,
outsideRth=true; there is no SMART fallback or automatic resubmission.
The overnight venue's session governs eligibility; the server does not schedule
or retry an order that IB rejects outside its accepted submission window.
GET on the same endpoint exposes mode, route, broker status and broker messages.
cancel_entry cancels the remaining entry only; generic close/BE/amend/add/trim
are rejected for this standalone group, so holding it cannot trigger an implicit
market exit. The existing iOS bracket buttons do not select this API mode.
Verification: unittest tests.test_paper_overnight tests.test_paper_chart.


## Orders management of standalone Paper entries (2026-10-03)

Orders now exposes cancel and price amendment for journal-owned overnight stock
entries, including Cancel all eligible. Foreign broker orders and protective
bracket legs remain excluded. Management uses the existing Paper chart endpoint
with action=manage_entry, expected_ref, operation=cancel/amend, and for amendments
expected_price/price. The server revalidates account, exact contract, original
reference, route, broker status and venue tick. Filled/partially filled entries
cannot be repriced here. Cancellation remains pending until broker confirmation;
no replacement entry is generated. The phone retains unknown-write blocking and
account epoch checks. Physical phone cold-start/network and actual broker
amend/cancel acceptance remain to be checked; current live Paper QQQ order is
deliberately preserved during mocked acceptance.
