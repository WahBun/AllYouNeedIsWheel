## 2026-10-14 existing CC BE and option chart display repair

Existing position-only manual BE could dereference an absent Wheel group before
saving an intent or placing a stop. It now uses the guarded existing-position
protection path. Legacy unknown requests are reconciled without resubmission only
for the exact unchanged, unadopted holding with no all-client working orders;
foreign orders keep the request unknown. No real orders were used for validation.

Option chart packets now carry a separate display-only cached bid/ask pair from
the shared ticker. This handles opening a chart after Portfolio received quotes.
The renderer labels this fallback as last quote/waiting; executable quote fields
and freshness checks are unchanged. The native chart shares the same asset.
Option auxiliary panes show only their dynamic current-timeframe EMA20; primary
preferences and stock/future auxiliary profiles remain unchanged.

Validation: 121 focused backend tests plus the added foreign-order recovery
regression passed; eight browser cases covered active/inactive auxiliary panes,
main preferences, desktop/mobile and cached quote isolation; 102 Simulator tests
passed. The 1-4 pane/two-four-pane synthetic refresh matrix passed, with 30 updates
per pane and preserved burst extrema. These are offline results, not Live fills.
User authorized this Wheel backend restart; Gateway and actual orders stay untouched.
User signing/project and localization changes are excluded from this commit.

## 2026-10-14 Paper existing-option Add parity fix

The reported disabled Add was an existing Paper short option holding without a
Wheel group: known position, no working orders, no sync error, but the position-only
management branch was Live-only. There is no unrealized-loss prohibition.
Expose the same guarded adoption path for Paper option holdings; preserve fresh
position/order identity, CSP cash and CC share checks. Add/Trim/Close requests do
not claim or trade a holding merely by reading it. Web/native Close include the
expected position. No actual orders were sent on the user's existing option.
40 focused backend checks and 102 iOS Simulator checks passed, including losing
short-put Add, cash denial and foreign-order/position races (all mocked).
This follow-up requires another approved backend restart before it is effective.

## 2026-10-14 final capability deployment verified

After separate user approval, Mini fast-forwarded to 74ef95f. A private profile
backup was retained and OPT/FUT/STK Live flags were verified true. The Wheel
backend restarted and recovered verified Paper selection with a new epoch;
Gateway start time was unchanged. No Live orders or original positions were
modified. GitHub development and native branches both received 74ef95f. The
QQQ acceptance automation was paused after completion. Native code is synced,
not installed on the phone; user performs Run from the verified checkout.
Standard option chart actions were already enabled. Coverage checks, explicit
prices, asset limits and broker reconciliation restrictions remain enforced.

## 2026-10-14 QQQ Paper differential acceptance passed; Live activation prepared

Mini backend 3ee8d84 was deployed after explicit restart approval. Gateway
container start time did not change. After reconnect, verified Paper identity and
new epoch, QQQ zero starting position and no pending orders; used one new group.
Broker evidence: 100-share protected LMT entry filled; aggregate Add 100 filled
(total 200; TP/SL each 200); LMT Trim 50 filled (remaining 150, TP/SL each 150).
A resting Trim 50 was resized to 25, then canceled; TP returned to 150 and SL
remained 150. Finally amended the 150-share SL near market; it actually triggered
in RTH, filled 150 and canceled its OCA TP. Final account/test-group QQQ position
zero, inactive group, every test order Filled/Cancelled, no broker pending orders.
Initial entry acknowledgement was unknown and recovered through reads only.
No original holdings/orders or Live orders were changed. Partial fills were
covered offline, not observed in this broker run. Previous no-fill cause remains
unproven; this run verifies the corrected route/workflow works, not causation.

Live candidate adds independent stock/futures capability flags alongside options.
Exact account, port, read-only setting and asset checks remain enforced. UI/native
Add/Trim/Close use explicit price requests, including TP/SL snapshots for Add.
70 focused backend policy/execution/routing/scaling regressions passed, alongside
85 earlier scaling regressions. Browser stock/future/option management tests cover
desktop/mobile, themes, payloads and stale quote refusal with intercepted APIs.
102 relevant iOS Simulator tests passed; no physical phone install was performed.

Native GitHub branch is to receive this validated source. The older Pro native
checkout has unrelated uncommitted changes and is not safe to fast-forward;
preserve it. Use the current Ben Options checkout's ios/Wheel.xcodeproj for Run.
Final Live capability deployment requires the separately confirmed backend restart;
no actual Live order is part of acceptance or activation.

## 2026-10-14 stock protected scaling candidate — broker acceptance pending

Option quote metrics now follow primary-pane chrome. Auxiliary panes hide them;
maximizing an auxiliary pane restores them. Browser interaction regression passed.
GitHub/Mini static deployment 0bd4111 was verified on the actual option page:
main display flex, three auxiliary displays none. No restart was needed.

Development candidate: aggregate STK Add uses one share-quantity parent with
attached TP/SL, distinct from FUT per-unit lots. Settled protected Trim repartitions
exits into retained TP/SL and Trim/SL OCA pairs with proportional reduction.
Pending limit Trim resize/cancel rebuilds the remaining protection from the
current broker snapshot. Cancellation/replacement has a protection gap; it is
not atomic. Fill races or incomplete acknowledgement stop further writes and
retain a durable pending plan. Recovery only reads broker evidence, never replays
missing orders. Partially filled protected stock Add cancellation is explicitly
blocked pending reconciliation rather than incorrectly reported successful.

Restored exact stock conIds use SMART only when advertised by IB, retaining the
primary listing. This fixes a route inconsistency; it does not establish why the
previous QQQ Paper orders did not fill.

85 focused offline tests pass: aggregate quantities, OCA partition, partial Trim,
resize/cancel, ownership and covered-call guards, unknown/restart reconciliation,
contract routing and shared entry/option/close regressions. These are mock results,
not broker acceptance. Backend changes require user-approved Wheel backend restart
before QQQ Paper validation. Gateway is not to be restarted. FUT/STK Live remain
closed; iOS workflow acceptance and native branch synchronization are outstanding.

## 2026-10-13 symbol-switch history admission recovery

Observed on the deployed Paper page: MNQ settled in 1.5 seconds; switching back
to QQQ left 1h at 9 bars while the other panes had data, then completed at 31.7
seconds. The shared history loader imposed a 30-second cooldown even when the
IB dispatcher explicitly rejected a read before execution. The 1h EMA seed
barrier made that delay visible as 3/4. Keep the seed barrier: removing it would
reintroduce the incorrect short-history EMA slope.

Development change: confirmed busy/unstarted history reads retry after two
seconds; optional indicator/execution reads wait until the chart group is ready.
Auxiliary context changes release their own history loading state, and stale
completions cannot release a new context's in-flight guard. Trading writes are
not retried. Main and auxiliary busy-history regressions pass with exact seeded
EMA values; symbol switching passes desktop/mobile and light/dark fixtures.
GitHub and Mini static assets were updated to 839f26d without a backend or
Gateway restart. The deployed page's next warm switch measured MNQ 1.52 seconds
and QQQ 0.51 seconds with all four panes ready. Cache state differs from the
31.7-second sample: these observations do not establish a cold-load guarantee.
The paired offline latency matrix remained comparable (four panes at 10Hz:
pre-fix p95 2–5ms, post-fix 2–5ms). Layout recovery, two four-pane pages, 100Hz
stress and eight distinct symbols passed without order writes.

Mini Git fetch diagnosis: no Git proxy configuration or proxy environment was
present despite the system proxy being enabled. Direct branch lookup/fetch
samples completed in roughly 2–4 seconds; explicit local HTTP proxy samples
exceeded 18–20 seconds. The original intermittent stall's network cause is not
proven. Repository-local lowSpeedLimit=1 and lowSpeedTime=20 were added after a
private configuration backup. Actual fetch then passed in 3.83 seconds and
matched the deployed commit. Use an external total deadline as well: low-speed
settings do not promise a total command timeout. No system/global proxy or
Gateway settings changed.

REA page observations were used, but the passive capture did not retain the
symbol-switch network requests. The 31.7-second measurement comes from direct
browser state sampling; do not present it as a captured TV implementation.

## 2026-10-13 RTH QQQ differential acceptance — incomplete

GitHub development/native branches and the clean Mini deployment were verified at
`7247996ce172ee26487fa4029fd92610c49c7eaf`. The selected session was verified IB
Paper with a stable account epoch. QQQ had no starting position or working orders.
Only a new isolated test group was used; no Live writes or service restarts occurred.

Broker evidence: a 100-share DAY LMT bracket was acknowledged, then an exact-snapshot
entry replacement changed the parent and both contingent exits to 120 shares.
Initial unknown responses were reconciled using reads only, never resubmitted.
No fills were observed. Cleanup was acknowledged; all three replacement orders
were Cancelled, the test group was done/inactive, position was zero, and there
were no pending broker orders. Raw identity-bearing evidence remains private.

Blocking code finding: protected STK entries use an aggregate bracket, whereas
protected FUT scaling requires per-unit lots. STK protected Add/Trim is not
implemented by that common path; the existing guard correctly disables it.
Do not enable it by relaxing the guard or treating a 120-share aggregate as one
futures lot. Actual stock fills, protection resizing after scaling, RTH stop
triggering and stock-specific recovery remain unverified. Stock/futures Live
activation and the final native workflow acceptance are NOT complete.

Focused offline validation: 47 tests passed across CoverageTests,
OptionAggregateTests, EntryEditTests and PricedChartCloseTests. A broader module
loader also discovered inherited ExistingPositionProtectionTests whose fixture
failed (15 failures/22 errors); those failures have not been repaired or dismissed
as production evidence. The focused pass does not replace broker acceptance.

# Project Handoff

## 2026-10-13 RTH 8h session-day correction

REA observed TV RTH 8h as one bar per regular session anchored at 09:30.
Wheel previously reused daily broker history, including futures settlement closes
and midnight timestamps. RTH 8h now aggregates 30-minute TRADES history plus
minute/live bars within the regular-session calendar. Daily/weekly/monthly paths
are unchanged. History is currently bounded to one month of intraday data.
Axis retains dates at day boundaries and 09:30 in the crosshair.
Offline chart/volume/stream tests, DST cross-period close regression, browser
axis check, 1-4 panes, two four-pane pages, 100Hz stress and layout/recovery
checks pass. Synthetic throughput remains consistent with recorded baseline.
Live broker comparison remains required after deployment; no trading writes.

## 2026-10-13 stable order editing controls

