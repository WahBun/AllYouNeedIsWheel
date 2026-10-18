## 2026-10-18 — position-based default price axes

In two-, three- and four-pane web layouts, left-column panes now default to
left price axes and right-column panes to right axes. Single-pane defaults to
right. Active trading host changes and maximize/restore do not change that
rule. Reordering/recreating panes recomputes automatic defaults. Explicit
axis menu choices use a separate per-pane override and survive reload and
layout changes. Old saves did not distinguish automatic/manual sides, so
legacy saved sides adopt the new position defaults once.

REA reuses the deployed-page capture
`ev_ca6c83f3d93053f3f70897a5df371c51b1af9aa250adf4483d12896dda624adb`.
Both captured scripts still exactly matched the starting checkout:
chart-layout SHA-256 `ee2747ffa5101380567a547f2b2543fdecfceec6c28e4e15c7b53f52e7ac495f`,
superchart SHA-256 `3a050b943cf46b13e88b79029529c049f06be44e8da4657564fcd90798990209`.
Its role-based auxiliary-left initialization explained the inverted two-column
default and stale sides after reordering. The new position rule is the user's
requested behavior, not a claim about TradingView defaults.

Four actual-host scenarios pass: desktop/mobile widths, light/dark, initially
active left/right panes, every layout, repeated activation, maximize/restore,
manual changes on active/inactive panes, reload, persistent overrides and
continued synthetic ticks. Two active alert lines are included per pane.
Seven refresh scenarios pass (1/2/3/4 panes, two four-pane windows and 6000-bar
history): all 23 pane observations receive 30/30 steady ticks, preserve the
200-tick burst extremes and measure source-to-apply p95 of 2–8 ms, within the
preceding 2–8 ms range. Repeated layouts, reconnect and visibility recovery pass;
price-axis menu/anchors, shared Plus-button state and One-click/Confirm entry
regressions also pass. These are local synthetic checks, not broker acceptance.
A read-only Mini check still reports clean commit
`cec405947e1e4da672b25feeaece415e7cf8d045`.
No production deployment, restart, physical-device Run or broker write occurred.
This batch changes only web host scripts: **Deploy only**, then refresh the page;
no iPhone Run is needed for this axis-default change. Prior native alert changes
still require the user's Run if not yet installed. Existing signing/localization
edits are preserved outside this commit.

## 2026-10-18 — alert drag, axis labels and shared magnet

The user corrected the report: iOS editing works; only web drags snap back.
REA inspected the deployed four-pane Wheel page, then a same-version Chrome
replay exposed `lostpointercapture` before actual release. Alert gestures now
follow document-level movement/release; capture loss alone does not cancel or
save. Explicit cancellation, account/contract changes and stale-alert guards
remain. The protected order gesture implementation is unchanged.

The user's final color choice is pale orange. The sweep is wider (45%, clamped
to 180–640px), softer and slower (18 seconds instead of 5). Six shared-chart
web/native touch cases pass including forced capture loss and held-refresh
checks; the old gesture implementation fails the same regression. All four
protected order-drag regression scripts pass. No broker writes were used.

The alert label now sits beside the price axis, mirroring on left-axis panes,
with room for High/Low badges. Alert dragging reuses the existing drawing magnet
algorithm (Off/Weak/Strong, Command temporary mode, touch radius and hysteresis)
with separate gesture feedback and a snapped-point ring. REA captured the
current deployed magnet source before this change; see PRICE_ALERTS_AND_PUSH.
Four additional axis/magnet browser cases and the current Fib interaction
regression pass. Legacy drawings.cjs stops at a removed toolbar entry before
its checks; no pass is claimed for that outdated script.

User-operated follow-up: **Deploy only**, then refresh the web page. iPhone Run
is needed only to update native chart assets. Mini was clean at
`cec405947e1e4da672b25feeaece415e7cf8d045`; no deployment/restart was performed.
A user screenshot confirms real iPhone receipt of the Wheel Bark test banner,
but not locked-screen display or a real price/fill/cancellation event. Existing
signing/localization edits remain uncommitted and are excluded from this change.

## 2026-10-18 — draggable pink alerts and Bark lock-screen notifications

Standalone price alerts now render in matching panes as hot-pink dashed lines
with a slow light sweep, hover/touch labels, price editing and Stop. Drag release
saves through account/contract/version checks; stale edits restore server state.
Changes reset the live-price baseline and exclude pre-edit queued samples.
Ray alerts retain their original drawing association and drag behavior.

The user chose Bark instead of paid Apple enrollment. The alert editor's
**Phone notifications · Bark** section enables a private per-account device key,
queues a test and disables delivery. A fixed HTTPS POST endpoint, stable event
identifier and the existing durable outbox handle price/fill/confirmed-cancel
events without new Python dependencies. Full setup, data disclosure and REA
evidence are in `docs/PRICE_ALERTS_AND_PUSH.md`. Actual phone receipt is pending
the user's registration and locked-device test.

Verified: 119 backend checks; real chart UI at desktop/mobile widths in both
themes; native touch bridge; stale edits, multi-pane sync, Bark setup/test/disable;
existing alert entries, toast and protected order-drag checks; Simulator build.
Seven synthetic market cases with two visible alert lines cover 1/2/3/4 panes,
two four-pane pages and 6,000 bars: all 30/30 samples per pane, p95 2–8ms, and
the 200-tick burst retains OHLC extremes. Repeated layouts and reconnect pass.

Read-only Mini check: clean at `a778eac2859bb9145b00a55534e43e6da54bfe0f`.
The user should choose **Deploy & Restart Backend**, refresh the webpage and
configure Bark. The native chart change needs the user's iPhone Run; receiving
Bark notifications itself does not. No deployment, service restart, Gateway
operation, real broker write or external notification was performed. Existing
signing/localization edits remain excluded. Notification timestamps use a new
separate table so the previous alert table layout remains compatible with rollback.

## 2026-10-18 — chart-only notifications, hover drawing rail and iOS daily change

Notifications now live inside the chart grid's top-right corner. The prior
`aside` inherited the trading sidebar's background and 14px padding, producing
a 350x28px dark strip even with zero notifications. A transparent `div`, an
explicit empty state and chart-relative positioning remove that strip and keep
cards out of the trading panel. Cards dismiss after five seconds (hover pauses).

Hovering the existing lower-left logo previews the drawing rail with an upward
reveal. Leaving the combined logo/rail/menu area closes an unpinned preview;
clicking the logo or a tool pins it. Explicit close, keyboard activation and
normal touch toggling remain available. Hover does not save drawing state.

The iOS navigation title now includes daily percentage change from accepted
current-contract/current-account last price and previous close. It reuses the
existing display-only reference endpoint every 15 seconds; chart packets still
update the numerator immediately. Green/red depend on the displayed sign,
rounded zero is neutral, and absent/expired data remains unavailable. Backend,
account, contract and foreground checks prevent reuse across contexts. No
executable-quote, order or price-delivery semantics changed.

REA evidence: current TV page inspection
`ev_d1ef4a0efee4e9ed4e9908cbebc4977f2b833749087b3592388d01cce09170a7`
and screenshot `ev_549bd5f880a1cdf10b0282a5835a17e5736826955f32e3d62344aaee42d464bc`.
The user's video establishes the horizontal logo-wordmark reveal; the upward
rail and click-to-pin behavior are the user's requested adaptation. A live hover
probe was inconclusive while the user operated the same reference tab; no claim
is made about TV's internal animation or pinning implementation. Wheel live-page
inspection `ev_edc2ec629e7f483875443d9d9916d86dc264002772efa7678ffc61ba9c879132`
and a separate DOM/style probe confirmed the empty notification container's
exact strip geometry and inherited background/padding before the fix.

Verified locally: actual-host alert/editor and toast tests at 1440/393px in both
themes, empty-state/placement/five-second dismissal, hover/pin/leave/keyboard and
native touch-mode checks, drawing history/peer isolation, and seven synthetic
market cases including 1/2/3/4 panes and two four-pane pages (30/30 samples per
pane; source-to-apply p95 1–9ms; 200-tick OHLC extremes retained). The native
percentage helper passed sign/zero/missing/freshness/context checks. Simulator
build succeeds; physical iPhone visual acceptance remains user-operated.

Read-only SSH verification found Mini clean on `codex/chart-labels-1.7` at
`218f22ce4d26b42987472bd542a476496b8f131d`. This batch needs Deploy only plus a
browser refresh; the iOS changes need the user's iPhone Run. If the earlier push backend has not yet been deployed, its
separate dependency/restart requirements still apply. No deployment, backend
restart, Gateway operation or broker write was performed. Existing signing and
localization edits remain excluded.

## 2026-10-18 — shared price-axis Plus button switch

The price-axis Plus button is now one shared preference across primary and
auxiliary web panes. Both the axis menu and Chart display settings update every
pane immediately, including hidden/recreated panes. Reload prefers the saved
shared value over stale per-pane copies. Toggling from an auxiliary menu no longer
activates that pane; other per-pane settings and trading routing remain intact.

REA inspected the actual open Wheel page and its loaded host/layout scripts:
ev_68229c4a1f83ecc3e3d42eb510b61ce591b9c74e1052667ec758c99e3fe2792d.
Both script digests matched local commit 408c60c. Their save/capture/activation
paths confirmed that the old switch was stored independently for each pane.
The earlier TV capture ev_d4500347deb7092c025019c82f426d4f9eca2591e61ecc909dd5d9926846d415
was reused: the same captured 16242 bundle contains module 983331's shared
`addPlusButtonProperty`, persisted under `add_plus_button`. This is source
evidence for the shared preference, not a claim of toggling the reference page.

The new actual-host regression fails on the previous code and passes the fix at
1440px/393px in both themes: main/auxiliary menus, actual glyph visibility,
settings dialog, unchanged active pane, independent EMA settings, 1/2/3/4 layouts,
stale saved copies, reload and ongoing synthetic tick updates; zero trading POSTs.
Existing axis-side and full-host One-click confirmation regressions also pass.
The older standalone `context-menu.cjs` still fails its first price-menu text
assertion; it loads only unchanged renderer/menu assets, not either modified
host script. It is not counted as passed. No live broker acceptance was attempted.

Deploy only and refresh the web page. No native assets changed, so this batch
does not require iPhone Run. No deployment, service restart or broker write was
performed; pre-existing signing/localization edits remain outside this commit.

## 2026-10-18 — price-axis packing, consistent badges and EMA20 above 1h

Scope: shared web/iOS price-axis presentation, every primary/auxiliary pane, and
an explicit user rule that periods strictly above 60 minutes show only the
primary chart-timeframe EMA20 (close, zero offset). 1h and shorter periods keep
their existing settings. Master/component switches and Visibility ranges remain
respected; saved inputs are not overwritten, so returning to 1h restores them.
ATR, additional EMAs, bar count, FVG, previous values and volatility channels/gauge
are suppressed above 1h, along with their unnecessary MTF/volatility reads.
The rule is stated in English on Visibility. No new settings synchronization.

Reference evidence and adoption:
- REA captured the actual current TradingView four-pane page and Wheel page:
  ev_8d3b8a93a6e3a576cf805e21164edec216fafb5cfa3d4b7b2bb2bc837f2e6e83 and
  ev_2323816587128bcced8e5279bc1cb22dea19fa477340ba9a15eaf1ed45a927b0.
- REA captured current TV shipped scripts, including its actual price-axis
  `_alignLabels` implementation, in
  ev_d4500347deb7092c025019c82f426d4f9eca2591e61ecc909dd5d9926846d415.
  Relevant bundle: 16242.d0142d8fa7ee8b7ed0c1.js, SHA256
  6c0cc0f48bb15b681abc9ccd49faf2abdaa7ba7239f899c38f95d7d2b98ce9ad.
  Static application analysis: ev_cdb51e6a2e1bacea0a2a4f1687cd128a79a6586e09a5d138f6ba4cfd392c19cb
  (partial semantic graph; not proof that all TV UI paths were covered).
- A separate browser runtime probe called TV's actual alignment method on
  independent mock label objects: nearest-price ordering, exact-price ties,
  countdown height, dense stacks, top/bottom boundaries and disabled alignment.
  Actual reference chart coordinates/settings were unchanged. TV keeps the main
  price as its reference, packs in price order, and moves labels rather than prices.
  This probe is controlled replay, distinct from REA's passive capture.
- Wheel adopts that behavior independently using measured DOM rectangles. No
  proprietary TV implementation is copied into the repository. Crosshair labels
  keep their separately verified topmost/no-displacement behavior.

Confirmed defects and changes:
- Empty-data recovery left High/Low `hidden=true` while inline `display:flex`
  painted them. The collision allocator skipped those visible labels. The new
  regression fails on the old code; restored extrema now rejoin layout.
- Greedy type-order placement and a fixed 6px gap could put nearby labels on the
  wrong side of the current price. Shared packing now follows screen-price order,
  uses whole measured rectangles, and touches neighboring badges without overlap.
  Countdown extends below the current-price row. Overfull stacks clip at their
  own edge rather than jumping across current price; offscreen prices stay hidden.
- High/Low and volatility had 15px intrinsic numeric cells versus the 18px
  current/order/holding badges. All use the shared 11px font/18px row, padding and
  numeric width on main/auxiliary/native charts. Countdown remains a second row.
  Width measures the badge font, cached by price/format, including long decimals.

Validation completed: eight native tests, including real WKWebView empty-data
recovery/uniform widths and existing viewport changes; four actual-host cases
(desktop/mobile × light/dark), independent main/auxiliary 1h/8h transitions;
label restoration, exact and near prices, countdown on/off, stable repeated
layout, left/right/inverted scales, small/negative/long decimal prices and pane
edges. Existing drawing-axis, scale-tick/crosshair, axis-side and native initial
spacing regressions pass. Protected entry/TP/SL dragging, One-click on/off and
Confirm/Discard regressions pass. Offline mocks made zero broker writes.
The refresh matrix passed 1/2/3/4 panes, two four-pane pages and 6000 bars:
30/30 updates per pane, source-to-apply p95 2–7 ms (previous baseline 1–8 ms),
with no errors or rejected requests. Repeated layout changes, symbol/timeframe
changes, disconnect recovery, close/reopen and simulated hidden/resume passed;
all panes resumed updates after the injected disconnect (1499 ms), with zero
trading POSTs. These are isolated fixture results, not live broker timing.

Mini source was read-only verified at dda31d5e49799e2169389b2b28e02efb62e3c2c3.
This batch requires Deploy only plus a web refresh, and user-operated iPhone Run.
No deployment, backend/Gateway restart, physical installation or broker order was
performed. Existing signing/localization edits remain outside the commit. This is
bounded local/browser/simulator validation, not a claim of exhaustive TV coverage
or physical-device/market-open acceptance.

## 2026-10-18 — indicator timeframe visibility and settings organization

Indicators → Visibility now contains only timeframe controls: Minutes, Hours,
Days, Weeks and Months, each with an enabled switch and inclusive From/To bounds.
All ranges default to enabled. Inputs contains calculation parameters; Style
contains component switches, colors, widths, labels and display choices. Both web
and native indicator settings use English. Tick/second/range controls are omitted
because Wheel does not offer those chart types.

REA passively inspected the actual open TradingView indicator Visibility dialog
at the user's reference layout, including its checked unit controls and selected
Visibility tab (ev_84974c371ce1432687e02cc2288ff57738ca3400c66eeadfc4ac6ca3c6722204).
The supplied screenshot establishes its numeric limits. Wheel adopts unit/range
selection for the indicator bundle, using existing immediate-save behavior and
native numeric controls; this is not a claim of reproducing TV's dialog transaction
or slider implementation. The reference settings were not changed.

Filtering gates EMA/MTF EMA, ATR, bar count, FVG, previous values and volatility
channels/gauge without changing saved component switches, candles, holdings or
order/P&L overlays. Each web pane evaluates its own interval. Hidden indicator
history reads are skipped; switching back restores the enabled components.
Timeframe preferences persist and join indicator templates; old preferences and
templates default to all timeframes. Existing per-pane/native preference storage
is reused; no new cross-device settings synchronization is introduced.

Validation: native model/template tests and viewport tests passed (8 tests), plus
rendered native Visibility in both themes. The offline browser acceptance passed
mobile/desktop × light/dark, English UI under a Chinese page locale, bounds,
hide/restore, master/P&L isolation, templates/reload, and independently configured
active/inactive panes with zero trading writes. The protected refresh matrix
passed 1/2/3/4 panes, two four-pane pages and 6000 bars: 30/30 updates per pane,
source-to-apply p95 1–8 ms, no errors or rejected requests, comparable to 1aff230.
Offline interactions/recovery also passed with zero trading writes. Numeric
controls were visually checked at 393px and 1440px, including a bounds-width
assertion that catches clipping. Physical-device acceptance is still pending user Run.

Mini source was read-only verified at 1aff2304b8093a067829de145baa7e58851068fa.
This change needs Deploy only plus refreshed web pages, and a new user-operated
iPhone Run for native settings. No backend/Gateway restart, deployment, physical
install or broker order was performed. Existing signing/localization changes stay
outside this commit.

## 2026-10-18 — 8h RTH prepares history in one background read

Scope: only 8h RTH startup/history. Other intervals and the existing intraday
aggregation/session anchors, tick delivery and layouts are preserved.

