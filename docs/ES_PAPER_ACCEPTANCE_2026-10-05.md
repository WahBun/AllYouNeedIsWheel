# ES Paper ETH 验收记录 — 2026-10-05

范围：北京时间约 06:02–06:32，IB Paper，CME ESZ6（2026-12 到期），仅模拟交易。主测 Mini 后端和网页版。未切换 Live，未操作其他标的持仓，未安装或运行新的 iPhone 构建。

## 结论

核心订单流程在实际 IB Paper ETH 会话通过。六项实测发现的问题已修复、推送 GitHub 并部署 Mini。最终代码版本 `a2ae26c`；417 项后端测试在 Pro/Mini 均通过。最终 ES 持仓为零、活动订单为空；已有其他持仓保持原样。

这是本次指定场景的验收结果，不代表所有异常路径或 Live 验收通过。

## 实际券商测试

| 场景 | 结果与证据摘要 |
| --- | --- |
| Paper/合约/行情 | 已验证 Paper 模式、端口 4002、ESZ6、实时 IB tick；未使用历史报价替代实时成交依据 |
| 旧单对账 | 历史 303/319 订单组确认撤销、零成交；修复 Orders 缓存复活后活动列表为空 |
| 多/空 LMT | 提交、改价、1→2→1、DAY→GTC、撤单通过；多头首次改价使用实际鼠标拖动，331 单从 7750 改至 7756.25 |
| 数量/TIF 替换 | 旧订单结束后生成新身份；两手拆单的每个父单均关联到同一图表订单组 |
| 多/空仓位管理 | 4→Add 2→6→Trim 2→4→Close→0，实际成交和 TP/SL 覆盖核对通过；最终版本重新跑过多头流程 |
| 分批入场 | 实际观察到一组四手先成交三手、剩余一手待成交；最终版本显示有效 TP/SL 各三手，待入场子单各一手。不是单张多手委托内部部分成交的认证 |
| BE 多/空 | 按成交价格基础及 0.25 tick 核对。多头 7785.50→7785.75；空头 7784.75→7784.50；后续退出归零。BE 不保证扣费后盈亏为零 |
| ETH SL — DAY | 多头、空头均实际触发成交，另一侧 TP 撤销，最终归零 |
| ETH SL — GTC | 多头实际触发成交，TP 撤销，最终归零；跨日持久性未在本轮验证 |
| TP/OCA | 多头 DAY、空头 GTC 分别通过改价使 TP 可成交，实际成交后 SL 撤销，无反向持仓 |
| STP 突破单：提交/改单 | 多/空停止单提交、改触发价、实际触发成交、Close 归零；空头曾超过短观察窗口，继续只读对账后确认原单成交，没有重发 |
| 持仓重启 | 六手多头及十二张退出单在后端重启后恢复；修复成交记录对账后减仓成功，没有重复下单 |
| A/B 独立组 | 同合约两组挂单；改 A 不动 B，重启后编号/价格一致，撤 A 后 B 三张单仍保持原状；最终全撤净 |
| 幂等/陈旧请求 | 原样重放同一 request_id 无重复订单；旧账户 epoch、旧改单快照被拒绝且无额外交易写入 |
| 网页观察 | Paper/ETH、订单线、首次鼠标拖动、Orders 返回 B 组已实测。其余批量操作通过同一公开后端 API 进行，不等同全部动作已完成手机 UI 验收 |

## 突破单自然触发补测

按用户用语将 STP 称为“突破单”。未改单自然触发与把触发价改到现价另一侧的路径分开记录。

- 多头：实时成交 7784.75、卖价 7784.75，固定买入触发价 7785.00（高一跳），保留触发价等待。IB 实际成交 7785.25，随后 Close 归零；触发价没有修改。这也说明触发价不保证等于成交价。
- 空头：实时成交/买价 7785.00，固定卖出触发价 7784.75（低一跳），未改单，IB 实际成交 7784.75。

### Close 的实际执行边界

本实现将原有 TP 限价单调整到实时买/卖价进行退出，保留对应止损和 OCA，因此 Close 不是保证立刻成交的市价平仓。

