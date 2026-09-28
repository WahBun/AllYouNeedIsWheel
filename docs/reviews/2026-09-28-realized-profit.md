# Realized profit on close fills

Executed CLOSE orders display Realized P&L in the history list, detail view and
foreground fill banner. Positive values show a plus sign and green; negative values
show red; zero and unavailable values are neutral. The iOS label is simply
Realized P&L / 已实现盈亏 / 已實現損益. No broker suffix or extra currency code.

Values come from execution CommissionReport.realizedPNL, not sale proceeds or a
position-wide P&L estimate. The broker value is retained without subtracting fees
again. Only USD reports are displayed. All execution reports for the cumulative
filled quantity must be available, valid and identity-matched; duplicates count once.
The existing library maps UNSET_DOUBLE to zero, so an instance-local capture saves
availability before that conversion and forwards the original report unchanged.
A true zero remains distinguishable from unavailable data.

SQLite migration adds a nullable realized_pnl column. Increasing filled quantity
clears an old partial P&L until updated reports arrive. Existing serialized background
metadata synchronization includes CLOSE orders missing P&L, allowing late reports
and available past executions to backfill. No opening costs are guessed. Old trades
outside available broker execution history may remain unavailable. Open-order
premium is not labelled realized profit. Missing P&L does not prevent order viewing.

Metadata can update a currently visible/queued banner or its detail without issuing
a duplicate notification. The foreground banner still expires normally and late
P&L does not create another banner. Other-modal overlay limitations remain unchanged.

Validation: 173 Python tests, including real ib_async wrapper sentinel/zero behavior,
complete/partial/deduplicated report aggregation, persistence, stale partial clearing,
and late background/API backfill. Isolated staged iOS export passed 76 tests,
including profit/loss/zero/missing/foreign/open visibility and late banner enrichment.
Theme-specific profit colors are implemented, but physical-device color/contrast and
live broker backfill were not verified by the Pro development task.

Deployment: back up config and SQLite consistently, pull GitHub, run tests, and only
restart the backend at a safe submission boundary. Keep the single worker/client and
Gateway running. The migration and ordinary metadata sync provide the data; do not
manually invent a P&L or change execution prices/quantities. Verify the affected close
order's value against matched broker execution reports, then confirm the history
API. If unavailable, report that fact and retain NULL. Rebuild/run iOS for the label
and rendering changes. No live trading operations were used for development.