REA inspected the current Wheel scripts and the user's supplied recording. A
read-only Mini log check showed the native expansion and monthly pager overlapping
while history grew in small batches. REA then exercised TradingView's ES1! RTH
chart: the existing series requested 300 bars, switching resolution to 480 returned
300 bars in one series update, and the last five bars each started at 09:30 New
York on successive trading days. Its resolved CME RTH session was 08:30–15:15
Chicago. The original 5-minute selection was restored; no layout save was made.
Reference evidence: ev_3cb71ba39d20b7de623c4246cc670e2b212c02e6e667be913ac535f29d3674b4.
This supports preparing the history window before panning; it does not establish
IB response speed or justify replacing intraday trade closes with daily settlement.
No authentication payloads or raw browser capture are stored in this repository.

The deferred 8h path now starts one six-month intraday TRADES read on the existing
IB event loop and returns the current chart immediately. Polling/expansion calls
share that in-flight read. A failed/empty bulk read falls back to bounded monthly
pages without advancing a failed cursor. Native paging waits until the initial
window is prepared, then remains available for older history. Current minute/tick
bars still override overlapping historical closes/extremes. Replaced state/client
identities reject late results. A dispatched read retains its 12-second timeout
cleanup rather than canceling the coroutine and bypassing ib_async's cleanup.

Validation: 46 related backend tests, native browser history across 40
period/session/theme combinations, and the actual Simulator WKWebView history and
viewport tests passed. Includes pending-history deduplication, >120 prepared RTH
bars, live-bar preservation, fallback/cursor retention, stale-state isolation and
resumed left paging. The protected 1/2/3/4-pane, two four-pane pages and
6000-bar refresh matrix also passed with no errors/rejected requests; the
interaction/recovery check passed with zero trading POSTs. Synthetic source-to-apply
p95 was 1–8 ms across these runs, with all 30 updates per pane preserved.
These are mock/Simulator results; actual IB cold-history latency and physical
phone acceptance require deployment and Run.

Deployment: this change requires **Deploy & Restart Backend** on Mini and a new
user-authorized iPhone Run for the bundled chart asset. No deployment, Backend or
Gateway restart, physical-device install, or broker order was performed for this
repair. Existing signing/localization edits remain excluded from this commit.

## 2026-10-16 — two cross-device drawing display scopes

The user clarified that both choices must synchronize between computer and phone;
the distinction is main versus auxiliary panes, never timeframe. This supersedes
the earlier drawing-timeframe-sharing section below. The English menu now has
Main chart only and All charts. Both use the existing annotation operation queue.
The web layout supplies its existing main-pane role independently of active-pane
selection or maximization; the native standalone chart is a main pane. Main-only
drawings are excluded from auxiliary SVG rendering, price labels and Remove all.

Legacy local/timeframe scopes map to main-only and layout/global scopes map to
all charts. Existing device-local drawings are imported through the server's
non-overwriting import operation; existing server edits and deletion tombstones
win. Legacy local storage remains a recovery copy, with imported IDs recorded to
avoid replaying it on ordinary reload. Default/global payloads are not rewritten
merely by polling, preserving undo history identity across synchronization.

REA rechecked chart-drawings.js before implementation; its unchanged pre-edit
artifact matched evidence ev_546efd6e5ae6f90fec97abda53ba7a09e81969828b3a1bd0e9a520e667a9eedb.
This is the user's requested Wheel behavior, not a claim about the reference
product beyond its supplied menu screenshot. Existing synchronization is reused;
price/OHLC delivery, order operations and the 1/2/3/4 layout remain unchanged.

Validation: drawing-sharing, drawing-sharing-layout, drawing-history and
crosshair-drawing-priority browser checks passed, plus four isolated drawing-store
regressions. Covers all 20 tool menus, browser HTTP and simulated native bridge,
period independence, auxiliary activation/maximization, actual 4→2→1→4 host
layouts, legacy migration/deletion, polling, reload, undo/redo, desktop/mobile
widths and both theme inputs. Menu screenshots were inspected. Tests use local
fixtures; no broker writes or physical iPhone acceptance were performed.

Deploy only is sufficient for Mini because these assets are read per request;
refresh web pages. The user must separately Run the iPhone app for its bundled
asset, and both clients should use the updated asset for matching scope semantics.
No Backend/Gateway restart or device installation was performed. Pre-existing
signing/localization edits remain excluded.

## 2026-10-16 — preview latest commit before Shortcut deployment

Wheel Backend now fetches the tip of codex/chart-labels-1.7 without manual SHA
entry. The read-only preview returns current/target SHA, branch and commit subject.
The native confirmation shows that summary, and the second SSH command uses the
exact preview SHA even if GitHub advances meanwhile. Restart-only is unchanged.
REA inspected the preceding generated workflow: evidence
`ev_91561c3f1ae5c74a655846972fd3f6a1c4471ef57b23e1e72af9544f31d2488a`.
Tests exercise branch movement between preview and confirmation, and a strict
read-only preview command. No production restart is part of this UI update.

## 2026-10-16 — combined cross-device Backend shortcut

The private Wheel Backend shortcut adds Deploy commit & Restart Backend alongside
Restart Backend only. The forced SSH entry accepts only those fixed commands and
hexadecimal SHAs, with a separate deployment-check command. No key permissions,
Gateway service or trading path changes. Deployments use the shared guarded
implementation; phone-triggered deployment reads GitHub on Mini, so Pro need not
be awake. Commit/push remains on Pro. See BACKEND_SHORTCUT.md for scope and REA.

Validation: 10 disposable Git/mock-deployment checks and 5 restart/SSH allowlist
checks pass. The generated shortcut imports with the intended native menu and
input actions. Physical iPhone execution remains to be confirmed by its user.

## 2026-10-16 — Pro-to-Mini deployment command

`python3 ops/deploy_mini.py <commit>` verifies GitHub branch membership on Pro,
transfers an incremental bundle, preserves a rollback branch, fast-forwards Mini,
and requests one Backend-only restart. Both workspaces must be clean. Changed
HEAD, concurrent restart, ignored-file collisions and unconfirmed prior attempts
stop. Exact SHA, a new PID and HTTP health are required for success. `--check`
performs preflight without updating code or restarting. Local settings are ignored.
See [operator guide](DEPLOY_MINI.md). No Gateway command or broker write is used.

REA inspected Mini's actual LaunchAgent (evidence recorded in the guide). Nine
isolated real-Git/mock-service tests pass. Tool creation does not authorize a
production restart; no deployment was executed while implementing this command.

## 2026-10-16 — consistent CME futures RTH candles

REA inspected TradingView runtime session resolution and bar construction
(Evidence `ev_422e823a1cff5853ac710acfa4b3939dab5df620d2176ab31e6e851c5670032e`).
Read-only runtime inspection confirmed MNQ US regular 08:30–15:15 Chicago,
81 five-minute bars on October 13–15, and holiday/early-close corrections.
Wheel mixed the stock 16:00 close with IB historical RTH ending at 17:00 New York.

Centralize CME-group futures display sessions at 09:30–16:15 New York (405
minutes). Apply the same windows to current candles, paginated history, EMA,
8h RTH aggregation, countdowns and Moonshine session extrema. Request intraday
source bars whose edges preserve the final 15 minutes, then filter and aggregate
locally. Normal 5m sessions contain 81 candles, ending at 16:10; holidays and
early closes remain calendar-aware. Stocks/options retain their existing session;
true daily/weekly/monthly bars and broker settlement/previous-close values retain
their existing semantics. Executable quote freshness and Daily P&L are unchanged.

Validation: six focused session tests and 45 existing chart/history/EMA/volatility
tests pass; 65 frontend tests pass. Real chart-page fixtures at mobile/desktop
widths in both themes verify 81 candles, the final close, CoY, EMA and overlays.
The 1/2/3/4-chart and dual-four-chart latency comparison, stream lifecycle,
interaction/reconnect, 100Hz stress and eight-distinct-symbol checks pass.
These are isolated synthetic checks, not deployed broker or physical iPhone proof.
Full offline suite: 177/180 pass; three existing fill-metadata/terminal-fee fixture
errors reproduce unchanged on baseline 26f665b. No unrelated test repair included.

Deployment pending: this Python change requires a user-authorized Mini Backend
restart. Previous deployed rollback point is 26f665b69a1c242a464927e7a5bdc3c893c3db78.
Native bundled asset updated in source only; physical iPhone Run remains user-owned.

## 2026-10-16 — per-drawing sync scope

REA inspected TradingView's current page and captured runtime script sources
(Evidence `ev_07f0b67147f5c7dd9d1e42ed77df50285579c8455c489b719efa3870860671c1`).
The supplied video and captured shared line-tool actions show per-object
No sync / Sync in layout / Sync globally choices using NotShared,
SharedInLayout and GloballyShared states. Adopt the shared object-level menu for
all 20 Wheel drawing tools, including the separate text toolbar.

Existing and new drawings retain the previous global default. No sync belongs to
a stable pane identity; layout sync shares same-contract annotations within the
saved browser layout. These two scopes use local browser storage and never enter
the cross-device operation queue. Global sync retains the existing backend.
Scope transitions retire the old scope's ID and create a new one so a remote
refresh cannot replace the private copy. Pane identities survive reordering and
reload. Wheel has one saved web layout per browser profile; local/layout drawings
are not cross-device backups. Native assets are shared, but physical iPhone Run
and native persistence acceptance are not part of this web update.

Validation: drawing-sharing covers all 20 menus, scope transitions, isolated
browser contexts, other-layout exclusion, polling/reload/delete, global request
payloads, small/desktop widths and both themes. drawing-sharing-layout exercises
the actual four-pane host through 4 -> 2 -> 1 -> 4, reload, layout sharing and
removal. drawing-history and crosshair-drawing-priority pass. Browser fixtures use
simulated drawing transport/market data; no broker writes or service restart.

## 2026-10-16 — uninterrupted cursor across dense drawing hit areas

REA refreshed the live Wheel page/scripts (Evidence
`ev_5cfdbad596c02948f94cdbd7d8f597e7e4259ad167ea72c7d2c204a2f65e0e3c`).
Reviewed the supplied video and reproduced the brief disappearance with actual
mouse movement through the drawings' transparent 22px hit strokes. The previous
priority test moved before the ray origin, so it missed canvas mouseleave caused
by entering those editable drawing elements.

Treat mouse hover over existing drawing geometry as remaining inside the plot.
Bridge its coordinates to the chart's visual crosshair and peer panes, suppress
only the intermediate canvas-leave clear, and clear on exit to axes/controls.
Pointer down, touch drawing, selection and drag handlers stay intact. The
foreground cursor and fixed-label allocator are unchanged; no quote scheduling
or broker actions are added.

Validation: the strengthened crosshair-drawing-priority test fails before this
change and passes afterward, sampling every animation frame while traversing
three clustered rays. Covers both axes/themes and desktop/mobile widths, current
pointer price, drawing drag, direct axis exit, and the actual four-pane host's
owner/follower cursor continuity and exit cleanup. Order-line-drag and
no-overlapping-labels pass. A separate legacy trading-panel-integration check
stalled at its four-pane loading gate before reaching the new
scenario; its temporary additions were removed and the scenario runs in the
working read-only market-feed harness instead. No broker writes or service restart.

## 2026-10-16 — foreground cursor for chart-only and synchronized panes

REA inspected the current Wheel page/scripts (Evidence
`ev_45404270da401f072cf5fc13f5f7651bf27d555c109458ad4d4e377f58ff3ce6`).
The supplied video exposed the remaining native canvas cursor under DOM drawing
badges when the order-plus cursor is absent. Add a noninteractive DOM price-only
cursor at foreground level, retaining the existing order-plus cursor. Disable
native price-label underpaint. Neither cursor participates in fixed-label spacing.

Refresh its Y coordinate on every pointer event independently of the optimized
OHLC readout; explicitly update/clear it for programmatic peer crosshairs because
the chart library does not emit their move events. Keep existing trade actions,
fixed labels, actual drawing prices and chart layout unchanged.

Validation: crosshair-drawing-priority checks actual chart-only pointer motion
and peer cursor updates across a horizontal-ray price badge, top paint order,
unchanged drawing label position and cleanup, for both axes/themes and widths.
Price-label-spacing and crosshair-axis-ticks pass. Four-pane controls test has
an existing stale 16px gutter assertion (both b0f5fb4 and this change render 8px).
A temporary test copy using that existing 8px value passes the remaining checks;
no repository test expectation or production layout changed. Browser fixtures
are isolated from the broker. Device Run and broker acceptance are not claimed.

## 2026-10-16 — 1.7 drawing labels participate in fixed-label spacing

Follow-up screenshot exposed blue drawing price labels painted by the library
canvas beneath DOM High/Low and live-price/countdown labels. The previous cursor
fix did not cover this distinct fixed-label collision. REA inspected the actual
Wheel page and shipped frame scripts (Evidence
`ev_da43aef69f99d881279b871e1a8fc3cb3d336447716c867419d1de3e36fb881b`),
confirming the separate drawing `axisLabelVisible:true` path. Reused the current
TV fixed-label alignment evidence recorded below.

Expose drawing price lines to the existing DOM allocator and suppress their
native canvas badges. Drawing numeric labels now move above/below occupied
fixed labels, preserving actual drawing prices/geometry, precision and colors.
Crosshair remains an independent foreground overlay. Drawing hide/delete/drag
lifecycle is retained. No trading or market-data path changes.

Validation: drawing-price-axis reproduces collisions with High and the two-row
live price, checks all labels visible and separated, and covers both axes/themes
at mobile/desktop widths, updates, dragging, hiding and cleanup. Existing
price-label-spacing and no-overlapping-labels checks pass. Screenshots visually
checked. Isolated browser verification only; Mini and physical iPhone have not
been updated by this task. Existing Xcode/localization edits remain excluded.

## 2026-10-16 — 1.7 cursor overlay without label displacement

Base: GitHub `codex/chart-labels-1.6` at `d35144ef5dda2c9f31f45617827b7f070bcb76f6`.
Continue on `codex/chart-labels-1.7`. Fixed price labels retain the existing
No overlapping labels allocator. The mouse crosshair and its price badge no
longer reserve space in that allocator; the existing opaque foreground badge
covers the fixed labels without moving them. No quote, order, or layout changes.
This supersedes the cursor-reservation adaptation in the October 15 chart-detail note.

REA inspected the current TradingView page and shipped scripts (Evidence
`ev_62065e6ecada3bf92fe7ecfbca6d7ecbb94ad37c3b893e95289d68eeace720b9`).
Bundle SHA-256 `20550a5624197c012efcab64aaaa3d37382c44f6e9026bce3c6d7701c05282da`
aligns ordinary views and then draws the crosshair separately, last on its top
canvas. Adopt that separation; the evidence is shipped-script inspection,
not a claim that REA moved the reference cursor. User-supplied video was reviewed.

Validation: price-label-spacing, no-overlapping-labels, crosshair-axis-ticks,
and native-axis-initial-spacing browser checks pass. Mouse sweeps preserve fixed
label rectangles; cursor paint-stack and pointer-coordinate checks pass across
mobile/desktop widths, both axes and themes. Indicator overlaps, tick masks,
setting toggle, inverted scale and native compact spacing remain covered.
These are isolated browser fixtures, not physical-iPhone or deployed acceptance.
No Backend/Gateway restart, device Run, or broker writes. Existing uncommitted
Xcode project/localization edits are excluded from this change.

## 2026-10-16 native instrument search and shared contract favorites

REA parsed the existing web option picker and favorite implementation: option-search.js evidence ev_b16ef3ef3a53d558f5e6346d894e96f61ae7f468f6b8bc9329f9598ec6ab02a7; superchart.js evidence ev_15f46e9eda5d989a57fbce9319b17917448238b15af3b6b52155052ba267b795. These are static source analyses, not observations of the user's running browser. The native sheet adapts the existing stock/futures and underlying → expiration → Call/Put → strike flow to SwiftUI, uses the same read-only endpoints, selects a nearest strike only when a valid underlying price exists, and rejects stale responses and nonmatching exact option identities. Saved favorites resolve their exact contract ID before opening; no order is created by selection.

Web and native now share /api/chart-favorites. This is a separate SQLite bookmark store (chart_favorites.db, ignored by Git), outside the IB dispatcher and account/order write guards; the existing same-origin API header is still required. Per-contract revisions, deletion tombstones and operation IDs preserve independent additions, reject stale changes and prevent legacy local imports from resurrecting removals. Original local favorites remain as migration backups. A lost write response is followed by reads, not automatic write replay. Both clients refresh on entry/foreground and every 15 seconds while visible (native: while the picker is open). A backend supports one shared instrument list across web/iOS; this does not synchronize trading state or settings. Limit: 100 favorites; excess migration items stay in the original local backup and are reported.

Validation: 21 backend unit/route tests passed; four native Simulator logic tests passed; the native picker was rendered and inspected in both light/dark themes with English labels despite a Chinese system locale. Browser checks passed for native-style option flow on the web, cross-context favorites add/remove, cached-old-template fallback and zero broker writes; the favorites module also passed migration/unknown-response checks. Existing 1–4-pane mock streaming/layout/recovery checks passed with zero order writes. The existing toolbar test has a stale 110px width assertion: unchanged GitHub baseline and this version both render the already-approved 96px. A temporary test using 96px passed all desktop/mobile and light/dark menu checks; no production layout or repository baseline test was changed.

