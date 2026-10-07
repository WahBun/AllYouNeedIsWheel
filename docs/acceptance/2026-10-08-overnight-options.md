# Tonight options Paper acceptance continuation

User permits retained test positions and resting orders; do not flatten after every
phase merely to finish a turn. At Beijing 01:21 actual Paper reads confirmed QQQ
400 shares, SGOV 1000, option flat and no pending orders. Preserve these stocks.
Maximum actual short calls plus pending sells is four, subject to fresh server
coverage validation. Preferred QQQ Oct 16 2026 775 Call, conId 867924875. No CSP,
no naked calls, no Live writes or gate activation, no phone Run/install.

See options-live-readiness.md for completed tests and blockers. Remaining: protected
aggregate Trim implementation and verification; sustained partial fills of one
broker order; external actual fills/ownership races; isolated in-flight Gateway
interruption. Do not re-label already-tested client response loss or idle restart
as those cases. Never replay unknown writes. No test orders currently retained.

Automation wheel-paper checks this thread every 15 minutes through Beijing 04:00
2026-10-08. Check running scripts and journals first; never overlap trading tests.
At cutoff stop new tests, read and record any test holdings/orders/protection and
remove the automation. Retained test positions are permitted, but record their
exact broker identity and next step. Notify only substantive failures, required
user action, or stage completion; do not send routine progress notifications.

Current steering: native chart Add/Trim still used legacy scalable gate. Source has been updated to honor separate add_allowed / trim_allowed, with expected position
and captured group/contract identity. Simulator build passed; this is not device acceptance and no installation is authorized.

User reported stale stock average after adds: confirmed QQQ 400 shares while
entry remained the first 100-share price. Old completed parent has broker totals
but historical execution details are absent from the current session. When
complete execution reconstruction is unavailable, use IB position avgCost divided
by contract multiplier (includes fees), expose entry_source, and never silently
reuse the first fill. Invalid broker basis yields unknown/zero and rejects BE.
591 backend tests passed, including stock fallback, option multiplier, and invalid
cost. Actual Mini verification pending deployment. Existing protection projections
with incomplete execution history remain unknown; no fabricated group P/L.
