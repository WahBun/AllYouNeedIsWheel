# Performance (MTD / YTD / ALL)

Portfolio > Performance reads `/api/performance/history?period=YTD` and
`/api/performance/live`. History runs on a separate bounded background worker,
not the IB execution queue. Live P&L uses the existing single Gateway connection,
serialized dispatcher and one `reqPnL` subscription. It does not place orders.
Only the visible foreground screen polls (one second for P&L, one minute for history).

## Benchmark names

The app displays **SPX** and **NDX** (Nasdaq-100), with Portfolio only,
SPX, NDX and SPX + NDX comparison choices. The initial selection is YTD with both
benchmarks. The response field `nq100` and FRED series ID `NASDAQ100` remain
unchanged for compatibility; NQ100 is no longer the displayed benchmark name.

## Private configuration

Set `WHEEL_PERFORMANCE_CONFIG` on the backend process to an absolute private JSON
file. Do not put tokens in connection.json, Git, the
phone, or a command argument. Example shape (placeholders only):

```json
{
  "token": "YOUR_FLEX_TOKEN",
  "query_id": "YOUR_FLEX_QUERY_ID",
  "account_id": "YOUR_CONFIGURED_GATEWAY_ACCOUNT",
  "history_path": "/private/path/performance-history.sqlite3"
}
```

Use owner-only file permissions. Alternatively `report_path` may point to an
existing UTF-8 Flex CSV/XML file; this is a fixed import until the file changes.
Daily Change in NAV must include TWR, Starting/Ending Value and From/To dates,
with Breakout by Day. CSV must include section codes (CNAV). Account selection
is explicit; aggregate date ranges, duplicates and missing TWR are not treated
as daily return observations. Zero-value pre-funding dates are omitted.

### Token maintenance from iPhone

In **Settings > Access & Feedback**, expand **Performance data** to inspect
retained history, the latest successful refresh in this backend session, and an
optional recorded token expiry. Expiry is entered from IB; Wheel does not infer
it from the save date. Refresh time is unavailable after a backend restart until
the next successful refresh.

For an existing Flex configuration matching the selected account, use
**Replace Flex token > Validate token > Save validated token**. Validation
fetches and checks the account report without importing it or changing history.
Only the explicit Save action replaces the private configuration on Mini; the
phone does not persist the token. A validation expires after ten minutes, and
account switches or configuration changes require a new validation. An uncertain
save response is reconciled by refreshing its status, without automatically
repeating the write. Other applications sharing the token need the same update.

The initial feature deployment requires a backend restart and a new iPhone
build. Subsequent token replacements take effect on normal performance reads
without restarting Backend or Gateway. Query IDs, accounts, database paths and
local-report configurations remain managed on Mini.

Each successful report upserts daily TWR/NAV in a separate SQLite archive.
Older records outside the latest Flex window are retained. ALL means the stored
history available, starting at its first close, not an invented account inception.
Back up this archive with the private configuration. A future installation must
carry the archive over; a fresh one cannot reconstruct unavailable old records.

Historical curves prefer IBKR SPX (IND 416904 / CBOE) and NDX (IND 416843 /
NASDAQ) daily TRADES closes, excluding reinvested dividends. The existing live
endpoint schedules finite asynchronous reads on the same Gateway owner loop;
it creates no additional production connection or streaming subscription.
The first read backfills available account history (up to 20 years), then reads
the most recent 30 days. Successful reads retry after six hours or a new completed
session; missing data retries after five minutes. This runs while Performance is
open, not as a new always-on collector.

Only exchange sessions closed at least 30 minutes earlier are accepted, including
holiday/early-close handling. These are the latest broker-reported daily closes;
later broker corrections can replace them on subsequent reads. They are not a
guarantee that the vendor will never revise a close. Rows are saved separately as
`ib_benchmark_close`, including exact contract ID and fetch timestamp. Existing
FRED SP500/NASDAQ100 rows remain a fallback where IB history is unavailable; IB
wins on every overlapping date. `benchmark_sources` identifies the source of the
last displayed date for each index. Missing index days never become zero or a
carried-forward price; portfolio history remains available. The UI shows the actual
start/end dates, truncated coverage and cached data. Normal refresh TTL is six
hours, with a one-minute failure backoff and one in-flight history job.

## Intraday boundary

`dailyPnL` is an amount in the account base currency, not an official TWR. The UI
shows it separately. During regular weekday US market hours only, a fresh value
can extend the historical curve with a dashed provisional estimate using the
last reported NAV. This requires the final aligned history date to equal the
latest Flex date and a gap of at most four days. It is not a reconstruction of
past intraday samples. Cash flows, IB reset schedules and non-equity holdings can
make this estimate differ from the next official Flex TWR. Indices remain daily
closes; the UI does not label them real-time. No API market-data entitlement or
new paid subscription is enabled by this feature.