Deployment requires the user's Backend restart for the new routes, browser reload, and user-operated iPhone Run for the native picker. Do not restart Gateway. Source sync/build success does not prove the updated backend is running or the phone is installed; real-device cross-client acceptance remains pending those user actions. Existing signing/localization edits remain uncommitted.

## 2026-10-16 default native CC opportunities to current coverage

Read-only Mini option data returned covered_call_capacity=3 for TSLL while the phone card displayed 2. Native source retained an old saved quantity and used quantity-versus-capacity differences as a manual-edit heuristic. REA decompiled the local device-build defaultCallQuantity function (ev_a46e5b669f87d1fff79d791f3eb097ff9618f8b3ace64e4f6a937990c7ea2a65); source inspection confirms the later preference/refresh override. This does not identify the phone's private saved preference value.

CALL defaults now use the current backend coverage cap. Legacy stored CALL quantity no longer overrides that default; explicit quantity edits are tracked on the current row and preserved across refresh, as are staged quantities, always clamped to refreshed coverage. New CALL edits no longer persist as future default quantities. PUT preferences and all submission/coverage guards remain unchanged. The prequote card uses the existing held/pending-adjusted capacity estimate.

Validation: three selected Simulator XCTest cases passed with zero failures, covering old quantity recovery to 3, automatic refresh, manual quantity preservation, a new row returning to maximum, pending-call reservation and staged-row preservation. Build succeeded. This is native logic/Simulator evidence; physical phone verification requires user-operated Run. No backend deployment/restart or broker order action is needed. Keep unrelated local signing/localization edits uncommitted.

## 2026-10-16 complete fast SL releases with a bounded quote wait

REA captured the current Wheel page/scripts (ev_02830a8479f012e5e1332877f89052cc01960ff93b9128595f7afd52b930255c). Read-only runtime inspection showed fresh chart packets but a missing executable bid while ask remained valid. The screenshot separately showed a confirmed request around 562 ms; no claim that this change reduces broker response or fill latency.

Use the final pointerup coordinate for web protection drags, including parent-frame coordinate conversion; ignore outside-pane final coordinates. In One-click mode, a released SL edit blocked only by unavailable quotes may remain unsent for at most one second while existing chart updates arrive. Revalidate context and quote before sending exactly once. Expiry, new gestures, Escape, focus/visibility loss, account/order/position changes, trading lock or disabling One-click cancel the unsent action. No new quote polling, broker-write retry or quote freshness relaxation. Confirm/Discard mode retains its existing persistent draft behavior.

Validation: the new regression reproduced the original dropped release and passes desktop/narrow widths for quote recovery, midpoint classification, deadline, cancellation and final release position. Existing sl-mid-close, stale-quote-protection-draft, entry-one-click-page, one-click-protection, fast-entry-drag and order-line-drag passed. All are isolated browser/mock checks; no real order was submitted. Web assets require reload; iPhone bundled assets require user-operated Run. The separate Orders history backend fix requires the user's Backend restart after source synchronization. Gateway remains untouched.

## 2026-10-16 recover persisted chart executions in Orders history

The Orders completed endpoint returned legacy local orders plus the broker's current completed/trade cache, but ignored chart_execution_marks after prior-session completed orders left that cache. Read-only Mini inspection found two exact TSLL Nov 20 2026 $11 Call BUY executions still persisted, while the endpoint omitted both. Original timestamps are Oct 14 New York. No deletion or trade replay is involved.

REA inspected the local device-build Orders endpoint string and native references (ev_bafcc6d049103fa010b8005b99de3c2518a5bdedfabcbe58f3f5ed5da5ce2c67; ev_352ab6e933eea2cfbd85878b253aea5671687493d4dd0a5b7ad818549b0cfce6). Source inspection and actual API/SQLite reads establish the missing backend join; this is not proof of the installed phone binary.

The completed feed now supplements missing permanent broker identities from the existing execution ledger, scoped to the verified account and an exact broker-resolved conId. It does not write orders or the ledger. Deduplicate against local/current broker rows; aggregate only consistent sides/contracts; match realized P&L by exact execution revision. Missing order type, TIF and commission stay unknown. Saved fills are labeled Execution recorded, without asserting an unknown remaining quantity or terminal broker order status. Rollovers and pending-order paths remain unchanged. This recovers already persisted chart fills; it is not a historical broker backfill for trades never captured locally. Contract lookup failures remain unavailable rather than guessed.

Validation: 42 focused tests cover the completed-service path, cache loss, account/Paper isolation, exact identity, partial-fill aggregation, revision mismatch, conflicting/invalid evidence and read-only DB behavior, alongside existing futures/external-order regressions. Backend restart is user-operated and required after code deployment. No iPhone Run is needed for this backend response fix; no Gateway restart or broker order actions.

## 2026-10-16 preserve scale ticks beside the moving crosshair

The supplied desktop video showed ordinary prices disappearing near the moving cursor. REA captured the current Wheel page and its executed-source inventory (ev_7521ecc0a3516dd3fb75ade54115b6405d375fe710d4b01abd0cf3d611435c5e); its separatePriceAxisLabels implementation matches the local source. Cursor clearance was incorrectly included in whole-tick masking, erasing neighboring ticks outside the opaque cursor badge.

Keep cursor clearance for label arrangement, but generate scale masks only from actual non-cursor labels. Preserve the opaque cursor, label avoidance, chart layout, quote delivery and order behavior. The new isolated browser regression fails on the old source and passes on the fix at offsets above/below a normal tick, on both axes, themes and desktop/narrow widths at DPR2. Existing no-overlap and native initial-spacing regressions pass. Screenshots were inspected. This is mock/browser evidence, not broker acceptance.

This shared chart HTML is served dynamically: a static Mini update and browser reload apply it without Backend/Gateway restart. iPhone uses the bundled asset and requires user-operated Run to update. Preserve unrelated local signing/localization changes.

## 2026-10-16 preserve native futures chart session preference

Remove the two forced ETH assignments when entering a futures chart or selecting a futures contract. Existing stockChartSession AppStorage defaults to RTH and persists explicit RTH/ETH choices; recent-chart restoration remains intact. Existing ETH preferences are retained, so users affected by the old override should select RTH once after updating.

REA inspected the local device-build Wheel.debug.dylib (SHA256 cc20d5b245962564819c13e3cf5294e69404e990e82ff85d074c859a64cec93d), found stockChartSession and its references, and decompiled its AppStorage initializer (ev_225e50aef318ddccaed53c225187d2744d600895790c3bc1ceb2e39fb7b67d4b). Combined with source inspection, this supports retaining existing persistence and removing only the overrides; it does not establish the installed iPhone version.

Validation: Swift replay of extracted production initialization/selection blocks changed fresh futures, saved-RTH reentry and saved-RTH symbol selection from ETH to RTH, while saved ETH remained ETH. Debug Simulator build succeeded. Physical iPhone UI acceptance remains user-operated after Run. No backend/web deployment or service restart required; preserve unrelated signing/localization edits.

## 2026-10-15 recover silent contract daily P&L independently of quotes

REA inspected the actual option page (ev_3edcb619571cecb910764263b33ec74a1b11b10d416a0bc4d8356323823fff98). Read-only API observations confirmed a 327-second-old P&L callback with value withheld by freshness guards, followed by a fresh broker callback; the page subsequently returned to unavailable. This is separate from executable bid/ask freshness. The cause of intermittent IB callback delivery is not established.

The P&L service now renews only silent PnLSingle subscriptions on its existing serialized connection, with 30-second initial retry and exponential backoff capped at 300 seconds. Cached stream reads never subscribe or drain IB. Freshness remains 15 seconds; old subscription callbacks and different accounts/contracts cannot revive data. Retain a separate last_value for display, without promoting it to fresh value. Disconnect clears it, and realized P&L retains its own basis/value.

The web header shows the last broker value with a neutral Daily P&L · Stale label and age tooltip until a new value arrives, instead of repeatedly hiding it behind an ellipsis. Missing/unverified/mismatched data remains unavailable. All updated text is English; layout and protected quote/order/drag semantics are unchanged.

Validation: 17 focused P&L unit tests; browser regression covering fresh/stale/missing values, refresh failures, fresh recovery, account/contract isolation and desktop/narrow layouts in both themes passed. Mock checks are not live resubscription acceptance. Backend deployment/restart is required for recovery and last_value; user operates restart. No Gateway restart or broker order actions.

## 2026-10-15 side-specific size updates preserve live quote freshness

REA rechecked the current TSLL option page (ev_23fb6f77096d1c6900d0c0a90a909cec785aa32313efef727737413998ff4bc9); prior read-only frame diagnostics showed current SSE packets but missing executable bid/ask. Local ib_async wrapper inspection confirms size ticks carry the matching side price. The chart handler previously ignored those events, allowing an unchanged price to expire despite an updated size.

Accept positive real-time bidSize/askSize events with their attached price for that side only. Zero size and delayed side events invalidate that side. Last trades, cached ticker reads and historical bars cannot refresh a quote. Existing freshness windows, marketDataType checks, layout and order submission guards remain unchanged.

Validation: all 33 stock chart unit tests passed, including side independence, live size-only recovery, zero-size and delayed-size invalidation, and no order submissions. This establishes the handler defect, not the actual raw event sequence on Mini. Backend deployment/restart and observation of the real contract are still required; no claim of broker acceptance. Preserve user signing/localization edits; no Gateway restart or live trade authorized.

## 2026-10-15 preserve SL draft before quote validation

REA rechecked the live page (ev_1a745396c8f08ee03b90f064f4eec17828b437c9809295414236f1cb638442f9). The follow-up video/log reproduced stale bid/ask rejection before stageChartConfirmation, explaining snap-back and absent Confirm even after the offscreen-controls fix. That earlier fix did not cover stale-quote staging.

With One-click off, missing/expired quote now creates a persistent SL draft with visible Confirm/Discard and Waiting for live quote. Confirm rechecks the quote; failure preserves the draft. A recovered quote that changes intent to Close at mid requires explicit review and another confirmation. Direct mode and invalid broker identity still block without submission. Cached quotes are never promoted to live quotes, and the actual stop is not changed until guarded submission.

The new stale-quote-protection-draft browser regression covers actual drag, repeated refresh, failed confirm without snap-back, fresh-quote amendment, explicit Close review, both desktop/native widths and zero broker writes. Existing offscreen confirmation, One-click, SL midpoint, fast-entry and full-line drag regressions passed. This is a shared static chart fix; no Backend/Gateway restart or actual order modification is required.

## 2026-10-15 reachable protection confirmation with offscreen entry

REA inspected the actual Wheel page (ev_8e228673d0a30cde35bfb5273b8a60e3844225707ca3a885fbede24229d1068a). Read-only page diagnostics and supplied video showed two independent conditions: stale executable bid/ask blocked multiple SL releases; with One-click off, a valid confirmation existed under the entry handle whose price was outside the visible candle scale. The broker-backed stop remained unchanged. Cached display-only quotes were not promoted to executable quotes.

Keep the existing entry-attached confirmation when visible. When entry is offscreen, retain the same confirmation DOM/actions in a bounded floating row near the selected protection price; no scale expansion or order-price change. Refresh preserves identity and held clicks. One-click, stale-quote guards, cancellation, and broker invalidation remain unchanged.

Tests: offscreen-protection-confirmation reproduces actual option SL drag at desktop/native widths, confirms visible controls and held-click refresh, discard, changed order identity, direct mode and stale quote rejection. one-click-protection, sl-mid-close, fast-entry-drag and order-line-drag passed. The SL-mid test now excludes read-only chartValidation/quoteStatus notifications from its trading-write count. No real order modification or Gateway/Backend restart; iPhone Run is user-operated.

## 2026-10-15 native initial price-axis spacing

REA inspected the running Wheel page (ev_ad41832cf92f082bcc688b221d3bc267857934068091ee320eaf487dc4edd2ed), and reproduced the supplied mobile initial-autoscale geometry: 30200 is 18.31px above the 30186 last-price center, but the old 10px tick half-height plus 2px clearance incorrectly treated it as overlapping the 18px badge. Native compact mode now reserves 6px tick half-height and 1px clearance at the existing 10px font. Web behavior stays unchanged. Genuine overlaps remain hidden; no prices or scale ranges change.

Native initial-autoscale regression verifies 30200 stays visible before any scale drag, on both axes and themes, with off/on and inverted-scale checks. Existing price-label and no-overlap regressions passed. iPhone Run remains user-operated; no Mini deployment or Backend restart is needed for this native-only adjustment.

## 2026-10-15 fully opaque Close footer

REA re-inspected the live Wheel page (ev_fc278cd15adce67c8bbd1bc1166317e330f2d0e1b1d9ef7fb347f385b210cc0c). The new screenshot showed underlying content at the rounded edges and below Close; the earlier button-only check missed that area. Wrap the existing button in a solid sticky footer spanning the panel padding, replacing its fading shadow. Preserve the same button, handlers, hidden/disabled states and geometry; hide the footer when Close is hidden. Runtime wrapping also supports cached server templates without restart.

Browser pixel comparisons now include the button edges and full bottom padding with contrasting scrolling content underneath, in light/dark and enabled/disabled states. Desktop checks passed; no trading requests or service restarts.

## 2026-10-15 shared no-overlapping price-axis labels

REA inspected the current TradingView page and shipped scripts (ev_42385f3e9fced2c51211b25fd1f7659d7141dfcfb3abf130990cb775da8de01f). The current 78312 bundle (SHA256 9220b8e18a335c4a6ff6d09947140c22258ae144603a00deb994e0bd7961ed87) arranges labels under alignLabels; the settings and price-scale menu expose No overlapping labels. Adopt label-only displacement, preserving actual prices, lines and drag handles.

Wheel adaptation: include DOM High/Low, last price/countdown, order/holding and volatility labels in one collision pass. Capture ordinary scale ticks via the library formatter and mask whole conflicting tick glyphs beneath foreground labels, instead of leaving partial digits visible. Keep the pinned library unchanged. Volatility labels restore from their price anchors even when their renderer is cached. Default-on switch is available in the web axis menu and Display settings (per-pane persistence) and iOS Display settings (AppStorage), with shared rendering logic.

Validation: no-overlapping-labels and price-label-spacing checks cover desktop/mobile, left/right axes, both themes, DPR2, inverted scale and off/on restoration. Browser four-pane menu/persistence checks passed. Market-feed interactions passed 1/2/3/4 panes, reconnect and simulated visibility resume with 455 pushed updates, zero errors and zero trading writes. Native trading lock and order-line drag checks passed; iOS Simulator build passed. No physical iPhone Run, real-order acceptance or service restart was performed. Existing signing and localization edits remain local and excluded.

## 2026-10-15 opaque sticky Close button

REA inspected the running Wheel page (ev_b4b79556e74d86d4cfb4b7b8f7f193cfa058e47dd92f9dfcf3ec6dacb6ff), and the supplied video confirmed scrolling hints under the sticky Close button. Global disabled opacity made its background translucent. Keep Close fully opaque and mute only its disabled text/border. GET-only browser verification compared button pixels with red/blue content underneath, in both themes and enabled/disabled states; all four passed. Trading eligibility and handlers are unchanged.

## 2026-10-15 native centered two-row ATR/gauge footer

The accepted native trading lock remains unchanged. The footer now places ATR
above the gauge with a fixed 6px vertical gap, both independently centered in
the full chart. Native indicator settings expose Bottom Center and select it
by default; a one-time migration moves prior bottom-left/right preferences to
Bottom Center. Explicit top placements remain selected. Web gauge code and
layout remain unchanged; no Mini deployment is needed for this native update.

REA refreshed the actual web reference
(ev_61fc628e10dcb3559074b4fd12abfb8f00fde0615b59993262f818a87ac57eea).
The user's native screenshot establishes the unwanted previous side-by-side
appearance and collision with return-to-latest; the adopted two-row arrangement
is the explicitly requested iOS adaptation. Browser native-asset checks pass
at 320/393/852 widths in both themes, with exact horizontal centers, fixed gap,
return-to-latest clearance and navigation while locked. Existing native lock
checks pass unchanged. Screenshot inspected and iOS simulator build passed.
Physical device visual acceptance awaits the user's Run. Local signing and
generated localization changes remain excluded.

## 2026-10-15 native trading lock and right-aligned gauge/ATR footer

Native chart status controls gain a lock beside collapse. New chart-view state
starts unlocked; a single tap toggles it without another confirmation dialog.
The native trading panel is disabled while locked, and both the WebKit action
bridge and the native pre-write boundary reject trading actions. Status and
indicator actions remain available; chart pan/zoom and data delivery continue.
The lock is scoped to this chart screen, not the account or Orders tab. It does
not cancel submitted broker orders. Locking discards local unconfirmed edits,
closes trading menus and cancels local pending Add/Trim gestures; unlock never
replays these actions. Existing One-click/Confirm/Discard behavior applies when
unlocked. Web/native detection prevents enabling the lock on desktop charts.

