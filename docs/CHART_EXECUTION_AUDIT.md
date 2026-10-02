# Supercharts paper execution audit — 2026-10-02

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
