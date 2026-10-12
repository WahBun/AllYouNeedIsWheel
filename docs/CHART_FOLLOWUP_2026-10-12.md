# Paper chart recovery and Profit input

## Paper chart loading

Read-only Mini logs showed a Paper Gateway connection timeout at 22:18:27
Asia/Shanghai and reconnection at 22:18:38. At 22:19:44 four cold chart reads
arrived together; the dispatcher has three read admission slots and rejected
one. Other reads completed about eight seconds later. This was a recoverable
connection outage amplified by concurrent cold reads, not evidence of a
permanently broken chart renderer.

The page now serializes cold owner snapshots and rechecks the immutable latest
cache after waiting. All normal SSE delivery remains unchanged. Canceled,
expired and old-account queued requests never reach the owner. The queue is
page-local; it does not expand backend capacity or retry trading writes.

Mock checks cover four-pane account epoch changes, initial 503 recovery, cold
and warm reads, failures, cancellation, queue expiry and subsequent recovery.
Real account switching and broker writes were not used as tests.

## Profit amount

The additional TP/SL input mode is `Profit`, initialized to 300 on selection.
It represents the total position amount in the contract currency before fees:
TP gain or SL loss. Price distance is amount divided by absolute quantity and
contract multiplier. Long/short direction and the contract tick determine the
final target. Rounding can make the actual amount differ slightly from input.
Existing Distance, Target price and percentage modes remain available.

New previews recalculate when quantity changes. Existing-position management
uses actual position quantity and rejects a stale quantity/cost-basis context.
Changing the display mode alone does not submit an order.

## Shared first-five-minute close channel basis

The user's final instruction selects B1 C: the confirmed close of the first
New York 09:30–09:35 five-minute candle. All display intervals now use that
same basis. The existing volatility endpoint derives it from the contract's
cached minute bars, requiring all five minutes and a completed time window.
No new broker history request, subscription or owner is introduced. Missing
anchor data waits instead of falling back to an opening price. Index history
uses the same 09:35 cutoff across panes, with the existing previous-day fallback.

Current cached MNQ B1 close is 30,952.25; the corresponding cached VXN close is
21.04. They produce first Bears 30,747.13. This implements the requested basis;
it does not guarantee identical IB and TV quotations. No coefficient or index
price was changed to force a match to a screenshot. The earlier hypothesis of
reproducing Pine's conditional day-reset behavior was not adopted.

Bounded post-B1 minute extrema retain touch flags while a coarse candle spans
the anchor. When that candle cannot establish the exact first-touch time, no
marker timestamp is fabricated. Historical corrections can update the cached
basis. This is not a guarantee of final exchange data.

REA confirmed the observed TV inputs: America/New_York, 09:30–16:00, VXN,
0.5/0.8. The B1-close rule is the user's requested specification; the retained
older Pine reference assigns `open`, so it is not proof of current TV source.
Inputs evidence:
`ev_8f684d4a4d5ad8efea24a893be83135d73b59a8b41e3691629ac8861c9e6638d`.

## Validation

63 frontend unit tests, 152 isolated order regressions and 70 chart/backend
regressions passed. Native simulator: 101 focused tests and final build passed.
The eight desktop/mobile, English/Chinese, light/dark Live-management fixture
combinations passed; all API writes were mocked. Profit preview tests cover
quantity changes, selected menu quantity, invalid multiplier rejection and
recovery. Four-pane Paper epoch recovery passes with initial busy rejection.

Paired synthetic chart checks retained 30/30 updates in each pane: 10 Hz four
panes and two four-pane pages had single-digit millisecond p95 apply latency.
The 100 Hz stress and eight-distinct-symbol tests passed with zero broker writes.
These are local synthetic observations, not exchange-to-display or physical
phone latency. Real orders, fills and stop triggers were not tested.
