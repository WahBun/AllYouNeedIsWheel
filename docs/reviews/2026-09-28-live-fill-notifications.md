# Foreground Live fill banners

The accepted Demo banner now renders actual Order snapshots in Live mode, including
symbol, side, option, expiration, cumulative filled/total quantity and average price.
Tap opens snapshot details including Eastern time and available commission. Demo
remains labelled separately. Partial and complete events share a queue; each banner
expires after six seconds, with explicit close and haptic feedback. Detail sheets
pause queue advancement. The overlay covers main tabs/navigation, not other presented
modal sheets; it is not an iOS background/lock-screen push notification.

The existing foreground order refresh is reused. History is fetched at initialization,
on disappearance from Pending, and otherwise at most every ten seconds (failed reads
can retry on the next existing refresh). Disappearance alone never means filled.
First successful combined snapshot is silent. Confirmed cumulative quantity increases
are deduplicated by local ID and permanent broker ID, including partial fills,
reconnections and later fee enrichment. Unknown historical rows are silent unless
their broker timestamp is newer than this session's tracker start. This accommodates
fast fills between polls, but incorrect/missing broker timestamps for previously
unseen orders cannot safely trigger a notification. Baseline resets on mode/backend
change. Backgrounding clears queued banners while retaining in-session deduplication.

No backend deployment is needed for banners. Existing API history limits (latest 50)
and broker-managed orders not persisted by the backend constrain coverage. Notifications
require the app foreground, a successful status/history response and actual filled
quantity; there is no instant delivery guarantee. Trade tab polling remains ten seconds.
No broker writes, automatic execution or retry behavior were added.

Tests cover silent baseline, partial/full, stale snapshots, fee-only updates,
disappearance, old unseen history, broker/local deduplication, fast new fills,
queue/detail/close behavior, mode reset, and pending-to-history integration across tabs.
Validation uses an isolated staged export and mocked network, not live orders.
The approved visual structure is retained; new layout combinations and real haptics
were not independently verified on a physical iPhone.
