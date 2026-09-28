# Practical workflow review — 2026-09-28

Scope: current GitHub baseline plus the existing local iOS worktree. Review focused
on execution correctness, slow/offline broker behavior, refresh races and recovery.
No live order was placed, modified or canceled. No deployment or Gateway restart.

## Findings repaired

1. Gateway outage recovery attempted an existing connection and then a replacement
   in the same request. Subsequent polling could repeat both waits. The shared
   manager now makes one attempt, retains the same client object, and backs off
   for 10 seconds after failure. Changed connection settings bypass the old
   backoff; timeout is included in connection identity.
2. Accepted requests could wait behind broker work and execute after their caller
   had timed out. Unstarted jobs now expire after 10 seconds. HTTP wait timeout
   cancels only an unstarted future. Already running work retains its response
   path and is never falsely declared unsubmitted. No trading write is retried.
3. Stock/option qualification, option definitions, account-summary loading and
   open-order capacity checks had unbounded synchronous IB reads. Added five-second
   metadata/account read limits and three-second capacity read limits, restoring
   the previous IB timeout afterward. Capacity failures continue to block execution.
   Existing margin/preflight timeout policy is preserved.

These are per-call bounds, not an end-to-end latency guarantee. A workflow may
perform several reads and an initial Gateway connection. Running orders can still
outlive the phone's timeout; the existing unknown-outcome/review lock remains.

## Workflow coverage

- Connection: shared single IB executor/client, reconnect, changed settings,
  queue saturation, expired work, read coalescing, navigation outside the IB queue.
- Portfolio: account routing, live position handling, quote subscription cleanup,
  previous close and stale-data handling.
- CSP / covered CALL selection: exact contracts, valid expiry and strikes,
  quote readiness, finite prices and covered capacity.
- Execution: atomic pending-order claim, readonly enforcement, account validation,
  preflight rejection/timeout, unknown submission recovery, no blind retry.
- Close / rollover: exact held contract, remaining quantity, outstanding orders,
  close-before-open requirement, independent leg state.
- Order lifecycle: partial fills, terminal state recovery, external-order matching,
  deduplication and late fill time/commission persistence.
- iOS/web: refresh cadence/backoff, stale response rejection, manual price
  preservation, unsaved-edit checks, demo order lifecycle and write timeout lock.

Coverage above combines source inspection with existing/new regression tests;
not every combination was exercised end-to-end against IB.

## Validation

- Python unittest: 155 passed, including seven new outage/queue/read-limit tests.
- JavaScript node tests: 39 passed.
- iOS simulator build and XCTest: 63 passed on the existing local UI worktree.
- Read-only deployed probes: health 0.25s; portfolio bootstrap 0.37s;
  live portfolio 0.31s; all HTTP 200. Single samples, not percentile benchmarks.
- No UI changes in this patch; existing uncommitted UI work is not included.

## Remaining operational validation

- Mini must pull the new commit and restart only the existing backend using its
  established launcher. Preserve local configuration, database, Gateway and client ID.
- Repeat mocked regressions on Mini before restart and read-only checks afterward.
- Observe the next user-authorized real trade from staging to acknowledgement to
  fill metadata. No claim of guaranteed fills or market-time latency is made.
- Verify phone background/foreground, Tailscale loss/recovery and broker session
  expiry on the actual device. This run did not deliberately interrupt live services.
