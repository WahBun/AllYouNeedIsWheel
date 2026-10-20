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