On iOS, the gauge defaults to Bottom Right and sits just inside the price axis;
ATR keeps its original horizontal center in the full chart and lowers to the
gauge centerline when there is room, leaving the
attribution logo clear. A one-time native preference migration moves the old
Bottom Left setting to Bottom Right, while top placements remain selected.
Subsequent explicit position changes are respected. If the pair cannot fit, ATR
retains its original centered position above the gauge instead of shifting
sideways or overlapping. Web gauge layout is unchanged.

REA inspected the current web reference
(ev_36e7e80c2ee92f8703926f7c201ac33cb4cd0ae6e52312113b62979276196f4c).
The supplied iPhone screenshot and native bundled gauge/ATR code informed this
iOS-specific layout and safety adaptation. Validation passed at widths 320/393/852
in both themes, including lock action/drag rejection, draft discard, navigation,
indicator access, no unlock replay and desktop exclusion. Native fixture screenshot
inspected and iOS simulator build passed. Required One-click protection, full-host
entry confirmation, fast-entry and full-line drag regressions passed with mocks.
The full-host regression now uses the current axis settings menu, replacing the
obsolete hidden header button. Empty status-clear notifications are suppressed
until a message actually needs clearing, avoiding spurious host bridge events.
No real broker writes, physical iPhone Run, Mini deployment or service restart.
Local signing and generated localization changes remain uncommitted.

## 2026-10-15 cached-template static compatibility

Mini's running Flask renderer retains its prior HTML template. Initialize the
Chart status summary and missing quote-status slot from the static host script
as well, so this update works without restarting the backend. Fresh templates
reuse the same slot. No duplicate elements or service restart are needed.

## 2026-10-15 compact quote freshness and consistent settings categories

The shared option overlay now shows only Stale or No quote. Full freshness
messages go through a deduplicated quoteStatus host notification and clear on
fresh data or a contract change. iOS shows the current contract's message under
Chart status > Market data and marks the existing status icon. Web Chart status
in Detail lists messages from all current panes and removes discarded panes.
Origin and iframe membership are checked; status messages never submit trades.
Display/indicator/status categories now use Chart display, Indicators and Chart
status on both platforms. The web display settings also expose the existing Plus
button preference, matching native classification; axis menu access is retained.
No palette, label avoidance, chart refresh or order interaction changes.

REA rechecked the actual web page
(ev_a30b80f7f0df739bf2cc302f1647b7e6dbfa4ea1f9ab565cf04ef652c9f01f1d).
Shared stale rendering and existing separate settings sections informed this
small presentation adaptation. Browser checks passed for quote states, native
compact/desktop sizes, four-pane host routing/clear, both themes and category
entry points; narrow screenshot inspected, no overflow or broker writes.
iOS simulator build passed. Physical device acceptance awaits user Run.
Local signing and generated localization changes remain excluded.

## 2026-10-15 move validation banners out of the chart

Shared chart validation messages no longer render over candles. Deduplicated
chartValidation notifications use the existing host bridge. The active web chart
logs them in Activity; iOS keeps the current contract's message in Chart status,
with its notice icon, and clears it when validation clears. Validation return
values, tick requirements and all order guards are retained. This targets the
white system/validation banner, not quote freshness labels or price/order labels.
REA refreshed the actual web page
(ev_30ae42d2bb49ec367421d3b2f803877e441a808c30c9e91b08ce987c67bcf2a2);
the supplied native screenshot and shared validation implementation identify the
overlay source. Host status routing is the adopted presentation change.
Validation: narrow/desktop isolated browser checks passed for hidden banner,
message deduplication/clear and missing-tick blocking, with zero trading writes.
Existing one-click protection checks and iOS simulator build passed. No physical
iPhone Run was performed; local signing/generated localization remain excluded.

## 2026-10-15 center native chart status independently of side controls

The status text and notice icon now occupy a centered layer across the full
chart width. A separate horizontal layer anchors collapse at the leading edge
and display settings/sound at the trailing edge. Equal 88-point horizontal
reservations keep the status hit area clear of the 80-point trailing controls
plus 8-point spacing; long text truncates. The 32-point row height and all button
actions remain unchanged, including full-screen collapse placeholder behavior.

The supplied iPhone screenshot and current SwiftUI source establish the cause:
one leading control versus two trailing controls shifted the old flexible center.
REA refreshed the actual web reference page
(ev_4a7ba9e4ccbc64d35db9f670b0aae13185872ece522295d115b90dac268e160a).
Native placement intentionally retains the existing external settings button;
this is not a claim of REA inspection of the installed native layout.
Validation: iOS simulator compilation passed. Physical iPhone layout and touch
acceptance remain for the user's Run. No chart asset/backend change or Mini
deployment is required. Local signing and generated catalog edits are excluded.

## 2026-10-15 publish retained iOS status and quote layout changes

The native chart uses a fixed 32-point status button opening Chart status.
Trading progress, market data/EMA history notices and trading warnings move to
that sheet so their text does not resize the chart. Order execution and refresh
logic are unchanged. Users must open the sheet to inspect these details.
The shared option quote reserves a 13px status row and toggles visibility rather
than removing that row, keeping quote numbers stable when status appears/disappears.

The string catalog retains its original formatting and all existing translations.
Only eight new English source keys are added. Automatic stale flags and pruning
were not accepted. Local signing team and bundle settings remain uncommitted.
REA passively refreshed the actual Wheel page
(ev_8a8669cf26609779b28a3f9e39243f73168068f0c02aa2930db29eb34bdd9fc2);
the previously inspected web status separation informs the native sheet, which
is an iOS adaptation, not a claim of REA-observed native execution.
Validation: iOS simulator build passed; option quote checks passed for web/native
compact modes, narrow/desktop widths, light/dark, stale/current transitions and
contract isolation. Additional geometry assertions confirmed no vertical movement
when status appears or disappears. Physical iPhone visual/touch acceptance is
not performed. This task publishes code only; no Mini deployment or service restart.

## 2026-10-15 native iOS Plus control and action flow

Chart display > General now includes a default-on Plus button toggle, persisted
with the other native chart preferences and forwarded through the existing
WebKit display configuration. The shared chart hides only the plus action;
the cursor price remains visible. This is a native global chart preference,
consistent with the existing iOS display settings, rather than web per-pane storage.
Add, Trim and BE labels gain a five-second sweep in their existing button color.
The noninteractive overlay reads the actual enabled environment and stops when
disabled, Reduce Motion is enabled, or the scene is inactive. Existing button
actions, disabled predicates, geometry and chart update delivery are unchanged.

REA refreshed the actual Wheel page and inspected the Add click registration
(ev_c7dda0a7c1b3ea36d20330ba8b7b15208eb0784b7eb986e085f5bf2af7771797,
ev_434688f934ed52271841e66c1214a5c1ac1ba375da76493e79c891ff82e123ff).
Adopted the already verified shared Plus renderer and enabled-only colored flow;
native settings and SwiftUI overlay are iOS-specific adaptations.
Validation: simulator builds passed for both the working tree and an isolated
copy containing only the staged changes. Shared Plus behavior passed across
four panes, reload, desktop/narrow widths and both themes, with zero broker writes.
Native visual/touch acceptance and physical iPhone Run remain user-operated and
unverified. No backend restart is needed. Pre-existing iOS edits remain unstaged.

## 2026-10-15 remove native crosshair-label underpaint

The prior DOM-height check missed a canvas layer: the native crosshair price
label remained beneath the custom badge, leaving a #131722 strip below its
18px edge. REA inspected the actual Wheel page
(ev_b8bb1b65b2723418ffeed1a8667a81ebf2aa274e2026ce0f6a44e56cb4507f4b).
A pointer-only live screenshot and pixel scan confirmed the extra native strip.
Observe custom badge visibility and suppress only the native horizontal-axis
label while it is shown; restore the native label when the custom badge hides.
The cursor line, price, plus action and chart-only auxiliary labels remain.
Eight screenshot combinations (left/right, desktop/narrow, DPR 1/2) verify no
native/custom dark pixels beyond either edge, exact equal geometry, restoration
and menu clicks. Label collision checks pass. No broker writes or service restart.
Unrelated local quote/iOS edits remain excluded.

## 2026-10-15 cursor plus height alignment

Use the same 18px height and exact top/bottom coordinates for the plus segment
and cursor price badge, centered on the crosshair. REA rechecked TV
(ev_242126a85e45143ca692307473a198550c2a43141551efc9797ed3b8db54f950)
and an actual pointer-only screenshot confirmed flush segment edges. Browser
geometry checks verify identical bounds on both axes at desktop/narrow widths;
price-menu interaction remains intact. Exclude unrelated local quote changes.

## 2026-10-15 axis menu icon column

Reserve a consistent left icon column for all price-axis menu rows; align labels
at 34px padding. Place the Plus button checkmark and More settings gear in that
column. REA inspected the open TV menu (ev_8b815d3545262299f4a9a89a7c7dd021f867f0c0a06584fc3a8165f5ad052897);
read-only DOM measurements confirmed identical text starts for Auto, Plus button
and More settings. Four-pane desktop/narrow light/dark checks verified aligned
text, gear presence and settings activation; no trading writes.

## 2026-10-15 compact Favorites-to-interval gap

Remove the obsolete 18px interval margin. The existing 7px group gap now separates
Favorites from the divider, reducing the entire centered group by 18px. REA
rechecked the toolbar (ev_b4893d132fac06a526e6059ab16766f06d6b623808c7fe0cfd60d9ea9a1e50cb).
Desktop/narrow light/dark geometry checks passed; menu behavior is unchanged.

## 2026-10-15 centered cursor price and optional Plus button

Center the crosshair price badge and match the live-price typography (11px,
500 weight, 14px line height, 18px single-price box). Preserve the cursor color
and independent 20px plus target. The axis-gear menu now offers a checked Plus
button item; default on, per-pane persistence through existing display settings.
Turning it off removes only the interactive plus, retaining the cursor price.
Main and auxiliary panes route through same-origin, exact-frame selection.
REA rechecked Wheel's price controls and TV's reference menu
(ev_e5e38458998fb13b271cd108822d34fee8d7dff421c6358e3df943d9d72c80bf,
ev_b12d6ebd52246a58e575be5fcec2673851409273358ce6a2c68f16748c343f0b).
Browser checks passed for all four panes, reload persistence, both price-axis
sides, desktop/narrow and light/dark; centered text geometry, clickable menu and
live/countdown/extrema collision checks passed. Zero broker writes. Unrelated
local quote-display and iOS changes are excluded. Static web deployment only.

## 2026-10-15 settings through each chart gear

Hide the header Settings control and add More settings... beneath a separator
in every price-axis gear menu. Reuse the existing settings dialog; a message
from an auxiliary pane activates that pane before opening its settings, with
same-origin and exact-frame checks. No order requests originate from this entry.
The existing right-aligned header closes the removed button's space naturally;
RTH/ETH text starts within about 2px of the trading panel boundary at 1920px.
REA inspected current TV and Wheel pages (ev_9274acfb82d3a820a737f19cae3c73031f741d511cc9f6162c243ef860dcce9b,
ev_9cb334427d1b9ae64969339e94a531144859e4fe9a439073da4cdab008c2792e),
using the supplied reference for menu placement. Browser checks opened settings
from all four panes at desktop/narrow widths in both themes, verified the correct
active frame, no overflow and no broker writes. Static deployment only.

## 2026-10-15 New York toolbar clock

Show HH:mm:ss UTC offset immediately before RTH/ETH, using America/New_York
through Intl so daylight-saving changes follow the timezone database rather than
a fixed UTC-4 offset. Update once per second and immediately on page visibility
return; no market-data or broker reads. REA inspected the current TV clock
(ev_52d6b7067a46c3d516ac12f8cf1513ce1e5b2e4c089620506dc46506af91c593).
Adopt its quiet single-line time/offset presentation in Wheel's upper toolbar.
Browser checks passed at 1920/1280/393px in both themes, with explicit Nov 2026
fall-back and Mar 2027 spring-forward boundaries, correct placement, no overflow
and zero broker writes. Static assets only; refresh the page after deployment.

## 2026-10-15 compact Favorites label

Remove the duplicate star from the Favorites placeholder and narrow its fixed
width from 110px to 96px. Keep the separate symbol favorite control and dropdown
chevron. REA rechecked the current toolbar (ev_4a708a9f52c22a69011d1471d00f1d94fbf7e21f08db9eb0039e670a31780027).
Observe internal toolbar controls when their sizes change so the whole centered
group recomputes its occupied width. Browser geometry verified a 14px total
shrink with the group center unchanged at the viewport midpoint.
Desktop/narrow light/dark browser checks passed with no overflow or trading writes.
This static change needs a page refresh; the prior fractional Trim backend fix
still requires the separately user-operated Backend restart if not yet performed.

## 2026-10-15 fractional holding Trim, enabled action sweep and fullscreen

Restore whole-share Trim for settled positive fractional stock holdings. Side-panel
and right-click exits use the same unreserved-share budget, including short CALLs,
pending CALL sales and stock exits. Keep exact position/ref checks, all-client
reconciliation, integer quantities, and persisted no-replay behavior. A 302.1533
holding with one standard short CALL has 202.1533 unreserved shares and permits an
integer Trim of at most 202. Full-position BE/Close/protection remain restricted.
The right-click dialog exposes the integer cap; unavailable-capacity text no longer
incorrectly asserts that all shares have exit plans.

Add/Trim/BE have a five-second sweep only when enabled, preserving their existing
colors and reduced-motion preference. The fullscreen control now uses a 28px
rounded-corner SVG inside a 38px button. Existing click/Shift+F behavior remains.
REA observed the current Wheel page (ev_b11c4d396eeaf8eddfc6d43220f3725af22a642d7446abb00c6fe0e76442567b)
and current TradingView reference (ev_495d5a1adb1845af047ac9fa67cb91ca978e88aa8cb683f18f6dcf8df408c4a4);
read-only DOM measurements established TV's 28px SVG/38px button versus Wheel's
small font glyph. No interaction was performed on TradingView.

Validation: 114 focused backend tests passed (fractional Add/Trim, coverage,
unprotected stock/options/futures); side-panel and actual right-click Trim pass
in desktop/narrow and light/dark mocked pages. Normal-position flows, enabled-only
sweep, reduced motion, fullscreen entry/exit, and protected One-click/entry/TP/SL
drag checks passed. No broker orders or physical-device installation were used.
Mini read-only state confirmed the reported fractional holding and one short CALL.

Deployment requires Wheel Backend restart after source sync. The user performs
that restart unless explicitly authorizing the agent for this task; Gateway must
remain running. Local iOS signing/localization/StockChart edits are excluded.

## 2026-10-15 signature optical correction

Per the user's visual review, move the Ben signature itself up 2px, including its
flow overlay; retain its 24px size. The previous title adjustment remains.
REA rechecked the current header (Evidence
`ev_542d2e8cb764e4f84167c80ad45421431a020a8103ea0d53fbb3abf555488eb2`).
Rendered screenshots and DOM geometry confirm the signature moved exactly 2px,
with title/status unchanged; desktop/narrow light/dark and animation checks pass.

## 2026-10-15 header optical alignment

Reduced the Ben signature from 26px to 24px and raised the adjacent Superchart
label by 1px to align the visible glyph centers with the connection status.
REA confirmed the current page structure before the adjustment (Evidence
`ev_22f6373162dccb831f35cfba1e9aa2a923ddf48b84ccbbc36aa80a41765165bc`).
Inspected rendered header screenshots and glyph bounds; desktop/narrow light/dark,
link behavior, five-second sweep and reduced-motion checks passed. CSS-only
presentation change; no layout, quote or order behavior changed.

## 2026-10-15 chart edge, diagnostics and Ben signature

Runtime market messages now live inside Detail's Activity section rather than
appearing as chart overlays. Existing status updates and diagnostic logs remain;
request, retry, order and market-feed behavior is unchanged. The right chart rail
is 8px instead of 16px; Detail's right edge uses the same inset. The panel toggle
retains its original hit area and works in collapsed/expanded layouts.

The header home link uses the iOS Settings GildedSignature's exact 𝓑𝓮𝓷 lettering,
gold base colors and red/gold five-second sweep from WheelApp.swift. CSS animation
adapts that existing signature to the web header and respects reduced motion.
The original home navigation and accessible name Ben are retained.

REA inspected the live page structure for the overlay, header and right rail
(Evidence `ev_c33b5ce6c11d8a07f5d0feeba03096635b6a346e57971490387373fdc91378b2`
and `ev_ecfcef509ca9de77a5bdd0ddec9ee7edce69d9f17eea96f7492a8c8a564369c8`);
read-only geometry confirmed a 16px rail and 14px footer inset before the change.
The signature's implementation came from the committed iOS Settings source,
not an inferred replacement font or an unverified native-app runtime capture.

Isolated browser checks passed for a real mocked 503 busy response (hidden on
chart, visible in Detail and Activity), 1920/393px 1–4-pane layouts, panel toggle,
maximized pane, signature light/dark rendering, five-second animation and reduced
motion. Screenshots were inspected; no trading writes. This static-only update
requires no Backend/Gateway restart or phone Run. Unrelated local iOS edits remain
uncommitted and excluded from deployment.

## 2026-10-15 compact Favorites and Fib drag precision

