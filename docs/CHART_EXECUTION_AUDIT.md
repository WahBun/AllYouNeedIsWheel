# App regression check and option chart entry — 2026-10-03

- Option holdings (long or short) now expose Supercharts using their exact conId, expiry, strike and right. Stock/futures lookup never substitutes an underlying for an option. Recent-chart navigation retains the same contract.
- Option charts are view-only. Native order controls and the price-axis order button are hidden, and the paper execution service rejects option requests before broker writes.
- Options use IB historical-bar updates and the existing shared quote subscription rather than unsupported option tick-by-tick subscriptions. Frozen/delayed quotes cannot declare a live chart or fabricate a current candle. Chart cleanup cancels its history stream without canceling the shared quote subscription.
- Verification: 303 Python tests, 39 JavaScript tests, 106 native iOS tests and all 12 chart browser suites passed. The signed iPhone build and installation succeeded. Tests include exact long/short option identity, reconnect lookup, update freshness, shared-subscription cleanup and rejection of option chart order writes.
- Paper account currently has no option holdings: real option holding navigation/data-entitlement checks remain pending. No option trade was made for this entry change. User deferred Gateway live login until after these checks; switching accounts and verifying the connected live account remain separate steps.

---

# Supercharts protected-lot verification — 2026-10-03

This supersedes the cancellation/replacement scaling path in the historical audit below. Verification used the paper-only backend endpoints and the exact MES December contract. No real-account execution is enabled by these changes.

## Current behavior

- New futures positions use one native Entry / TP / SL bracket per contract. Add creates new unit brackets without changing existing exits.
- Trim reprices selected units' existing TP limits to bid (long) or ask (short). Each selected unit retains its SL until its exit fills; the broker then cancels that unit's sibling. Other units' TP/SL remain unchanged. Close applies the same operation to all remaining filled units; unfilled parents are canceled separately.
- These are limit exits, not guaranteed immediate fills. A moving market may leave some requested units working. Further Add/Trim is blocked while that adjustment is unresolved; Close can explicitly update remaining exit limits. No uncertain write is automatically replayed.
- Older single-bracket and non-futures positions cannot use Add/Trim through this implementation. They are not silently converted.
- Amendments refresh and preserve the broker's canonical OCA group/type and parent linkage. Previously, changing those fields caused IB errors 10326/10327. Amendment rejection is now reported even if the local order status later returns to Submitted.
- Reconnected completed parents are recovered by permanent IDs and included in position reconciliation.

## Broker-confirmed results

- Long 4 → trim 1 → add 2 → trim 2 → BE → flat. Each trim preserved every surviving SL's original ID, quantity and price; Add retained old stops and added new units. The final three SLs filled after BE, and their three sibling TPs were canceled.
- Short 4 → request trim 2 → first unit filled while the second limit remained working as the market moved. The filled unit's SL canceled; all three unclosed units still had SLs. A subsequent explicit Close filled the remaining exits and finished flat. This exercise intentionally records partial completion instead of claiming an immediate two-unit trim.
- Buy and sell × LMT and STP, four units each: parked entry, TP amendment, SL amendment, cancel. All four combinations returned flat.
- The earlier four-unit test group was closed after correcting OCA field preservation, without canceling its stops in advance.
- Final read-only reconciliation: paper account, known state, MES position 0, chart inactive, MES pending orders 0. Unrelated holdings were not part of the tests.

## Final repeat with order-based arrows — 2026-10-03 00:45–00:47 CST

Both long and short completed 4 → Add 1 → Add 1 → Trim 2 → BE → flat. Each side's execution payload exposed three distinct opening request groups with total quantities 4, 1 and 1, rather than grouping by candle. After Trim, the surviving stop IDs, quantities and prices matched the pre-trim snapshot. BE closed the remaining positions in both directions. Final MES reconciliation was flat with zero working orders. This repeat used the app's paper execution endpoints, not automated taps on the physical phone.

