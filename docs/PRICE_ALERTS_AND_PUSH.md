# Price alerts and notifications

This adds two price-alert entries to the shared chart: **Add alert at…** in the chart context menu, and **Add alert on horizontal ray** in the selected ray toolbar (also available by right-clicking the ray). The editor includes saved alerts and a Stop action. All new visible labels are English.

Active standalone price alerts appear as **pale-orange dashed lines with a broad, gentle light sweep** in every open pane for the same account and exact contract. Hover or focus reveals the condition, price, edit action and Stop button beside the price axis: right for a right axis, mirrored for a left axis. A small inset keeps High/Low badges from covering Stop. Drag anywhere on the line or its label and release to save the new threshold. A short label click opens the price editor; the focused line also accepts Arrow Up/Down for one-tick changes. The sweep spans 45% of the plot (180–640px) and takes 18 seconds per cycle. It pauses in the background and is removed for reduced-motion users. Ray-bound alerts continue to follow their original draggable horizontal ray rather than introducing a second independent threshold.

Dragging reuses the drawing tools' current **Off / Weak / Strong** magnet and temporary **Command** key mode. It selects the nearby candle's O/H/L/C prices with the same mouse/touch radius and jitter tolerance; a small ring marks the snapped point. Alert feedback is separate from drawing feedback, and only actual release persists the threshold.

Price changes compare the alert version and exact contract/account. A concurrent edit, stop or trigger rejects stale changes; the chart reloads the server state without resending the write. Changing account/contract, Escape, pointer cancellation or window focus loss cancels the local drag. Losing pointer capture alone retains the draft: document-level pointer handling follows the gesture until actual release and saves exactly once. Threshold edits establish a new live-price baseline and ignore queued samples from before the edit. An accepted change is shared immediately with matching panes; other open pages refresh saved alerts every two seconds. Saved-alert reads bypass the broker queue but retain an explicit account-epoch guard.

The web workspace shows price, execution and confirmed-cancellation notifications in the **top right of the chart area**, once per event per page, regardless of pane count. The container is transparent and hidden when empty, so it cannot cover the trading panel. Notifications stay for five seconds, pause dismissal on hover, and can be dismissed manually. The initial feed snapshot is silent. This is an in-page notification feed, not browser Web Push; a closed browser does not receive OS notifications.

## Monitoring and broker evidence

- The existing Mini backend monitors the exact IB conId, independently of open charts. Alerts belong to the selected account identity. Switching Paper/Live pauses the other profile's alerts; it does not reinterpret them for the new account.
- Conditions are Crossing, Crossing up and Crossing down. Trigger choices are Only once or Every crossing, with a minimum of one minute between notifications. These are live last-price alerts, independent of chart interval, not bar-close technical alerts. Maximum: 32 active alerts across eight exact contracts per account.
- The first live sample establishes a baseline. Delayed/frozen prices, reconnects, processing gaps and a gap exceeding 60 seconds between samples reset that baseline; the backend does not invent a crossing during an unobserved gap. If live data or the selected Gateway connection is unavailable, monitoring pauses. This does not guarantee detection of every exchange trade.
- A ray alert follows the server-accepted ray price. Moving a ray resets the crossing baseline. Deleting it stops the alert; restoring an old drawing cannot resurrect the stopped alert. A ray must finish syncing before its alert can be saved.
- Execution notifications use IB execution evidence, including partial executions, deduplicated durably by account and execution identity. Four-part IB correction revisions are not counted as extra executions. Historical executions before notification tracking began are silent.
- Cancellation notifications require a previously observed nonterminal order and `Cancelled`/`ApiCancelled` in IB's completed-order response. SDK status callbacks alone are insufficient because ib_async can synthesize a local cancellation for an untransmitted order; confirmation waits for a completed-order read on the approximately 15-second reconciliation cadence. A local cancel request, `PendingCancel`, a missing order, or a disconnect is insufficient. Persisted order identities support read-only reconciliation after reconnect/restart. Terminal state does not regress on a stale snapshot.
- No order submission, modification, cancellation, force binding or trading-write replay is added. No existing quote freshness, order-drag, confirmation, P&L or chart OHLC calculation is changed.

Notification state, device tokens and the outbox are stored in ignored `notifications.db`, separate from trading databases. `WHEEL_NOTIFICATION_DB` can select a private absolute path. The worker runs in the existing single backend process; do not run multiple application workers against the same notification database. IB work stays on the existing serialized owner. Tick callbacks only enqueue bounded events; SQLite and push delivery run outside those callbacks. Alert monitoring timestamps use a separate table, preserving the existing alert table layout for rollback.

Events are persisted before delivery. APNs failures use bounded backoff, invalid tokens are disabled, and unsent notifications expire after one hour. Stable APNs event/collapse identifiers reduce replay duplication. APNs acceptance is not proof of device receipt, and transport retries cannot promise exactly-once OS delivery.

## Enable iPhone notifications with Bark — no developer membership