Pending type labels use LMT/STP. Entry controls retain DOM identity across
unchanged quote refreshes; actionable cells no longer enter long-press drag.
Local browser regression holds quantity down across 20 updates and 400ms, then
releases and verifies the popup opens on desktop/mobile. Existing confirmation
and Paper interaction tests pass; no broker orders used. Assets-only update.

## 2026-10-13 TV pending-label spacing follow-up

REA read-only screenshot of the open TV draft shows approximately 64px between
order controls and price axis. Wheel now uses 64px desktop / 48px narrow-screen
clearance, 24px cancel cell, 19px entry labels, neutral Discard and bright-blue
Confirm with an 11px gap before order details. Protection label content and
quantity confirmation semantics are unchanged. Desktop/mobile draft, discard,
confirm, stale-context, P&L and label avoidance tests pass with mock data.
This follow-up changes assets only and needs no Wheel or Gateway restart.

## 2026-10-13 quantity confirmation and price label spacing

Working-entry quantity changes now stage a local draft with Confirm / Discard;
TP/SL amounts use draft quantity at unchanged prices. Refresh preserves the draft
only for the same contract, account epoch, order reference and broker snapshot.
Quantity presets remain 1/2/3/4. Confirm uses the existing guarded edit request.
REA observed the user-opened TV quantity draft and matching confirmation controls.
Pending-entry labels join quantity, side/type and cancel; TP/SL styling is retained.
Order labels now leave 24px between controls and price axis. The current-price
DOM badge avoids order price badges without moving their actual price lines.

Fixed pending-entry price being overwritten by zero execution basis when historical
order groups exist. Execution basis now applies only to filled positions.
Mock entry-edit tests use explicit broker client/permanent identities, matching
the attribution requirement; 25 entry-edit, 108 Paper, 68 attribution and 65 frontend
tests pass. Browser checks cover draft/discard/confirm, refresh and epoch invalidation,
P&L, spacing/collision on desktop/mobile, existing Paper interactions and eight
exit-plan viewport/language/theme combinations. No real broker orders were changed.
Backend activation requires a Wheel service restart; iPhone installation was not done.

## 2026-10-13 compact pending-order labels

REA observed the user's visible TV pending entry and attached TP/SL:
`ev_a68ad0ab70a69759a04e1663a9ce2eddc5a43eb0efba346f6598ff70752e74bf`,
screenshot `ev_7e12f64a9d0d8815a50f27f67d446a9e83c734dec1b15d6a67bfbdc337e2617f`.
Wheel adapts the compact segmented labels: 21px visual height, lighter type,
joined protection cancel cells, no TP/SL information icon. The 44px drag surface,
price/quantity/order-type/cancel actions and broker reconciliation are unchanged.
Backend projection calculation and breakdown renderer remain available internally.
Eight exit-plan theme/language/viewport checks, Paper renderer and exact broker
edit/cancel regressions pass with simulated data and no actual orders.

## 2026-10-13 optional right-click submission and display settings

Chart display adds rightClickTrading, false by default. Only the desktop chart
context menu passes the opt-in to new-position Buy/Sell and 1–4 quantity choices.
It reuses submitPreview, the host UUID write path and existing broker/account,
quantity, protection, busy and unknown-outcome guards. The host also checks the
current setting. Panel Buy/Sell and the price-axis plus remain preview-first;
Add/Trim/Close confirmation semantics and Live asset gates are unchanged.
Selected Limit/Stop terms are submitted; fills are not guaranteed or converted
to market orders. No actual broker test orders were placed for this change.

REA inspected the user's open Trading settings dialog:
`ev_fedbd21d990a98056d412a5092576dcbad7740d1a24f168da54c8f112ea2df16`,
screenshot `ev_2c3f7deaff287b3459c86d029ae2109d979957d73c7677701bd3c4be05547127`.
The display layout adapts its general/appearance grouping, left checkboxes and
indented P&L units. Wheel retains only its existing controls; the explanatory
text is specific to right-click Buy/Sell. Immediate-save behavior is unchanged.
Desktop/mobile, English/Chinese and light/dark layouts are checked separately.

## 2026-10-13 per-pane view controls and tail following

Each pane now has compact maximize/restore and reset buttons above ATR. They
reveal only when hovering their small control area (or keyboard focus), not on
whole-chart hover. Touch devices keep an accessible visible target. Mac
labels use Option: Option+Enter or Option+click toggles the selected pane;
Option+R resets only that pane to recent candles and automatic price scaling.
Inputs and open dialogs do not consume these shortcuts. Auxiliary chart logos
and drawing-tool chrome stay hidden until maximized; restoring the grid hides
them again. Existing drawings, pane settings and main-pane attribution remain.

REA current-page evidence
`ev_e0235c7e9f34b4bcc4d4976bb8f28e6ea70dc089640f580838f20ba0b46eeb71`
matched retained TV bundles 762 (SHA256
`2732aebe665f0d01abb81089f4d3a24838e7bb0347ee68173adb6d49afb9ae36`)
and 62766 (`20550a5624197c012efcab64aaaa3d37382c44f6e9026bce3c6d7701c05282da`).
They expose per-widget maximize/restore, scrollToRealtime and new-bar range
shifting. User screenshots establish the two buttons and Option shortcuts;
this is source/UI evidence, not a replay of all TV interaction paths.

Wheel's corrected-history snapshot branch preserved an old range even when a
new candle arrived. Tail following now preserves the actual latest candle's
screen offset across new bars only when it was already visible. Browsing old
bars stays anchored. Same-candle ticks do no new viewport work. Reset uses the
actual logical coordinate rather than candle count, because indicator series
can extend the shared time axis. Quote transport and aggregation are unchanged.

Validation: per-pane browser interaction and tail/history regression, 65 frontend
checks, 1–4 pane and dual-page baseline comparison, repeated layout/recovery,
100Hz stress and eight-distinct-symbol workloads passed with no trading writes.
At 10Hz, four-pane apply p95 remained 5ms; dual-page maximum was 7ms versus
5ms baseline. These are local synthetic measurements, not IB latency claims.

## 2026-10-13 holding basis and compact protection labels

Runtime release `7b3bb36d023441c3b7470c8e8759a1e2bda503a4` is deployed to
Mini; rollback is `5b5ed285a72c5b54e8581fd5286d74913fa391f3`. Wheel-only restart
recovered, configuration was preserved, and normal reads cleared the old marker.
Read-only production Chrome verified all four MNQ panes and 183 hourly seed bars
with zero trading writes. GitHub web/iOS branches share this runtime release;
iPhone installation remains unverified.

Futures holdings without a local fill price now fall back to IB average cost
divided by the verified contract multiplier (stocks use one). Unknown multipliers
remain unknown; recorded fill/report precedence is unchanged. This repairs the
missing MNQ holding line rather than inventing a price from the current quote.
Read-only same-price broker orders share one quantity label. Persisted reference,
client, order ID and permanent ID identify TP/SL roles; external orders are not
classified by price. Editable orders retain separate identities and controls.
The shared iOS chart asset is updated; physical iPhone Run remains user-owned.

REA verified the loaded TradingView trading bundle against retained source hash
`7bedce64082b21c073f079fb5270e2d953ee5de1ff2f10ffeca62710386d3dbc`
(evidence `ev_02548b8160263b1e1009d68119d92707691d0f082dbdf7fa02c27f5e836fe75a`).
Its renderer separates quantity, text and action controls. No active TV position
was visible, so this is source evidence, not a live order workflow replay.

Authorized independent IB Paper MNQZ6 acceptance: buy 2, add 3, trim 1,
add 4, add 2 (10-contract cap), trim 4, close 6. Broker-confirmed position and
TP/SL quantities progressed 2/5/4/8/10/6/0; final group was done and flat.
Original positions/orders were not modified. QQQ buy 100 DAY LMT with protection
was PreSubmitted with zero fills during premarket; all three test orders were
subsequently canceled and the group is done/flat. QQQ actual fills and scaling
remain unverified. Neither Live futures nor Live stocks has been enabled.

The deployment preflight found a cancellation-only Close retaining its pending
marker despite all three broker orders being Cancelled with zero fills. Flat
Close now clears it after position reconciliation; status reads recover legacy
markers only from confirmed terminal orders, never replaying writes.

Validation: 65 frontend checks, 118 offline backend checks, desktop/mobile broker
label identity and holding renderer checks. Mock checks are separate from the
broker evidence above. Additional broker acceptance after deployment: independent unprotected MNQZ6
short 2, add 1 to short 3, trim 1 to short 2, close 2. Each broker outcome was
read before the next write; the final account/group position is zero with no
working orders. Partial-fill/race and actual stop-trigger
acceptance remain outstanding; this is not blanket order-channel certification.

## 2026-10-13 hourly EMA seed and Paper futures scaling

Read-only MNQ RTH evidence reproduced seven fast hourly bars yielding EMA20
30893.7215875 with a positive last slope, versus 31010.4015091 with a negative
slope after 176 earlier bars. Auxiliary snapshots previously shared a mutable
array with the renderer, so prepending history could bypass its historical-reset
check. Snapshot handoff now copies the array; immediate delta delivery is unchanged.
The web hourly EMA waits for at least max(100, 5 * period) seed bars, requests
bounded/retried history through the existing owner path, and shows loading while
prices continue. Late auxiliary history requests check contract/period/session.
A real read-only four-pane preview now matches the full-history EMA calculation.

REA current Tradesea evidence
`ev_3ba6417b9eb557ce5160cda73abcf1c60e0d4d1c5fd02594ce85cfd8bf8d689f`
identifies the same TradeScreen-ciiZNcao.js/main-DeEIo2vj.js reference bundles.
Retained client code limits partial-close quantity to position size and guards
repeat submission; it routes full quantity through closePosition and partial
quantity through an opposite-side order. This does not establish its server-side
protection guarantees. Wheel keeps its own grouped broker-confirmed lifecycle.

Owned, reconciled futures without TP/SL now use the existing unprotected Add/Trim
path, with the 10-contract total cap, exact position guards, reserved trim quantity,
outside-RTH flag and partial-Add cancellation of only the remaining quantity.
Paired protected futures retain their existing per-lot bracket path. No existing
external position is newly adopted. Stock/option policies and Live gates remain.

Validation: 179 offline order regressions, 63 frontend checks, renderer plus
full-page delayed-history EMA regression, eight desktop/mobile EN/ZH theme panel
checks, multi-pane/two-page latency and layout/reconnect checks. Browser checks
block trading writes. Paper was verified; actual test orders await the user's
specific contract, maximum quantity and permission to close the test position.
No futures/stock Live enablement or actual order acceptance is claimed.