Favorites uses a 110px native selector with a shared interval-chevron CSS rule
instead of the platform arrow; desktop and narrow layouts retain a 34px height.
The label remains complete and native favorite selection behavior is retained.

REA inspected the current Wheel and TradingView pages, then verified that the
current TV Fib and common drawing-source script hashes match the previously
captured source (Evidence `ev_eb541647f4985547551286b22de2f808e87cc94afa432d94df37be67fa0cc548`;
source Evidence `ev_41684b3dfba36eff971e7892a63ea42bbcb1a3b2b173daa92b58848cb4f600a2`).
TV Fib uses two anchors and its common drawing move path translates chart indices
and screen coordinates. Wheel previously added elapsed seconds to every anchor.
A replay spanning an RTH gap reproduced a 75px pointer movement translating the
Fib edges by about 57.47px and 71.75px, deforming its width. The fix converts each
original anchor through chart coordinates; both edges now move 75px. Fib/Fib
extension also retain sub-bar offsets with magnet off and preserve the handle's
grab offset. Continuous sub-bar movement is a Wheel adaptation; TV's captured
whole-object code rounds its index delta. Existing colors, levels and layouts
remain unchanged, as do non-Fib drawing and broker drag paths.

Focused browser checks cover desktop/narrow, mouse and real touch endpoints,
cross-session translation, cancellation, undo/redo, OHLC magnet, normal creation,
and 5→15→60→5 timeframe changes. Text/history checks and dark/light toolbar matrix
also pass. Existing 1–4-pane feed/reconnect checks run against the final source;
these are isolated fixture evidence, not broker acceptance. Static deployment needs
no Backend/Gateway restart; iPhone bundled assets require the user's Run.

## 2026-10-15 drawing shortcuts and independent Text toolbar

REA inspected the current TradingView page for Undo and reused the still-applicable
captured toolbar/command-stack source from the Text analysis below. Evidence:
`ev_e0284a74d9798e9f7b86f057dd3262b56e5e361c3ac3cd99a3c88fb52a2a37fe`
(page Undo accessibility) and `ev_41684b3dfba36eff971e7892a63ea42bbcb1a3b2b173daa92b58848cb4f600a2`
(shipped scripts). The floating toolbar has a draggable handle; undo/redo moves
commands between stacks and a new command clears redo. No user reference drawing
was modified during analysis.

Text and its formatting toolbar now move independently. Drag the toolbar grip to
position it; moving the drawing, editing text, or changing style keeps that screen
position. Viewport clamps keep the toolbar reachable; placement is session-local.
Cmd/Ctrl+Z undoes drawing changes; Cmd/Ctrl+Shift+Z redoes them. No new undo buttons.
Text fields keep native input undo. Only analysis drawings are affected. Per-ID
history preserves unrelated peer drawings and declines conflicting newer edits;
contract changes reset history. These synchronization guards and shortcut routing
are Wheel adaptations, not claims about TradingView's broker behavior.

Passed text-editor and drawing-history browser checks (desktop/narrow editing,
drag separation, style/position undo, create/delete redo, host/frame shortcuts,
input focus, peer conflicts and contract reset), dark/light toolbar menu matrix,
and existing 1–4-pane market-feed interaction/reconnect fixtures. No trading writes.
Static deployment needs no Backend or Gateway restart. Phone bundled assets still
require the user's Run. Existing unrelated iOS edits remain uncommitted and excluded.

## 2026-10-15 Text in-place editing

REA passively inspected the user's current TradingView chart and shipped Text
editor scripts (Evidence `ev_41684b3dfba36eff971e7892a63ea42bbcb1a3b2b173daa92b58848cb4f600a2`).
The captured editor uses a positioned textarea, live text, multiline input,
blur/Escape completion and an undoable text change; the current DOM exposes a
floating color/font-size toolbar. These are runtime/source observations, not a
claim that REA performed editing actions on the user's reference drawings.
Wheel independently adopts in-place Text input and a compact nearby toolbar for
color, size, bold/italic, edit, lock and delete. Anchoring the toolbar near the
text, explicit Done/Cancel, Cmd/Ctrl+Enter, and discarding empty new drafts are
Wheel adaptations. Note retains its existing editor. Legacy text keeps its
appearance; new text styles persist through existing annotation storage.
Editing guards also cover a remote request started before text editing. Same-touch
trailing clicks cannot activate the newly displayed toolbar. No broker paths,
price aggregation, layout, or quote transport changes.
Validated desktop/narrow rendering, actual touch placement, keyboard-sized viewport,
multiline/style save and restore, blank drafts, cancel, lock, undo, drag, contract
isolation and delayed remote-read protection; drawing timeframes/axis labels,
light/dark toolbar menus, and 1–4-pane feed/reconnect fixtures pass with no trading
writes. The old drawing-cancel-fib context-menu assertion fails identically on the
unmodified pre-change script; it is not represented as a passing check.
Static webpage deployment needs no Backend/Gateway restart. iPhone bundled asset
requires the user's Run; no physical-device installation is implied.

## 2026-10-15 extension toggle retains axis connectors

When Order and TP/SL extension lines is off, hide the plot-side extension but
retain the label-to-scale connector for entry/position, TP/SL and additional
orders. Left scales mirror the connector. Hidden extensions no longer hit-test;
visible connectors retain guarded dragging and confirmation semantics.
REA statically parsed the shared chart and additional-order scripts (Evidence
`ev_dc4666d6f31506c3dd7f8fe084eea1475cf076074a639cd6960e2299b63e3780`).
Manual source inspection identified whole-line visibility as the original cause;
static REA evidence does not establish runtime behavior. Browser fixtures verify
connector bounds, both scales, desktop/mobile, toggle restoration and SL drag.
Existing line-drag, fast-entry, One-click protection and full-host entry tests pass.
All trading checks use mocks. Static deployment needs no service restart;
iPhone bundled assets require the user's Run.

## 2026-10-15 option overlay and strike-list latency

REA passively inspected the running shared chart script (Evidence
`ev_9652ecf866a1900399a7a54a04e4db961994ec5e83f59c1bc637f821e5588499`):
nativeCompact enabled a separate 44px quote footer and reduced chart height;
its status was clipped to a dot. Remove that reservation. Web and native now
share an in-plot three-value row with status on the next line; mobile uses 13px
numbers and 10px status. Quote freshness, identity isolation and price delivery
remain unchanged. Browser screenshots cover 320/393/1440 widths, two heights,
web/native-compact and light/dark. Physical iPhone rendering awaits user Run.

Read-only Mini logs show repeated TQQQ strike-list requests timing out inside
reqContractDetails after about 10 seconds (including December/January expiries).
This corroborates the screenshot's 503 failure class; the exact screenshot
request ID was not found in the bounded log slice. Replace wildcard contract
enumeration with the existing reqSecDefOptParams definition/cache shared by
quote and expiration reads. Require SMART, standard multiplier and listed expiry.
The returned strikes are chain candidates: IB does not guarantee every
expiry/strike combination exists. Selected values still require existing exact
contract qualification before quote/staging; no rounded/substituted contract.
See https://interactivebrokers.github.io/tws-api/options.html .

The native picker caches metadata per server/demo/ticker/right/expiry for up to
30 minutes, bounded to 12 lists, and ignores canceled/obsolete completions.
Validation: 13 Python strike/qualification/quote-readiness tests; browser overlay
and stale/identity tests; generic iOS Simulator build. No device install, broker
orders, Gateway restart or Backend restart. No measured post-fix live latency
claim: backend runtime remains the prior version until the user restarts it.
After source/static deployment, web layout is active; backend strike optimization
requires the user's Backend restart, and native changes require the user's Run.

## 2026-10-15 chart detail refinements

REA inspected the deployed Wheel frame and TradingView's shipped browser scripts
(Evidence `ev_aecdda1cfb2599457b326f4f17fee993326479897a52482cbf8c598a6016b867`).
TV aligns ordinary price labels using rendered heights and draws the crosshair
last; Wheel now reserves crosshair/order-cursor space in its DOM label allocator.
This reservation is a Wheel adaptation, not a claim that TV moves High/Low around
its cursor. Order numeric anchors and trading/drag semantics are unchanged.

Empty drawing menus omit Remove. Sync keeps its existing two settings and
semantics, now with right-aligned pill switches matching the supplied reference.
TV's execution renderer uses a narrow 3px stem and 1px outline; an independently
implemented plot-clipped overlay renders that silhouette while preserving Wheel's
fill grouping, marker geometry and touch targets. Cached bar lookup avoids
scanning full history for every marker on every animation frame.

Daily P&L accepts valid account/contract push updates before a separate position
snapshot catches up. A transient read failure no longer erases a still-fresh
value; original 15-second expiry and identity invalidation remain. Flat persisted
realized totals retain their existing basis. No fabricated P&L or quote-derived
estimate; unavailable IB data still displays unavailable.

Verified browser fixtures: cursor label clearance on both axes, mobile/desktop,
light/dark; real Sync/menu/arrow taps; P&L transient failure, early push, expiry and
account isolation; compact order labels and TP/SL drag anchors. Multi-pane
interaction passed repeated 1/2/3/4 layouts and reconnect recovery. The 100Hz
synthetic stress passed single, four and two-page/eight-pane workloads: 180
updates per pane, final OHLC integrity, no errors or trading writes (measured
apply p95 2–7ms; this is local fixture latency, not IB latency). No broker orders.
Static web deployment requires no Backend/Gateway restart. The shared iOS chart
and previously completed footer swap require the user's own iPhone Run. Local
signing and localization edits are preserved and excluded from this change.

## 2026-10-14 dense price-axis label spacing

REA inspected the current deployed frame and confirmed the existing allocator
placed High/Low before the live-price block. Prioritize the complete current
price plus countdown block, then move High/Low around it with six pixels of
clearance and rendered-height measurement. Order price anchors and lines remain
unchanged. Verified close/equal prices at both axis sides, mobile/desktop and
light/dark, with a rendered phone-width screenshot and existing extrema/order
label regressions. No quote transport or order behavior change.

The user now explicitly runs iPhone builds themselves. The attempted final
install/launch for 2077f56 was rejected before execution after that instruction;
13 targeted physical-device tests had already passed before the instruction.
Do not install, launch or run more physical-device tests without new authorization.
2077f56 was deployed to Mini static assets with unchanged Backend/Gateway.
This shared-chart update also requires the user's iPhone Run.

## 2026-10-14 SL drag across midpoint closes OPT/STK positions

User explicitly requested this exception to existing stop-drag semantics.
Reused applicable REA deployed host/frame evidence from the same 0c88da2 base:
protection drags pass through shared confirmation before host/native management.
Only OPT/STK SL drags are classified at release using fresh account/contract
bid/ask: short SL <= midpoint or long SL >= midpoint chooses Close at mid;
otherwise the original stop amendment remains. FUT, TP and non-drag edits retain
existing behavior. Missing/expired/crossed quotes block classification.

One-click ON dispatches immediately; OFF retains the selected draft and existing
Confirm/Discard controls, with a visible Close at mid label when appropriate.
Routine quotes cannot flip the selected action; position/order/account changes
invalidate the draft. At confirmation, existing host/native Close processing uses
the latest fresh midpoint and retains the original expected position/ref. No
backend change, automatic retry or live order test. A midpoint limit is not a
market order and does not guarantee immediate execution.

Validation includes both sides, equality, direct/confirm/discard, quote updates,
position invalidation, invalid quotes, desktop/mobile, original line dragging,
web host-to-mocked-API payloads, and native Close midpoint guards.
Web deployment is static only. iPhone needs the rebuilt bundled chart asset.

## 2026-10-14 preserve chart-selected option Trim limits

REA 6.5 inspected the deployed web host/iframe and found `midManagement`
unconditionally replaced explicit OPT/STK Add/Trim/Close prices with midpoint.
Read-only incident reconciliation confirmed an initial BUY Trim limit of 0.52,
a fill at 0.52, and a later attempted 0.46 amendment rejected after the fill.
The original intended price is reported by the user; it was already overwritten
before the request journal. No broker order was changed during investigation.

Web and native now preserve valid explicit prices/order types; only unpriced
quick actions derive fresh midpoint limits. Invalid explicit inputs reject instead
of falling back to midpoint. Position identity and backend guards remain intact.
No backend, layout, feed, drag-confirmation or broker reconciliation changes.
Validation: 12 targeted Simulator tests, 27 Live option and 5 Paper holding mocked
backend tests, midpoint regression (chosen 0.46 versus mid 0.52), actual chart
menu/dialog requests at desktop/mobile widths and light/dark, plus existing
One-click/Confirm/Discard regressions. All order writes were mocked. Native
source requires a new iPhone build; Simulator success is not device installation.
Publish to codex/chart-labels-1.6 and codex/ios-native. Deploy web static assets
without restarting Backend or Gateway; retain the previous deployed SHA as rollback.

## 2026-10-14 fractional stock holding Add

A positive stock holding such as 302.1533 shares may adopt its exact reconciled
position for a whole-share Add. CC reservations do not reduce BUY capacity;
existing asset limits, stale identities, all-client open-order checks and unknown
outcome guards remain. Fractional Trim/Close/protection remain unavailable; no
fractional-order support was introduced. OPT/FUT execution is unchanged.
49 focused mocked backend checks, eight browser combinations for fractional
stock Add, and 105 Simulator trading checks passed. No broker orders submitted.
User authorized Wheel backend restart and physical iPhone Run for this repair.
Keep local signing/localization edits out of commits; do not restart Gateway.

## 2026-10-14 inline confirmation correction

Replaced the floating confirmation card with Discard/Confirm directly left of the
relevant TP/SL or entry label, matching existing futures quantity-edit controls.
Shared HTML covers web and native. No order routing or backend changes.
Desktop/mobile confirmation and quantity-edit regressions passed; mobile screenshot
reviewed. One-click bypass, stale-context guards and Escape behavior preserved.
Static deployment only; no service restart or real order operations. Phone requires
user Run to bundle the updated asset; no new physical-device installation verified.

## 2026-10-14 shared one-click protection confirmation and Detail collapse

One-click trading now covers chart right-click entry plus dragging/removing TP/SL.
The existing web preference is retained; native adds a default-off local toggle.
Off: shared chart displays an English Confirm/Discard panel before protection
amendments or removal. On: these actions dispatch directly. Ordinary entry price
edits still require confirmation regardless of the toggle. Drafts are invalidated
by contract/account/order/position changes or busy state, and Escape discards.
Web no longer uses browser confirm() for protection removal; the native bridge
accepts shared-chart confirmation without showing a second dialog. Backend
ownership and unknown-result handling remain unchanged.

Detail now collapses after a valid Orders/Positions selection; disabled/busy rows
do not navigate. Validated with eight offline web management cases, shared chart
confirmation tests at desktop/mobile widths, right-click/settings regressions and
104 Simulator checks. Screenshots reviewed. No real orders or gateway operations.
REA passive TV inspection was available, but no live cancellation was triggered
on the reference product: confirmation UI is a Wheel adaptation of its existing
Confirm/Discard controls and the user's supplied screenshots, not a claim of
observed TV cancellation behavior. Static deployment needs no backend restart.

## 2026-10-14 option and stock midpoint management

Web and native chart Add/Trim/Close for OPT/STK now select the latest valid
bid/ask midpoint at submission, including Paper. Round BUY down and SELL up to
the confirmed contract increment; reject missing rules, invalid/crossed/stale
quotes and account/contract mismatches. Display-only cached quotes are excluded.
Explicit Add/Trim/Close inputs also take the fresh midpoint; amendments to already
submitted orders retain their existing explicit-price behavior. No automatic
repricing or market fallback. Futures preserve existing pricing and routing.

Validation: 24 isolated browser management combinations across OPT/STK/FUT,
desktop/mobile and themes; dedicated midpoint direction/rounding guards; 104 iOS
Simulator checks; 112 relevant backend regressions. All writes were mocked;
no real orders were placed, modified or canceled. An initial broad unittest
invocation also discovered an imported base fixture with incompatible inherited
tests; corrected explicit test-class selection passes without backend changes.
Only frontend/native changes: web assets can deploy without a backend restart.
User performs the physical-device Run. Local signing/localization edits remain
uncommitted and are excluded from synchronization.

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

## Wheel 1.6 — fixed order price labels and live-price avoidance

Development branch: `codex/chart-labels-1.6`, based on GitHub commit
`11dfd40d7860784131435d03a6b525938d64a642` (both 1.5 and ios-native branches).
The position handle shows quantity and a separate P&L segment, retaining side,
contract multiplier, fractional quantity, and money/percent/ticks preferences.
Entry, TP/SL, Add, Trim/Close and other broker-order axis badges remain centered
on their actual price coordinates. Only the live price/countdown badge moves
to the nearest free gap. Price lines and order controls retain their anchors.
Canceled order badges are removed; near-edge positions use one edge indicator.
If the axis has no complete free gap, the live badge is hidden until space is
available; the underlying price ray and chart data are unaffected.