空头自然突破补测中，Close 的买入限价 7785.00 因市场移动而仍在 Submitted，仓位仍为 -1；系统正确保留 working/pending 和一手保护，没有误报平仓或自动重复下单。只读确认当前卖价 7786.00 后，将同一张退出单改为 7787.00，实际成交后仓位归零、SL 取消。此场景验证了未立即成交时的对账和原单修改，不能把“Close 请求已确认”当成“已平仓”。

## 已修复问题

1. `f1938f3`：期权与期货列表共用最新 IB 快照，防止五秒节流分支回退旧缓存，让已撤单再次出现。
2. `8256af5`：拆成多个单位的期货父单保留图表订单组关联。
3. `3de290e`：期货 Trim/Close 使用 ETH 行情检查；原先写死 RTH 导致实时 ETH 行情被拒绝。
4. `abcef9c`：重连后加减仓使用恢复后的成交记录，避免图表已识别成交、减仓校验却误报不一致。
5. `551f82a`：期货单位括号单设置 outsideRth；原先挂着的止损可能不在 ETH 触发。DAY 与 GTC 都已通过实际 SL 触发对照。股票/期权的默认时段策略未扩大。
6. `a2ae26c`：区分待入场子单与已成交仓位保护，消除分批入场时把待激活退出单算作现有仓位保护的误报。

