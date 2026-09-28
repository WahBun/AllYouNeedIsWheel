# Demo fill banner and Eastern time display

Demo mode Settings includes a fill notification preview. After tapping, it schedules
partial 1/2 at 3 seconds and full 2/2 at 11 seconds. Each top banner dismisses after
6 seconds, supports explicit dismissal and opens a Demo detail sheet. The sample
is explicitly labelled Demo; no real order is created, updated or observed. Mode
changes cancel the preview. Background notifications and live fill detection are
not implemented in this preview. The overlay spans root tabs, not every modal.

Order detail timestamps now use America/New_York and en_US_POSIX, displaying EDT
or EST according to the timestamp. UTC/offset parsing is unchanged. This corrects
device-dependent presentation, not already incorrect persisted timestamps.

Investigation: the installed ib_async decoder assigns TimezoneTWS to timezone-naive
execution times when configured; otherwise Python astimezone uses the host timezone.
The application does not currently set TimezoneTWS. A broker/host timezone mismatch
is therefore a possible source of shifted persisted timestamps. The affected Mini
record and raw broker time have NOT been inspected: SSH authentication failed.
Do not bulk-shift stored timestamps or assume the Gateway timezone is UTC.

Mini follow-up: read the affected order's stored fill_time, existing execution logs,
Gateway/API timestamp timezone setting, host timezone and installed ib_async version.
Compare a broker-confirmed execution instant before selecting the timezone fix.
Use the existing serialized broker connection; do not create another client or
place/cancel an order. Do not restart Gateway during diagnosis.

Validation: an isolated export of the staged files built and passed all 68 iOS tests.
New date assertions cover UTC, +08:00 equivalence, winter EST, summer EDT, fractions
and a previous-day conversion. Simulator Demo settings/preview entry was observed.
Full animated banner interaction, bilingual/theme visual checks and haptics remain
unverified: Device Hub capture/input intermittently failed during UI verification.
No backend changes or production record edits are included.

## Explicit backend timezone configuration

The backend accepts optional `execution_timezone` in its existing connection JSON.
Set an IANA zone such as `UTC` or `America/New_York` only after confirming the API
execution output convention. The value is validated before client construction and
assigned to ib_async.TimezoneTWS before connecting. An omitted value retains the
library default; this compatibility default does NOT fix ambiguous timestamps.
Changing it replaces the shared connection through the existing manager, so apply
only at a suitable service update boundary, not while a submission is in progress.
Timezone-qualified execution times are normalized to UTC before persistence.

159 Python tests passed, including explicit configuration, invalid-zone rejection,
connection identity and seasonal UTC conversion. No deployed configuration or stored
record was changed. Raw API output and targeted historical correction remain pending.