REA analyzed the current shared ChartAssets bundle (parent Evidence
`ev_f2d3a69bf8a156a1ce5cc0d177669a19cfda8ec11a72d499a65ee797ea844974`;
semantic coverage partial) and passively inspected the isolated Wheel fixture
(`ev_dd53493dce98e8b98930a719dc1fac60c5c19e37cac842b49a48abad41f9ce0d`).
With explicit screenshot authorization, REA captured the user's TV viewport
(`ev_56405ed5791cb48977ef45d52499cbc2acad79e9f8ec022491131dba3f6ed230`).
The visible limit-order label aligns with its order line. That single viewport
is not proof of TV's dynamic collision algorithm; moving only the live label
implements the user's explicitly requested behavior as a Wheel adaptation.

Passed: position-segments (desktop/mobile, appearance settings, STK/OPT/FUT,
short/long P&L, tick changes, units, fixed axes during crossings, additional
orders, removal, left axis and edge recovery), quantity-confirm, add-price-drag,
live-management (8 desktop/mobile, EN/ZH, light/dark combinations with mocked
writes), and pane-view-controls. Passed the existing market-feed latency matrix,
interactions, stress and distinct-symbols checks: 1–4 panes, two four-pane pages,
200-tick extremes, 100Hz stress, context isolation, bounds and recovery.
A same-host run of unmodified 1.5 and this version delivered all 30/30 steady
updates in every matrix pane; dual-page price-apply p95 was 2–5ms in both runs.
These are synthetic browser measurements, not broker or physical display latency.
Evidence logs and screenshots are under `/tmp/wheel16-*`; temporary fixture
servers, workers and browsers were closed. No broker writes were performed.

Known baseline failures: `submit-button.cjs:14` tries to click a hidden working
order direction label, and `pending-exit-lines.cjs:19` expects an immediate amend
message. Both failures reproduce on unmodified 1.5; those tests were left intact.
No Mini deployment/restart or physical iPhone build/install occurred in this task.
Existing local project signing and localization edits remain outside this commit.

### 2026-10-14 — Position P&L preference correction

REA inspected the authorized current Wheel page and its rendered position label.
The supplied settings screenshot plus source identified a missing `positions`
condition: an active position showed P&L whenever the master switch was enabled.
Require both switches; otherwise show quantity and Buy/Sell plus order type.
Restore the one-pixel separator on the left of the close control. No refresh,
price-axis, layout or broker execution logic changed.

Validated `position-segments.cjs` (master/position/bracket combinations, desktop
and mobile widths, fractional STK and OPT/FUT multipliers, fixed price axes) and
`quantity-confirm.cjs`. A local synthetic full-page check clicked the real Chart
settings and Position P&L controls and verified immediate switching, with zero
order writes. Screenshots: `/tmp/wheel-pnl-real-settings.png` and
`/tmp/wheel-position-off-*.png`. Generic iOS Simulator build succeeded; bundled
stock-chart.html matched source. User will Run the iPhone app themselves from
this checkout's `ios/Wheel.xcodeproj`; signing/localization changes stay local.
Deploy the static resources on Mini by fast-forward with a rollback ref and
served-document hash verification; no service or Gateway restart is required.

### 2026-10-14 — Reused API order IDs blocked bracket reconciliation

The earlier cancellation-only recovery fix (`7b3bb36`) is already an ancestor
of the deployed `e9715ce`; Paper and Live use the shared chart service. This
incident instead exposed a historical/current identity collision in the group
ledger. A saved permanent ID was OR-matched with a reused client/order ID,
causing distinct old and new orders to become ambiguous. Use the saved permanent
ID exclusively when present; retain account, contract, reference, action, parent,
execution and terminal-state checks. No record deletion, lock override or replay.

REA passively inspected the authorized active four-pane page and observed the
unknown outcome, disabled cancellation and zero TP/SL totals (evidence
`ev_a62afe1ca3da9d3413b394c3268423e07cccb629c3f5484dd39b5f15a61fad9f`).
Read-only Paper state and journal inspection established that the outstanding
request was the original submit; subsequent UI cancellation had not been sent.
A filtered, anonymized snapshot replay reproduced the ambiguity. With the fix,
the same 28 groups and 6 current orders reconcile with no errors and zero net
position. This is offline replay, not a broker cancellation acceptance test.

Bracket labels now show planned entry-based amounts for confirmed unfilled
working entries even if unrelated reconciliation disables editing. Filled
positions retain realized-plus-remaining projections; unknown projections remain
unknown. No market-data scheduling, pane layout or price-axis policy changed.

Validation: 219 focused backend tests passed, including cancellation/fill races,
durable history, group attribution, exact identity and Live capability guards.
The reused-ID test first failed under both synthetic Paper and Live accounts,
then passed with the fix. `quantity-confirm.cjs` and `entry-recovery.cjs` passed
at desktop/mobile widths, covering planned TP/SL, request-key isolation, no
write replay and one explicit simulated cancellation after authoritative recovery.
Temporary evidence stays outside Git. No production order, Live switch, Gateway
restart or iPhone installation was performed. Backend activation requires an
explicitly authorized Wheel backend restart and fresh broker/read-only UI checks.

### 2026-10-14 — Full-line order dragging and segment cursors

The preceding identity repair (`68e2d09`) was activated on Mini after the user's
explicit Wheel-backend restart authorization. Read-only reconciliation reported
known working orders with entry editing enabled and no sync error; TP/SL labels
returned to nonzero planned amounts. Gateway remained unchanged. Broker writes
were not performed by the agent.

REA inspected the current TradingView page and its loaded trading-module hash,
which matched the previously exported source. The line hit test uses vertical
distance across the visible line, excludes separately handled label bodies, and
returns a vertical-resize cursor. The user supplied the long-press/hand-cursor
observation; no TradingView order was dragged or submitted for this comparison.

Wheel now routes visible entry, TP, SL, Add and Trim line hits into their existing
guarded drag handlers. The nearest line wins within the pointer tolerance, with
axes, hidden lines and non-canvas controls excluded. Dragging a line uses the
vertical-resize cursor; label/button drags use grabbing. Quantity, type and cancel
segments support long press, while short clicks retain their actions. Unchanged
release does not amend. Grab offsets, account/order identity, confirmation and
existing order ownership checks remain in place. No feed or layout changes.

Validation: `order-line-drag.cjs` covers desktop/mobile widths, mouse and touch,
left/middle/right line hits, entry/TP/SL, cursor states, confirmation, short clicks,
unchanged release, hidden lines and account changes. `add-price-drag.cjs` covers
full-line Add, exact order identity, refresh/capture loss and fill races.
`quantity-confirm.cjs` and `entry-recovery.cjs` passed. iOS Simulator build passed;
no iPhone installation or Run was performed. Deploy these shared static assets
without restarting Wheel or Gateway; retain a rollback ref and verify the served
frame equals the committed source.

Follow-up: per user request, all chart Confirm/Discard controls now sit beside
the entry/position line, including TP/SL price amendments and protection
cancellations. Their accessible descriptions retain the affected role. Confirm
and Discard are excluded from segment drag/anti-click handling so immediate
confirmation after a drag remains usable. This is a requested Wheel adaptation
of the already analyzed controls, not a claim about TradingView placement.
Desktop/mobile confirmation and drag tests cover the unified anchor and actions.

### 2026-10-14 — Entry drag regression: direct mode and persistent draft

REA passively inspected the actual Wheel page (evidence
`ev_29a7d6b53dcbc8fe49244f0ae5d57daee0c69b1bf6ec8606b0501b96a59e5cdc`).
User video and settings screenshot exposed two frontend regressions: direct
mode excluded entry price amendments, and configuration refresh restored the
broker entry instead of retaining its unconfirmed draft. Confirm/Discard was
also rebuilt on every render, making clicks vulnerable to concurrent refresh.

One-click now includes entry price drags; when off, the entry draft remains at
the target until Confirm/Discard or a real identity/state invalidation. TP/SL
retain the same policy. Confirmation nodes are reused across ordinary refresh;
position P&L text still updates without replacing the controls. Help text now
states the entry-drag behavior. Original broker identity/confirmation guards and
request tracking remain intact; no order writes were performed against IB.

Verification: `entry-one-click-page.cjs` exercises the actual settings checkbox,
full host/frame bridge, mock POST and returned confirmed entry at 1400/393 widths,
with direct mode on/off and delayed confirmation across polling. The confirmation
test holds the mouse button across 50 configuration updates and still confirms
the intended price. Fast segment drag/capture-loss and position P&L tests pass.
Static deployment only; no backend or Gateway restart required.

### 2026-10-14 — Native entry cancel-cell alignment

The supplied iPhone screenshot showed a 24px native entry label joined to a
19px cancel cell. REA inspected the current shared page controls (evidence
`ev_55c21bf172912cef92c56fc5a44499322be126e216a8aff29500f3391e9aee61`);
the native-only CSS override omitted `#cancel span`. Both visible segments now
use 24px height, preserving the existing 44px hit-region height, separator,
colors and all event/confirmation logic. This is a CSS-only runtime change.

Chromium native-mode geometry and screenshot checks confirmed equal top/bottom
edges and the shared 1px boundary. Position-label and order-line-drag regressions
passed. iOS Simulator build passed with matching bundled chart resource. Local
Playwright WebKit is unavailable; no physical iPhone install/Run was performed.

### 2026-10-14 — Keep pending replacement SL visible after quantity edits

REA inspected the current Wheel page (evidence
`ev_0889890b80dd8060f6a70b5f93bd8482848cad66da9051e2d1222e8cf9f40a89`).
The user's video shows SL disappearing during quantity replacement's unknown
outcome and returning after reconciliation; TP remains. Read-only saved request
results confirm the eventual matching bracket prices, but intermediate results
have been overwritten by reconciliation. Source analysis explains the asymmetry:
the grouped SL summary is zero until Submitted/PreSubmitted/PendingCancel, while
individual PendingSubmit rows can already contain the replacement stop price.

The shared chart now derives a display-only stop level from the current snapshot
when all nonterminal stop rows are PendingSubmit/ApiPending with the same valid
price. It keeps the existing line and adds an ellipsis until confirmed. It never
caches a prior account/symbol/order price, promotes broker state to confirmed, or
uses canceled, filled, Unknown, missing or conflicting rows. Backend state,
replacement operations, confirmation policy and no-replay guards are unchanged.

`stop-pending-display.cjs` reproduced the disappearance before the fix and passed
afterward. `quantity-stop-recovery.cjs` tests actual webpage quantity Confirm,
unknown replacement, polling and reconciliation at desktop/mobile widths, with
one mock write and retained line identity. Quantity-confirm, one-click-protection,
order-line-drag and entry-one-click-page regressions passed. iOS Simulator build
passed with matching bundled chart resource; no physical device Run or IB write.
Deploy static assets without restarting Wheel/Gateway; preserve a rollback point.

User preference follow-up: pending replacement SL uses the same ordinary label
style as TP, without an SL-only ellipsis. The page's existing unknown/confirming
order status continues to report reconciliation; broker state remains unchanged.
The common price-amendment in-flight marker is unchanged for both roles.
Both pending-stop and full-page quantity recovery tests check matching TP/SL
label treatment, retained line identity and a single write.

### 2026-10-14 — Command magnet in expanded auxiliary charts

REA inspected the active multi-pane Wheel page (evidence
`ev_2885fb51e7b45eb7e0eb1daab78c2b753d1e031a96d5c093282d9667d53138b3`).
Keyboard magnet wiring was installed only on the initial chart document and
addressed the mutable active trading frame. New auxiliary frames lacked the
handler, so expanding one did not reproduce the main chart's Command behavior.

Install the existing shortcut on each ready pane, once per document. Frame
keydown events target their own window; parent-document events retain the active
chart target. Release, blur and hidden-page cleanup reset the window that actually
received the temporary mode. Saved magnet preferences and drawing snap math are
unchanged. No order, market-data or chart-layout behavior was changed.

The four-pane browser test expands an auxiliary with magnet off, presses Command,
places a horizontal ray and checks its actual anchor equals the candle high.
It checks other panes are unaffected, release/blur restore off, and the saved
preference stays off. Existing maximize, restore, reset, tail/history and Option
shortcuts passed with zero broker writes. Web host scripts only; no phone build
or installation is required for this correction. Deploy statically without a
backend or Gateway restart.

### 2026-10-14 — English-only chart control tooltips

Removed Chinese from both hover controls: Maximize/Restore chart and Reset chart
view. Shortcut hints and behavior are unchanged. AGENTS.md now requires English
for all future UI text, including hidden controls and every control state, until
an explicitly requested coordinated localization pass. This is a copy-only change
and uses the documented REA exception for text changes. Checked all three labels
and JavaScript syntax; deploy static assets without restarting services.

### 2026-10-14 — Focused chart UI audit and toolbar menu polish

Scope: current chart chrome, toolbar menus, main/auxiliary controls, header/OHLC,
desktop/mobile widths, and light/dark themes. This is not an exhaustive audit of
all settings or broker workflows. Existing order-state warnings remain intact.

REA captured current Wheel and TradingView viewports (evidence
`ev_72827d229a0723dbd91e5d72799a8517e7ac0c9556d137c0daed97c4aa0fa494`,
`ev_b2c9caa4c8ce841e816fe4bcb482c7a88ab62f714a21f57f0972a4038c9a6458`).
Current TV script inventory evidence
`ev_44a20b199f71a6e8b01481b4a42e1f53a8f035d3766b826b4d26d4579696cbad`
confirmed the exact previously captured `53500.3a5fc4bc7516b767bee2.js`
SHA-256 `ef15a7ca514a0f9934e3f3e974d13dfc1cabab0edba67549dded0b276f9e3c7b`.
Reused source evidence
`ev_1f744bc99761235fe3d7f4ce2ff0b205c2ca713122775a24f9adc8d858f63fa0`:
module 26696 enables click-away, Escape, scroll/resize and Tab closure; the
popover uses initial focus and keyboard navigation. These are static source
observations, not a claim that TV menus were dynamically exercised.

Reproduced: interval and layout menus remained visible after clicking the chart
iframe; interval Escape did nothing. Session menu already behaved correctly.
Fixed those gaps, added visible keyboard focus and arrow/Home/End navigation,
restored focus after an interval favorite re-render, and removed mixed-language
favorites/fullscreen labels. Wheel adaptation: preserve Tab access to individual
favorite buttons, closing when focus leaves the picker; keep its existing layout.

`toolbar-menus.cjs` covers 1400/393 px and both themes, frame click, Escape,
focus departure, keyboard movement, favorite focus, viewport bounds and English
toolbar labels with zero order writes. Existing pane controls/magnet and header
checks passed. No order, streaming, aggregation or iOS asset changes. Static web
deployment only; no backend/Gateway restart or phone installation required.

### 2026-10-14 — Bracket explanation moved to hover

Removed the new-order panel's persistent “Optional · GTC exit orders” note.
Bracket now has the English hover explanation: “TP/SL orders remain active until
filled or canceled.” Existing-position editing guidance remains available. This
is copy-only and uses the REA text-change exception; no order behavior changed.
The existing template is handled by the static host script, so no service restart
is needed. Verify the hidden note and tooltip with a synthetic browser page.

### 2026-10-14 — Remove duplicate maximized-chart gutter

REA inspected the current Wheel viewport (evidence
`ev_6c78f427b41b4629bad060abb388c2b02b22307edf96cf663fed321ef5aa05f6`).
The current live page was in normal multi-pane mode; the synthetic full-page
maximize path reproduced a 32 px right gap instead of the normal 16 px sidebar
gutter. The absolute pane is positioned inside the grid content area, which
already excludes the sidebar padding; its extra right inset exposed a gray strip.
Changed only the maximized pane inset from `0 16px 0 0` to `0`. Kept the normal
sidebar gutter and panel toggle, multi-pane sizing and fullscreen rules intact.
The targeted geometry assertion failed before the fix (32 versus 16), then the
pane maximize/restore, shortcut, magnet and history regression passed afterward.
Static CSS deployment; no service restart or order operations.

### 2026-10-14 — Unified desktop chart toolbar

User requested combining the page header and chart toolbar into one row. REA
confirmed the current two-row page layout (viewport evidence
`ev_fd9e71133ba6593c0720325bc36a88141f471b08f1af3e532e6570decb7e0967`).
At widths of at least 1280 px, move the existing nav into the existing header:
branding, connection status, instrument/favorites, periods, session/layout/view
controls and settings share a 58 px row instead of roughly 115 px. Preserve every
control and chart iframe node. Narrow screens retain the workspace toolbar and
allow many favorite periods to wrap. In workspace fullscreen, return the same nav
to the fullscreen subtree; restore the unified row after exit. No chart data,
order or saved pane configuration changes. Static JS/CSS only.

`unified-toolbar.cjs` checks 1920/1400/1280/1024/393 px, dark/light themes, normal
and all favorite periods, row geometry, no horizontal overflow, menu access,
fullscreen entry/exit and retained chart/control nodes with zero order writes.
Pane maximize/restore, duplicate-gutter, Command magnet and shortcut regressions
also passed. Deploy without restarting backend/Gateway; no phone build needed.

### 2026-10-14 — Centered toolbar group and native-size axis settings icon

The user requested the instrument/favorites/interval group return to the center
of the single desktop toolbar. Center it on the whole header when it fits between
connection status and right-side controls; retain the non-overlapping inline
layout when space is insufficient. Observe only control sizing/text changes, not
market packets. Preserve fullscreen/narrow-screen placement and existing nodes.