## 2026-10-13 complete cold-start restoration

Bare /superchart now restores the saved active contract, interval and session;
an explicit valid URL contract wins. Old partial saves recover a valid contract
from another pane. Auxiliary reads wait until the root context is initialized.
A cover exists in the initial HTML, stays until all selected panes paint, and
shows a working instrument chooser when no contract can be restored. Slow
loads expose the same chooser without revealing a partial layout. Existing
stream delivery, account gates and order behavior are unchanged.

REA evidence `ev_00c79fc3c7ce0fb6cf1ce220bef243398683ca4ee6b60551bf65b224d09e90d5`
confirms the currently loaded TV layout bundle SHA matches the earlier retained
source `ev_1f744bc99761235fe3d7f4ce2ff0b205c2ca713122775a24f9adc8d858f63fa0`.
Its loadContent restores chart contents, layout and synchronization preferences
before initializing widgets. This is code evidence, not a replay of TV login.

Eleven offline cold-start scenarios cover 1–4 panes, auxiliary active, partial
saves, direct-link precedence, unlinked symbols, missing/null storage, invalid
URL and chooser completion. Panel/crosshair and indicator browser checks plus
63 frontend tests pass. A read-only real MNQ preview restores four live panes
when returning from the contract URL to bare /superchart; no order writes.

## 2026-10-13 auxiliary axes and panel edge handle

Cold-start auxiliary panes default their price axes to the left, including a
saved active auxiliary pane. Main axis preferences and in-session axis edits
remain intact. The web trading panel toggle moves from the header to a compact
right-edge toolbar-style arrow, with an 8×26px rounded tab when collapsed.
There is no visible text label; localized accessible labels remain. A reserved
16px edge keeps the collapsed expand tab permanently visible off the price axis.
The main/auxiliary column boundary now supports pointer dragging and keyboard
resizing, saves a bounded ratio per layout and hides in single/maximized views.
Existing panel preference, ticket fields and chart frame identities are retained.
REA current viewport evidence: `ev_167285eaa01e079f84788dab723f8b77e0dcb0206f69acc53513703ad8b5d4f2`.
The final tiny arrow follows the user-provided drawing-toolbar screenshots,
not the larger order-pad tab in the initial REA viewport. No order behavior changes.
Crosshair routing now uses direct same-origin calls, with owner-aware clearing
and OHLC readout updates (the library does not emit crosshairMove for programmatic
positions). Missing candle intervals clear rather than clamp to stale history;
chart periods and visible ranges remain independent. REA script evidence
`ev_99b778f205e414400e59984f8d824b273a031742fc8b5375a74ee1a0d43a8077`
shows Tradesea timestamp/price mapping and separate viewport synchronization.
TradingView evidence `ev_1f744bc99761235fe3d7f4ce2ff0b205c2ca713122775a24f9adc8d858f63fa0`
confirms separate hovered/external cursor state, plus-menu visibility only on the
hovered chart, change-only view invalidation and requestAnimationFrame painting.
Wheel now gates order cursors and publishing on local pointer ownership; follower
repaints cannot show the plus control or echo into the group. OHLC layout runs on
bar changes, not every vertical mouse pixel. In a read-only real MNQ 4-pane
preview, 81 updates measured 0.2ms p95/0.3ms max synchronous group dispatch; this
measures handler work, not display latency or equivalence with TradingView.
This is source evidence, not an observed end-to-end reference gesture comparison.
Browser checks cover desktop/mobile, English/Chinese, dark/light, cold axes and
panel preservation using mocked data and no broker writes. Current quantity-menu
checks and 63 frontend tests pass. The legacy context-menu fixture omits the
shared add-orders module and fails identically at baseline; the current
context-quantity fixture loads that module and passes all eight cases.

## 2026-10-12 Paper recovery and Profit input

Cold chart owner reads now serialize within each page and recheck cached data,
preventing four-pane startup from exhausting the three read-admission slots.
Normal realtime SSE delivery is unchanged. TP/SL adds Profit, default 300,
using total position amount in contract currency before fees on web and iOS.
The final channel rule uses confirmed NY 09:30–09:35 B1 Close from cached
minute bars across all panes; it does not reproduce conditional Pine resets. See `CHART_FOLLOWUP_2026-10-12.md` for evidence
and test scope. User Runs the phone app manually; no real orders were tested.

## 2026-10-12 chart orders, panel and device synchronization

User authorized GitHub/Mini deployment after local checks and iPhone source
synchronization; user will Run the iPhone app. Never use real orders as deployment
verification. Retain Wheel Buy/Sell preview/confirmation and existing close policy;
do not add account-wide Flatten All.

Live standard USD options now use `live_options_scope`: both entry sides,
multi-contract LMT/STP and optional TP/SL, plus reconciled TP/SL/Add/Trim/BE/Close.
The original exact-account gate, coverage/cash checks, quantity ceiling and
unknown-outcome fences remain. Quick sizes are 1/2/3/4. Old-server
`live_initial_scope` remains restricted in clients for compatibility.

Web right-click/price-plus quantities enter a preview, not a direct write.
The panel can collapse without recreating chart frames. Cold-start auxiliary
panes keep current-frame dynamic EMA20, ATR and FVG; other indicators default off,
while main-pane settings remain. In-session manual choices are not reset.
Four-pane synchronized symbol switching retains each pane's interval.

Validation: 59 frontend tests; isolated backend execution/fault/recovery tests;
eight-case browser matrices for Live management, context quantities, panel
integration, cold-start indicators and symbol synchronization. Native simulator
build and 100 focused tests passed. Physical iPhone Run and actual broker fills,
partial fills and stop triggers are not certified by these mocked checks.
See `ORDER_BUTTON_COMPARISON_2026-10-12.md` for REA evidence and exact scope.

Preserve the accepted refresh release below. No price aggregation, stream
transport, Gateway/routing or account configuration changes are part of this
order/UI release. Mini's Live option capability switch was already enabled.

## 2026-10-12 planned chart-stream renewal

Chart transport lease expiry now emits an explicit renewal event after releasing
admission. The browser reconnects its shared contexts immediately and requires a
new snapshot; genuine failures retain bounded backoff and epoch/sequence guards.
Cache immutable New York calendar-day identities for EMA/FVG calculations with
a 24,000-entry bound. No quote throttle, new IB owner or execution-policy change.

Exact isolated release candidate: 55 frontend and 171 offline regressions passed.
Four-pane renewal replay improved from about 1.07 seconds to 2–5 milliseconds;
this is synthetic loopback timing, not broker latency. The wider paired matrix,
stress, distinct-symbol and recovery checks passed during local validation.

Passive runtime evidence places the main half-second cadence upstream of Wheel:
Gateway trade bursts around 0.50–0.53 seconds, with normal Mini handling measured
in milliseconds. Active upstream networking showed about 223–241 ms RTT and
out-of-order traffic. Network versus IB farm batching remains unresolved; do not
claim a fixed IB throttle or Tradesea-equivalent real-feed performance. The user
has deferred upstream tuning near market open and authorized Pro/Mini refresh
synchronization via GitHub. Preserve Gateway, routing and account settings.
See docs/TICK_REFRESH_INVESTIGATION_2026-10-12.md for evidence and limitations.

User-authorized deployment: refresh code 6c7e488a synchronized through GitHub to
Mini, Wheel restarted around 21:14 Asia/Shanghai, Gateway/config unchanged. A
real read-only MNQ four-pane renewal took 89–377 ms to receive replacement
snapshots, with all panes Live. No trading writes were used.

## 2026-10-12 Inactive evidence correction

Do not classify IB Inactive alone as cancellation, rejection, or replay permission.
Chart state normalizes it to Unknown; protection remains unknown even when a
position snapshot is flat or the ambiguous child is contingent on an entry.
Remove Inactive from cancellation/replace/close confirmation and group retirement.
Legacy persisted Inactive terminal rows and request results are rechecked rather
than trusted after restart. Missing orders remain Unknown. Permanent-ID/reference
conflicts cannot overwrite group ownership. Unknown group evidence cannot release
an uncertain request. Explicit operation errors do not establish old-order death.
No market/UI changes and no expansion of the unshipped Live policy work.

Seven new regressions fail on 87fbb39 and pass with this patch; 153 affected
order/entry/broker/Live-policy tests pass in an isolated clean candidate. The exact
16 deterministic tests from round two pass separately. Counts overlap.
Round two actually filled one entry and an amended original TP via Close, with
explicit sibling cancellation; that was not a natural TP/SL trigger. Round three
must separately observe an unchanged target or stop before claiming that branch.


## 2026-10-12 first MNQ ETH / Paper acceptance loop

Verified Mini bed4c69, Paper identity and MNQZ6 conId 815824267 before writes.
A separately identified one-contract, nonmarketable limit entry completed submit,
identical-UUID duplicate, price amendment, cancel and identical-UUID duplicate
cancel. IB order 59 ended Cancelled, zero fills and zero position. Initial submit
returned unknown, then a read observed Submitted; no new UUID retry was sent.
HTTP operation durations were 247 / 12 / 223 / 453 / 10 ms respectively.
Existing orders were outside the test group and were not modified.

Real ETH browser observation covered 1/2/3/4 panes and two pages with four panes
each. New-trade receipt-to-SSE enqueue p95 was 13–24 ms; eight-pane repeat 20.5 ms.
Browser data-application p95 was 2–5 ms (eight-pane 3.9 ms). These are separate
stages, not exchange-to-screen latency: clock alignment, physical presentation,
and native iPhone display were not measured. Heartbeats with unchanged trade
counts are excluded from new-trade latency. UI/layout and market code unchanged.
REA passive runtime evidence: ev_51e15d7e4fe65c411fccb52806f923a1f44a7c670526f8cdbe9b3b3f881a7e3a.

Minimal order fix: capture clientId and permanent broker order identity before
amending and require both for acknowledgement. Previously a same-number/ref,
different-client or different-permId snapshot could confirm the wrong order.
A fault regression reproduces that false acknowledgement; the corrected clean
candidate passes 137 order/entry-edit/Live-policy tests. Existing unshipped Live
policy changes are excluded. No iPhone bundle update or Live action.