1. Install [Bark – Custom Notifications](https://apps.apple.com/app/bark-custom-notifications/id1403753865) and allow notifications. Keep Lock Screen enabled in iOS notification settings.
2. Open the Wheel price-alert editor and expand **Phone notifications · Bark**. Paste the HTTPS push address or device key shown in Bark and choose **Enable Bark**. Enrollment belongs to the selected account; enable Paper and Live separately if both are wanted. Only the official `api.day.app` service is supported by this setup form. An existing price alert is not required to configure notifications.
3. Choose **Send test**, lock the phone and verify actual receipt. “Test accepted by Bark” only confirms the service accepted the request. Price, execution and confirmed-cancellation events use the same durable outbox, so closing Wheel does not stop delivery while the selected backend/account and live feed remain available. **Disable** stops new deliveries for this account; a notification already in transit may still arrive.

Bark receives the alert title/body, including contract, threshold or execution summary; these notifications do not include the broker account number. This implementation uses HTTPS transport, not Bark's optional end-to-end payload encryption. The device key is stored in the private notification database, never returned to the browser, and is cleared from the input after saving. The sender uses a fixed HTTPS endpoint with the key in the POST body and refuses redirects. It never sends to an arbitrary pasted host. Changing the key or disabling the subscription clears its pending deliveries, and a new registration does not replay historical events.

Bark delivery works without APNs keys, paid Apple membership, an app rebuild, or additional Python packages. Stable Bark notification identifiers reduce duplicate display on retries; unsupported server/client versions or uncertain transport outcomes cannot promise exactly-once delivery. Existing unconfigured native APNs entries cannot block Bark's queue. To install this backend change, the user selects **Deploy & Restart Backend** and refreshes the webpage; Gateway restart is unnecessary. Updating the native chart's line/drag UI still requires the user's normal iPhone build/Run.

## Optional native app push after paid developer enrollment

1. Enable Push Notifications for the app's actual Apple App ID. Create an APNs authentication key; keep its `.p8` file outside Git. The Team ID, Key ID and bundle identifier must match the signed app.
2. In the ignored `ios/Signing.local.xcconfig`, enable the included entitlement file:

   ```xcconfig
   WHEEL_PUSH_ENTITLEMENTS = Wheel/Push.entitlements
   WHEEL_APNS_ENVIRONMENT = development
   ```

   Development device builds use `development` (APNs sandbox). Distribution/TestFlight builds must set `WHEEL_APNS_ENVIRONMENT = production` and use the matching distribution provisioning profile. `WheelAPNSEnvironment` in the built app selects the corresponding delivery environment. The public defaults leave push entitlements disabled so free personal-team builds remain possible.
3. Provision these private environment variables for the Mini backend service:

   ```text
   WHEEL_APNS_KEY_ID=<Apple key ID>
   WHEEL_APNS_TEAM_ID=<Apple team ID>
   WHEEL_APNS_KEY_PATH=<absolute private .p8 file path>
   WHEEL_APNS_TOPIC=<actual signed app bundle identifier>
   ```

   Install the updated `requirements.txt` in the backend's existing environment. Do not put the key or service environment file in this repository. The `.p8` pattern and SQLite sidecars are ignored.
4. The user deploys this commit and restarts **Backend only**, then builds/runs the signed iPhone app. The Gateway does not need a restart for this feature. In the app, connect the intended account, open **Settings → Notifications → Enable iPhone notifications**, and allow notifications. Enrollment is per backend/account; enable each profile intentionally. The app refreshes its APNs token on launch/resume and keeps registration requests bound to the account epoch.
5. Verify a deliberately chosen price alert with the iPhone locked. Confirm the actual device receipt and the corresponding top-right web notification. Verify execution/cancellation notifications only during separately authorized broker testing; this implementation work does not authorize new test orders or changes to existing orders.

If registration fails or the backend is unavailable, Settings reports the failure and offers retry. If the phone is registered but APNs service configuration is missing, it explicitly reports setup pending. Disabling an account subscription is confirmed by the backend before the app reports it disabled.

## Reference and validation

REA inspected the current TradingView alert editor and its Notifications tab: Price/Crossing/Value, Only once/Every time, and app/toast/sound destinations. It also inspected the shipped alert/drawing source association: a chart context action supplies the clicked price, while a line source carries an alert association and synchronizes source changes. Evidence IDs: `ev_f3697f033a571def5747ef29539f8a28d333c7053423f7ac777fbfde4183cba9`, `ev_d4500347deb7092c025019c82f426d4f9eca2591e61ecc909dd5d9926846d415`; static analysis had a semantic-node coverage cap. No TradingView alert was created or modified. Wheel uses its own backend implementation and the requested top-right position; no TradingView source is copied into this feature.

For draggable lines, REA captured the user's two existing TradingView alerts (`ev_d5149dae3ab45db5e1cd7bae3aa6a7e949de5f5d9759647decb56fdba3727edd`) and their hovered label (`ev_d7d02b2bfd8d2751142b8a6f4dfba09c2da6ab8fd6f2ff01c8595ec35af5bf54`). Runtime inspection showed a dashed line, price-axis marker, hover label and remove control. A read-only inspection of the existing `AlertLabel.move` and coordinate conversion functions confirmed price-scale conversion and price-precision rounding. The reference alerts were never dragged or changed. Wheel's sweep is a user-requested visual variation; guarded persistence and multi-pane delivery are Wheel implementations.

Primary references: [TradingView horizontal ray alerts](https://www.tradingview.com/support/solutions/43000518121-horizontal-ray-drawing-tool/), [server-side alert monitoring](https://www.tradingview.com/support/solutions/43000548327-will-alerts-work-if-tradingview-is-not-open-on-the-computer/), [Apple APNs registration](https://developer.apple.com/documentation/usernotifications/registering-your-app-with-apns), [HTTPX HTTP/2](https://www.python-httpx.org/http2/), [PyJWT signing](https://pyjwt.readthedocs.io/en/stable/usage.html).

Bark references: [official app and usage](https://github.com/Finb/Bark), [POST request format](https://github.com/Finb/Bark/blob/master/docs/en-us/tutorial.md), [notification identifiers and parameters](https://github.com/Finb/Bark/blob/master/docs/en-us/params.md). [WebKit's membership-free Web Push option](https://webkit.org/blog/13878/web-push-for-web-apps-on-ios-and-ipados/) was also checked; the user selected a third-party notification app instead.

Local verification is recorded with the feature commit: targeted notification tests (including real ES256 signing with a temporary test key and mocked HTTP transport), guarded API tests, real shared-chart browser interactions using isolated synthetic data, related broker/state regressions, the market-data matrix, and an iOS Simulator build. These are not real IB/APNs or locked-device acceptance. Deployment, APNs provisioning, physical iPhone Run and real notification receipt remain user-operated follow-up steps.

### Verified locally on 2026-10-18

- 15 notification tests and 98 related account/order/quote/dispatcher regressions passed.
- Shared-chart alert flows passed at 1440px and 393px, in light and dark themes. The test covers the auxiliary-pane account epoch, both alert entry paths, ray binding, Stop, top-right placement and replay deduplication. Existing pane ticks continued throughout.
- Seven market-data latency cases passed, including 1/2/3/4 panes, two pages with four panes, 6000-bar history and a 200-tick callback. All visible panes received 30/30 sustained samples; source-receipt-to-chart-apply p95 was 1–7ms, within the preceding local baseline range. This excludes real network and display latency.
- Layout/recovery interactions, 100Hz stress and eight distinct symbols across two four-pane pages passed. Stress p95 reached 10ms in the dual-page case; all expected 180 updates and OHLC extremes were preserved.
- Final iOS Simulator Debug build succeeded, and the built app contains `chart-alerts.js`. No physical device was installed or launched.
- Mini was not deployed or restarted; Gateway and broker orders were not changed. Real APNs acceptance and locked-iPhone receipt remain unverified until setup and user-operated acceptance.

### 2026-10-18 web drag follow-up

The user confirmed iOS price editing works and reported the web line snapping back.
REA inspected the deployed four-pane Wheel page and its alert reads
(`ev_2c4b4fb09b29070e84447a3b6b8c5824ddfcfda8ba16f0d802e0123d8be85d57`).
A controlled replay in the same Chrome 154 version observed capture loss before
actual release, canceling the draft without a price write. The regression now
explicitly releases pointer capture on both line and label drags, holds across
alert polling and verifies one save on release. Old code fails this regression;
the fix passes desktop/mobile, dark/light and native touch checks. The protected
entry/TP/SL and One-click regression scripts pass without broker writes.

The user changed the requested color to pale orange and asked for a wider, slower
sweep. These static chart changes need **Deploy only** and a webpage refresh;
the native color change requires the user's normal iPhone Run. Mini was read-only
verified at `cec405947e1e4da672b25feeaece415e7cf8d045` before this follow-up.
The user's screenshot confirms the Wheel test notification reached Bark on the
iPhone. It shows a foreground banner, so locked-device display and real price/IB
event delivery remain separate acceptance checks.

The subsequent label/magnet request uses the current deployed drawing implementation
captured by REA (`ev_ca6c83f3d93053f3f70897a5df371c51b1af9aa250adf4483d12896dda624adb`,
source SHA-256 `b5721deebc5b2f0d84103aa4278e6344221acc6b5f640e6c3f5c91112a70d6a4`).
The same OHLC-selection function serves both callers, each with its own feedback.
Four additional desktop/mobile dark/light browser cases pass axis placement,
High/Low/Stop hit testing, Off/Weak/Strong, temporary Command and touch snapping.
The six alert cases and current Fib interaction regression pass. The legacy
`drawings.cjs` script still looks for the removed "Expand drawing tools" entry
and times out before reaching its drawing checks; it was not reported as passed.
