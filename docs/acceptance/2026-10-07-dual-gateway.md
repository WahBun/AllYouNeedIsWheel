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
