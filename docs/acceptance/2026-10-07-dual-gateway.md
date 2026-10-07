# Dual Gateway read-only experiment — 2026-10-07

Original single-instance Paper configuration was retained. A temporary Live container used the exact existing image, separate settings directory, loopback-only port, read-only API, no automatic restart, and user-confirmed IB Key. No broker orders were sent. The Wheel API owner was paused during sequential read-only probes and restored afterward.

| Probe | API connect | Identity | MNQ data over 8 seconds |
| --- | --- | --- | --- |
| Paper | 0.312 s | Correct | 0 updates; IB 10197 competing live session |
| Live | 0.677 s | Correct | 50 updates, real-time bid/ask |
| Paper again | 0.344 s | Correct | 0 updates; IB 10197 |

Conclusion: warm API switching is fast, but keeping Live logged in prevents this shared-subscription Paper session from receiving data even when the Live test API client is disconnected. This does not satisfy Wheel's requirements; no dual-mode change was adopted.

Rollback verified: temporary Live container stopped and removed; original backend restored with verified Paper identity. MNQ subsequently returned status live with current bid/ask and tick timestamp. Existing compose, account profiles, and original Paper container were not changed. Isolated test settings remain local and private.

IB also returned warning 2172: installed 1045.1 will be unsupported on 2026-12-15, with minimum 1050.1 then required. This is evidence for a separately tested Gateway upgrade, not evidence that upgrading removes shared-market-data restrictions.

## Asymmetric warm Paper follow-up

User prepared verified Live and authorized a read-only warm-Paper experiment after the stable 10.50.1f upgrade. Kept original Live configuration; separate readonly Paper container pre-authenticated on a private loopback port. Paused Wheel API owner while measuring, no order calls.

- Warm Paper API connection/account verification: 0.393 seconds.
- Starting the stop of original Live to container stopped: 0.428 seconds.
- Starting that same stop to first valid bid/ask returned on a renewed Paper subscription: 1.842 seconds (MNQ).
- Before stopping Live, the 3-second observation window had no quote. This short window did not reproduce a 10197 message; the earlier experiment documents that conflict.
- This is one first-quote observation, not a tick-by-tick latency claim, controlled repeated benchmark, sustained-feed test, or end-to-end phone/account-switch acceptance. Paper was already connected for measurement, so production API reconnection/UI latency is additional.
- Temporary Paper stopped and removed; original Live container and Wheel backend restored, with selected Live and verified account. Formal account-switch implementation remains unchanged. Consider opt-in prewarming only after further lifecycle/recovery testing; switching back to Live still requires authentication.


## Opt-in application integration

The account selector now supports a local `gateway/warm-paper.json` containing
`{"image":"ghcr.io/gnzsnz/ib-gateway@sha256:<verified registry digest>"}`.
Without that file the original single-service controller is unchanged.
With it, `ops/warm-gateway.yml` provisions separate Live/Paper containers, loopback
4001/4002 and separate settings directories under the private credential root.
Existing profile API permissions, account checks, databases and write epochs remain.
There is still only one application API client; standby is Gateway login only.

A verified Live status requests Paper prelogin once per Live selection/process.
Failed prelogin is reported separately and does not make Live unavailable. Selecting
Paper stops Live completely, then runs idempotent Paper compose up (no forced
recreate). Startup operations serialize; an obsolete queued prelogin cannot run
after a newer selection. Stop failure aborts handover. Selecting Live starts its
session and still requires IB authentication. No broker writes are added.

Provisioning must stop the original container and disable its auto-restart before
using the same host ports; retain it and its settings for rollback. Pin the tested
image, copy current Paper settings while stopped, and verify Paper account and
quotes after backend restart. To roll back: pause backend, stop both new containers,
rename the opt-in file, restore the original container restart policy/start it,
and resume backend. Never allow both deployments to compete for ports/sessions.

Regression: 22 focused Gateway/account routing tests passed. Phone end-to-end
Live-to-Paper latency is pending; the earlier 1.84-second probe preconnected the
Paper API too, while this implementation preserves a single API owner and connects
it after handover. Do not claim the experimental timing as a phone guarantee.

