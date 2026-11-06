# Wheel: v1.9.0

iOS **1.9.0 (6)** · Web **1.9.0** · Branch **`Ben/wheel-1.8`**.

## Performance and Trade review

- Open Trade review from the calendar icon at the top right of Performance.
- Review monthly realized P&L, a daily P&L calendar, symbol contributions and paginated execution details. Assignment, exercise and expiration book entries are shown separately from exchange executions.
- See daily and monthly commissions for the whole account, separately by fee currency. Missing values stay unavailable; commissions already included in realized P&L are not deducted again. Subscription charges are not included.
- Pull down on Performance to refresh. The spinner closes after at most four seconds and keeps the current chart visible. If history arrives later, it still updates the chart. The information button beside Today explains daily P&L and history.
- Complete Simplified and Traditional Chinese for recent native screens, including review, help, commissions, contract search, indicator settings, notifications and maintenance. Instrument codes and standard trading abbreviations remain unchanged.

## Included fixes since v1.8.5

- Reduce repeated chart work during opening bursts and use fresh Level 1 trades through tick-by-tick gaps.
- Reconcile proven historical fills/closed groups and restore editing of eligible working orders on Superchart and iPhone.
- Improve option price-alert crossing detection after price edits and across sparse trades; open an alert's instrument from its notification.
- Keep drawing undo available with the drawing toolbar closed and after server synchronization.
- Apply the reviewed toolbar/footer layout and blueprint editing improvements.
- Recover incomplete frozen Trade quotes after account changes, recognize Flex lifecycle book entries, and recheck Gateway window geometry after automatic restarts.

## Optional cloud backup

A separate Mini job can encrypt completed database snapshots and upload them to Tianyi. It verifies each new archive by downloading it and comparing its SHA-256 digest. See [setup and recovery](ENCRYPTED_CLOUD_BACKUP.md).

## Upgrade

- **Mini running v1.8.5** — use **Deploy & Restart Backend** to load the intervening backend changes, then refresh the web page.
- **Mini already on #151** — the web and backend application files match this release. If you want the Mini checkout to match the tag, use **Deploy only**. The optional backup job has its own installation and schedule.
- **iPhone** — install the 1.9.0 (6) build from this release if upgrading from an older version. A device already running the #151 build has the same app code and resources.

## Validation

- The four-second refresh check retained the current chart and applied late history with one forced request. Success and failure paths were also tested.
- Six Trade review tests: report pagination/context isolation, missing values, commission decoding, localized help/weekdays and English/Simplified/Traditional layouts at 320/393 points.
- Native localization checks preserve broker contract identities, unknown diagnostics and trading abbreviations. The older Call/Put invariant was corrected to match the translations already present in the baseline.
- Catalog audit: 1,118 entries checked for both Chinese variants and interpolation consistency, with compiler-extracted UI-key coverage.
- Simulator build and signed iphoneos Debug build passed; package metadata is 1.9.0 (6), and all translated entries match the compiled localization resources. This is build validation, not a physical-device install or Live broker acceptance.