REA inspected current TV page/scripts (evidence
`ev_b99304d032f108084f17c19d5c90f54eb9c3c6f1eeeec5c09268fe6e6d4f765b`).
Its loaded `62766.1efe8c749b4c28f0453c.js` matches the earlier retained source
SHA-256 `20550a5624197c012efcab64aaaa3d37382c44f6e9026bce3c6d7701c05282da`
(source evidence `ev_1f744bc99761235fe3d7f4ce2ff0b205c2ca713122775a24f9adc8d858f63fa0`).
Module 766998 supplies the 15x13 filled hexagon/circle SVG. Axis stub `_drawLabel`
centers its native view box using rounded device-pixel coordinates. Reused this
geometry and sizing instead of shrinking a 24x24 stroked substitute. The button
now uses the existing price/time-axis corner dimensions, a transparent background
and English title. Wheel adaptation: retain existing menu contents and button
availability; do not claim TV menu execution or full menu parity.

Unified-toolbar and toolbar-menu checks passed across desktop/narrow widths,
themes, favorite counts and fullscreen. Price-axis tests passed at 1x/2x device
scale, including native icon size and pixel alignment, both axis sides, menu
operation, drawing anchors and visible ranges. Synthetic checks only; no orders.
Static frontend deployment, no iOS bundle change or service restart.


## 2026-10-14 — Browser tab quote display

REA inspected the current TradingView chart (evidence
`ev_23cfcf33e26a84bb845cb337ac8cfc8fc19b4b75dfd947dc0574818238601f11`).
Current `main_chart.bc04d2d77efe2bc12a54.js` SHA-256
`fcaaf2824af6e78cf0cd9d82e98ed09514970e7726c896c5f232ffdfd0c54358`
matches the retained REA source. Its title controller follows the active chart's
quote provider, formats `last_price` / `change_percent`, and writes document.title.
This is source evidence, not an observation of TradingView's server-side baseline.

Wheel retains its favicon and shows the active contract, latest price, direction
and daily percent. The baseline is IB's `close` tick (previous available trading
day close), not the prior candle or ETH opening. Futures feeds may use settlement
conventions; do not promise equality with TV's continuous MNQ1! contract.
Reference subscription uses the existing bounded connection cache through a
separate read-only endpoint, with account/current-chart checks. No new IB owner,
historical requests, order writes or quote throttles. Raw latest trade metadata
is independent of the chart's selected RTH/ETH and bar interval. Missing/invalid
or delayed references omit the percentage. No stale account/symbol fallback.
Browser title formatting samples accepted state separately from price rendering;
it changes the document title only when the displayed value changes.

User authorized one Wheel Backend restart after verification; never restart
Gateway. Preserve the local signing/localization edits and broker database.

Validation: 81 focused offline backend tests passed. The browser title fixture
covers rising/falling/zero/missing references, independent symbols, active-pane
changes, and desktop/narrow layouts without broker writes. The before/after
1/2/3/4-pane and dual-page matrix retained every generated event and OHLC extreme;
per-case worst-pane applied-update p95 was 3–9 ms before and 3–9 ms after (local
synthetic results, not physical-screen or live-broker latency). Layout/recovery,
100 Hz stress and eight distinct symbols on two pages also passed.


## 2026-10-14 — Compact intervals and hidden dropdown repair

REA inspected the current TV toolbar (`ev_3cba5670828dabbb9b219eedbc2a01316e0ab5a4b3a153425d09084c171c51a9`)
and captured its visible styling (`ev_6d10f93ca13ec96cb851ac94da9e9644cee5b712ac13afd4eacf9c3d29c86211`).
Adopt the observed borderless compact interval strip, neutral rounded selection,
small chevron and D/W/M abbreviations. Wheel keeps its favorites, supported
intervals, menus and centered toolbar; no new interval/data capability is implied.

Reproduced the dropdown failure at 1920 px: `hidden=false`, but elementFromPoint
at a visible menu row returned the chart iframe. Centering's CSS transform creates
a stacking context below the chart. Raise the header/workspace toolbar layers so
menus render and receive clicks above charts; keep chart layout/feed code intact.

Expanded the existing toolbar test from mere open/close checks to real pointer
hit testing and 3m/5m selection, verified through the rendered chart title at
1920/1400/1280/1024/393 px in dark/light themes and fullscreen. Existing favorites,
keyboard navigation, dismiss behavior and retained-frame tests also pass.
Synthetic read-only fixtures; no orders. Static assets only: no backend/Gateway
restart and no iOS app installation required.


### Desktop-only toolbar follow-up

User canceled further small-screen layout work. Do not pursue narrow-width
centering in this task. Reuse the still-applicable full-toolbar REA screenshot
above: pill-shaped symbol group, quiet icon/text controls, aligned heights and
neutral hover. Apply the polish only under the existing `unified-chart-toolbar`
class (normal desktop); keep current header height, centering, menu behavior,
chart layout and narrow/fullscreen styles. No new controls or features.
Existing toolbar checks pass in both themes, including actual interval/menu
selection and a new assertion that desktop icon height is 34 px while narrow
controls retain their prior 40 px. No broker writes or service restart.

## 2026-10-14 — Filled positions and compact pending-order labels

REA inspected the user's current TradingView Paper chart
(`ev_e503fc9297c276385de382604bcd5d309fd21e7c37e58b3036f926ca289d2f0c`)
and captured its filled-position UI
(`ev_d2c93c739039c8094fdee802a3ea834adc5f2b2eaf6bba42809a0e06255d685a`).
Observed: with position P&L hidden, the blue position segment shows quantity
and close, without an entry-order type; bracket amounts remain visible.
Wheel previously rendered the shared entryType field on filled positions, so
that label was not reliable evidence of the executed order type. Remove that
filled-position fallback, retain quantity, side color and close, and keep the
existing master/position/bracket P&L switches and unit formatting. This does not
claim reconciliation of the user's historical Join fill or modify order routing.

Add/Trim use compact joined segments with 44px touch targets and retain their
existing drag/edit/cancel guards. Prices remain on the axis and in tooltips;
this is a Wheel adaptation, not an assertion that TV implements Add/Trim this way.
Pending-order extension lines honor the existing Chart Display setting.
High/Low labels yield to fixed order-axis badges during dragging; the live-price
badge then uses the remaining space. No price, feed, scheduling or layout changes.

Ten focused browser checks passed, including actual TP/SL pointer drags across
High/Low on both axes, desktop/native-width labels, Trim editor/cancel bridge,
Add drag/capture-loss/fill-race, position display matrix, protected One-click and
Confirm/Discard, full-line/fast drags and quantity-stop recovery. Mock requests
only; no broker orders. Screenshots reviewed at 1200 and 393 px. The older
standalone-trim.cjs fails at its cancelProtectionPreview expectation on both
base a9f5d0b and the changed tree; it is not reported as passing. The compact
Trim editor/cancel path is separately covered by compact-pending-labels.cjs.

Static deployment only, without backend or Gateway restart. Shared iOS assets
are source-synced; no physical-device Run or installed-app verification.

### Pending-label anchor correction

REA passively inspected the current Wheel page
(`ev_42809d642413bf526162f8de493ef2d062aef46f12ffb248a7a22e1cbd3715ea`).
The supplied screenshot and source identified vertical collision displacement:
Add near SL moved off its actual price line. Pending labels now preserve their
price height and yield horizontally when controls collide, including pointer
updates. Add shows `Add 1` without redundant direction; blue/red reflects side.
Trim shows `Trim | 1 | ×`; the quantity segment opens the existing guarded editor.
No broker/confirmation semantics changed. Compact-label checks cover the near-SL
regression on both axes and desktop/mobile, exact labels, and real quantity/cancel
clicks. Add drag/fill-race and One-click/Confirm/Discard regressions also pass.

### Price-scale compression follow-up

REA rechecked the current Wheel page
(`ev_9c1e812232e9985e9e8b6de0211ca39c204b9b842fe7fe0c5534b37e5234912c`).
The user's video shows Add changing horizontal lanes as the price axis compresses.
Remove pending-label collision displacement entirely: Add/Trim now use the same
fixed price anchor and axis gap as entry/TP/SL. High/Low still yield separately.
The focused browser test varies the visible price range on both axes at desktop
and native widths and asserts unchanged axis gap and exact price anchoring.

## 2026-10-14 background chart quotes

Hidden browser tabs now retain their existing bounded shared SSE transport for
all retained panes. Accepted packets update the tab quote directly, so background
timer/rAF throttling cannot freeze the title. Page exit still closes transports;
sequence, epoch, reconnect and snapshot guards are unchanged. Optional indicator
history and position polling remain foreground work. No quote throttle or layout
change; no backend or Gateway restart is required.

REA inspected the deployed host scripts and confirmed both hidden-tab stop paths
(evidence ev_3499a65295b7133e05fce29828751f014ea0ddc7d1035825979f4b2d3a3de018).
TV was passively inspected, but its background implementation was not established.
Normal Chrome with no forced-focus or background-throttle overrides verified a
truly hidden four-pane tab: 35 updates per pane over 3.5 seconds, changing title,
one shared stream, hidden disconnect/resnapshot, foreground recovery and close.
Synthetic before/after 1–4 panes, two four-pane pages, 100Hz stress, eight distinct
symbols, OHLC extremes and lifecycle checks passed. The 10Hz chart-apply p95
remained 2–6ms in the matrix. These are local mock/browser measurements, not
broker latency or phone background execution guarantees.

## 2026-10-14 pending Add quantity editing

The Add label now has the same separate clickable quantity segment as Trim.
Its editor provides minus/plus, direct whole-unit input, Back and Confirm quantity.
A paired futures Add uses one plan identity across its unit brackets; increasing
adds only the requested pending units, decreasing cancels only the selected
unfilled units. Existing filled lots are retained. Standalone Add edits amend the
exact unfilled parent. Grouped price/cancel actions retain exact selected IDs.
Asset-capacity checks constrain increases; existing larger Add plans can reduce.

REA rechecked the deployed frame implementation: Trim had a quantity editor while
Add had only drag/cancel controls (ev_3499a65295b7133e05fce29828751f014ea0ddc7d1035825979f4b2d3a3de018).
The implementation follows that existing quantity-segment UI. Broker operations
are Wheel-specific and keep UUID, ownership, exact terms, position and account
checks. A persisted edit journal reconciles outcomes from broker evidence and
never replays missing legs after disconnect/restart. Uncertain partial sends
block further edits; fill/cancel races keep filled-lot protection intact.

Validation: 58 focused backend/policy regressions; Add editor at desktop/mobile
widths in both themes; compact labels, One-click on/off, entry/TP/SL drag,
pending-stop display and quantity recovery all passed with mocked writes.
No actual broker acceptance or physical iPhone installation was performed.
This change requires a separately authorized Wheel Backend restart to deploy;
Gateway must remain running. Local signing/localization changes are excluded.

The prior background-quote commit fe3fd3c is deployed separately. Read-only
verification against Mini used a genuinely hidden four-pane Chrome tab: 105 SSE
packets arrived over eight seconds and the tab quote changed, with one transport
and no trading writes. Backend and Gateway process state remained unchanged.

## 2026-10-16 drawing timeframe sharing

Drawing scope now offers Same timeframe, Sync in layout and All timeframes.
Same timeframe uses the existing cross-device operation queue while filtering
rendering, price labels and bulk removal by the current interval. Legacy private
drawings remain recoverable. No market-data delivery or order logic changed.

REA parsed the current drawing asset without parse failures and inspected its
structure (ev_546efd6e5ae6f90fec97abda53ba7a09e81969828b3a1bd0e9a520e667a9eedb).
Review retained the existing synchronization and chart-context reset paths.
Local browser checks passed: drawing-sharing, drawing-sharing-layout,
drawing-history and crosshair-drawing-priority. Coverage includes isolated
web/native-shaped contexts, 20 tools, interval visibility and price labels,
polling/reload, layout transitions, undo/redo and mobile/desktop menu bounds.
These are mock/browser checks, not physical iPhone acceptance.

User will deploy Mini with the Wheel Backend shortcut. Mini was not deployed
or restarted for this change. The iPhone uses bundled chart assets and needs
the user's Xcode Run to receive this UI change. Unrelated local Xcode signing
and localization changes remain outside this commit.

## 2026-10-16 Long Text annotations and resizing

REA statically analyzed the current shared drawing asset (parent Evidence
`ev_fe141dd23db78e1b84c4a969f9c9cffaea3831f79459f79896ca0190f127a988`).
Source inspection found both a 120-character textarea limit and save-time slice;
CSS also disabled native resizing. The earlier TradingView textarea/multiline
findings above still apply to this editor; no new TradingView limit or resize
behavior was inferred from the static analysis. A literal feature trace returned
no matches and was not treated as proof of absence.

Text now retains its complete value, wraps within a persisted width and offers a
bottom-right resize handle during editing or selection. Height grows to fit text;
editing a note taller than the viewport scrolls, including reopening at its end.
New notes use a bounded initial width; legacy notes retain their original wrapping
until resized. Resize is undoable and remote drawing updates wait for its gesture.
These sizing details are Wheel adaptations. Note's separate editor is unchanged.

Verified: 5,000+ mixed-language characters, actual typing past 120, wrap, resizing,
undo/redo, complete reload/re-edit, desktop/mobile widths and both theme settings;
existing inline-text tests and actual 4→2→1→4 shared-pane tests pass. Three isolated
SQLite tests cover long text/dimensions, concurrency and duplicate/tombstone behavior.
No broker writes or market-data/order logic changes. Physical iPhone not tested.
Deploy only plus web refresh is sufficient; bundled iOS assets require the user's Run.

## 2026-10-16 Web Trading lock

REA analyzed the web host/layout (parent Evidence
`ev_d2fae2c136ef40a55e767c592efada82217ab88ada45e0c71b2523c1a722528a`)
and shared order asset. The HTML inventory explicitly excluded inline scripts,
so the largest actual script body was extracted unchanged and analyzed separately
(`ev_7357aba92de54c7557c50e473a3794e43f56f03c79b8e6ac6ec8092adde95525`).
These are static observations, not broker execution evidence. Source inspection
of StockChart.swift confirmed the reference iOS action allowlist and disabled
trading controls. The shared lock previously required nativeCompact; it now
honors tradingLocked independently of layout.

An English-accessible lock button beside Trading disables panel order controls,
frame order gestures and the host write/action paths. Indicators, drawings,
quotes, P&L and outcome reconciliation continue. The default remains unlocked,
matching iOS; sessionStorage additionally retains this tab's selection on reload.
It is not an account/server lock or a cross-tab/device setting. All panes receive
the current flag, independently of their display presets. Locking closes trade
editors, discards chart confirmation and queued Join/drag intent, and prevents
further cancellation-loop requests. Already-sent requests retain normal outcome
reconciliation; unlocking never resends discarded intent.

Verification: web lock browser fixtures cover Paper/Live mock profiles,
desktop/mobile and light/dark, real text analysis while locked, forged frame
messages, disabled controls and order drags, persisted reload, 1–4 pane switches,
confirmation disposal and locking during a pending request with queued amendment.
Existing native-trading-lock, entry-one-click-page, one-click-protection,
fast-entry-drag and order-line-drag checks pass. No real broker writes, deployment,
service restart or physical-device Run. The frontend files and chart_document's
per-request asset reads need Deploy only and a webpage reload; templates and
backend Python are unchanged. The preceding long-text commit is included.

## 2026-10-16 Cross-symbol active-pane title percentage

REA statically analyzed the current host and pane-layout assets (parent Evidence
`ev_dcc03f31c6f5e2b5eeffdb58c888851a45513b31d7dd5976c099bef0cb2e298d`).
Read-only live inspection confirmed TSLL delivered a live last_price but null
previous_close, including after chart-reference returned 200. Mini HEAD was
0576dc5632b308a49ebfe5bbe04e71a5f0c16365; no deployment or restart was performed.

The reference service discarded the returned bounded-cache ticker, although it
can differ from the chart's tick-by-tick ticker. It now returns that ticker's
finite positive broker close (live/frozen only). The title consumes this value
only for the exact current contract/account epoch, expiring it after 30 seconds;
it still prefers a valid chart-packet close. Delayed responses cannot cross
contexts. No historical/session-open fallback, extra subscriptions, quote
freshness changes, chart aggregation, or stream-pump edits were introduced.
The actual live cached ticker was not introspected; the distinct-ticker case
was reproduced with an isolated test rather than asserted as a runtime observation.

Three offline service tests pass, including distinct-ticker identity, invalid
and delayed values, and broker-action exclusion. Four-symbol browser fixtures
pass at desktop/mobile widths: positive/negative/zero change, missing close,
reference-only close, ongoing ticks, pane activation and delayed cross-symbol
responses. Live result after deployment remains unverified. Because Python
service code changed, use user-operated Deploy & Restart Backend, then reload
web pages; do not restart Gateway or run the phone for this web-title fix.


## 2026-10-16 Missing IB close tick after restart: daily reference fallback

Post-restart Mini HEAD was verified as f404208e06028672d01cf317ae0f82781014d039.
Read-only stock-quotes diagnostics showed TSLL exact conId 578561429, SMART,
NASDAQ, requested/actual data type 1, fresh last/bid/ask but null close. CRCL
on the same connection had a valid close. Thus the preceding cache-reader fix
was insufficient; a different ticker was not established as the live cause.
The exact reason IB omitted the TSLL close tick remains unproven.
Read-only IB daily chart data did contain October 15 close 9.32, distinct from
the still-forming October 16 daily candle. No broker writes were performed.