Deployment verification: 567 backend regression tests passed. Mini updated to
6d27446; original container retained stopped with restart disabled. Separate Paper
container started on loopback 4002, account verified, MNQ returned live bid/ask
with 50 ticks and 404 bars. No broker orders or phone installation. The user's next
Live-to-Paper phone handover remains the end-to-end latency acceptance step.


## Same-container dual login experiment

User authorized a read-only test of the same-machine exception, without buying
another data subscription or mixing Live market data with Paper execution.
The deployed stable image has native `TRADING_MODE=both`: two Gateway processes
in one container, independent settings and API ports. Both IBC configurations
were verified `ReadOnlyApi=yes`. The original backend and Paper container were
paused; original settings were copied into isolated experiment directories.
A ten-minute cleanup deadline and finally block restored the original deployment.

Both logins completed. One API probe at a time used the existing client identity
and checked the exact configured account before requesting MNQ market data.
Live remained logged in throughout all three stages:

| Stage | API connection | Updates over 10 seconds | Market data type | 10197 |
| --- | --- | --- | --- | --- |
| Paper | 0.319 s | 55 | 1 (live) | absent |
| Live | 0.756 s | 62 | 1 (live) | absent |
| Paper again | 0.341 s | 86 | 1 (live) | absent |

All stages returned valid bid/ask. Reported farm notifications included
2104/2106/2119/2158; these are not the competing-session error. These are quote
updates, not a count of trades. This differs from the earlier separate-container
experiment, but does not establish exactly how IB identifies a machine.

No order was placed, modified, or cancelled. Temporary container removed and
original Paper/backend resumed. This is an isolated short-duration experiment,
not deployed account-switch behavior or phone end-to-end latency acceptance.
The existing asymmetric warm handover remains installed. Sustained RTH operation,
reconnects, restart behavior and integration with the account selector still need
validation before adopting a permanent dual-session deployment.


## Permanent dual-session selector integration

Opt-in `gateway/dual-session.json` (same pinned-image format as warm-paper.json)
takes precedence over the asymmetric warm mode. `ops/dual-gateway.yml` uses the
image's native both mode, separate settings and loopback ports 4001/4002. Both
profile API permission values must match; provisioning never relaxes either.

When the shared container is running, selecting an account leaves both Gateway
sessions intact and immediately connects the existing serialized API owner to the
selected profile. Account identity verification, separate databases, unresolved
submission guards and epoch rotation are unchanged. Standby prelogin is disabled
in dual mode. If the container is stopped, one bounded compose startup starts both;
initial authentication and the image's Paper startup delay still apply. Container
running does not imply either broker session is authenticated: existing verification
continues to gate readiness. An expired login may require fresh IB Key authentication.
No promise of two-second cold startup or permanent login is made.

Rollback: pause backend, stop dual container and disable its restart policy, rename
dual-session.json, restart the retained original warm container(s) appropriate to
the selected profile and resume backend. Do not run competing deployments together.


Deployment acceptance: 571 backend tests passed; adfd3aa deployed to Mini.
Native dual container is active; old separate warm containers remain stopped with
restart disabled. Current account API permissions were preserved (no relaxation).
Both logins completed. Actual /api/account/select calls measured Paper 0.694s in
first pass, then Paper 2.316s and Live 0.992s in the second pass, each verified.
Container StartedAt remained unchanged with RestartCount=0. No trading endpoints
were invoked. Selected account was restored to Live.

Live initial chart reads returned transient HTTP 503 during this acceptance;
subsequent reads returned live bid/ask and 167 ticks. Paper also returned live
bid/ask. Account-ready latency is distinct from first-chart/history readiness;
these API measurements are not phone end-to-end or sustained RTH acceptance.
The known first cold-login connection attempt can time out before a subsequent
attempt succeeds; this change avoids cold login on ordinary warm switching,
without broadly rewriting connection/history recovery.