Reference: official NautilusTrader a10f7b8521f664428ab7dec24a4898d0a68f4d3e,
crates/adapters/interactive_brokers/src/execution/order_state.rs lines 25–125.
Remaining: Inactive after a rejected amendment is not necessarily terminal
(updates.rs lines 1594–1640); Wheel's broader terminal-status handling needs a
separate durable-state regression/fix before Live readiness. Partial fills,
TP/SL triggers, multi-group fill races, actual Gateway disconnect/restart and
RTH option behavior were not triggered in this first loop. Do not claim them
accepted from offline tests. Account-switch transient 503 was observed and
recovered; it was not used as evidence for an unrelated market-path rewrite.


## 2026-10-11 validated market and order recovery release

Preserve the existing UI and serialized IB owner. The deployment scope includes
Lightweight Charts 5.2.1 (verified vendor SHA-256), bounded per-page SSE multiplexing,
eight active contract sources, incremental OHLC delivery, cached volatility work,
and historical-volume provenance. It does not certify complete live trade volume.

Order recovery now persists cancellation intent before broker transmission,
mutually excludes amendment/cancellation claims, preserves unknown outcomes without
replay, deduplicates execution identities and handles conflicting/corrected fee
evidence conservatively. A follow-up fixes Unknown -> Submitted after a persisted
cancel: the UI remains canceling until terminal broker evidence. Right-click
single-unit Close now keeps its chosen limit price through host dispatch and backend
submission; plain Close retains its existing behavior. No Live policy expansion is
included. The older local Live management allowlist work remains unshipped.

Fresh offline/browser validation: 168 protected-foundation tests, 111 focused order
fault tests, 221 close/protection/scaling/policy regressions, 51 JavaScript tests, lifecycle,
volatility and actual right-click browser routing. Counts overlap across suites.
The matrix with eight cached fake order-status checks per tick passed 1/2/3/4 panes,
two pages, eight distinct symbols, 200-tick bursts and reconnect/layout changes.
Dual-page 10Hz max update gap was 103ms, apply p95 2-7ms; 100Hz p95 4-10ms.
These are synthetic local measurements, not broker/network/physical-display claims.
Stress assertions now cover both pages rather than silently skipping dual-page data.

REA 6.4.0 reused the retained public Tradesea worker analysis rather than repeating
it: parent ev_3d5cc80a4ec6ac6cb1577caf442db80d6fd9547372baa0b768b7341a9a4b901c;
trading module view ev_3b06c4644792ae1947c86b8b659b29b8972b01b337bf35ed25bc30ee9931d6fa;
asset view ev_b9ef6275e1f710b923d1dc3f54654d1481ce164d815ab55fefc342d2a818e038.
Static public worker evidence supports isolated connection state, stale-connection
handling and jittered reconnect. It does not establish server-side idempotency,
execution reconciliation, or a license to copy proprietary code. Wheel retains
its own durable UUID/intent mechanisms and licensed chart engine. Public source:
https://tradesea.ai/blog/UnderTheHood and app.tradesea.ai public assets.

Mini preflight verified Paper on 4002, no unresolved local writes or unpersisted
chart requests, and one existing processing order. Preserve it, all saved chart
groups, local configuration and account selection. Back up privately before the
nullable cancellation_pending migration and restart only Wheel, not Gateway.
No Live writes, test orders, account switch or iPhone installation are included.
Market-open Paper fills, partial fills, TP/SL triggers, real Gateway recovery and
physical-device acceptance remain outstanding before a Live-readiness claim.


## 2026-10-09 Live Orders refresh guard

Allow only POST /api/options/check-orders through the option-only Live legacy
endpoint guard: this reconciles broker status and does not submit/cancel orders.
Account epoch validation still applies. Other legacy mutations remain blocked.
Account-profile and Live-policy tests pass (16 tests).

## 2026-10-09 pending-entry cancel visibility / Live option gate

The Close control remains visible for active groups with zero filled position.
Editable pending entries use the existing guarded edit_entry cancel path; filled
positions retain Close. Browser mock checks cover visibility and cancellation.
User explicitly requested activation of the existing option-only Live capability.
Keep the current standard USD option, one-contract CC/CSP limit-entry scope; do
not widen assets/actions or place verification trades. Mini profile provisioning
is local-only and must not enter Git. Real Live fills remain unverified.

## 2026-10-09 independent pane indicators and weekly history

Each layout pane now stores its own display configuration, including option ATR.
Indicator controls in inactive panes select that pane before handling the action.
Defaults hide auxiliary volatility content; individual settings may enable it.
15m/1h auxiliary panes asynchronously backfill when their span is under seven
days. History is retained across snapshots and live deltas; auxiliary pan-to-load
is supported. Failed or short history responses retry with a 30-second cooldown.
Mock checks cover per-pane visibility, settings dialog routing, reload persistence
and at least seven days of backfilled data; layout regression also passes.

## 2026-10-09 auxiliary channel table

Distance table is shown only in the main layout pane (right in 3/4-pane layouts,
first in 1/2-pane layouts). Focus changes do not enable tables in small panes.
Auxiliary gauges and channel lines are also hidden. All volatility channel
content remains confined to the main layout pane, including after focus changes.

## 2026-10-09 responsive symbol changes

Symbol and interval/session transitions cancel outstanding main-pane finite market
reads before requesting the new context. Retired responses remain context-guarded.
The symbol sync label is English-only. Mock symbol-switch-speed delays the old
contract by four seconds and verifies the next contract renders within 1.5 seconds
and is not overwritten afterward. Account/layout-link regression passes.

## 2026-10-09 account transition and optional pane links

Layout menu now persists independent opt-in symbol and RTH/ETH links. Explicit
changes in the active chart propagate only the enabled property; pane intervals
stay independent. Enabling a link immediately aligns the other panes.
Account identity/verification changes abort old reads, invalidate account state
and clear holdings/executions while retaining dimmed candles until replacement.
Auxiliary reads restart concurrently without empty snapshots. Desktop rendering
retains time anchors and manual price bounds for same-chart generation changes.
Mock account-layout-sync covers Paper/Live/unverified recovery, concurrent reads,
retained viewports, independent defaults, on/off links and persisted settings.
No broker account switching or trading writes were used for verification.

## 2026-10-09 immediate same-page drawing operations

Drawing-change messages forward idempotent pending operations directly to loaded
same-contract panes. Receivers merge without resetting tool selection/preferences
or reconfiguring chart data. Active gestures defer peer application. Origin saves
start server synchronization immediately; the existing three-second recovery poll
remains for external devices. Operations are deduplicated and cleared on context
changes. Mock offline-server tests observe add/delete in all panes after 150ms.
Local two-client tests pass union, deletion, stale import protection and new lines.

## 2026-10-09 SVG screenshot coordinates

Before html2canvas capture, direct-body SVG overlays are rasterized using live
viewport dimensions and original viewBox, then substituted only in the clone.
This prevents left-axis FVG/PV/drawing overlays shifting during SVG image export.
Pixel regression covers 535/1100px charts and both price-axis sides. Previous
capture fails the compact left-axis case (background at expected FVG center);
new capture passes all four. Live drawings and chart data are not modified.

## 2026-10-09 split chart image capture and ATR alignment

Copy image (including Cmd/Ctrl+Shift+S) composites all visible chart frames at
the current grid geometry and device scale. A maximized view excludes hidden
peers. Existing clipboard permissions and success/error UI remain in the source
frame. Desktop compact ATR keeps the main chart bottom-center anchor with smaller
type instead of inheriting the native mobile raised position. Native unchanged.
Browser capture checks assert all four renderers contribute and PNG dimensions
match the grid; composed PNG inspected and layout regression passes.

## 2026-10-09 crosshair feedback guard

Only crosshair events with a native sourceEvent are broadcast to peers. A pane
with the actual pointer inside its plot rejects peer coordinates; pointer exit
clears peer cursors. Regression holds the source pointer stationary while follower
programmatic crosshair changes and quote updates occur, asserting no source
callback or peer position assignment. Maximize/restore icons match the requested
top-right and bottom-left orientation.

## 2026-10-09 toolbar grouping

Favorite toggle joins the instrument control. Toolbar right side orders session,
then layout / selected-pane maximize / workspace fullscreen, with a separator
between session and view controls. Maximize moves out of the footer; behavior
and shortcuts stay unchanged. Layout and narrow instrument-picker checks pass.

## 2026-10-09 refresh status layout stability

Transient market-status messages now overlay the workspace rather than adding
and removing a row above the grid. Status toggles must preserve every pane height
and manual price range; ordinary new-bar scrolling remains unchanged. Maximize
uses the requested opposite-corner icons and Option/Alt+Enter in the host and
chart frames, excluding editable fields and open dialogs. Browser layout checks
cover repeated status toggles, shortcuts and all-pane maximize/restore.

## 2026-10-09 selected pane maximize

Footer expand/restore button temporarily fills the chart grid with the selected
pane. Peer iframes retain their dimensions and data while hidden; restore returns
to the same layout. Layout selection exits maximize; single-chart mode hides the
button. No iframe recreation or trading writes. Four-pane browser regression
checks each pane fills the grid and restores geometry with unchanged instances.

## 2026-10-09 multi-pane startup

Verified account discovery immediately starts all ready panes instead of waiting
for the auxiliary two-second timer. Initial reads prefer epoch-scoped immutable
latest packets (800ms timeout), falling back to finite history requests on cache
miss. The main initial request also waits for a verified epoch. Healthy SSE
behavior is unchanged. Mock browser tests cover warm startup with zero history
requests and cold concurrent history fallback plus existing focus regression.
Network/broker responses may still complete at different times; no loaded chart
is hidden while another pane waits for data.

## 2026-10-09 linked crosshairs

Desktop panes of the same contract share cursor price and time, mapped to the
containing bar in each interval. Programmatic updates do not echo or activate
the trading pane; leaving the plot clears peer crosshairs. Different contracts
are excluded. The price-axis gear uses a 20px hexagonal SVG in a 28px button,
centered within the axis width on either side. Browser mock tests cover pointer
movement, clearing, unchanged focus, and button geometry.

## 2026-10-09 remove duplicate pane headers

Removed the extra symbol/timeframe strip above each pane. The chart retains its
own title and selected-pane outline; clicking inside the chart selects it.
Layout regression uses actual chart clicks and checks full-height frames.

## 2026-10-09 layout focus follow-up

