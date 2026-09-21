# Wheel iOS preview

Open `Wheel.xcodeproj` in Xcode and run the Wheel scheme on an iPhone simulator.
Deployment target: iOS 18.0. No external Swift packages are required.

## Local signing

Simulator builds need no personal signing identity. For physical devices, create
`Signing.local.xcconfig` alongside `Signing.xcconfig`, setting `DEVELOPMENT_TEAM`
and a unique `PRODUCT_BUNDLE_IDENTIFIER` for your own Apple developer account.
The optional local file is ignored by Git; do not put personal signing values in
`project.pbxproj`. The public defaults build as `com.example.wheel`.
Enter your private HTTPS address only in the app, never in source control.

## Behavior and boundaries

The preview starts with explicitly labeled synthetic demo data. Settings accepts
a private HTTPS backend URL. Appearance follows the system by default, with
optional Light and Dark overrides. Refreshes run sequentially while foregrounded
with error backoff; order status is reconciled through check-orders.
Portfolio and order refresh now run independently, targeting a two-second
start-to-start cadence without overlapping requests within either stream.
Requests taking longer than two seconds finish before another starts; failures
back off to ten seconds. Account summaries refresh less often than held quotes.
The close ticket polls only while visible in the active Portfolio tab and pauses
for confirmation, backgrounding and completed staging. It preserves manual price
and quantity edits, retains but marks failed quotes stale, and blocks staging
when the last response is over 15 seconds old or the held quantity has shrunk.
The successful-receipt clock is separate from the backend snapshot timestamp;
neither is represented as an exchange tick timestamp. The visible Trade board
also polls the selected strategy about every two seconds, sequentially per symbol,
reusing expiration choices instead of fetching them on every tick. More symbols
or slow backend responses lengthen that interval. It pauses offscreen, during
confirmation and while staging. Manual limits, quantities and staged flags survive
refresh; failed quotes retain their display but cannot stage. Opportunity drafts
require a successful response within 30 seconds. Opportunity detail and rollover
comparison quotes still use explicit refresh; these are not exchange tick streams.
Settings offers system language, English, Simplified Chinese and Traditional
Chinese. Wheel, tickers and trading abbreviations remain unchanged. Broker error
messages are preserved verbatim. The app icon reuses the existing web brand asset.

Trade supports covered-call and cash-secured-put drafts. Option positions support
partial-close tickets. Orders supports pending-draft price edits, execution and
cancellation with confirmation. Broker-managed external orders remain read-only.
The opportunity board includes per-symbol OTM/expiration/quantity preferences,
custom CSP tickers, hidden tickers, SGOV exclusion, available CC coverage, quote
spread/Greeks, manual limits and batch draft staging. Preferences are local to
the app/backend context, not automatically imported from browser localStorage.
Pending entry quantities can be edited; close quantities remain locked after
staging. Execution and cancellation share one confirmation preference in Orders,
defaulting on and retaining the existing saved preference. It applies to swipe
actions, order details and cancel-all. Swipes reveal buttons; full-swipe execution
is disabled. Trade entries stage drafts directly from a left-swipe button, detail
view or Stage all, without confirmation; right-swipe hides the ticker. Staging
does not execute at IB. Close/rollover staging and edit confirmations remain separate.
Tabs follow Portfolio, Trade, Orders, Settings. Hidden tickers are restored only
within the selected CC/CSP strategy. Premium estimates use green, occupied CC
coverage uses a compact warning, and spread colors follow the web thresholds:
up to 10% green, up to 20% amber, above 20% red.
Cancel-all skips external and unknown orders and stops on the first failure.
Short-position rollovers stage two independent legs; they are not atomic spreads.
Portfolio samples the backend live endpoint between less frequent summary reads.
Already submitted orders cannot be repriced here. Ambiguous write outcomes lock
further writes until the user verifies the exact order and fills in IB/web and
explicitly acknowledges that review in Settings. Requests are not automatically
resubmitted by the app.

Demo actions are local simulations and never submit broker requests. Unit tests
cover validation, external-order restrictions, simulated lifecycle and uncertain
submission handling using a mocked transport. Run the Wheel scheme's tests in
Xcode. No live trading was used for validation.

This is not yet feature parity with the web app. Full web estimates,
existing browser preference import, and comprehensive iOS 18
physical-device trading validation remain. Reconnect navigation was corrected
after a physical iOS 18 navigation-bar crash; the simulator tests are not a
substitute for physical-device acceptance. Do not put real addresses, signing
identities or credentials in public commits.

## Margin inspection

Initial margin opens a symbol-grouped holding list. Position details also link
to margin impact. The account total remains the reported IB value; individual
holdings are not assigned fabricated portions of that total. On explicit request,
the new backend endpoint `/api/portfolio/position/<con_id>/margin-impact` simulates
closing the entire exact holding with IB what-if. It reports signed initial and
maintenance margin changes, not actual margin used or an additive allocation.
Positive changes can occur when removing a hedge. The estimate excludes a joint
simulation of other closing legs and can change with markets or pending orders.

This endpoint requires the updated backend and a verified USD base account.
It uses the existing serialized IB dispatcher and what-if preflight only, never
the live order submission or database staging path. It is manually requested,
not part of periodic refresh. Unsupported, missing or sentinel results remain
unavailable rather than zero. Old backends show an update notice. Demo estimates
are explicitly synthetic. No live account what-if request was made during tests.

## Verification Results

Trade stock prices and prior-close percentages use one batch request to
`GET /api/options/stock-quotes` on a separate two-second target loop. The batch
updates rows together; option responses cannot overwrite that stock sample.
Option quote failures back off per symbol, not for the entire board. Existing
IB subscriptions are sampled without repeating the initial bid/ask wait; market
data mode changes renew the affected subscriptions. Requests still share the
serialized IB dispatcher, so cold qualification or broker/network delays can
exceed two seconds. Deploy the backend before installing this app version.

Trade automatic quotes now follow the NYSE regular-session calendar via
`GET /api/options/market-session`, including holidays, early closes and DST.
Install the updated backend requirements before using this iOS version.
The calendar endpoint bypasses the IB queue and never requests broker data.
Outside the session, existing quotes remain visible with a closed-market notice;
manual refresh remains available. Unknown session status pauses automatic quotes
with a separate notice. The app rechecks on foreground entry and at session
boundaries; Demo is unaffected. This polling policy is not an exchange trading
permission check and does not stop order-status reconciliation.

The 2026-09-21 preview review passed 28 simulator tests, including quote failures,
stale responses, manual input preservation, default covered-call quantity,
exact-contract demo closes, currency formatting, write-timeout locking, spread
thresholds, quick-action validation, duplicate draft protection and strategy-scoped
hidden tickers, connection status and margin-estimate identity validation.
The backend unittest suite also passed, including eight mocked margin-impact tests.
English/light and Simplified Chinese/dark layouts, navigation and hide/restore
were checked in the simulator. Debug tests and Release compilation are checked
without submitting real broker orders. Market-hours latency, partial fills and
wireless iOS 18 behavior still require device acceptance; tests do not guarantee
execution or full web feature parity. Publishing code does not deploy the backend
or install the app on a phone.