REA re-analyzed superchart.js (parent Evidence
`ev_3ec51afa0fd7dd2003d454941e86e862f14261843d9f94d6c867986d6860ef18`);
its existing exact-contract/epoch title reference is retained. For USD stocks
missing a valid close tick, chart-reference now schedules one finite 10-day IB
RTH daily-history read on the existing owner event loop. It returns immediately,
uses only the exact previous NYSE calendar session, and caches by chart state
and New York date. Current-day or older missing-session bars are rejected.
Late results from replaced/disconnected charts are discarded; failures retry
at most every five minutes. A valid direct close tick retains precedence.
This supersedes the earlier no-history-fallback description for this display
reference only. No live ticker, executable quote, aggregation, layout, trading
logic or stream-pump changes. Futures/options retain their existing close path.

Six offline reference-service tests and the desktop/mobile four-symbol tab-title
browser checks pass. Coverage includes pending-read deduplication, previous-day
selection, holiday/weekend handling, day rollover, failed reads, context rejection
and direct-close precedence. Browser checks use fixtures, not deployed acceptance.
Use user-operated Deploy & Restart Backend, then refresh the webpage. New code
has not been deployed or restarted by the agent; verify the returned reference
and actual browser title after the user deploys it. Existing iOS project and
localization changes remain excluded.

## 2026-10-16 8h RTH historical-page candle identity

User confirmed the tab percentage works after deploying 330af7957f9b533fcb47e8d7fcc503cd6c009429;
that SHA was also verified on Mini and GitHub before this change. They reported
repeated-looking TSLL auxiliary 8h candle extremes. REA analyzed chart-layout.js
(parent ev_69d9deac3d0963cdd842a475fed1efb3dc3439bee436150af892da9d9835f871):
panes retain and merge historical bars by exact timestamp. Live read-only API
comparison confirmed 8h RTH snapshots use session-open timestamps while the
history endpoint returned daily bars at New York midnight. Both identities can
survive an overlapping page/snapshot merge. The user's browser's in-memory rows
were not inspected; do not assert that every equal high/low is erroneous.

History pagination now uses the same 30-minute RTH trade source and session-open
8h aggregation as the initial non-CME snapshot, with bounded one-month pages.
CME keeps its existing session-aware source. Daily/weekly/monthly and ETH paths,
frontend layout/merge, tick aggregation, live delivery and trading are unchanged.
Reload the webpage after user-operated Deploy & Restart Backend to discard old
in-memory midnight bars. No agent deployment, restart or broker writes.

Validation: three history tests plus existing RTH 8h DST/trade-close and option
8h cooldown checks pass. The desktop/mobile two-symbol browser fixture verifies
main and auxiliary historical loading, snapshot overlap, exact OHLC retention
and one candle per trading date. This is fixture evidence; the user's actual
page after deployment remains to be checked. Existing iOS edits are excluded.

## 2026-10-17 Margin-backed short puts and mobile Trade staging

The user explicitly clarified that short puts are backed by IB margin against
SGOV, with collateral sales performed manually before taking assignment. This
supersedes the cash-only put requirement in earlier CSP notes. The observed web
error was Wheel's `Fresh settled USD cash is unavailable; CSP is blocked`, not
an IB rejection. The phone Trade screenshot separately showed HTTP 403 from the
blanket legacy-options write guard. Current broker state was read only; no real
orders, cancellations, collateral sales or service restarts were performed.

Chart short puts no longer call the full-assignment settled-cash guard. Broker
acceptance determines available margin; Wheel does not estimate SGOV collateral,
substitute market value for buying power, liquidate holdings or replay a prior
failed request. Covered-call share coverage, exact-account capability gates,
quantity/price checks and the chart request journal remain in place. Paper and
Live share this put behavior. The standalone cash-only helper is retained but
is no longer imposed on every chart put order.

Mobile Trade retains its existing stage-then-confirm workflow. Only the existing
option entry draft/execute/edit/cancel/delete routes are reopened under verified
Live options capability and current account epoch, with the same 1–10 quantity
limit. Unknown legacy operations, rollover and close staging remain blocked.
The existing Orders execution path still qualifies the exact contract, claims
the draft once, runs IB what-if, sends only after preflight success, and records
unknown outcomes without returning them to pending. Standard-option capability
is rechecked at execution. Stage all still creates drafts only, never orders.
The iOS estimate label is now Assignment notional, not Cash required.

REA's unchanged superchart.js order path analysis was reused (parent
`ev_3ec51afa0fd7dd2003d454941e86e862f14261843d9f94d6c867986d6860ef18`),
together with the supplied recording, actual HTTP rejection, native Trade call
site and backend route/journal inspection. No reference-product claim is made.
98 focused offline tests pass: real Flask staging/execution routes with mocked
broker, no-cash margin put entry/Add, covered-call preservation, IB preflight
rejection, stale epoch/wrong account/read-only/quantity gates, duplicate requests,
unknown submissions, amendments and replay boundaries. No live broker acceptance
was tested. Earlier broad test loading hit imported fixture classes and the
runner's deliberate production-DB guard; the final focused run is isolated.

User deployment: Deploy & Restart Backend enables the functional fix for both
existing web and installed phone clients. Refresh/reconcile before submitting a
new intentional request; old failures are never replayed. Phone Run is only
needed for the new estimate label and remains user-operated. Pre-existing iOS
project and localization changes are excluded from this commit.

Simulator validation: Wheel/TradingTests and ChartLiveManagementTests completed
109 tests with zero failures; iOS Simulator build/test succeeded. No physical
phone installation or launch. This verifies mocked client workflows and build,
not live margin availability or broker order acceptance.

## 2026-10-18 — Option chart Join Mid

Web options now show one full-width Join Mid button in place of Join Bid/Ask.
Choose Buy or Sell first (selected direction has a visible border); Join Mid then
uses the existing guarded join submission path with that direction. No direction
is inferred. Midpoint rounds to the nearest confirmed price increment and must
remain inside the spread. Both quotes, freshness, account/contract context,
quantity, state and final submission settings are checked. Stocks/futures keep
their existing Join Bid/Ask controls. Chart delivery, layouts and native iOS are
unchanged. Runtime button creation supports an older cached HTML template.

REA statically analyzed the current superchart host before implementation:
parent evidence ev_5e2a1053c23ab39da04de25f51a205f5c0a786aa4ad7345d044905c756919479.
Adopted the existing direction-preview → join revision → guarded submit path;
static analysis is not broker or runtime acceptance.

Validation: join-mid.cjs passed eight actual mocked browser cases across desktop/
mobile widths, light/dark themes and Buy/Sell: no direction blocks, quote guards,
cent-increment rounding and exactly one intended submission. Screenshots reviewed.
entry-one-click-page.cjs passed One-click on/off and stable Confirm/Discard at
both widths. No broker orders, service restart or physical-device Run performed.
Recommend user-operated Deploy only followed by browser refresh. Preserve existing
uncommitted iOS project/localization changes.
Additional protected-interaction checks passed: one-click-protection.cjs,
fast-entry-drag.cjs and order-line-drag.cjs. The last script required explicitly
selecting the existing Python environment; its completed rerun passed.

## 2026-10-18 — Native Join Mid and foreground-first long-period history

Native option entry now matches web: explicitly choose Buy/Sell, then Join Mid.
Direction selection is scoped to the chart/account/group; quotes require matching
account/contract, positive noncrossed bid/ask, confirmed increments and freshness.
The bridge rechecks current midpoint/direction/quantity and retains its revision
replay gate. Stock/futures Join Bid/Ask and order-drag behavior are unchanged.

8h RTH, D, W and M now opt into deferred historical expansion in both web and iOS.
- 8h first paint uses the existing recent minute history aggregated at session open,
  without another synchronous 5-day/month-range request. Full expansion requests
  six months of intraday trades, never substitutes daily settlement bars.
- D/W/M first request correct calendar bars over 1 month / 6 months / 2 years,
  then expand to 1 year / 5 years / 10 years. Option daily expansion targets
  six months. Available bars still depend on contract lifetime and IB history.
- Expansion starts only after initial data and a quiet interval (web: after all
  panes reveal; native: after matching fresh data is present for two seconds).
  Client task/controller cancellation and context checks prevent old page results
  from replacing a newly selected contract. Already-running IB reads retain the
  existing bounded 2s option / 5s other historical timeout.
- Optional expansion yields rather than entering the dispatcher behind pending
  foreground reads/writes; it expires if queued for two seconds. Trading job
  admission, acknowledgement and no-replay behavior remain unchanged.
- Warm chart snapshots reuse the exact active connection's resolved contract and
  cached historical subscriptions. Failed expansion retains recent bars; a larger
  successful calendar subscription replaces/cancels the smaller one only after
  receipt. Legacy clients without defer_history retain their existing load path.

REA: inspected the current shared chart artifact; HTML inline-script coverage was
explicitly absent, so extracted its two script bodies for actual JS analysis
(artifact digest 658bbbdbcd6acbdc309b51b52bab50e6c4f8aa85c646ca3aded070c7e1df0fb6).
Then analyzed current chart-layout.js and chart-stream.js for startup sequencing
and cancellation, parent ev_ec0df47d068f0d6684e97dba355eb1473cda89e0e35aa72fae58cc51ef008ea0.
Source inspection confirmed serialized cold snapshots and synchronous additional
8h history as avoidable waits. This is static/source evidence, not a measurement
of the Mini's live IB response times.

Validation so far: 110 iOS Simulator TradingTests/ChartLiveManagementTests pass;
8-case browser Join Mid regression passes. deferred-history.cjs verifies actual
8h/D/W/M page first paint while expansion is held, rapid three-contract switches,
no expansion for abandoned symbols, and later history merge. Backend aggregate,
cache, latest-read and dispatcher run: 55 of 56 pass. The existing
StockChartTests.test_cold_snapshot_countdown_does_not_wait_for_first_trade fails
with None vs the expected deadline on both unmodified HEAD and this tree;
not caused by deferred history, not silently counted as passing.

User follow-up: Deploy & Restart Backend, then update iOS using user-operated
Xcode Run and refresh the web page. Native UI/device acceptance and live IB
history depth/latency remain for the user's check. No broker order, Mini deploy,
Gateway/backend restart or physical-device installation was performed. Exclude
pre-existing iOS project.pbxproj and Localizable.xcstrings changes from this work.
Final protected-refresh verification: latency-matrix.cjs passed 1/2/3/4 panes,
two pages with four panes each, 5/10Hz plus 200-tick bursts and long-history
rendering. No rejected transports or page errors; every pane preserved extremes
and final close. interactions.cjs passed repeated layouts, symbol/period changes,
disconnect/resnapshot and account isolation, with zero trading POSTs. These are
local synthetic measurements, not deployed Mini/IB benchmarks.
8h recent-history maintenance also stays deferred: after expansion, bounded
one-month refreshes run separately when due and merge into the retained older
range. Verified refresh does not discard the six-month prefix. D/W/M keep their
existing live historical subscription updates.


## 2026-10-18: RTH 8h paging and historical execution metadata

8h RTH expansion now requests one month of intraday trades per background read,
then resumes from the oldest successful source bar until the six-month target.
Failed/empty pages retain both existing candles and the cursor. Successful partial
pages advertise a short retry; foreground reads still use the existing cached path.
The native chart now forwards user-driven left-edge history requests to the existing
paged endpoint, scopes tasks to contract/interval/session/account epoch, and retains
paged candles across ordinary snapshots. Initial viewport changes do not trigger
native paging. Web main/auxiliary pagination and existing session-open aggregation
remain unchanged; no daily settlement bars substitute for 8h intraday trades.

Orders recovery now saves broker-observed order type/TIF by account/conId/permId
and commission reports by exact account/conId/execId. Sparse late replies do not
erase fees; conflicting duplicate fee reports remain unknown. Execution corrections
do not inherit fees from an earlier revision. Existing realized-P&L calculations
are unchanged.

The existing Performance Flex worker additionally archives EXECUTION-level trade
metadata in its private history database. Recovered Orders rows can use that archive
only with exact account, contract, execution ID, action, quantity and price matches.
ORDER summaries and closed lots are excluded. Flex commission cash-flow signs are
converted to displayed costs (rebates stay negative). No extra network request runs
on the IB owner thread, and report credentials remain in existing private config.
A read-only check against the configured Mini report matched all five locally saved
executions, including the three screenshot rows, with official type and commission.
The current report does not include TIF; historical DAY/GTC without exact broker
term evidence remains unknown. Do not infer it from requested journal bodies or
another protection leg. New observed terms persist for later recovery.

REA analyzed current superchart.js/chart-layout.js startup and history request flow
(parent ev_1595a523c7d143c4d8182eb2b27aabbcd5a1bcc4ff95d5b0d7a58d75557cf896),
and the Orders module (parent ev_ed2b5d8d6246bf9a350876b79d84daef2df772e6b322ae7bc40e102554a4502d).
These were bounded static analyses, supplemented by source tracing, actual browser
checks, and read-only deployed-version/report checks. Mini was at 963ae97 before
this fix; it has not been updated or restarted by this task.

Validation: 87 focused backend tests passed, covering monthly paging/failure
recovery, execution account/correction/partial-fill isolation, official-report
matching, and existing performance/stock-cost/P&L behavior. iOS Simulator's 110
TradingTests/ChartLiveManagementTests passed. native-history.cjs passed light/dark
left-edge requests, throttling, viewport preservation and symbol isolation;
eight-hour-history.cjs passed desktop/mobile main/auxiliary overlap; deferred-history
passed 8h/D/W/M first paint and rapid symbol switching. The protected 1/2/3/4-pane,
two-four-pane-page and long-history latency matrix and interaction/recovery checks
passed without rejected transports or trading POSTs. Tests use fixtures, except the
explicit read-only official Flex matching check; actual deployed history latency
and physical-device acceptance remain to be checked after the user's deployment.

Follow-up: user-operated Deploy & Restart Backend, Xcode Run, and web refresh.
The first existing Flex background refresh populates the execution-detail archive;
Orders may initially retain blanks until it finishes. No Gateway restart, broker
write, Mini code/database edit, or physical-device installation was performed.
Preserve the pre-existing project.pbxproj and Localizable.xcstrings local changes.

## 2026-10-18 native history preload and all-timeframe paging

Native history requests previously required a gesture within 1.5 seconds and only
accepted 8h RTH. D/W/M could expand their initial snapshot but could not page left.
REA inspected the current bundled chart scripts and the web context-menu history
trigger (parent ev_28f7da0b7f8292dbc87e31afbc8f6a28e79f15f3eee2f4d5ec9f6d2496abc27c).
This was static analysis, not observed broker/runtime behavior. The adopted web
behavior is visible-left-edge paging without a recent-gesture deadline.

All ten listed native intervals now prepare history automatically after first
paint, with no need to pan first. The existing D/W/M bulk expansion remains;
bounded pages supplement it and other intervals toward roughly 300 intraday,
126 eight-hour, 250 daily/weekly, or 120 monthly bars when IB has them. These are
minimum preload targets, not guaranteed available bars or maximum history ranges.
Left-edge paging can continue to the existing 20,000-bar cap. Each request retains
its exact contract, interval, session and account context. Switching context or
leaving the view cancels its task; late responses cannot merge into the new chart.
Busy/errors retry independently of trading writes. Two empty responses stop
automatic prefetch at that boundary; later left-edge browsing can request again.

Paged history remains present in later snapshots and stream packets. Retention
uses an older-prefix merge, preserving current corrections without sorting on each
tick. A separate history revision forces a full JS delivery for an insertion even
if a new tick coalesces over it while WKWebView is busy. Subsequent consecutive
ticks retain the existing changed-bars path. No backend, order, layout, quote
freshness or broker connection implementation was changed.

Validation: native-history.cjs passes all ten intervals, both sessions and both
themes, contract/epoch switching, automatic preload away from the left edge,
empty-history stopping/manual retry, viewport preservation, deduplication and
incremental ticks after insertion. The real Simulator WKWebView bridge covers the
same interval/session/theme combinations and changing contract identities; native
unit tests cover history/current-correction merging, cap and coalesced-tick delivery.
117 Simulator history/viewport/trading/live-management tests passed, followed by a
final focused history/viewport rerun. 45 offline backend chart/history/futures
regressions passed. The fixed-date countdown fixture now supplies its matching
calendar window, avoiding failure when the real date moves beyond its 14-day window.
The protected 1/2/3/4-pane, two-four-pane-page and long-history latency matrix,
layout/symbol/period/recovery interaction checks also passed, with no trading POSTs.
These are fixture/Simulator checks; actual IB latency/availability and physical
phone acceptance remain unverified for this revision.

Mini source was read-only verified at 7187bcdb4853559670c18369d172558c90b71e40.
This native/static-only change needs user-operated Xcode Run. Deploy only is enough
for repository/static synchronization; this change adds no Backend restart need.
No Mini deployment/restart, Gateway restart, physical-device install or broker
write was performed. Preserve the pre-existing project.pbxproj and
Localizable.xcstrings edits; they are excluded from this commit.
