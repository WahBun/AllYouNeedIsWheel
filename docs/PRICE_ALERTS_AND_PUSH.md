# Price alerts and notifications

This adds two price-alert entries to the shared chart: **Add alert at…** in the chart context menu, and **Add alert on horizontal ray** in the selected ray toolbar (also available by right-clicking the ray). The editor includes saved alerts and a Stop action. All new visible labels are English.

The web workspace shows price, execution and confirmed-cancellation notifications in the **top right**, once per event per page, regardless of pane count. Notifications stay for ten seconds, pause dismissal on hover, and can be dismissed manually. The initial feed snapshot is silent. This is an in-page notification feed, not browser Web Push; a closed browser does not receive OS notifications.

## Monitoring and broker evidence

- The existing Mini backend monitors the exact IB conId, independently of open charts. Alerts belong to the selected account identity. Switching Paper/Live pauses the other profile's alerts; it does not reinterpret them for the new account.
- Conditions are Crossing, Crossing up and Crossing down. Trigger choices are Only once or Every crossing, with a minimum of one minute between notifications. These are live last-price alerts, independent of chart interval, not bar-close technical alerts. Maximum: 32 active alerts across eight exact contracts per account.
- The first live sample establishes a baseline. Delayed/frozen prices, reconnects, processing gaps and a gap exceeding 60 seconds between samples reset that baseline; the backend does not invent a crossing during an unobserved gap. If live data or the selected Gateway connection is unavailable, monitoring pauses. This does not guarantee detection of every exchange trade.
- A ray alert follows the server-accepted ray price. Moving a ray resets the crossing baseline. Deleting it stops the alert; restoring an old drawing cannot resurrect the stopped alert. A ray must finish syncing before its alert can be saved.
- Execution notifications use IB execution evidence, including partial executions, deduplicated durably by account and execution identity. Four-part IB correction revisions are not counted as extra executions. Historical executions before notification tracking began are silent.
- Cancellation notifications require a previously observed nonterminal order and IB's `Cancelled` status. A local cancel request, `PendingCancel`, a missing order, or a disconnect is insufficient. Persisted order identities support read-only reconciliation after reconnect/restart. Terminal state does not regress on a stale snapshot.
- No order submission, modification, cancellation, force binding or trading-write replay is added. No existing quote freshness, order-drag, confirmation, P&L or chart OHLC calculation is changed.

Notification state, device tokens and the outbox are stored in ignored `notifications.db`, separate from trading databases. `WHEEL_NOTIFICATION_DB` can select a private absolute path. The worker runs in the existing single backend process; do not run multiple application workers against the same notification database. IB work stays on the existing serialized owner. Tick callbacks only enqueue bounded events; SQLite and APNs delivery run outside those callbacks.

Events are persisted before delivery. APNs failures use bounded backoff, invalid tokens are disabled, and unsent notifications expire after one hour. Stable APNs event/collapse identifiers reduce replay duplication. APNs acceptance is not proof of device receipt, and transport retries cannot promise exactly-once OS delivery.

## Enable iPhone push after paid developer enrollment

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

Primary references: [TradingView horizontal ray alerts](https://www.tradingview.com/support/solutions/43000518121-horizontal-ray-drawing-tool/), [server-side alert monitoring](https://www.tradingview.com/support/solutions/43000548327-will-alerts-work-if-tradingview-is-not-open-on-the-computer/), [Apple APNs registration](https://developer.apple.com/documentation/usernotifications/registering-your-app-with-apns), [HTTPX HTTP/2](https://www.python-httpx.org/http2/), [PyJWT signing](https://pyjwt.readthedocs.io/en/stable/usage.html).

Local verification is recorded with the feature commit: targeted notification tests (including real ES256 signing with a temporary test key and mocked HTTP transport), guarded API tests, real shared-chart browser interactions using isolated synthetic data, related broker/state regressions, the market-data matrix, and an iOS Simulator build. These are not real IB/APNs or locked-device acceptance. Deployment, APNs provisioning, physical iPhone Run and real notification receipt remain user-operated follow-up steps.

### Verified locally on 2026-10-18

- 14 notification tests and 98 related account/order/quote/dispatcher regressions passed.
- Shared-chart alert flows passed at 1440px and 393px, in light and dark themes. The test covers the auxiliary-pane account epoch, both alert entry paths, ray binding, Stop, top-right placement and replay deduplication. Existing pane ticks continued throughout.
- Seven market-data latency cases passed, including 1/2/3/4 panes, two pages with four panes, 6000-bar history and a 200-tick callback. All visible panes received 30/30 sustained samples; source-receipt-to-chart-apply p95 was 1–7ms, within the preceding local baseline range. This excludes real network and display latency.
- Layout/recovery interactions, 100Hz stress and eight distinct symbols across two four-pane pages passed. Stress p95 reached 10ms in the dual-page case; all expected 180 updates and OHLC extremes were preserved.
- Final iOS Simulator Debug build succeeded, and the built app contains `chart-alerts.js`. No physical device was installed or launched.
- Mini was not deployed or restarted; Gateway and broker orders were not changed. Real APNs acceptance and locked-iPhone receipt remain unverified until setup and user-operated acceptance.