## Display and checks

Execution markers aggregate by logical order request, recovered from the existing write journal. A four-contract request renders one arrow, including partial fills across candles; four separate one-contract requests render four arrows even on the same candle. Entry, TP/SL, Add and Trim requests remain distinct. Tapping each arrow shows its own symbol, quantity, weighted average and fills. Broker executions without a known local batch are grouped only by their broker order identity. Marker placement uses the first fill of the order. The details panel scrolls when necessary. Add/Trim, Close Position and BE use equal flexible widths and matching heights.

299 Python tests passed, including broker OCA preservation, rejected-amendment reporting, reconnect recovery, no-replay and protection-preservation regressions. Chart execution-touch and paper-order browser checks passed, including four-fill aggregation and blank-tap dismissal. OHLC is aligned to the right of the symbol/exchange header; narrow and wide viewport checks showed no OHLC overflow, and price-scale tick labels moved three CSS pixels toward the right edge. The device build succeeded and was installed. These checks are not real-money certification and do not cover every broker, exchange or network failure. Individual unit brackets also mean more broker orders than a single aggregate bracket.

---

# Historical audit — 2026-10-02 (superseded scaling implementation)

Scope: existing chart controls plus newly requested Add / Trim. The user explicitly authorized paper-account broker writes, starting with at least four contracts. Options chart access is a subsequent task, not part of this audit. Tests used the exact MES December contract returned by the backend; existing unrelated holdings were preserved.

## Broker-confirmed scenarios

- Buy/sell × LMT/STP: four-contract parked brackets, TP and SL amendments, cancellation; each ended flat.
- Join Bid price: buy 4 → add 2 → trim 3 → add 1 → close 4. Remaining TP/SL quantities were 6, 3 and 4 respectively.
- Join Ask price: sell 4 → add 2 → trim 4 → TP closes remaining 2; sibling SL canceled.
- Buy 4 → BE → repeat BE without loosening the stop → SL exit.
- Sell STP triggers 4 → trim 1 → BE for remaining 3 → flat.
- Buy STP also triggered four contracts during the initial scaling investigation.
- Orders feed included individual scaling fills, allocated entry/exit fees and realized net P&L. Chart bracket amounts followed remaining position size.

Live exercises used the same backend write endpoints as the app. Browser tests exercised chart controls and price-axis order choices; this is not a claim that every phone control was manually tapped during live execution.

## Findings and repairs

- Market adjustment orders omitted explicit DAY. IB's preset warning 10349 was interpreted as a transient cancellation by the client, before the real execution arrived. Add, Trim and Close now specify DAY.
- Position snapshots can lag fills. Replacement protective orders are sized from the pre-adjustment position plus confirmed adjustment fills, not a post-fill snapshot.
- Standalone replacement exits must be transmitted individually. Both use the same OCA group with proportional reduction and blocking; protective acknowledgments are checked.
- Broker futures avgCost includes fees. The chart price basis now uses chronological executions and retains the average basis after trims.
- Closed, locally held orders can disappear after reconnect without a permId. Confirmed terminal states are retained; unknown orders are not assumed canceled.
- Close refuses a position/execution mismatch instead of risking an unintended reverse position.
- Realized P&L handles multiple opening executions and partial exits, allocating opening fees once.

## Verification and limits

289 Python tests passed. All chart browser suites passed, including scaling quantity/P&L assertions. Native ChartViewportTests passed; the iPhone build succeeded and was installed/launched. GitHub main and the Mini backend contain the fixes.

Add/Trim remains paper-only, enforces the existing quantity cap, refuses unrelated orders/position discrepancies, and never retries uncertain writes automatically. Scaling cancels old exits, executes the adjustment, then creates protection for the remaining position. This is not an atomic broker transaction: protection has a cancellation/replacement window, and an unresolved broker or network failure requires reconciliation. The tests do not certify real-money readiness, guarantee execution prices, or cover every exchange/network failure.
