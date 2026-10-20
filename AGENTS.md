# Project Working Agreements

Read `docs/HANDOFF.md` and `docs/MAC_MINI_TAILSCALE.md` before deployment changes.

- Iterate the web version first. Build or update the Mac App/DMG only when explicitly requested.
- Keep changes local by default. Push to GitHub only when explicitly requested.
- Preserve local connection configuration, databases, pending orders and user changes.
- Never commit account IDs, credentials, local databases, logs or device-specific network addresses.
- Treat deployments as potentially live trading. Test with mocks and read-only requests; do not place, modify or cancel real orders for verification.
- Keep one server process and one stable IB client identity. HTTP threads are safe only with the dedicated serialized API dispatcher in place.
- Do not automatically retry trading writes or interpret an unknown order status as canceled.
- Verify account routing, exact contracts, quantities and prices when changing execution code.
- Check mobile and desktop layouts and light/dark themes for UI changes.
- Run the relevant tests and record material limitations. Do not promise bug-free trading or guaranteed fills.
- Conversation history is not a source of deployed state: inspect Git, local configuration and service status on the current host.

## iPhone Run and Backend restart: user-operated by default

This rule applies across computers and new conversations. The user performs
iPhone Run and Backend restarts by default. Explain when either is needed and
leave the action to the user. Perform it only when the user explicitly asks the
agent to do so for the current task; a general repair, deployment or verification
request and previous one-time authorization do not grant permission.

- Do not install or launch the app on a physical iPhone, or run device tests
  that implicitly install or launch it, without that explicit authorization.
- Do not restart Backend through a service manager, process termination/relaunch,
  deployment script or another indirect mechanism without that authorization.
- Continue authorized code changes, local builds, simulator/mock checks and
  static web updates that require neither action. Report what still needs the
  user's Run or restart; do not treat a code push as an installed/deployed update.
- Gateway restarts remain separately restricted and are never implied by
  permission to restart Backend.

## Order changes: physical-device Run gate

Before installing a changed order workflow on the user's iPhone, finish relevant
backend regression, simulator trading tests, and chart interaction checks.
Cover price/quantity/TIF edits, replacement-order identity and Orders synchronization,
confirmed rejection, unknown outcomes, recovery after restart, cancellation/fill races,
and Paper/Live isolation. Compilation alone is not acceptance.
Use broker Paper acceptance only with the user's authorization and verify the actual
Paper session first. Keep test effects bounded and verify the final order state.
Report mock/simulator evidence separately from broker evidence; market-open fills,
partial fills, and TP/SL triggers remain unverified until actually observed.

## Protected market-data foundation

Keep the price/OHLC delivery path stable by default. Before changing aggregation,
streaming, chart scheduling or indicator work on that path, follow
`docs/MARKET_DATA_BASELINE.md` and compare the same workload against its baseline.
Cover 1–4 panes, repeated layout changes, two four-pane pages, latency distributions,
data integrity, context isolation and recovery. Do not add quote throttles or
parallel IB owners to hide regressions. Report mock/browser and broker evidence
separately, including the documented trade-volume gap. Preserve the current layout.

## Protected order-drag and confirmation behavior

These rules apply on every computer and in every new conversation. The user
approved this behavior at commit `9df6bd644d32c09d1434240b076d6598cd43a399`.
Treat it as a protected behavioral baseline, not a requirement to stay on that
commit. Future UI, styling and layout changes must preserve it. Change these
semantics only when the user explicitly requests a behavioral change.

- With **One-click trading on**, releasing an entry-price or TP/SL-price drag
  submits the amendment through the existing guarded request path without
  Confirm/Discard. Do not introduce an entry-price exception.
- With **One-click trading off**, releasing a drag leaves the line at the chosen
  draft price until Confirm or Discard. Ordinary quote updates, polling and UI
  refresh must not restore the old broker price or discard the pending change.
- Put Confirm/Discard beside the entry/position line, including for TP/SL changes;
  do not move these controls onto the TP/SL lines.