GTC 决定跨日有效性；outsideRth 决定是否允许时段外触发/成交，两者独立。依据：[IB Order 文档](https://www.interactivebrokers.com/docs/tws-api/ref/order)、[IB 交易时段说明](https://www.interactivebrokers.com/en/trading/trading-hours.php/1000)。

## 本地/模拟回归

- Pro 与 Mini：417 项 Python 后端测试通过。
- 图表 paper-orders：单次提交、拖动修改、券商确认关闭的浏览器模拟测试通过。
- independent-orders：未知旧单不阻断独立新单且旧请求锁保留，通过。
- web-superchart：提交/编辑/撤单、Orders 同步、响应丢失恢复、Live 隔离及响应式回归通过。
- 浏览器模拟测试使用独立的纯页面服务及 API mock，未创建第二个 IB 客户端。

## 未验证与后续

- 物理 iPhone 锁屏/前后台、Wi-Fi/蜂窝切换，以及手机与网页真实双端竞争。
- 真实网络中断造成的请求已执行但响应丢失；现有覆盖为 mock 和原样请求重放，不能等同真实丢包。
- 可稳定复现的撤单撞成交、券商拒绝退出、多手单内部部分成交；已有故障注入回归，但本轮没有相应券商实况证据。
- GTC 跨交易日存续、RTH 特有行为、QQQ 正股/期权、Live，均不在本轮通过范围。
- 修改后的部分入场统计有实际三手已成交/一手待成交证据；不保证异步事件的每一个瞬间都已被观察。

后续先补 ES 异常与真机缺口，再扩展 QQQ。图表库仍为 5.2.0；纯视觉优化继续暂停。

## 证据保管

原始带时间戳的请求/响应、测试日志及本轮临时验收脚本保存在本机 `logs/acceptance/2026-10-05-es-eth/`，按仓库规则不提交原始日志。脚本是本轮专用证据，不应在未核对账户、合约、当前订单和持仓时直接重跑。

## Web rapid-drag acceptance, 06:52–07:03 CST

Scope: ESZ6, verified IB Paper, web only; Close remains the existing bid/ask limit exit. No iPhone build or installation.

Reproduced before repair: after releasing an entry-price drag, the pending HTTP write disabled the order handle; an immediately following drag did not amend the order. Also observed web preview entry moves leaving TP/SL at their old absolute prices, allowing the preview SL to end up above a buy entry.

Repair (`8aefebd`, published to GitHub and deployed on Mini):
- During a price amendment, the same entry/TP/SL handle remains draggable. Keep only the latest released target for that role; send it after the prior amendment is acknowledged and its returned price matches the request.
- Recheck account epoch, chart generation, order reference, order IDs, quantities, fills, TIF and position before sending the queued target. Discard it after rejection, unknown/lost response, fill or identity change. No write replay after reload.
- Entry snapshots refresh when an earlier acknowledged amendment finishes during the next drag. Reads started before a write cannot overwrite its resulting state.
- Distinguish pending targets in the web status and order label. Web preview TP/SL translate with entry, retaining their selected distances. Native behavior is gated separately and was not installed or accepted on a phone.

Actual broker evidence: one unfilled BUY LMT, quantity 1, DAY, with parent 511 and TP/SL 512/513. Rapid entry changes finished at 7776.75. Three TP drags targeted 7786.00 → 7784.00 → 7785.00; IB ended at 7785.00. Three SL drags targeted 7766.00 → 7765.00 → 7766.50; IB ended at 7766.50. Activity showed two serialized writes for each three-drag protection sequence, coalescing the intermediate target. Chart, Orders and fresh broker-derived snapshots agreed; order IDs stayed 511/512/513 and fills stayed zero. Final cancellation confirmed all three Cancelled, ES position zero, protection flat and pending-orders empty. Existing SGOV holding was not changed.

Validation: 417 backend tests passed; host queue regression covers latest-target coalescing, fresh snapshot, TP/SL, fill/identity/quantity/account change, rejection, unknown outcome and lost response. Existing entry-edit and paper-orders chart regressions passed; web-superchart covers submit/edit/cancel, Orders sync, reconciliation and Live isolation.

Limits: actual rapid-drag broker evidence in this addendum is an unfilled long LMT and its contingent TP/SL. Held-position rapid protection edits, short/STP rapid sequences and a real fill arriving mid-drag were not separately accepted here. One in-flight role is freely re-draggable; other order actions/roles wait for its confirmation. This does not certify Live trading or guarantee immediate fills.

## Held positions, confirmation latency and fill overlap, 07:08–07:19 CST

Continued on verified ESZ6 IB Paper, one contract per group, web only. GitHub code: `2790603` then `ce6b2f7`; stable web status layout: `c60a98f`.

### Findings and repairs

- `ib_async.placeOrder` immediately mutates the local Trade. The old protection-amend check could accept that local echo as acknowledgement. All price amendments now capture immutable requested price/identity and confirm them against a completed broker open-order snapshot (or an actual Filled event).
- Actual Paper testing showed the first snapshot can still contain the previous price. A single immediate snapshot caused premature `unknown` responses at 256–287 ms even though the requested change subsequently reached IB. The bounded confirmation loop now waits for broker events and re-reads within three seconds; it sends the write only once. Late protection acknowledgements can reconcile through the read-only request-status endpoint.
- Removed the fixed 200 ms post-action sleep for entry/protection edits already covered by their confirmation/cancellation logic. This is not a claim of a measured net 200 ms improvement.
- Order status text wrapping changed iframe height, resetting the manually adjusted price scale and pushing a TP handle out of view. Fixed the footer height and kept long feedback on one truncated line with full hover text/Activity details. Actual three-drag measurement remained 496.75 px throughout; existing 1440/393 web regression now checks this invariant.
- A fill received while an entry handle is held cancels the stale drag and restores the broker entry basis. Release emits no amendment for the filled entry. Protection edits optionally validate the expected order reference as well.

### Actual Paper results

- Group parent 523: buy limit changed to 7788.75, filled 1 at 7787.50; SL ultimately confirmed at 7778.50 with position covered. During discovery of the premature-unknown issue, Close first rejected for a stale quote without writing; after a fresh quote, the existing TP 524 filled at 7787.00 and SL 525 canceled. Verified flat before the next deployment; no retry of the uncertain write.
- Long parent 535 / TP 536 / SL 537: actual long 1 at 7787.75. Held SL rapid changes confirmed; held TP changes ended at 7800.25. SL dragged into the trigger region and immediately dragged again; original SL filled one contract and TP canceled. Final position 0, no reverse position or active exit order.
- Short parent 538 / TP 539 / SL 540: sell entry amended to 7785.25, filled one at 7787.25. Held TP rapid changes ended at 7776.75; held SL changes ended at 7797.50. Four releases into the SL trigger region coalesced into three amendments; the original SL filled one contract, TP canceled, final position 0 and no pending orders. No replacement exit or duplicate entry was created.
- Page reload while the long position existed recovered the same order group and protection without resubmission. Existing SGOV holding remained unchanged.

### Measured latency

Timing begins in the iframe message emitted by release and ends after the broker-confirmed response is applied on the host page. Includes postMessage dispatch, waiting behind an earlier amendment, transport, serialized backend work and broker snapshot verification. UI drag/render frame latency was not separately instrumented. Small sample; not a Live latency guarantee.

Final stable-layout run, 14 confirmed amendments (milliseconds):

| Role | Target | Release to response | Request duration | Queue/dispatch wait |
|---|---:|---:|---:|---:|
| TP | 7801.00 | 791 | 790 | 1 |
| TP | 7800.25 | 644 | 526 | 118 |
| SL | 7789.00 | 547 | 547 | 0 |
| SL | 7789.50 | 950 | 847 | 103 |
| Entry | 7785.25 | 1399 | 1400 | 0 |
| TP | 7776.00 | 681 | 683 | 0 |
| TP | 7778.00 | 1134 | 856 | 278 |
| TP | 7776.75 | 1164 | 451 | 713 |
| SL | 7798.50 | 592 | 593 | 0 |
| SL | 7796.50 | 880 | 622 | 258 |
| SL | 7797.50 | 983 | 505 | 478 |
| SL | 7785.25 | 784 | 788 | 0 |
| SL | 7784.75 | 875 | 535 | 340 |
| SL | 7783.75 | 809 | 753 | 56 |

Median release-to-response 842 ms; min 547 ms, max 1399 ms. Millisecond clock sampling/rounding can cause a few milliseconds of difference between the columns. Earlier same-backend held-SL run before the footer fix recorded 525, 1105 and 1160 ms (the latter two included 248 and 667 ms queue waits).

### Validation boundaries

423 backend tests passed, including optimistic local echo rejection, first-old-then-current broker snapshot, late protection acknowledgement without replay, fill during amendment, idempotent fill outcome and replaced-reference rejection. Host queue tests cover discarding queued entry and protection changes when a fill/identity change arrives. Browser gesture tests inject a fill while the pointer is held and verify that release sends nothing stale and displays the actual entry basis.

Actual broker coverage includes held long/short TP and SL rapid amendments, marketable entry amendment followed by fill, and SL trigger-region amendments followed by actual exits/OCA cancellation. Exact ordering of a real broker fill between pointer-down and pointer-up was not controlled or independently timestamp-proven; that narrow event ordering was verified by deterministic browser/broker fixtures. Single-order partial-fill timing, true connection-loss races and Live remain outside this run.

## Detail trading-panel acceptance, from 07:25 CST

This round exercised writes through the web UI, with independent read-only broker-derived order/fill/position checks after each step. Existing non-ES holdings remained read-only. Phone and Live were not tested.

### Repairs found while reviewing the complete UI flow

- `cc44d87`: Added a separate Add / Trim quantity field. The original entry quantity is locked after submission and previously also supplied the adjustment size, preventing an intentional 4 → Add 2 → 6 → Trim 2 → 4 workflow. Invalid fractional quantities, Trim of the whole position, and Add beyond the 10-contract limit disable the corresponding buttons. Adjustment requests carry the current order reference.
- The same change sums all unit entry legs in the edit dialog, rather than showing the first unit's quantity. Pending entry quantity and TIF in the panel now follow acknowledged broker state after replacements.
- Protection rows have separate navigation ownership metadata, allowing an Orders TP/SL click to select its correct independent group without granting those rows entry-edit authority. Paper/account/contract and saved order-ID checks remain in place.
- `d08a9e9`: Hide adjustment controls while flat, overriding the general label layout rule.
- `2374e12`: Protected Trim/Close now uses the fresh Bid/Ask returned by the quote filter independently of the Last-trade status. Last trades can pause in quiet ETH while the bid/ask feed remains current. Stale, delayed or missing quotes remain filtered out. Regression fixtures separately verify quiet Last with current quotes, stale quote rejection and delayed-feed rejection.

### Actual Paper UI evidence

- Long unfilled limit: parent 550 at 7783.50; 1 → 2/GTC replaced with 553/556; 2 → 1/DAY replaced with 559. Old orders no longer appeared in the authoritative pending list. The editor correctly displayed quantity 2 and GTC before reverting. Drag-release changed 559 to 7782.50 without another Buy click; chart/Orders/IB agreed. Cancellation ended 559/560/561 with zero fills and no pending orders.
- From a new draft, clicking that long order's SL row recovered the original group and its entry. The UI selected the correct reference after asynchronous refresh.
- Long held: parents 562/565/568/571 filled four contracts; Add 2 created 574/577 and position 6; Trim 2 filled existing TP 563/566 and position returned to 4. At each stage effective TP and SL quantities equaled 4/6/4. BE used entry basis 7788.00 plus one tick, moving remaining stops to 7788.25. Those four original stops filled; paired TPs canceled, position zero.
- Short held: parents 580/583/586/589 submitted at 7788.25, dragged to 7787.00 and filled four contracts. Add 2 used 592/595; Trim 2 returned position from -6 to -4 with four TP/four SL protection. Close eventually filled the existing remaining TP limits and canceled paired SLs, leaving zero position. An earlier Close attempt explicitly rejected for quote availability with no order change; it was reconciled before a new request.
- One initial long submission received an explicit dispatcher QUEUE_FULL rejection. Broker checks confirmed no order or position before a manual new submission. No automatic write retry was introduced; admission under concurrent read load remains a usability limitation.
- A/B isolation: A was a 1-contract SELL STP group 607/608/609 at 7783.50. B was SELL LMT at 7793.50, replaced 610 with 613/616 for 2/GTC, then 619 for 1/DAY. A's IDs, quantity, trigger and DAY remained unchanged throughout. Clicking A's TP from B returned to A. Canceling A ended all three A orders while B 619/620/621 remained unchanged and working. B was then canceled, leaving no pending orders.
- GTC BUY STP 622 with TP/SL 623/624 was submitted at 7787.75, one tick above the displayed Last 7787.50. Reloading the web page recovered the same group, STP, GTC and IDs without resubmission. Subsequent controlled amendment moved the trigger to 7787.25 while Last was 7787.00.

### Regression evidence and limits

426 Python tests passed after the exit-quote change. The web shared-chart suite passed, covering real browser UI with mocked APIs: submit/edit/cancel, total unit quantity, independent adjustment size and invalid-size guards, response-loss reconciliation, no reload replay, Live isolation, fixed chart geometry and 1440/850/393-width layout. The latest-target queue suite also passed. These fixtures do not certify broker races or real disconnect timing.

This round extends the earlier actual TP/SL, BE in both directions, natural STP trigger, restart and rapid-drag evidence above; it does not repeat every earlier scenario. The exact fill-between-pointer-down-and-up race, a single multi-contract order's partial fill, physical mobile transitions and Live remain outside this UI acceptance.

Final broker/UI result, approximately 07:40 CST: the amended GTC BUY STP 622 actually filled at 7788.00. The updated backend's Close used the existing TP 623 at 7789.00, which filled; SL 624 canceled. ES position 0, pending-orders empty, existing SGOV quantity unchanged. This proves the post-fix limit-close lifecycle against Paper; the exact quiet-Last/current-BidAsk condition was covered by fixtures, not deliberately forced at the broker.

A final display-only follow-up labels the disabled main quantity as Position size while held and updates it to the actual remaining position, including after Add/Trim and page recovery. The independent Add / Trim quantity remains the requested adjustment. Browser fixtures verify 4 → 6 → 4 display updates.

## Scope correction: a partial fill inside one multi-contract ES order

On the subsequent request to test this case, both the Pro checkout and deployed Mini were verified at `51d3068`. The current FUT submit branch calls `add_lots` once per requested contract. Each entry, TP and SL has broker totalQuantity 1. Thus a UI quantity of 4 creates four distinct one-contract parents, not a single four-contract parent. A partial group fill is possible; a partially filled multi-contract parent is not generated by this ES chart workflow.

Correct classification: **not applicable to the current ES unit-order path; not broker-verified for a separate single multi-contract implementation**. Earlier wording listing this only as an outstanding ES acceptance case was too broad. Do not introduce a test-only broker order or change the order structure to label the current path accepted. Supporting a consolidated ES parent would be a separate execution/protection design change.

Verification: 92 mocked backend tests in `tests.test_paper_chart` and `tests.test_paper_entry_edit` passed. Relevant coverage includes partially filled groups separating contingent protection, partial Trim progress, rejection retaining protection, stop-fill accounting without another write, unknown-request non-replay and an existing stock-path partial-fill/cancel race. These are regression evidence, not actual broker partial-fill acceptance. No broker orders were submitted, amended or canceled during this scope check.


## Speed/stability maintenance: reserved write admission

After the user's direction to retain unit brackets and prioritize speed/stability, the API dispatcher now limits reads/background synchronization to three of its four admitted jobs. Read saturation can no longer consume the final write admission slot. Total capacity remains four and IB execution stays on its single serialized thread. Identical reads share work; writes are neither deduplicated nor retried. Already-running writes retain their acknowledgement path after an HTTP wait timeout; unstarted expired writes never reach their handler.

Regression evidence: 427 Python tests passed, plus the latest-drag queue regression. A deterministic concurrent test holds three distinct reads, rejects an additional read, admits one POST, rejects a further POST at full capacity, then verifies exactly one executed POST, one IB execution thread and recovered read capacity. Existing tests cover full write saturation, shared reads, cancellation of unstarted work, exceptions, expiry and running-job acknowledgement. This removes read-only admission starvation; it does not prioritize execution ahead of earlier jobs or prove a measured reduction in live broker latency. No additional broker order was placed for this maintenance verification.

## User-reported protection drag failure — acceptance reopened

The user's 10:18–10:19 recording shows SL/TP moving and then reverting without an
amendment request in the corresponding backend access log. A later successful
sample reports 560 ms release-to-response (446 ms request, 114 ms pre-request),
which does not explain the missing requests. Prior steady-position success is
insufficient to certify the complete drag experience; this issue remains open
for broker/UI acceptance.

A browser regression reproduces silent request loss when pointer capture is
lost before pointerup. Previously that event cleared the drag; the later release
was discarded. The web protection gesture now retains its contract, account
epoch, order reference and pointer identity until an actual release, observing
release on both the frame document and host. Capture loss alone never writes.
True cancellation/focus loss restores the confirmed level and reports interruption.
Changed/finished orders are rejected; an entry fill within the same protected
order retains the pending exit-price gesture. Native gestures keep their existing
path. Tests cover pending and filled positions, injected capture loss, entry fill
during dragging, order identity changes, pointer cancellation and host release.

The capture-loss condition is reproduced; the recording itself lacks event-level
evidence to establish it as the sole cause. Do not mark the reported incident
passed solely from these mocked regressions. Existing user positions were only
read; no test amendment was applied to their protection orders.

Post-fix read/write Paper check: an independent one-contract unfilled GTC bracket
had TP 7774 → 7775 and SL 7754 → 7757.25 dragged through the browser. IB confirmed
both prices; measured release/response was 420 ms (417 request, 3 wait) and 506 ms
(505 request, 1 wait). The test parent and both children were then broker-confirmed
canceled, with ES flat and no pending orders. This verifies normal browser-to-IB
amendments while the entry is pending; injected capture-loss and fill-transition
coverage remains mocked, and the user's full reported incident is not certified
closed. Chart assets were deployed without restarting the active backend; the
separate daily-P&L backend activation remains deferred.

## NQZ6 follow-up and daily P&L activation

Per user direction, switched to NQZ6, exact conId 563947726, CME December 2026,
multiplier 20, tick 0.25, IB Paper only. The first one-contract long bracket was
submitted using web Join Bid; TP/SL amendments while pending were confirmed in
339/360 ms. Entry limit modification filled at 31149.50. Post-fill TP/SL browser
amendments confirmed in 463/420 ms. Two consecutive TP targets confirmed in
452/604 ms (second waited 244 ms for the first); two consecutive SL targets in
425/671 ms (second waited 305 ms). All final prices and protection quantities
were reconciled against IB. Existing limit-based Close filled at 31143.50; the
other exit canceled, NQ/ES were flat and no pending orders remained. This is a
small Paper sample, not a latency guarantee or a complete Live acceptance.

Daily P&L is now active and exact-contract IB values were observed during the NQ
position. Base-currency labels use the existing cached account summary, never a
new blocking request. Per user styling: positive green, negative red, rounded
zero/unavailable neutral, retaining signs in both light and dark themes.
IB stopped publishing this contract's P&L after the position became flat; after
15 seconds the field correctly became unavailable instead of showing a stale
number as live. Closed-position daily accounting remains a source limitation.
