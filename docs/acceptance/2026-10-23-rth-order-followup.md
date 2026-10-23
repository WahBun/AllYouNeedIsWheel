# RTH order follow-up — 2026-10-23

## Verified baseline and scope

GitHub, the Pro source checkout, and the clean Mini checkout were verified at
`Ben/wheel-1.8`, commit `dd3777484b49eea2438da566878770cb6b9cfa4c`.
This continues the evening Paper acceptance recorded separately in PR #63.
The user authorized continued bounded Paper acceptance and narrow repairs.
Existing QQQ holdings, Live trading, deployment, service/Gateway restarts, and
physical-phone operations remain outside this work.

## Observed behavior

REA inspected the existing dedicated Chrome Wheel target. A 45-second passive
sample of the QQQ four-pane RTH page saw successful API replies only. This is a
short observation, not evidence that contention has been eliminated.

Read-only request diagnostics for 21:33–22:23 Shanghai separated **130 read 503s**:

- **103 immutable-latest snapshot misses**. This endpoint bypasses the IB owner;
  these responses must not be counted as dispatcher queue rejection.
- **27 actual queue rejections**: ten execution reads, five chart-order reads,
  four history reads, two account-profile reads, two P&L reads, two volatility
  reads, one EMA read, and one pending-orders read.

No queue capacity, quote path, or polling frequency was changed. The earlier
121-response count used a shorter observation window and is not an A/B baseline.
Fourteen of the 27 actual rejections coincided with an identified HTTP owner job
(five pending-order reads, three EMA reads, two profile reads, and one each of
history, chart-order, P&L, and order POST). Thirteen could not be assigned to an
HTTP job from these diagnostics; background work and admission/release timing
remain possible explanations, not established causes. This does not justify
attributing all rejections to order writes or increasing queue capacity.

A new unprotected one-contract Paper limit entry was changed from DAY to GTC
through the actual chart order editor. The editor sent exactly one request,
including its unchanged price and quantity. The original order was still
PendingCancel at the approximately 5- and 10-second observations and Cancelled at
the approximately 15-second observation. No replacement or fill occurred. The UI
recovered to `Trading · done` and `Reconciled: canceled` without another POST.
This repeats safe late-cancel handling; it is **not successful TIF amendment**.

The [IBKR TWS order-modification guidance](https://www.interactivebrokers.com/docs/tws-api/doc/orders/modifying-orders)
recommends preserving the original identity for supported price/size amendments,
but its explicit TIF example is DAY-to-IOC. It does not establish DAY-to-GTC as a
supported direct amendment for this case. The existing cancel/replace policy and
its bounded cancellation wait were therefore retained.

## Narrow recovery repair

The investigation exposed two different mistakes in deciding whether an unknown
entry edit was a price-only amendment:

1. The full editor sends price, quantity, and TIF even if only price changed.
   Recovery formerly rejected the price-only rule merely because the unchanged
   fields were present. If a fresh broker snapshot retained the old price, the
   pending request could remain locked. Recovery now compares quantity/TIF with
   the original validated snapshot and uses the existing exact-parent read rule.
2. An OVT price change uses cancel/replace. The old price-only recovery rule could
   nevertheless resolve its pending cancellation from a still-working original
   parent. Recovery now excludes the OVT route from that rule. Confirmed late
   cancellation still releases the request without creating a replacement.

Both defects were demonstrated by failing isolated regressions before their
respective fixes. The runtime change only adjusts the read-only classification in
`PaperChart.request_status`. It changes no order submission, cancellation,
replacement, account routing, queue scheduling, chart layout, or quote delivery.

## Validation

- 28 entry-edit regressions pass, including full-editor timeout/restart recovery,
  absent authoritative evidence remaining unknown, genuine quantity/TIF changes,
  OVT cancellation, partial-fill races, stale snapshots, and no automatic replay.
- 125 related Paper order, process-fault, and status-recovery checks pass.
- The real-browser mock recovery test passes in Paper and Live modes at desktop
  and mobile widths. Unknown outcomes send no cancel/replay; confirmed recovery
  clears only its own account request; a subsequent explicit cancel sends once.
  Its legacy fixture needed the normal user unlock step after default-locked
  trading was introduced. Production UI behavior was not changed.
- `git diff --check` passes for the touched files.

These are local regression results. The candidate repair has not been deployed
or accepted against the broker; the live observations above used the verified
baseline. There was no physical-phone validation.

## REA evidence

- Target verification: `ev_ce8bab40470a03419bc0cca2832215fb81a1112fbd826f830dd9f248270dbdbf`
- Passive QQQ read sample: `ev_bb29bca439e657e91671af3450d51d870a18ac477465613d6ad918f0ad46f084`
- Actual TIF edit and late cancellation: `ev_818c52e830d58cb8639d1b7529a69dd787be69154b0f2f7cdf262743254661ff`
- Subsequent one-contract protection display: `ev_97a8f706688c05d79a4f4083dfc23f4baf2274b93763a9224581d2b8a12d760a`

## Delivery boundary

Backend Python changed. After merge and user-authorized deployment, choose
**Deploy & Restart Backend**. No Gateway restart or fresh iPhone Run is required
by this backend-only change. Reload the web page for the post-deployment check.
Unrelated local localization edits are excluded. Raw account data, request
journals, broker logs, and browser captures are not committed.

## Bounded natural-trigger observation

A separate one-contract Paper position received a TP at 3.30 and an SL at 2.61.
The settings were left unchanged while the market moved. Read-only broker and
REA page observations showed matching coverage and persistent TP/SL labels. The
roughly ten-minute observation ended without either protection order triggering.
This does not establish TP/SL-trigger acceptance or a natural partial-fill race.

The explicit bounded-test close then filled one contract at 2.65, and both TP and
SL were confirmed Cancelled. The test group returned to zero position with no
active orders. This was a manual test close, not a triggered protective exit.

Final broker reconciliation confirmed all six evening test groups flat, zero
pending orders, and the original QQQ holding unchanged. The original locked QQQ
four-pane RTH page was restored (REA
`ev_683a32adb65f2de8e417145a9cdee2384758e142e37fb7e127f804df90af2e3c`).