A live deployment needs the private configuration on Mini and a controlled
backend restart. Xcode compilation/mocked tests do not verify the Mini endpoint,
Gateway P&L callbacks, phone chart rendering or production freshness.

## IB daily-close validation (2026-10-20)

REA captured bounded read-only requests against the Mini Gateway, without a backend
or Gateway restart or order operations. SPX and NDX each returned 500 daily bars
from 2024-10-21 through 2026-10-19 without request errors. Latest reported closes
were SPX 7690.73 and NDX 29529.34. Evidence:
`ev_78df8fef61c38ded320f00dededdcc3a15139a36bf73039c48d210161691f4d0`.
The probe connection was disconnected after the check; production uses only the
existing shared connection. This establishes Gateway historical-data availability,
not deployment of this change or final acceptance on the user's phone.

## Trade review (iOS)

Portfolio > Performance > Trade review adds a realized P&L calendar, daily
execution detail and monthly symbol contributions. Existing TWR/benchmarks and
intraday account P&L keep their own definitions. The new view reads
`GET /api/performance/analytics` only while visible, with a bounded retry while
an existing Flex refresh is pending. It does not poll quotes or create a broker
connection. GET bypasses the IB queue and checks the selected account and epoch
both before and after reading the archive.

Optional query fields: `month=YYYY-MM`, `currency=USD`, `day=YYYY-MM-DD`,
`offset=0`, `refresh=1`. Daily detail returns 50 executions per page. A report
version change invalidates further pagination until Refresh, avoiding mixed
snapshots. The month response includes covered days, per-currency totals and
symbol contributions sorted by absolute realized P&L. Options use their reported
underlying symbol for ranking and retain exact contract fields in execution detail.

The same Performance worker imports execution-level TRNT/Trades from the report
already fetched for TWR. It reuses Wheel's validated execution parser and stores
account-scoped `analytics_executions`, `analytics_days`, and `analytics_status`
in the private Performance database. The report-covered window is replaced in
one transaction, removing corrected/deleted rows while retaining older months.
No order ledger is read or changed. A malformed execution report preserves the
last verified snapshot with a warning; it does not prevent TWR refresh.

- Realized FIFO P&L is reported net; commissions are shown separately, never
  subtracted twice. Received option premium is not realized profit.
- Original currencies stay separate. There is no implicit FX conversion or
  cross-currency total. Missing P&L remains unavailable, never zero-filled.
- Dates are report trade dates. New York execution time may be the previous
  evening for overnight futures/FX. No local-phone-timezone regrouping occurs.
- Covered dates with no executions show zero. Dates outside report coverage show
  a dash. Totals represent reported dates, not a promise of complete history.
- Initial history is limited to the execution detail in available Flex reports;
  TWR-only older history cannot reconstruct executions. Further reports extend
  the retained archive. There is no separate daily daemon or new Flex credential.
- Demo shows a connection prompt; no synthetic analytics are labeled as real.

Source comparison: REA static analysis of Studio `src/app.js` and `src/parser.js`
confirmed its clickable calendar, daily order recap and absolute-P&L contribution
ranking. Wheel adapts this to native SwiftUI and its existing execution identity
and fee rules, with explicit missing-data and currency handling. REA evidence:
`ev_eaab93ab88d4703ec97acf51b66679c60af1a09f998190db6d15ccdf17f50f56`.
This is static source evidence, not a Studio runtime interaction recording.

Rollout requires **Deploy & Restart Backend**, then a fresh iPhone build after
merging. Gateway restart is unnecessary. No Superchart/blueprint resources change.
Removing the Trade review entry and optional archive hook rolls back the feature;
the new private archive tables can safely remain. No release version is changed.

Validation for the first Trade review increment (2026-11-05):
- 48 focused Python cases across analytics, existing MTD execution history/TWR,
  and the analytics read while broker dispatch is busy passed.
- Six iOS Simulator cases passed: calendar/model/pagination/context isolation,
  320/393/834-point light/dark snapshots, compact help layout, and the existing
  live P&L loop with a delayed benchmark. Explanations now open from information
  icons beside Realized P&L, calendar, contributions, Daily P&L and Refresh.
- Mini archive was inspected read-only: report through 2026-11-03, nine retained
  executions across USD/HKD/CNH, no existing archive verification issue. This
  confirms existing source availability, not deployment of the new endpoint.
- No production write, real order, backend/Gateway restart or physical-device
  installation was performed. Screenshots use deterministic fixtures.

### Historical book entries (2026-11-05 follow-up)

The first complete production report revealed nine `BookTrade` records among
400 exchange executions: option expirations and assignment-related stock/option
entries. The MTD order-history parser intentionally requires `ExchTrade`, a
positive trade price and an execution ID. Reusing that strict default for a full
year incorrectly rejected the entire analytics import.

