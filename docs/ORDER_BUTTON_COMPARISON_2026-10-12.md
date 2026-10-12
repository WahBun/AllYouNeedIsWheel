# Order button comparison — 2026-10-12

Scope: retain Wheel Buy/Sell preview/confirmation and existing close execution policies. Do not add account-wide Flatten All. User subsequently authorized removing the old Live option single-contract/sell-only/no-initial-bracket restrictions and requested a trading-panel collapse button. After local validation, the user authorized GitHub/Mini deployment and iPhone source synchronization (user will Run the app). Broker writes remain prohibited for acceptance. Keep the accepted market-data refresh implementation unchanged.

## Observed comparison

REA passively captured the running Tradesea trade page and its client bundles. No order buttons were clicked. Client behavior is evidence of request construction, not proof of server-side fill, cancellation, or OCA guarantees.

| Control | Tradesea client evidence | Wheel decision |
| --- | --- | --- |
| Buy/Sell | DOM buttons request market orders in the observed order-flow path; other modes can select other types. | Preserve Wheel preview, confirmation and existing permitted order types. |
| Join Bid/Ask | Buy at best bid / sell at best ask using limit orders. | Existing quote identity, freshness, tick and duplicate-intent checks already cover this. Correct quantity validation and overnight submission defect. |
| Close Position | Selects symbol position; sends position ID/account and optional amount. Has an in-flight guard and pending-close tracking. | Preserve Wheel selected-order-group scope, authoritative reconciliation and existing exit policy. A limit close is not a guaranteed fill. |
| Flatten All | Account-level endpoint, account guards and in-flight suppression. | Explicitly excluded by user; do not replace Wheel logic or introduce this endpoint. |
| Breakeven | Requires a position, positive P&L and tick size; submits a rounded average-price stop through bracket editing. | Retain Wheel cost-basis/tick calculation and never-loosen-existing-stop rule. Do not claim commission-inclusive break-even. |
| TP/SL, Add/Trim | Client inspection alone does not establish server protection behavior. | Retain existing identity, remaining-position, OCA and unknown-outcome safeguards; verify through offline regressions. |

## Confirmed local fixes

- Removed an undefined `pending` reference in the normal OVERNIGHT submission path that could throw before submitting an otherwise valid stock limit intent. Join retains its own scoped validation.
- Unified new-entry quantity bounds across the input, +/- controls, preview, Join and final submission: futures/options 10, stocks 1000. Old-server `live_initial_scope` remains single-contract compatible; the new backend emits `live_options_scope`, enabling the authorized multi-contract behavior. Covered-call defaults also respect the cap.
- Added regression tests against the actual parent action and quantity-control functions. Updated the recovery test fixture for the existing chart-layout dependency.

## Verification

- Frontend unit tests: 59 passed.
- Session recovery / Join / shared preview tests: passed without network or broker.
- Mock browser management checks: passed across 8 desktop/mobile, English/Chinese, dark/light combinations, including stale-quote rejection; every API write intercepted.
- Isolated backend regressions: 176 passed (`test_paper_chart`, `test_optional_protection`, `test_live_option_management`, `test_live_options`). Harness forbids network, IB construction, app startup and persistent database access outside temporary storage.
- Actual market fills, partial fills and TP/SL triggers remain outside this mocked acceptance.
- Expanded backend run also passed new Live entry tests and order action/service crash, process fault, request crash, amendment and status recovery regressions.
- Right-click quantities: 8 desktop/mobile, English/Chinese, dark/light combinations, including stale contract/account/busy/market-crossing rejection. Selection produces a preview with atomic price/quantity data, not an order submission.
- Panel presentation and full-page integration: each passed 8 combinations. Actual four-pane iframe nodes/windows remain intact, ticket values persist, sound controls coexist, and no order POST occurs.

## Evidence

