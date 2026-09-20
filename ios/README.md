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
staging. Execution confirmation defaults on and is configurable in Orders.
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

## Verification

The 2026-09-20 preview review passed 21 simulator tests, including quote failures,
stale responses, manual input preservation, default covered-call quantity,
exact-contract demo closes, currency formatting and write-timeout locking.
English/light and Simplified Chinese/dark layouts, navigation and hide/restore
were checked in the simulator. Debug tests and Release compilation are checked
without submitting real broker orders. Market-hours latency, partial fills and
wireless iOS 18 behavior still require device acceptance; tests do not guarantee
execution or full web feature parity. Publishing code does not deploy the backend
or install the app on a phone.