Analytics now opts into a separate report-only parser mode. Recognized
Assignment (`A`), Expiration (`Ep`) and Exercise (`Ex`) codes use namespaced report
TradeID/TransactionID identities; no Gateway execution/order ID is synthesized.
Zero-priced closed options are accepted for these events. Unknown types,
correction/cancellation codes, conflicting identities, negative prices and
invalid lifecycle terms still reject the new snapshot. The ordinary Orders
parser keeps its original defaults and checks.

Reported FIFO P&L from these records participates in the same date/currency/
symbol totals. `executions` counts exchange executions; `book_entries` counts
lifecycle records. Daily pagination includes both, and native detail identifies
Assignment/Expiration/Exercise as a Book entry. The information sheet explains
the distinction. Older responses without these optional fields remain readable.

IBKR references:
- [Trades - Flex Statement](https://www.ibkrguides.com/reportingreference/reportguide/tradesfq.htm)
- [Statement codes](https://www.ibkrguides.com/reportingreference/reportguide/codes_default.htm)

REA controlled replay captured the original rejection at
`ev_5086a790d7b467d51aed76fcbca7f0c6468eded7693f792990762e9ebb43b80f`.
The patched parser/archive was then replayed against the complete real Flex
report in a separate diagnostic process and temporary database: all 400
executions and nine book entries were retained across 13 calendar months
(2025-11-04 through 2026-11-03), with no archive warning. Production code,
production database and broker orders were not changed by that replay.

Validation: 50 focused Python cases passed across analytics, execution history
and Performance, plus four native simulator tests covering pagination, snapshot
isolation and light/dark layouts at 320, 393 and 834 points. Narrow-screen
calendar and lifecycle detail screenshots were visually inspected.

Rollout requires `Deploy & Restart Backend`, followed by the normal Flex report
refresh, and an updated iPhone build for separate activity counts and labels.
No Gateway restart or Superchart/blueprint resource update is needed. This
follow-up has not been deployed or installed on a physical device during validation.

### Daily/monthly commissions and toolbar entry (2026-11-05)

Performance now opens Trade review through a calendar icon in its trailing
navigation toolbar, with an accessible label and a 44-point minimum target.
The previous list-row entry is removed. Trade review displays Monthly commissions;
opening a reported calendar day displays Daily commissions. Explanations remain
behind the information icon.

Studio reference: source revision `dbf073f8507fc9eb1b8ebcf6b2e8cee062b9fecc`,
`analyzeDailyTrades`, `analyzeMonthlySummary` and `summarizeDailyTradeRows`.
REA examined `src/parser.js` and `src/app.js` and replayed the exported parser:
two daily charges of 1.25 and 2.50 total 3.75 for the month while reported net P&L
stays 7.50. Replay evidence:
`ev_f7cc534aae526a89504e5342d6156683b4dd5acd38c8e6e69a25bd02d6bc5ca5`.

Wheel adapts the existing daily/monthly aggregation to its verified Flex archive:
- Totals cover all instruments and trade currencies for the selected account and
  report month/day, independently of the P&L currency filter and detail pagination.
- Fees stay in their reported commission currency. Unlike Studio's base-currency
  conversion, Wheel keeps currencies separate. Existing signed fee values retain
  rebates as credits rather than converting them into positive costs.
- Missing amounts make that currency total unavailable. Covered no-activity days
  return an empty list; unreported days return null. A missing optional field from
  an older backend also displays unavailable. Replacement reports replace totals.
- Realized P&L is not reduced again. Market-data subscriptions and other account
  charges are excluded; fee-waiver eligibility is not inferred from these totals.

Validation: 13 analytics Python tests and six focused native simulator tests
passed, covering mixed trade/fee currencies, credits, duplicates, pagination,
missing/zero amounts, corrected reports, account isolation and older responses.
Dark/light calendar/detail layouts were rendered at 320/393/834 points; narrow
dark calendar, light detail and Performance toolbar screenshots were inspected.
A read-only comparison against the deployed
archive matched all 409 records across 13 months and 365 covered dates, with no
missing commission amounts. These reads did not fetch another Flex report or
write the production database.

After merge: Deploy & Restart Backend and rebuild/install the iPhone app. The
existing archive is sufficient; no report migration or Gateway restart is needed.
No Superchart/blueprint resources changed. Device installation and production
deployment are not part of this validation.


## 1.9.0 native presentation

Performance now uses the native pull-to-refresh gesture instead of a Refresh row.
The gesture waits up to four seconds for the existing history refresh. It ends
earlier on completion or failure; a pending/failed refresh retains the same-account
cached chart. Ending the pull indicator does not cancel the history task, and a
late result can still update the chart. The independent live P&L loop and
account/period isolation stay unchanged. Today has one information button with
both Daily P&L and Performance history explanations.

Trade review remains in the top-right calendar button. English, Simplified Chinese
and Traditional Chinese cover the review, help, fee totals and weekday labels.
Date grouping remains the report trade date and the calendar remains Sunday-first.
Commissions remain separate by fee currency and are not deducted from realized
P&L again. This UI update does not change accounting or order behavior.
