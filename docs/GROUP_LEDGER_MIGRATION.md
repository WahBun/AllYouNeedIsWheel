# Order-group evidence migration and rollback

This is an additive, Paper acceptance candidate. No UI or quote delivery changes.
Existing request/group journals are retained. First migration uses SQLite backup
into `<database>.before-group-ledger.sqlite`. Migration adds immutable raw order
and execution evidence, exact ownership, a verified-flat-start baseline and
sticky conflicts. A backup left by an interrupted migration requires explicit
inspection; it is never overwritten automatically.

Group position is the signed sum of exact, deduplicated executions. Account
position is only a reconciliation check. Conflicting identities/corrections,
missing evidence, unknown orders and unassigned post-baseline executions block
writes. Pre-existing execution evidence may be excluded only when explicitly
observed at a no-group, no-position, no-working-order start; it is not allocated
to a new group. Missing history is never reconstructed from account net position.

Rollback: do NOT restore the pre-migration database or drop the new tables.
Quiesce execution first (requires permission for a normal service interruption),
make a fresh SQLite backup of the current complete database, preserve its hash
and all new request/intent/evidence rows, and keep that upgraded database as the
source of truth. An older executable is permitted for read-only diagnosis only:
it does not understand multi-group ownership and must not resume trading.
Return to the corrected executable with the same database after reconciliation.
An old-code writable rollback is unsupported. This avoids losing post-migration
intents/fills or replaying them from an old backup.

Acceptance must use the same candidate code, isolated process/client/database,
exact A/B one-contract fences, and actual Paper identity. Passing offline tests
is not broker or physical-phone acceptance. Do not deploy to the shared service
before A/B evidence is complete and interruption approval has been obtained.
