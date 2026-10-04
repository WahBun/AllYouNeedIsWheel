# Chart order interaction acceptance

## Expected interaction

- The chart price menu stages a preview. Moving that preview or applying its
  quantity/price/TIF settings does not send an order.
- Click Buy/Sell to submit that preview once. Join Bid/Ask still submit directly.
  Recreating the WebView must not replay a consumed Join gesture.
- A wholly unfilled working entry can be dragged. Release sends one edit using
  the exact reference and broker snapshot. Polling must not move the dragged line.
- Long press direction, quantity, type, or cancel cell to drag. Releasing a long
  press must not also open an editor, submit a preview, or cancel the order.
- Short press quantity/type edits it. Short press X shows immediate cancellation
  feedback; remove the order only after broker acknowledgement. No blind retry.
- Close Position uses the same exact-snapshot cancellation as X when no entry
  has filled. Filled positions use the existing close workflow, show Closing
  feedback, refresh Orders, and reject duplicate close requests.
- Pure cancellation skips contract/price revalidation and the fixed 200 ms
  post-write delay; ownership, snapshot and fill-race checks still apply.
- An explicitly closed filled standalone OVT position uses SMART DAY MKT
  during regular trading hours, never an OVERNIGHT market order.
- The preview and active-order editors both expose price, quantity and TIF.
  The editor's purpose and reference remain fixed while it is open.
- DAY/GTC are available for supported stocks, options and futures. OVT is only
  available for USD stock BUY/SELL LMT entries, with explicit no-TP/SL acknowledgement.
  Options and futures never offer or submit OVT.
- Chart-owned single-parent orders expose the same settings in Orders. Option
  enrichment keeps its existing row identity and does not duplicate the row.
  Split-lot groups are edited from the chart as a group, not as independent legs.
- All four order cells align vertically. The persisted order/TP/SL extension-line
  setting defaults on; hiding lines preserves handles and axis prices.

## Repeatable checks

- Backend: `python -m unittest discover -s tests` (mock broker only).
- iOS: `WheelTests/TradingTests` on Simulator, including stale snapshots,
  Paper/Live separation, unknown outcomes, Join replay and OVT capability matrix.
- Chart: `submit-button.cjs`, `entry-edit.cjs`, `paper-orders.cjs`, `controls.cjs`.
  Include actual pointer/touch events and polling during a held gesture.
- `test_repeated_drag_release_and_replacement_stay_synced_in_orders` edits five
  times and reads chart state plus Orders five times after each edit. It checks
  price, total quantity, TIF, identity, deduplication and no writes from reads;
  it then checks confirmed cancellation across five further reads.
- Native UI: verify DAY/GTC/OVT menu for a stock preview; Apply only stages the
  settings; reopening retains the chosen TIF. No broker submit during this check.

These checks do not certify real market fills, partial fills, TP/SL execution,
physical-device network recovery, or broker latency. Those require separately
observed Paper market-session acceptance. Live execution remains restricted.

## Latest local acceptance (2026-10-04)

386 mocked backend tests and 85 Simulator TradingTests passed. Signed iPhone
build passed. Chart pointer/touch checks cover immediate cancellation feedback,
repeat-click suppression, and broker-confirmed removal. These results measure
application behavior, not real IB cancellation latency.

## Stability regression pass (2026-10-04)

Scope frozen: no new trading features, UI changes or mobile-network work.
390 mocked backend tests, 86 Simulator TradingTests and seven chart browser
suites passed (submit-button, entry-edit, paper-orders, controls, resume,
holdings, execution-touch). Existing suites cover account isolation, stale
snapshots, duplicate submission, uncertain writes, cancel/fill races, protected
exits, rejection and Orders reconciliation.

New fault-injection checks cover:
- Confirmed OVT cancellation reports success and remains idempotent after restart.
- Broker acceptance followed by a lost response reconciles without another write.
- Partial entry fill during replacement cancellation retains protective children
  and blocks replacement; this does not certify broker-adjusted protection sizes.
- An immediately filled standalone close is recognized as completed after restart,
  without another market order.

Fixed two result/recovery defects: confirmed OVT cancellations were marked as
failed, and persisted `done` close results were omitted from recognized outcomes.
No broker test orders were sent. Actual fills, partial-fill protection quantity,
OCA execution, and physical-device recovery still require Paper-session acceptance.
No iPhone installation is part of this pass.

## Approved: symmetric stock OVT (2026-10-04)

USD stock limit previews and pending-order editors offer OVT for both BUY and
SELL. Standalone submission preserves direction in its ownership journal and
broker order; price/quantity/TIF replacements keep the original side. Options,
futures, non-USD contracts and stop entries remain excluded. Existing-position
checks and broker rejection handling remain in place; no short-sale permission
or borrow availability is inferred from showing the OVT choice.

394 mocked backend tests, 88 Simulator TradingTests and submit-button/entry-edit
browser checks passed. Sell-side coverage includes direct OVT, DAY/GTC/OVT
replacement, price/quantity edits, cancellation and filled-short BUY close.
OVT disables Buy Stop and Sell Stop choices; native and backend guards reject
STP requests without placing or canceling a broker order. User approved GitHub
push and Mini deployment. Physical-phone Run remains deferred.
