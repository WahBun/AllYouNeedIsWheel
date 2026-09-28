# Targeted raw execution timestamp diagnostic

Optional local connection configuration: `execution_diagnostic_order_ref` set to
an exact application order reference (`AYNIW-<database order id>`). An explicit
account_id is required. Keep execution_timezone absent while collecting baseline
source evidence. Configuration remains local and must not be committed.

The hook is installed on this IB instance's execution decoder handler before
connect. It observes only matching account + orderRef packets, and confirms execId,
account and reference against the actual decoded execution before logging. It
records raw timeStr, actual parsed time/UTC, execution identity, observation UTC,
TimezoneTWS setting, ib_async version and server version under
`EXECUTION_TIME_DIAGNOSTIC` in the existing connection logs (logs/tws). Account
number and complete packets are not logged. Execution identities are still private
operational data: retain the local logs, do not commit them.

The original decoder and callback run once, unchanged. The temporary callback is
restored in finally, including when decoding fails. This uses the existing serialized
connection thread, does not create a client, change a broker order, update historical
records or initiate another execution request. Existing connection startup execution
synchronization can capture evidence even when normal metadata backfill has no work.
At most 16 distinct target records are logged per process, duplicates suppressed.

Deployment: preserve the current config and consistent SQLite backup; review local
changes, pull GitHub, run tests, add only the diagnostic reference to local config,
and gracefully restart the backend once when no submission is in progress. Keep the
single worker and existing client ID. Do not restart Gateway. Record the version and
search existing local TWS logs for the diagnostic marker after normal connection
startup. If no matching execution is returned, absence of evidence is not a timezone
result. Stop and report; do not create test trades or guess an offset. Remove the
optional diagnostic configuration after collection and apply at the next appropriate
backend restart. The patch is not remotely deployed by the Pro development task.

A naive raw timestamp alone still does not identify its timezone. Compare the exact
execId to a broker-confirmed execution instant or a documented API output setting.
Do not choose America/New_York merely from the Gateway login timezone or UTC merely
from the container timezone. Any later historical correction must be narrowly matched
and separately verified; this patch contains no correction operation.

Validation: 166 Python tests passed. Seven new tests use the installed ib_async
Decoder to verify raw and parsed evidence, timezone-qualified summer/winter inputs,
account/order filtering, duplicate callback delivery, restore on decoding failure,
logging failure isolation, and rejection of unscoped configuration. Real broker
capture remains to be performed on Mini. The handler depends on the current ib_async
execution packet layout; decoded-identity checks prevent treating mismatched layouts
as evidence. Unknown handlers are rejected on diagnostic installation.