Pane activation now rebinds the host to the existing iframe; it never swaps or
recreates panes or clears candle data. The old pane becomes read-only and keeps
its bars, drawing context and viewport. Focus regression cycles all four panes,
asserting unchanged iframe windows, no empty packets, and preserved timeframe,
time range and manual price range; contract/quantity routing remains covered.
RTH-only volatility channels are filtered on ETH charts and when the latest bar
is outside RTH, including historical sessions in longer-timeframe side panes.
The price-axis menu also has a visible gear button beside the time/price corner.
Browser checks remain mocked and do not constitute broker execution acceptance.

## 2026-10-09 web chart layouts and price-axis side

The RTH toolbar now has a four-choice layout picker: single, equal columns,
two stacked left plus a large right pane, and three stacked left plus a large
right pane. Stacked layouts use 1:2 column widths. New panes start with the same
instrument; the four-pane defaults are 1m/15m/1h left and the current 5m chart
right. Clicking a pane transfers the existing trading host to that pane's
contract/session/timeframe. Auxiliary renderers cannot submit trading actions.
Each pane can subsequently select its own contract. Layout, pane intervals and
price-axis sides persist in browser storage. Closed auxiliary panes stop SSE.

Right-clicking a price axis offers Auto and Move scale to left/right. This uses
the library's actual series scale, with plot-to-document coordinate conversion
for drawings, indicator overlays and labels. Switching sides preserves the time
range and a manually set price range. Shared native assets retain the existing
right-axis default; the menu and layout controls are web-only. No phone install.

Mock browser checks passed for four layouts, candle rendering, active-pane
contract/CC quantity, restoration, narrow toolbar, read-only auxiliary panes,
axis side/labels/drawing anchors, fractional Fib across timeframes, channel
rendering, holding labels, and existing picker/CC quantity behavior. The older
web-stream.cjs test still times out looking for #order-direction; the same failure
was reproduced with the pre-change host JS, so it is not a passing regression
check. No broker orders were placed, amended or canceled. Real multi-pane live
market throughput remains to be observed during trading hours.


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

## Web chart contract daily P&L (2026-10-05)

Trading's right-hand header now shows the exact selected conId's IB `dailyPnL`,
account-scoped and including all order groups for that contract. It follows IB's
instrument-specific daily reset, not local calendar midnight. The metric is in
account base currency; `BASE` is shown if the ISO currency cannot be established.
It is not an account-total or a sum of lifetime realized/unrealized values.
Missing, unset or older-than-15-second values show an em dash, including when IB
does not publish P&L for a contract no longer present in the account.

The web chart opts into P&L on its existing quote request. Up to four subscriptions
reuse the serialized Gateway connection, with account/contract/epoch isolation
and disconnect invalidation. No new polling request or trading write is added.

Design: lieflat-charts G18 (Glance gallery, “H1 revenue, drawn in one stroke”)
number/label hierarchy adapted to the requested existing header. L3 requires
multiple observations; F2 requires a time series; F11 requires a target/range.
Those inputs are absent. Only G18's numeral hierarchy is used: Mono signed
numbers, existing theme tokens, no fabricated sparkline or counting animation.
The narrow header request takes precedence over a standalone template card.

Source: https://interactivebrokers.github.io/tws-api/pnl.html
Validation: `tests/test_chart_pnl.py` and `tests/chart/daily-pnl.cjs` cover missing,
zero, negative, stale and invalid values, account/contract switching, reconnect,
subscription limits, and English/Chinese light/dark at 393/850/1440px.

## Web chart push (2026-10-05)

The browser now uses the same `/api/portfolio/stock-chart-stream` SSE endpoint as
native iOS for supported intraday intervals. Healthy streams replace chart polling;
changed bars go directly to the shared chart renderer even while a trading write
is waiting. Order reconciliation remains separate and never replays writes.
An eight-second packet watchdog, bounded reconnect backoff and snapshot-first
sequence validation recover lost streams. Hidden/unloaded pages close subscriptions;
contract, interval, session and account-context changes discard old callbacks.
Unsupported higher periods retain snapshot refresh, and disconnected streams use
snapshot fallback. P&L is read independently every five seconds with its own expiry.
The existing backend limits (two streams and one active chart contract) still apply;
SSE does not imply an unfiltered exchange tick feed or upgrade market-data entitlement.

Verification: 433 Python tests; browser stream regression (deltas during pending
writes, gap recovery, old-timeframe isolation, no write replay); lifecycle watchdog
and account-context tests; existing web order/Live-isolation/responsive regression;
and P&L freshness, contract/account, Chinese/English and light/dark checks passed.
All automated trading interactions in these browser checks use intercepted mocks.

### Closed-contract P&L retention

The chart now persists authoritative IB commission-report realized P&L by account,
exact conId and execution identity in `chart_realized_executions` in the existing
local database. Corrections replace older execution revisions; duplicate reads do
not add P&L twice. Pending commission reports suppress partial totals. Once the
broker position is flat, the card reads **Realized today** and uses this retained
execution total instead of expiring the last open-position daily P&L. Open positions
keep the original IB daily mark-to-market figure. No order is submitted by this path.

The realized basis is explicitly distinct from IB's configurable portfolio reset:
CME-family futures use 18:00 America/New_York session boundaries; other contracts use
New York calendar dates. Currency is the commission report currency, with mixed
currencies withheld instead of guessed. The tooltip identifies basis and date.
Only broker reports available to this API connection can be recovered initially;
subsequent reads preserve them across browser refreshes and backend restarts.
This is not an import of historical account statements. No-trade/missing-report
states remain unavailable, not zero. Regression: 440 Python tests passed, including
persistence, deduplication, corrections, pending reports, scope and session rollover;
a read-only mocked browser check verified the realized label, amount and reload.

## Desktop priced adds and event-driven P&L (2026-10-05)

The plot's price plus is restored; only mouse movement into the actual right
price-axis pane hides it. Native touch behavior remains unchanged. The plus and
context menu share one desktop priced-add choice/confirmation path. A held long
position permits Buy Limit/Buy Stop, a short permits Sell Limit/Sell Stop; opposite
side entries are disabled. Quantity comes from Add/Trim and is editable in the
confirmation. The backend validates the exact group reference, side, tick, limit,
and unchanged TP/SL before creating independent unit brackets at the selected
LMT/STP price. Existing protection is unchanged; target prices must lie between
current TP/SL. Pending adds are marked on the chart and included in Orders. Further
adds wait for outstanding parents to resolve. The existing market Add stays intact.
Unknown outcomes retain the request lock and are never resent automatically.

Web SSE opts into cached contract P&L. IB pnlSingle events trigger a packet even
without a price tick, without another IB request or nested event-loop drain.
Periodic execution-ledger reads still preserve realized values after flattening;
an older HTTP response cannot overwrite a newer pushed value. The broker's P&L
publication cadence remains the limiting source, not a synthetic tick valuation.

Verification: 448 Python tests; browser plus/context payload parity, plot/axis hover,
stale preview rejection and pushed P&L checks passed. Includes long/short adds,
old protection retention, contingent protection counts, invalid prices/identity,
and lost-response non-replay. Broker acceptance of priced adds is still outstanding;
no orders were placed, amended or canceled by this maintenance verification.

### Add-order cancellation, multiple pending adds and quantity policy

Supersedes the preceding pending-add and ten-contract restrictions: the user
explicitly removed the aggregate add cap. Market and priced adds accept positive
integer quantities including 20, even with existing acknowledged, unfilled unit
parents. Uncertain/pending-cancel or incomplete protection states still block
unsafe changes. Initial-entry limits are unchanged by this add-specific request.

Each pending unit add now exposes a chart cancel button and a scrollable ticket
list with exact order IDs, so overlapping prices remain individually reachable.
`cancel_add` validates account, conId, group reference and the recorded unit parent;
it sends at most one cancellation for that parent and never directly cancels its
children. Cancellation is confirmed only after broker parent/child outcomes arrive.
A fill wins the race and retains protection; timeouts remain unknown and GET
reconciliation resolves them without another write. Confirmed canceled units no
longer block another add. The add preview now uses a styled responsive modal with
quantity, price, TIF, TP/SL and existing pending quantity, plus dark/light treatment.

Verification: 458 Python tests, including repeated pending adds above ten, exact
single cancellation, other-unit protection retention, canceled-unit reuse, filled
cancellation races, unknown-response recovery, identity rejection and non-replay.
Browser mocks verified repeated priced adds, no quantity max, per-ID cancellation,
and popup rendering. Actual broker cancel/fill race acceptance is not claimed.

### Browser trading sounds

The user's supplied filled/cancelled/rejected/disconnected WAV assets are served
locally under static/audio. The current chart observes confirmed broker state:
filled quantity/new executions, confirmed cancellations, rejection and verified
connection loss. Initial snapshots and replayed history are silent; a fill takes
precedence over its simultaneous OCA cancellation, and repeated packets do not
repeat the announcement. Request rejections also produce rejection feedback.

Sound is enabled by default with a persisted Sound on/off header control. Browser
user-gesture activation is required; no stale sounds queue before activation.
Muting stops queued sources. Node transition tests and a browser AudioContext mock
verified initial silence, event classification, OCA priority, audio loading,
gesture activation, mute and preference retention without broker writes.

## 2026-10-06 protection cancellation and native rejection recovery

New chart TP/SL children use GTC independently of the entry TIF. Existing broker
orders are not migrated. Chart TP/SL handles and native Orders offer paired
protection cancellation with explicit confirmation, exact group/reference checks,
and broker reconciliation. Filled positions remain; pending entries must finish
or be canceled first. Unknown cancellation outcomes are reconciled without replay.

Native confirmed application rejections clear the current write lock. Unknown
responses retain it, while opportunity navigation, refresh, and chart access remain
available. Settings exposes manual reviewed-outcome recovery for legacy Paper locks.
Validation: 467 backend tests, native simulator suite, and mocked desktop/mobile
chart lifecycle checks. Broker cancellation and GTC overnight persistence still
require actual Paper observations; no existing protection orders were changed.

## 2026-10-06 / AllYouNeedIsWheel 1.4: optional TP and SL

The chart entry preview on web and iOS now has independent TP and SL switches.
Omitted/null legs create no order; zero or invalid enabled prices are rejected.
TP accepts distance, absolute target price, or entry-premium profit percentage.
For short options, 2.12 at 75% profit previews a 0.53 buyback before fees, rounded
to the contract tick. Preferences remain separate by asset class and client.
New exits retain GTC independently of entry TIF. OVT remains entry-only.

