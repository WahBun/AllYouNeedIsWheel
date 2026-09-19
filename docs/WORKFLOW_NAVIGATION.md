# Workflow Navigation

Navigation is shared by phone and desktop and must never submit a trading action.
Use this checklist when adding another action, rather than wiring only one page.

| Action | Destination after success |
| --- | --- |
| Dashboard Add | Exact saved Pending row |
| Dashboard Add All | Last saved Pending row, once the batch ends |
| Add custom ticker | New PUT opportunity row |
| Portfolio stage close | Exact Pending row after the modal has hidden |
| Rollover Roll | Suggestions section |
| Rollover stage pair (including its batch button) | Closing leg in Pending |
| Cancel single open order | Matching Dashboard ticker and CALL/PUT tab |
| Cancel single close order | Matching Portfolio conId |
| Cancel rollover order | Rollover suggestions section |
| Cancel All | Current page's opportunity/position workspace, once all cancellations are confirmed and no active orders remain |

Failed, unknown or pending cancellations stay in Pending. External active orders
also prevent the bulk return. All cancellation requests settle before reporting
the batch result; no automatic retries. Prevent repeated clicks while a batch runs.

Execute, price/quantity/expiry edits, refreshes, background polling and removal
of a ticker keep the current reading position. Closing a dialog without staging
also stays in place. These are not workflow transitions.

Cross-page returns store a one-shot destination in sessionStorage, not an order
submission. Missing target rows do not cause a guessed click or automatic re-add.
Honor reduced-motion preferences; highlights are temporary.

Apply highlighting before measuring/scrolling, and keep its styles free of
scroll-margin or geometry changes. Transient alerts live in a fixed notification
container outside document flow. Mocked 393/1440-pixel checks verified unchanged
scroll position and target bounds after both highlight and alert dismissal.

Mocked browser checks: single staging/cancellation across all three pages at
393 and 1440 pixels, cross-page open/close returns, and Cancel All confirmed,
pending-confirmation and failure outcomes. No real broker writes were used.
