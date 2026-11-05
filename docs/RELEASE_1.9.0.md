# Wheel: v1.9.0

Release candidate · iOS **1.9.0 (6)** · target branch **Ben/wheel-1.8**.
Prepared for user review; not yet merged, published or deployed as this release.

## Performance and Trade review

- Open Trade review from the calendar icon at the top right of Performance.
- Review monthly realized P&L, a daily P&L calendar, symbol contributions and paginated execution details. Assignment, exercise and expiration book entries are shown separately from exchange executions.
- See daily and monthly commissions for the whole account, separately by fee currency. Missing values stay unavailable; commissions already included in realized P&L are not deducted again. Subscription charges are not included.
- Pull down on Performance to refresh. One information button beside Today holds daily P&L and history explanations.
- Complete Simplified and Traditional Chinese for recent native screens, including review, help, commissions, contract search, indicator settings, notifications and maintenance. Instrument codes and standard trading abbreviations remain unchanged.

## Included fixes since v1.8.5

- Reduce repeated chart work during opening bursts and use fresh Level 1 trades through tick-by-tick gaps.
- Reconcile proven historical fills/closed groups and restore editing of eligible working orders on Superchart and iPhone.
- Improve option price-alert crossing detection after price edits and across sparse trades; open an alert's instrument from its notification.
- Keep drawing undo available with the drawing toolbar closed and after server synchronization.
- Apply the reviewed toolbar/footer layout and blueprint editing improvements.
- Recover incomplete frozen Trade quotes after account changes, recognize Flex lifecycle book entries, and recheck Gateway window geometry after automatic restarts.

## Upgrade

Merge the reviewed PR before publishing this Release. A new iPhone build/install
is required. Updating GitHub or Mini alone cannot update the installed app.

For a Mini already running the Trade review/commission changes through #147,
this release-preparation PR needs **Deploy only**, with a page refresh for web
version metadata. A Mini upgrading directly from v1.8.5 needs **Deploy & Restart
Backend** for the intervening backend changes. No Gateway restart is required.
Existing Releases and tags remain available as rollback references.

Live orders were not placed, modified or canceled for release verification.

## Candidate validation

- Native pull-to-refresh: one forced history refresh per gesture; spinner waits for completion; success and failure end refreshing; failed requests retain the same-account chart.
- Six Trade review tests: report pagination/context isolation, missing values, commission decoding, localized help/weekdays and English/Simplified/Traditional layouts at 320/393 points.
- Native localization checks preserve broker contract identities, unknown diagnostics and trading abbreviations. The older Call/Put invariant was corrected to match the translations already present in the baseline.
- Catalog audit: 1,118 entries checked for both Chinese variants and interpolation consistency, with compiler-extracted UI-key coverage.
- Simulator build and signed iphoneos Debug build passed; package metadata is 1.9.0 (6), and all translated entries match the compiled localization resources. This is build validation, not a physical-device install or Live broker acceptance.
