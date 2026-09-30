# Performance (MTD / YTD / ALL)

Portfolio > Performance reads `/api/performance/history?period=YTD` and
`/api/performance/live`. History runs on a separate bounded background worker,
not the IB execution queue. Live P&L uses the existing single Gateway connection,
serialized dispatcher and one `reqPnL` subscription. It does not place orders.
Only the visible foreground screen polls (five seconds for P&L).

## Private configuration

Set `WHEEL_PERFORMANCE_CONFIG` on the backend process to an absolute private JSON
file. Do not put tokens in connection.json (which has legacy logging), Git, the
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

Each successful report upserts daily TWR/NAV in a separate SQLite archive.
Older records outside the latest Flex window are retained. ALL means the stored
history available, starting at its first close, not an invented account inception.
Back up this archive with the private configuration. A future installation must
carry the archive over; a fresh one cannot reconstruct unavailable old records.

Historical curves align common reported dates with FRED SP500/NASDAQ100 daily
price indices (not dividend-reinvested total-return indices). Missing index days
never become zero; TWR compounds across omitted dates. The UI shows the actual
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