Each chart exit handle cancels its selected role; a separate explicit operation
removes all exits. Broker-side OCA effects are reported from the next snapshot,
never silently repaired. Manage TP / SL can replace or add exits to settled,
fully owned chart positions. It requires the exact group reference and order
snapshot, blocks unfinished entries/foreign working orders, confirms old exits
are terminal, and checks fresh positions and fills before sending replacements.
A fill during cancellation stops replacement. Unknown requests are journaled
and reconciled on reads without replay, including after restart.

Protection replacement explicitly discloses a cancellation gap. Paired new
standalone exits share an OCA group with proportional reduction/blocking;
only the last order transmits the group. See the [IB OCA documentation](https://interactivebrokers.github.io/tws-api/oca.html).
Retired order IDs/permIds remain available for accounting and reconnect recovery.
Single-leg/no-exit positions use the reconciled Close path. Add/Trim remains
available only for the original unit brackets with both exits confirmed covered;
rebuilding protection currently disables unit scaling. BE requires a working SL.
Pending entries remain blocked; see the existing-position follow-up below for holdings without chart entry groups.

Validation uses mocked broker responses, shared-chart browser interactions across
desktop/mobile, English/Chinese and light/dark, plus native simulator tests.
Actual Paper fills, OCA reduction, single-leg cancellation behavior and GTC
persistence still require broker acceptance. No broker write was made for tests.
Validated locally: 484 backend tests, 125 native simulator tests, optional-exit browser checks and order-interaction regressions. Deployment uses the GitHub commit on Mini; physical-device installation follows these gates.

The unrelated legacy `mobile-preview.cjs` drawing-toolbar fixture times out on
its Horizontal ray locator on both the pre-change chart and this revision;
it is not included in the passing trading-interaction checks above.

## 2026-10-06 existing-position TP follow-up

The first 1.4 implementation omitted management for holdings without a chart
entry group. The read-only broker snapshot now exposes a position-specific
management reference and exact quantity/cost snapshot. Explicit Apply claims
that holding only after checking all clients' open orders and rereading the
position. No synthetic entry order is created. TP-only shorts place a GTC BUY
limit for the actual remaining quantity; SL remains optional. The editor starts
with TP enabled and 75% as an editable suggestion, and never submits on opening.
Broker cost basis may include fees and option/futures multipliers are required.

The persisted starting quantity plus owned exit fills drives later replacement,
close, and reconnect checks. Outside position changes, competing groups (even
with uncertain writes), and existing working orders block a second claim.
Standalone exits now carry protection identity in Orders despite having no
parent entry ID. Tests cover adoption, stale snapshots, foreign orders, partial
fills, quantity changes, no replay after lost responses, and Paper/Live isolation.
No existing broker order was changed during validation.

Follow-up validation: 497 backend tests and 125 native simulator tests passed, plus existing-position and existing chart lifecycle browser checks.

## 2026-10-06 account-switch connection follow-up

Native Settings now completes profile verification and portfolio loading as one
operation. Temporary bootstrap failures receive bounded read-only retries; success
requires the requested mode and verified account epoch, then returns Settings to
Portfolio. The always-visible Connect button is removed. Connected is a status;
failed attempts expose Retry connection. Submitting an edited backend address
also connects. Account-selection writes are not automatically replayed.

Validation: 497 backend tests, 127 native simulator tests, and the shared-chart
browser lifecycle/isolation/responsive regression passed. New mocked connection
tests cover temporary bootstrap failure, wrong epoch/mode, exhausted retries,
and absence of trading writes during recovery. Device build passed. No actual
Gateway account switch or broker order was performed for this verification.

## 2026-10-06 drawing price-axis labels

Analysis drawings now expose their price levels through native right-axis labels:
horizontal rays and price/arrow marks, geometric anchor/boundary prices,
long/short entry-stop-target prices, and Fibonacci levels. Text and freehand
annotations do not add price labels. Labels update on edits and are removed when
drawings are hidden, deleted or replaced by another chart's drawing set. They
never create order lines or broker writes. Native labels use series precision.

Verified mobile/desktop price labels, dragging, Fib values and lifecycle cleanup;
timeframe drawing/edit regression passed. Physical iOS build passed.
The older drawing-cancel-fib browser fixture still fails its final normal-context-
menu assertion on both this revision and the unchanged prior drawing script;
its cancellation/Fib assertions pass before that point. This is not counted as
a passing regression check.

## 2026-10-06 TP/SL ticket visual refresh

Removed the custom latest-price horizontal line from the shared chart while
retaining the right-axis current price/countdown. Web TP/SL controls and the
position protection editor now use matching cards, compact switches, and aligned
mode/value fields. Checkbox sizing overrides the generic full-width trade input
rule. Existing IDs, optional-exit behavior and submission logic are unchanged.
Browser optional-exit checks passed across mobile/desktop, English/Chinese and
light/dark; desktop screenshot reviewed. No broker writes used for validation.

Follow-up: Fibonacci retracement/extension retain their existing inline prices
and no longer duplicate those levels on the right axis. Other drawing labels
remain enabled. Native simulator regression passed (127 tests), alongside shared
chart lifecycle and optional-exit browser checks for the ticket refresh.

## 2026-10-06 SL input modes

Web stop-loss controls now match TP with Distance, Target price and Loss % modes,
including the position protection editor. Percent uses entry/broker cost basis,
not account equity; shorts add the loss percentage and longs subtract it.
Calculated targets use contract price increments and shared chart validation.
Mode and value persist per security type. Native configurations without slMode
retain distance behavior. Browser regression covers long/short percent math,
absolute wrong-side rejection, invalid zero targets and submitted position SL.
497 backend tests and optional-exit mobile/desktop, language/theme checks passed.

## 2026-10-06 cursor price badge

The selected-price badge now matches the compact reference: a 20px outlined plus
cell, separator and right-aligned grouped price on a near-black background. The
price cell is visual only; the plus retains the existing order-menu action and
the axis retains its interactions. Grouping applies only to the integer portion,
preserving contract tick precision. Price-menu interaction regression passed.

## 2026-10-06 session-specific Bar Count defaults

ETH now defaults Bar Count off while RTH retains its existing default on. Web and
iOS persist independent session preferences so manually enabling ETH does not
change RTH. Indicator reset uses the current session default. Verified web
settings defaults/independent overrides and physical iOS build. The unrelated
session-scroll-header fixture reports its header `below` assertion false against
the unchanged chart HTML; it is not counted as passing validation.

## 2026-10-06 right-click priced trim

The sidebar Trim retains its current bid/ask exit behavior. Opposite-side limit
choices in the shared plus/right-click menu now open a quantity confirmation for
a limit trim at the selected price. Selecting the full remaining size closes at
that limit. Stop-triggered priced exits are explicitly unavailable in this pass.

The backend validates the expected reference and signed position, then amends
only selected filled-unit TP limit orders, retaining their IDs, parent/OCA fields,
paired stops, and the other lots. It never creates a separate opposite entry.
Pending entries, unreconciled protection and unsupported older/non-unit groups
retain their existing blocks. Existing adjustment reconciliation tracks fills
and uncertain acknowledgments without replaying writes. Pending priced exits
must settle before another adjustment. No broker orders were sent for tests.

Validation: long/short target-price and quantity tests, full exit, stale position,
unchanged stops/other lots and request deduplication; shared menu/browser payload
checks and 127 native simulator tests passed. Device build passed. Actual broker
Paper acceptance of priced trims remains outstanding.

## 2026-10-06 pending trim chart visibility

Read-only Paper verification found the user's one-unit priced trim acknowledged
and working at the broker; the chart had omitted its distinct price because it
only rendered the common TP. State now exposes acknowledged working adjustment
exit rows, and the shared chart renders independent Trim/Close quantity labels.
Repeated snapshots update in place; filled/canceled exits and chart/account
changes remove stale lines. No broker write was made for this display repair.
503 backend tests and pending-exit rendering/lifecycle checks passed.

## 2026-10-06 combined TP projection and independent trim dragging

TP Sigma sums realized exit P&L from actual unit fills and projected P&L for
remaining TP/trim quantities at their current targets. Each unit uses its own
entry fill and contract multiplier; values exclude fees. Missing fill basis
produces an unknown amount instead of an invented zero. During dragging the
preview recomputes immediately. A trim drag submits the exact exit order ID,
original price/quantity and group reference; remaining TP amendments exclude
units reserved for trim. Targeted amendments do not enter the generic price
coalescing queue. Snapshot drift rejects the amendment; no replay is performed.

The TP/SL ticket cards now sit side by side with abbreviated badges. Add follows
position direction, Trim purple, and BE the SL color; disabled controls fade.
505 backend and 127 simulator tests passed, plus optional protection variants,
aggregate amount, drag payload and line lifecycle browser checks. Real broker
amendments were not exercised; existing user orders were not modified for tests.

### TP aggregate reconnect correction
- Recover per-lot filled quantities and weighted execution prices from deduplicated broker fills when completed-order status fields reset after reconnect. Missing completed entry evidence renders unknown rather than a zero profit.
- Backend unittest suite: 507 passed; includes reconnect fixtures for stock and option protected lots. Validation uses mocks and read-only broker state, no order writes.
- Add color verified in sync(): positive position blue, negative position red.

### Position ticket synchronization and Trim controls
- Filled-position TP/SL cards default to broker target prices, convert distance/percent including signed breakeven stops, preserve unfinished edits through unchanged polling, and submit explicit per-card Apply amendments. Confirmed chart edits refresh the cards. Existing Manage TP/SL handles adding/removing protection.
- Trim drag now listens for actual document pointer release and tolerates lost capture plus refresh. Added an explicit cancel-plan dialog: amend only that unit back to the current ordinary TP (or its saved original TP), retain SL/OCA, then remove its Trim designation. Unknown restores reconcile without replay.
- Validation: 511 backend tests; 127 native simulator tests; browser ticket tests across mobile/desktop, language/theme combinations; Trim lost-capture/refresh/cancel checks; full web order lifecycle and Live isolation passed. Device build succeeded. No broker orders changed for testing.

### Position TP/SL commit on editing completion
- Removed Apply buttons. Enter or blur commits a changed, tick-normalized target; Escape restores the confirmed value. Empty/invalid values restore the confirmed value with feedback. Mode-only changes and unchanged targets do not write.
- Avoid transiently disabling held-position inputs during polling, which could otherwise blur an unfinished draft. Existing write confirmation/unknown-outcome handling remains in use.
- Browser tests passed for desktop/mobile, English/Chinese, light/dark, draft focus across polls, signed stops, Enter-plus-blur deduplication, unchanged target and Escape; full web order lifecycle and Live isolation also passed. This change is web-only; no native binary or broker order was modified for testing.

### Multiple working Trim plans and Trading clarity
- Confirmed working Trim units are reserved separately from ordinary protected units. Add can proceed while Trim works; another Trim uses only unreserved filled units. Aggregate adjustment state preserves every prior plan, original order identity, and paired stop. All-reserved positions retain a separate ordinary TP basis for new Add protection.
- Each Trim remains independently draggable/restorable. Lost acknowledgement of a subsequent Trim reconciles its exact broker IDs and target price without replay; prior plans survive. Unknown/rejected exits still block further allocation.
- Web displays working exit plans, available Trim quantity, projected total meaning, operation-specific disabled reasons, and order-group versus contract-position scope. Buttons state Market / Quote limit / Entry ± 1 tick. Filled positions hide entry-only controls; Close labels its actual path. Cancellation tooltips distinguish entry, protection, and Trim plans. Native Trim quantity limits honor reserved units.
- Validation: 517 backend tests, 127 native simulator tests, shared Trim gesture/multiple-line tests, complete web lifecycle/isolation, desktop/mobile and language/theme ticket checks, plus visual inspection passed. Physical-device build succeeded. Tests made no broker writes; real multi-plan fills and stop/OCA races remain for Paper acceptance.

### Aggregate stop-exit outcome
- Added sl_projection: realized exits in the current lot group plus remaining units at their acknowledged stop prices. Shared chart displays SL Σ, including positive locked-profit scenarios, and previews aggregate changes during SL dragging.
- Uses recovered executions and per-lot entry prices; requires stop coverage to match the current position. Missing/canceled stops or unsupported trailing-order price representations yield unknown rather than treating a trailing distance as a stop price. Does not enable an automatic trailing strategy.
- 519 backend tests, 127 native simulator tests and shared-chart SL aggregate/drag tests passed; physical-device build succeeded. Amounts exclude fees and assume fills at the displayed stop price; actual trigger fills remain subject to Paper acceptance.

### Independent pending Add price edits
- Split the Add chart control into a draggable price label and a separate cancel button. Document-level pointer release tolerates capture loss; refresh, contract/account changes and fills invalidate stale gestures.
- amend_add verifies the exact group, owned pending unit parent, original price/quantity, zero fills and paired protection. It edits only the LMT price or STP trigger while preserving type, quantity, children and order identity. Unknown outcomes reconcile exact broker state without replay.
- 523 backend tests, 127 native simulator tests, desktop Add drag/fill-race tests, mobile Add/cancel tests and priced-order web tests passed. Physical build succeeded. Broker writes were mocked; live Paper amendments were not exercised against user orders.

### Foreground quote recovery independent of account reads
- The IB owner publishes immutable, account-scoped chart snapshots. A bounded HTTP-only endpoint reads these without entering the serialized broker queue; expired packets return unavailable, retaining actual IB tick timestamps and delayed/waiting labels.
- Web foreground/focus reads immediately, checks at 250 ms during the first 1.5 seconds and every second afterward, and keeps healthy SSE connections. Slow bootstrap reads run separately; late snapshots cannot overwrite newer prices. Context/account changes invalidate pending read results. No write retries were added.
- Validation: 547 backend tests passed, including cache-only tick callbacks, blocked-executor HTTP reads, immutable tail/full snapshots, expiration and account isolation. Mock browser foreground recovery with an 80 ms quote response and 3-second account reads measured 88-95 ms; this is controlled test latency, not a guarantee of broker tick arrival.

- The cache-only recovery path also attaches to owner-thread tick callbacks before SSE reconnects; it can publish while ordinary IB reads yield. Controlled cache-warming retry recovered in 491 ms despite a 3-second legacy read.

- Live-page testing exposed 3-second recovery outliers when no new ticks arrived during a slow IB read. A 200 ms owner-event-loop heartbeat now publishes already-received state while that read yields, independent of queued pulses and ticker events. It performs no broker requests and retains quote/tick freshness fields. A dedicated event-loop regression covers this quiet-market case.

### Cold MNQ chart history timeout
- User video and Mini logs showed blank first-load charts after repeated 5-second IB historical-data cancellations. Cold history now has a 15-second budget, coordinated with 20-second initial SSE/bootstrap waits; established-stream watchdog and fast quote reads retain their short recovery intervals.
- Keep the concrete bootstrap error visible until valid chart data arrives instead of replacing it with a generic reconnect message.
- 548 backend tests, cold-stream watchdog regression and web quote recovery tests passed. Tests do not submit broker orders.

### Continuous stream stutter follow-up
- Live capture observed a 4.8-second server emission gap alongside recurring history-request timeouts. Removed automatic historical backfill/retry from the live stream pump; cold initialization and explicit older-history paging remain available.
- Quote events no longer reconfigure the complete trading/indicator UI unless contract metadata changes. Order updates and user edits still synchronize immediately.
- 549 backend tests passed. Browser checks cover 100 continuous updates with only one configuration pass, foreground recovery, trading lifecycle, and 1,000 tail updates plus immediate first-trade rollover without a full series reset. Real feed gaps are not disguised with synthetic candles.

- Follow-up live observation still found stalls from ordinary chart reads and multi-timeframe indicator history. Intraday chart GETs now default to the warm read path. Indicator history requests run as bounded tasks on the same IB owner event loop and return cached/partial frames immediately; at most two requests per chart are in flight. They never create another IB connection or trading worker. 550 backend tests passed, including pending-history nonblocking behavior and indicator value/session tests.

### Restore price-order controls after fast chart optimization
- Root cause: cold chart initialization skipped market rules; subsequent fast reads returned before loading them, while the removed history-maintenance path had previously supplied them. Empty price_rules suppressed both axis and right-click order controls across instruments.
- Broker contract/market-rule metadata now loads asynchronously on the existing IB owner loop, independently of history, with bounded requests, single-flight per chart, retry and retired-state rejection. Metadata arrival triggers an SSE update even without a new trade. No guessed price increments or trading-write retries.
- 551 backend tests passed; browser empty-rule-to-valid-rule recovery restores both entry points without reload. Verification uses mocks/read-only state, not broker order submissions.

### Compact templates and immediate quantity edits
- Indicator settings now have a footer Template menu, direct saved-template application, defaults and a focused Save as dialog. Existing browser templates remain compatible; same-name saves explicitly offer Replace. Dark/light and English/Chinese desktop/mobile checks passed.
- Chart quantity +/- and presets commit immediately; typed values commit on Enter/blur, with unchanged-value deduplication and invalid-input restoration. Working entries retain exact reference/snapshot, editability and busy checks, and close after dispatch. Preview edits stay open. No Apply step or automatic write retry.
- Entry edit/fill-race checks and settings integration tests passed using mocks. Native source shares the chart change, but no iPhone binary was installed and no broker orders were submitted for validation.

### Original multi-unit entries versus Add overlays
- Futures/options initial units share entry/entry_N roles with later adds; the chart had incorrectly treated every suffixed entry as Add. Persist entry_kinds by broker ID for newly created groups and expose the intent on order rows. No-position initial units use the aggregate entry control; partially filled original units retain Entry labeling. Legacy unclassified pending units are labeled Pending rather than asserting Add.
- Pending-entry TP/SL amounts use entry-price projections instead of an empty filled-position aggregate. No broker writes were made during diagnosis; the user's queried two one-unit parents were already Cancelled.
- 552 backend tests and chart add drag/cancel/fill-race checks passed, including original-unit versus actual Add classification.

### Order lifecycle audit and fast working-entry dragging
- Mouse dragging now starts after 3 px on direction, quantity, type and cancel segments, without the previous 350 ms hold. Preserve grab offset, retain gesture identity across polling/capture loss, submit once on actual release, and cancel on focus loss. Touch keeps its hold gesture. Subsequent intentional clicks remain usable.
- Original partially filled multi-unit orders expose every remaining parent, including the first unit, as Entry rather than Add; exact owned pending units can be amended/cancelled while filled-unit protection is retained.
- Close first reconciles pending parent cancellation, includes an Add filled during that race, and checks actual position against protected units before exits. Unknown outcomes remain locked; status reconciliation never replays closing writes.
- Open protection estimates refresh when price rules arrive without overwriting input drafts.
- Validation: 559 backend tests passed. Mock browser regressions cover fast dragging across four segments, capture loss, focus loss, submit/cancel clicks, latest-intent amendments, independent entries, Add/Trim overlays, protection editing/cancellation and flat recovery. An unrelated legacy mobile drawing-preview fixture still targets an unavailable Horizontal ray button; excluded from order acceptance. No broker orders were submitted, and actual fill/race acceptance remains pending. No iPhone Run/install. Quote delivery behavior was preserved.

### Paper confirmation and restart acceptance
- Normalize MKT unset prices; retain uncertainty for transient broker states and resolve via authoritative reads without write replay. 561 backend tests passed.
- MNQ Paper stable pending bracket survived a real backend/API restart with identical three order IDs, prices and quantities. New pending-confirmation response also reconciled against IB. Both test brackets cancelled and final flat verified. See docs/acceptance/2026-10-07-mnq-paper.md for evidence and remaining gates. No Live or iPhone Run.

### New-order Bracket master switch
- Stocks/options default off; futures default on. Per-asset master preference is separate from retained TP/SL leg choices and values. Turning the master off strips protection from new submissions only; existing exits remain managed through Manage TP/SL.
- Web mock browser checks cover defaults, retained values, one-leg selection, reload, responsive layout, zero writes on toggles and entry-only submit. Native source parsed only; no iPhone Run/install or broker test orders for this UI change.

## 2026-10-08 Orders history responsiveness

Executed records previously filtered the full history again inside every row's
first-day lookup, repeatedly parsing dates and causing quadratic main-thread work.
ExecutionHistoryPage now creates one linear projection and precomputed headings,
deduplicates row identities, and displays 50 records per page with Load more.
Search, date and asset filters still cover all history; no records are deleted.
ISO8601FormatStyle parsing also replaces per-record formatter construction for
fill dates used by sorting and display. New tests cover 10,000 records, page
continuity, filtering, duplicate IDs and New York day boundaries. Simulator suite:
129 passed. The 10,000-record projection measured approximately 8 ms locally;
this is not physical-device screen latency. Phone installation remains deferred.

## Native trading sounds (2026-10-08)

The iOS foreground app now bundles the same four WAV files as the web chart.
A single app-wide observer consumes the existing synchronized orders/history;
page changes do not create duplicate observers. Confirmed fills use FillTracker's
monotonic quantities and broker identity handling. Cancellations/rejections require
confirmed state, never disappearance. Initial/account-switch snapshots and resume
history are silent. Fills take priority over cancellation in the same snapshot.
Confirmed write rejection and connection-loss transitions also provide feedback.
Settings and chart controls share a persisted sound preference. Backgrounding stops
queued playback; the iPhone silent switch is respected. Background push delivery
is not implemented, and no broker order was sent to verify audio.

## CC BE and action availability (2026-10-08)

Explicit BE can now create a standalone stop for a settled owned option position,
using broker basis and directional tick rounding; short calls buy back on the stop.
Default option entries still have no protection. The stock CC reservation guard
remains stock-only. Shared action hints disable Add at exhausted call coverage,
limit stock Trim to free shares, and block covered-stock Close/BE. Hints use the
existing broker cache; fresh authoritative checks remain on writes.
Web and native consume these hints and quantity bounds. A BE-only aggregate
option position can now Trim using a retained stop plus an equal-quantity OCA
stop/exit slice. IB type-2 blocked OCA reduces the slice on partial fills; a full
Trim cancels only its paired stop. Stop replacement first confirms cancellation
and unchanged actual position. Missing members stay unknown and never replay.
Cancellation-only recovery releases the request without submitting replacement
orders. Concurrent Trim is disabled until the active exit resolves.
Validation: 651 backend tests, including full-coverage CC BE creation and request
deduplication; native simulator build and JS syntax passed. No new broker order,
physical iPhone install, or native runtime interaction acceptance for this change.

Protected Trim follow-up: 656 backend mock tests passed, covering equal-quantity
OCA construction, partial/full fill snapshots, stop-first and cancel outcomes,
old-stop cancellation races, missing members and read-only restart recovery.
Actual IB OCA execution remains pending Paper acceptance; no real fill is claimed.

Right-click Trim follow-up: remove the stale paired-protection-only UI restriction.
Unprotected stock/option Trim now accepts an explicit LMT exit_price; market Trim
is unchanged. BE-only priced Trim uses the OCA path. Whole-position exits remain
Close actions for these paths. 657 backend tests passed; direct execution of the
menu availability function covers unprotected, BE-only, paired, blocked and busy
states. JS syntax passed; no broker write or physical-device installation.

Trim click/display follow-up: the menu was enabled but choosePriceOrder still
silently required scalable paired protection. Route every reducing LMT click
through chooseExit, where current availability is rechecked. Standalone limit
Trim rows now populate pending_exits and display on the shared chart; legacy
TP-plan edit/restore controls are disabled for these distinct order rows.
Add/Trim quantity now reuses Position's minus/input/plus layout and respects the
largest currently allowed adjustment bound. 657 backend tests passed. Isolated
Playwright actual menu-click, confirmation, limit request bridge and pending-line
checks passed for unprotected and BE-only states (standalone-trim.cjs).
Read-only Paper snapshot showed short 3 with SL 3 at 1.59 and no pending Trim;
no user request was replayed and no broker write was sent for this fix.

## Standalone Trim editing and multiple plans (2026-10-08)

Standalone limit Trim supports exact-identity price amendment, quantity editing,
and cancellation via zero quantity. Quantity edits reconcile cancellation and
unchanged fills/position before rebuilding owned exit plans; preserve other plan
prices and full stop quantity. Unknown writes remain locked and reads never replay.
New protected Trims consume only unallocated standalone stop quantity, preserving
existing OCA slices. Stops are explicitly transmitted (the earlier transmit=False
member was observed stuck PendingSubmit in Paper). The existing unknown Paper
request was NOT retransmitted, canceled or rebuilt during this code change.
660 backend tests and browser menu/quantity-editor interaction passed. Actual IB
multi-plan and edit fill/race acceptance remains outstanding. No phone install.


## 2026-10-09 Paper history recovery
Paper account/API stayed online while US history requests timed out across QQQ
stock, option and MNQ. Backend reconnect did not recover it; Paper-only IBC cold
restart restored bars without restarting Live. Exact IB internal cause is unknown.
Added passive timeout evidence and bounded Paper-only watchdog; no quote polling
or order retries. Live, permission/empty results and uncertain local writes are
excluded. Recovery is latched until successful fresh history; 30-minute cooldown,
maximum two attempts per rolling day. Mock tests cover guards. Do not deliberately
break the working Gateway for fault-injection acceptance.


## Trading holding edge cue parity
Read-only holdings already clamped an offscreen average-price badge to the pane
edge. Active trading holdings suppress that overlay and previously hid their
controls outside the viewport without an edge cue. Added an independent passive
arrow/price badge for active positions, shared by Paper and enabled Live; no
trading capability or autoscale changes. Browser regression covers long/short
offscreen cues, return into range, hidden holdings and flat cleanup, zero writes.
Web and native share the chart asset; phone installation remains deferred.

## CC quantity isolation and chart polish
Reset new-ticket quantity on contract/group/account changes and after completion.
Call defaults use backend cached unreserved standard-CC capacity (stock shares
minus short calls and pending sell reservations); 400 free shares defaults to 4.
Zero/unknown coverage defaults to zero rather than inheriting stock size. Manual
input survives polling; active-order quantities and Live scope limits are retained.
Execution still revalidates coverage. Quote snapshots expose capacity without new
broker requests. Web preview/Join require positive quantity.
Web default viewport shows 40 recent bars with 5-bar right margin; manual view
updates remain preserved. Toolbar spacing separates controls, normal status moves
to connection tooltip, and fully missing option quotes show one empty-state label.
Trade panel layout unchanged. 30 history tests plus quantity unit/browser and
holding browser checks passed; browser verified 400 -> 4 and manual 2 retention,
zero order writes. Native shared chart source changed; phone installation deferred.


## Default viewport rollback
User reported slower chart loading after viewport polish. Restored web initial
range to 50 recent bars plus 10-bar right margin. Retained CC quantity fix and
other unrelated changes. The reverted change only adjusted rendering bounds;
no causal claim that it caused broker/network latency. No backend restart needed.


## Unified web instrument picker
Toolbar search, Options and contract dropdown now share one dialog launcher.
Existing stock/futures search and option dates/strikes/resolve handlers are reused;
favorites, intervals, session and fullscreen remain outside. Contract label is
compact with full title tooltip. Browser mock covers stock and option flows,
narrow layout and zero writes. No chart data loading or execution logic changed.

Toolbar follow-up: center primary instrument/favorites/interval controls across the
chart toolbar using equal side tracks; keep RTH/fullscreen right. Favorites closed
width 125px, native menu retained. Narrow layouts wrap to prevent overlap.

## Volatility channels and intraday extreme gauge (web first)
Ported the newly supplied Pine channel formula, fixed per-RTH-session levels,
TQQQ 3x leverage, first-hit memory/distance display, and exact ES/NQ probability
arrays. Four settings groups: Volatility Channels, Volatility Symbols, Intraday
Extreme Gauge, Gauge Colors. Explicit asset families gate rendering; option
contracts and unrelated stock symbols are excluded. Broad Pine substring matches
are narrowed to exact supported ticker/root names to avoid unrelated symbols.
Gauge uses New York bar time and only ES/NQ families. Channel session is the
source default 09:30-16:00 NY; partial-day data never substitutes for opening.

Optional index history starts asynchronously after primary bars, uses the same
IB owner event loop, caches for 60 seconds, has bounded waits, and is canceled
when its chart expires. Current-day intraday close falls back only to a prior
daily close. Unavailable index data is labeled, never fabricated. Canvas overlays
do not affect price autoscale. Hit alerts are in-chart only, not external pushes.
Native phone installation/settings integration deferred per web-first preference.
Formula and browser tests cover mappings, leverage, arrays, DST, partial sessions,
no daily lookahead, render/cleanup, zero writes; backend tests cover async cache.
Live broker index availability is separate from mock calculation/render tests.


## Volatility visual and latency follow-up
Restored original Pine Unicode channel labels and two-column distance table,
including row order and hit typography. Price-axis channel values now have opaque
colored badges; stale unavailable notices clear when levels become available.
Index intraday/daily history fetches run concurrently and publish each completed
part; pending web results poll sooner, and primary bars trigger optional loading
without awaiting it. Completed index caches are reused across chart states on the
same connection only, qualification is reused, and transient errors retain data.
Calculation and browser tests plus async progressive/cache-isolation tests passed.
TV MNQ1! and IB MNQZ6 are different contracts/feeds; numerical equivalence of their
opening/index inputs is not asserted. Native installation remains deferred.


## TV overlay styling parity
Aligned the distance table nearer the top-right with centered cells and Pine-sized
text; reserved space for high/low axis labels. Historical session channel labels
now persist, align vertically with their lines, and clip before the price axis.
Channel axis numbers use grouping separators and right alignment. Gauge segments
are contiguous with Pine-like dimensions. No history requests or viewport changes.
Formula and browser layout/cleanup checks passed. Screenshot-derived channel
centers differ by 34.75 between MNQ1! and MNQZ6; do not hard-code TV prices.


## Native volatility synchronization
Added bundled volatility module identical to web, native bridge using complete
merged chart bars, account/context-scoped optional index reads after main bars,
and four persisted settings groups plus template save/restore. Symbol gating
matches web; options/unrelated stocks do not request index history. No plot-level
unavailable banner. Recent badge, table and logo/gauge placement fixes included.
Small screens use compact gauge and lower table to avoid header/ATR overlaps;
the same responsive behavior is included on web. Simulator build and 390px
browser bridge/render checks pass; asset verified in built app. User will Run
manually: no installation, launch, physical-device or broker trade test performed.


## Cross-device analysis drawings
Web and native share contract-ID-scoped annotations via /api/chart-drawings, stored
in ignored chart_drawings.db on the backend. No IB calls or order endpoints.
Both clients use the same drawing module and poll every three seconds while
visible and idle; native uses a dedicated HTTPS session/bridge. Existing local
drawings import once when opened, local preferences remain local, pending edits
persist locally across failures. Idempotent per-object operations preserve unrelated
edits; deletion tombstones prevent stale imports resurrecting lines. Concurrent
edits retain a conflict copy; stale deletion cannot erase a newer edit. Same conId
shares across Paper/Live and intervals, different expiries/conIds stay separate.
Python tests cover merge, replay, deletion, conflict and validation; two-browser
clients cover web/native-message transport, merge and delete propagation. Native
Simulator build passes and unused rows warning removed. User installs/Runs phone.
