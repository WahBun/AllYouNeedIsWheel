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
