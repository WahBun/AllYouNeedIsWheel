# iOS interaction performance — 2026-09-28

Preserves existing layout, trading data and execution rules.

- Portfolio/order refresh tasks remain alive across tab changes rather than
  canceling and restarting requests. Foreground, mode and backend changes still
  restart the tasks; each iteration reads the current tab to select its cadence.
- A shared bounded cache holds successful nonempty expiration/strike lists for
  five minutes, keyed by full backend URL and query. Same-key concurrent requests
  share one fetch. New York date rollover and context reset invalidate cached
  metadata. Empty responses and failures are not cached. Quotes, coverage and
  order state always bypass this cache.
- Opening the strike sheet no longer waits for an unrelated multi-symbol quote
  refresh loop. It requests metadata immediately; the backend still serializes
  IB access. The previous independent 30-minute strike cache is no longer used.
- After acknowledged staging, navigate to Orders before awaiting its refresh.
  This does not navigate on failed staging or invent a broker acknowledgement.

Verification: first local iOS build/test passed; isolated staged build/test passed
67 tests including seven new metadata-cache tests. Mocked TradingSession test
performed five repeated pairs of metadata reads with two HTTP requests instead
of ten, while repeated quote reads still issued separate requests. Tests cover
expiry, date rollover, context reset, backend/contract isolation, empty/error
responses and concurrent request sharing. Demo simulator manual check covered
Trade -> TSLL -> strike sheet, showing the existing selected strike and list.

No real-device frame-rate benchmark or live first-load latency improvement is
claimed. Cache hits accelerate repeated list reads; first loads and live quotes
remain dependent on network/IB response. This change is iOS-only: rebuild and Run
on the phone; no backend or Gateway restart is required. Existing unrelated local
UI edits are preserved but excluded from this commit.