- Page: https://app.tradesea.ai/trade
- REA evidence: `ev_d25691fb98850010e9fce27dc7170160d7e8cd754a890ef9165539c87b7eb8ab`.
- Main bundle: `main-DeEIo2vj.js`, SHA-256 `ad57a6db587dba5c282a3aac6f89efe4c0b240605c1b701124d5f79950d8530b`.
- Trade screen: `TradeScreen-ciiZNcao.js`, SHA-256 `d2baa51bf6251fae6e37d8113201075f93c66a2a692c5c9b0b078d06662dfa55`.
- Raw runtime evidence remains temporary/local; third-party source is not copied into this repository.

## Right-click quantity refinement

Follow-up user scope: learn the detailed right-click order menu while retaining Wheel execution logic. The captured main bundle's `context_menu.items_processor` (UTF-16 offset 415706) replaces TradingView limit/stop rows with quantity subitems `[1,2,5,10,15]`. This differs from its DOM order pad presets `[1,3,5,10,15]`. Each subitem carries side, selected price, order type and quantity to the client order service. The source constructs `limitPrice` for a limit and `stopPrice` for a stop. This is static client evidence; no menu order was executed.

Wheel already has a desktop right-click menu in `chart-context-menu.js`, shared order choices in `chart-add-orders.js`, and an axis-plus menu. Above the displayed market price it offers Sell Limit / Buy Stop; below it offers Buy Limit / Sell Stop. Existing position choices lead to Add or Trim/Close dialogs with state guards. The scoped adaptation adds quantity selection to new-entry rows while preserving those position workflows and the existing preview/confirmation path. Presets must respect Wheel's current per-instrument execution limits; learning the interaction does not authorize increasing order size limits.

Additional passive page observation: `ev_2e665c59ae71ec5de7c80ea0fef78c59220752e3ed43ace489b9cf45e260a841` (no clicks, evaluation, navigation or order writes).

User-selected Wheel presets: **1, 2, 3, 4**, filtered by the existing account/instrument cap. Tradesea's larger presets are reference evidence only, not the requested Wheel design.

## Authorized Live option scope

Standard USD options now allow buy/sell limit or stop entries, 1–10 whole contracts (quick choices 1–4), and optional initial TP/SL through the existing bracket construction. Existing-position TP/SL, BE, Add, Trim and Close are exposed when reconciled state permits them. Add accepts an explicitly priced limit or stop; ordinary Add/Trim/Close buttons retain quote-limit construction. Account-level Flatten All is excluded.

Exact selected account, provisioned capability, Live port, read/write connection, standard contract checks, DAY/GTC, existing CC stock coverage/CSP cash checks, order identity and unknown-outcome fences remain. Buy entries are no longer blocked by the former sell-only gate. Add with conflicting option exit orders remains blocked rather than silently canceling protection. These are operational constraints, not disabled UI features.

Read-only configuration inspection found Mini's `chart_options_live_enabled` already true, port 4001 and readonly false. No configuration change is required. Runtime availability depends on deploying the reviewed code; local tests do not establish real broker acceptance.

## Trading-panel collapse

Captured main bundle around offset 462149 exposes minimized-pad state, persists `ORDER_PAD_MINIMIZED`, and restores it through maximize. Tradesea also animates and supports dragging its minimized pad. Wheel independently implements only the requested hide/show button and saved preference: a persistent top-right toggle hides the trading sidebar and expands the chart area without recreating chart frames or clearing pending ticket state. No additional draggable widget or trading action was introduced.

## Cold-start auxiliary indicators

User-selected default: retain each auxiliary pane's current-timeframe dynamic-color EMA20, ATR (including option ATR) and FVG; disable extra EMAs, previous values, bar count and volatility overlays/tables/gauge. Apply once when the page initializes, including saved auxiliary panes; in-session choices remain editable. Primary-pane settings stay unchanged. Eight mocked browser cases pass, including reload with an auxiliary pane selected and different primary indicator preferences. No price-delivery or EMA formula changes.