- Keep confirmation controls stable across ordinary refresh. Do not recreate
  their DOM nodes on every update: users must be able to wait before confirming,
  and a click held through a refresh must still work without racing the update.
- Confirm submits the intended draft through existing identity and state checks;
  Discard restores broker-confirmed values. Real account/order identity changes,
  fills, cancellations or invalid state must still invalidate unsafe drafts.
  Never bypass broker guards or automatically replay trading writes.
- Support dragging anywhere on the visible editable order line. Use a vertical
  resize cursor on the line and a grabbing cursor when dragging its label or
  button segments. Long presses on those segments support dragging; short clicks
  retain their original actions. A drag must not accidentally cancel an order
  or open quantity editing, and an unchanged release must not amend the order.

When changing related UI, run the directly relevant checks, especially
`tests/chart/entry-one-click-page.cjs`, `tests/chart/one-click-protection.cjs`,
`tests/chart/fast-entry-drag.cjs` and `tests/chart/order-line-drag.cjs`.
Cover One-click on/off, desktop/mobile, draft persistence across polling, delayed
confirmation and a click held through refresh. Preserve tick-level delivery and
the existing 1/2/3/4-chart layouts. Report mock/browser results separately from
broker acceptance; do not place real orders merely to verify UI changes.

## Protected TP/SL presentation after quantity changes

The user approved this behavior at commit
`454c63ea008336fb61e8eed149c0b4e508bd43f2`. Preserve it across computers,
new conversations and all future UI changes unless the user explicitly requests
a behavioral change.

- After a quantity change is confirmed, TP and SL must retain the same ordinary
  label style throughout submission, waiting and reconciliation. Neither line
  should flash, disappear and reappear, or jump merely because a replacement
  order is awaiting confirmation. Do not add an extra `…` to either label for
  this quantity-change waiting state.
- Show waiting/unknown outcomes through the existing page-level order status.
  Consistent label styling does not mean the broker has confirmed the change.
- Preserve the display-only pending-stop handling: use valid, consistent prices
  from pending stop rows in the current snapshot, not cached prices from another
  account, contract or order. Do not fabricate confirmed protection or retain
  canceled, filled, missing, unknown or conflicting stop rows to hide a flicker.
- Keep order submission, replacement, reconciliation, One-click trading,
  Confirm/Discard and no-replay guards unchanged. This presentation rule does
  not override genuine broker state changes or the shared price-drag in-flight
  indication outside quantity changes.

For related UI changes, run `tests/chart/stop-pending-display.cjs` and
`tests/chart/quantity-stop-recovery.cjs`. Verify desktop/mobile rendering,
matching TP/SL styles, stable line identity through pending-to-confirmed updates,
and exactly one intended quantity-change request with no automatic replay.

## UI language: English until localization is explicitly requested

This rule applies across computers, new conversations and all future UI changes.
All new or modified visible UI text must be English only: buttons, menus, titles,
tooltips (including hidden/hover controls), placeholders, errors, help text and
visible annotations. Do not introduce Chinese text or mixed Chinese/English UI.
Keep every state of a control in English, including maximize, restore and reset.
Defer Chinese localization until the product and interactions are mature and the
user explicitly requests a coordinated localization pass. Continue communicating
with the user in Chinese. This does not authorize unrelated UI or behavior changes.

## Active iteration and branch cleanup

The active development and GitHub default branch is `Ben/wheel-1.8`.
It contains the full 1.7 history; do not treat an older branch's tip as the
latest development version. Rename the current Codex chat when the user advances
the iteration version. After each iteration, the user permits deleting obsolete
feature branches only after verifying ancestry into the active branch, closed or
merged PRs, and no deployment, signing, automation or ongoing-work dependencies.
Keep branches with unique commits or unresolved dependencies, historical tags,
Releases and rollback points. Branch cleanup is not deployment authorization.
Mini may remain on 1.7 until its separately authorized branch/entry-point migration;
verify the real machine before changing or removing that dependency.
