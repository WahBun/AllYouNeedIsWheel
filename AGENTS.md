# Project Working Agreements

GitHub = 唯一正式代码真源
所有项目的正式代码必须提交并推送到 GitHub。以指定仓库、目标分支和 commit SHA 判断版本，不能只看文件夹日期，也不能默认 main 最新。开工前核对本地改动、当前分支和远端状态；保护未提交内容，不覆盖、不丢弃。明确区分开发版、已验证版、已合并版和已部署版。密钥、账号凭证、私有环境配置、交易数据库和敏感日志不得提交。

授权原则 = 已授权的工作直接完成
“帮我修复”“照这个做”“继续”等明确行动指令，授权完成当前范围内的查因、最小修改、必要验证、Commit、Push，以及需要的 PR 创建或更新，不要在每一步重复询问。若我明确要求暂不推送、仅分析或先观察，以当前要求为准。
已有明确授权在相同任务和范围内持续有效。收到补充说明时，直接调整当前工作，不重开任务，不把已完成步骤重新来一遍。只有确实扩大范围、存在无法自行判断的冲突，或触及下文独立授权事项时才询问。

PR 合并 = 默认允许管理员权限
当我明确要求“合并”“把 PR 合进去”或同意包含合并的完整方案时，默认授权执行该 PR 的合并，并在必要时使用 GitHub 管理员权限绕过 required review／缺少审批这一类限制，无需再次征求同意。
合并前核对仓库、目标分支、PR 范围和最新 head SHA，确认当前提交的相关验证结果。仅缺少人工审核不构成再次询问的理由；不要为了证明被阻止而反复尝试普通合并。
此授权允许本次管理员合并，不允许关闭或永久修改分支保护、伪造审核、忽略真实测试失败或未解决的代码问题。发现实质问题，先在当前范围内修复；确需我决策时一次说明。
合并后核实 GitHub 的实际 merged 状态及合并 commit SHA。网络超时或响应丢失时先查询结果，不能把未知状态当失败盲目重发。
“提交／推送”“合并”“发布 Release”“部署”分别判断；没有合并指令时，不擅自合并。GitHub 管理员授权不自动扩展为系统管理员操作、生产部署、服务重启或交易授权。

REA = 先取得证据，再设计和修改
涉及 UI、交互、行情刷新、订单链、状态同步、断线恢复，或参考成熟项目实现时，必须主动优先使用 REA，不用等我提醒。设计或修改前确认 REA 可用，并完成针对当前问题的实际分析。
不能用“已经理解”“凭经验即可”、普通搜索或仅写在计划里的调用代替 REA。已有分析可复用，但须确认其对应的版本、运行环境和行为仍适用于当前问题；不要重复做无收益的分析。
参考产品的实际行为与 Wheel 自己的适配方案要明确区分，不能猜测参考实现。使用现有专用 REA 浏览器，先核对目标；不要切换、关闭或重启我的日常浏览器、视频页面及参考页面。
REA 不可用时，先在已有授权内排查；仍受阻就说明具体原因和可行替代方案，不默默跳过，也不擅自安装工具或修改系统配置。
取得证据后直接推进修复和相关验证，不能停在原因说明或建议列表。结束时简短说明实际分析了什么、采纳了什么、验证了什么。纯文案、格式等明显无关行为的小改动无需 REA。

开发方式 = 最小改动，完成闭环
先确认当前版本、真实复现路径和问题证据，再做最小必要修改。优先覆盖我实际使用的页面和操作，不擅自扩展功能、重构或引入新的常驻服务。
只运行与改动和风险相关的验证；检查通过后，不因“再保险”反复运行整套测试。只有新改动、新失败或明确疑点才扩大验证。
脚本通过不等于页面好用，编译成功不等于真机验证，模拟数据不等于券商验收。未验证部分明确说明。
性能优化先测量瓶颈、再修改，并比较相同条件下的结果。不要把市场活跃度、测试时段或网络条件变化直接归因于代码优化；证据不支持收益时，不为交差而改代码。

交易项目 = 保护已经稳定的基础
保护现有布局、1／2／3／4 图和已验证的 tick 级行情刷新能力，不因参考其他项目擅自重构。
已确认的 One-click、Confirm／Discard、订单拖动、报价新鲜度、止损修改和 Daily P&L 行为属于受保护基线；普通 UI 调整、清理和性能优化不得顺带改变。
订单状态以券商证据为依据，正确处理成交、撤单、重连和历史恢复；不能靠删记录、强制解锁或盲目重发掩盖问题。断线、超时或重启后先核对实际结果，再决定后续动作。
Paper 与 Live 严格隔离。测试仅处理当前任务明确授权的 Paper 测试订单，不擅自操作已有持仓、原订单或重启 Gateway。Live 交易由我本人操作。
期货交易时段使用 ETH／RTH，不套用股票盘前、盘后概念。

UI 语言 = 统一英文
所有新增或修改的可见 UI 文字，包括按钮、菜单、标题、提示、占位文本、错误信息和说明注释，一律使用英文，不出现中文或中英混排。功能与交互成熟后再统一本地化。与我的日常沟通仍使用中文。

MacBook Pro = 主开发机
日常开发、代码修改、UI 调整、Xcode、SwiftUI、Simulator、签名与 iOS 构建默认在 Pro。Wheel iOS 通过 GitHub 同步代码。
本地构建与模拟器验证可在任务范围内直接完成。真实 iPhone 的 Run、安装和启动默认由我操作；只有我在当前任务明确要求代为执行时才操作，不能沿用以前的一次性授权。

Mac mini = 长期运行与后端机
IB Gateway、Wheel Backend、API 和常驻服务运行在 Mini。Pro 与 iPhone 通过 Tailscale 访问。优先从 Pro 经现有 SSH 做必要的只读排查，不为了操作 Mini 强制使用屏幕共享。
部署和 Backend 重启默认由我操作。修复、Push、PR 合并、管理员合并授权和部署建议，都不自动授权部署或重启。Gateway 重启必须另外获得当前任务的明确授权。
避免在运行目录临时改代码；获准热修时，保留回退点并同步回 GitHub，不能留下仅 Mini 才有的版本。

Codex Cloud 与额外任务 = 按环境需要选择
不依赖本机环境的独立开发、审查和测试可以考虑 Cloud；涉及 Xcode、证书、Simulator 或本地 Gateway 时优先 Local。普通修复不随意迁移环境。
跨设备接续依靠 GitHub 和简短任务记录，不假设 Cloud 自动同步本地文件、对话和运行状态。
未经同意，不新开额外 Codex 聊天、不启动子代理或并行代理、不创建持续任务或定时监控。当前任务内的普通工具调用无需逐项确认。

发布与换机 = 代码可追溯，部署可核实
换机前检查改动 → Commit → Push；另一台先确认工作区无冲突 → Fetch／Pull 正确分支 → 开工。禁止为同步而强制覆盖未提交内容。
每次交付说明目标分支、准确 commit SHA，以及是否已推送、已合并、已部署。分别核实后端、网页和手机 App 的实际版本，不能把 Push 或 Merge 当作用户端更新。
Wheel 每次改动后明确建议选择 Deploy only 或 Deploy & Restart Backend，并说明是否需要刷新网页或重新 Run iPhone；由我选择用电脑还是手机执行。
Release 按当前任务要求创建，不能把普通 Push／Merge 自动扩展为发版。Wheel Release 标题使用 Wheel: v<version>，保留历史 Releases、tags 和必要回退点。
清理分支前核对合并关系、独有提交和部署／签名／自动化依赖，只在已获清理授权的范围内删除。
我明确指定项目迭代到新版本时，同步修改当前 Codex 聊天标题。

沟通与额度 = 简短、准确、少打断
先说结果，再说必要证据、验证范围和真正阻塞；不堆砌过程、不重复计划、不用大量术语代替结论。
优先复用仍有效的分析，只读取当前任务相关材料。长任务只在出现新发现、方向变化或阻塞时做简短更新。
必须询问时，先完成所有不依赖该授权的工作，给出具体可审阅的方案，并说明为什么已有授权不覆盖这一步。多个相关问题一次说清。
遇到必须由我另行授权的步骤，五分钟未回复就暂停依赖该授权的部分，不反复催问、重试或自行视为同意。
如平台或工具权限仍阻止执行，如实说明实际拦截和剩余工作；不要把既有授权重新包装成同一个确认问题。

# Wheel repository-specific constraints

The policy above is the user-approved workflow as of 2026-10-20. The constraints
below retain the existing Wheel behavior and implementation requirements.

- Read `docs/HANDOFF.md` and `docs/MAC_MINI_TAILSCALE.md` before deployment changes.
- Iterate the web version first. Build or update the Mac App/DMG only when explicitly requested.
- Keep one server process and one stable IB client identity. HTTP threads are safe only with the dedicated serialized API dispatcher in place.
- Verify account routing, exact contracts, quantities and prices when changing execution code.
- Check mobile and desktop layouts and light/dark themes for UI changes.
- Inspect actual deployed state; conversation history and folder names are not deployment evidence.

## Order changes: physical-device Run gate

Before installing a changed order workflow on the user's iPhone, finish relevant
backend regression, simulator trading tests, and chart interaction checks.
Cover price/quantity/TIF edits, replacement-order identity and Orders synchronization,
confirmed rejection, unknown outcomes, recovery after restart, cancellation/fill races,
and Paper/Live isolation. Compilation alone is not acceptance.
Use broker Paper acceptance only with the user's authorization and verify the actual
Paper session first. Keep test effects bounded and verify the final order state.
Report mock/simulator evidence separately from broker evidence; market-open fills,
partial fills, and TP/SL triggers remain unverified until actually observed.

## Protected market-data foundation

Keep the price/OHLC delivery path stable by default. Before changing aggregation,
streaming, chart scheduling or indicator work on that path, follow
`docs/MARKET_DATA_BASELINE.md` and compare the same workload against its baseline.
Cover 1–4 panes, repeated layout changes, two four-pane pages, latency distributions,
data integrity, context isolation and recovery. Do not add quote throttles or
parallel IB owners to hide regressions. Report mock/browser and broker evidence
separately, including the documented trade-volume gap. Preserve the current layout.

## Protected order-drag and confirmation behavior

These rules apply on every computer and in every new conversation. The user
approved this behavior at commit `9df6bd644d32c09d1434240b076d6598cd43a399`.
Treat it as a protected behavioral baseline, not a requirement to stay on that
commit. Future UI, styling and layout changes must preserve it. Change these
semantics only when the user explicitly requests a behavioral change.

- With **One-click trading on**, releasing an entry-price or TP/SL-price drag
  submits the amendment through the existing guarded request path without
  Confirm/Discard. Do not introduce an entry-price exception.
- With **One-click trading off**, releasing a drag leaves the line at the chosen
  draft price until Confirm or Discard. Ordinary quote updates, polling and UI
  refresh must not restore the old broker price or discard the pending change.
- Put Confirm/Discard beside the entry/position line, including for TP/SL changes;
  do not move these controls onto the TP/SL lines.
- Keep confirmation controls stable across ordinary refresh. Do not recreate
  their DOM nodes on every update: users must be able to wait before confirming,
  and a click held through a refresh must still work without racing the update.
- Confirm submits the intended draft through existing identity and state checks;
  Discard restores broker-confirmed values. Real account/order identity changes,
  fills, cancellations or invalid state must still invalidate unsafe drafts.
  Never bypass broker guards or automatically replay trading writes.
- Support dragging anywhere on the visible editable order line. Use a vertical
  resize cursor on the line and a grabbing cursor when dragging its label or
  button segments. Long presses on those segments support dragging; short clicks
  retain their original actions. A drag must not accidentally cancel an order
  or open quantity editing, and an unchanged release must not amend the order.

When changing related UI, run the directly relevant checks, especially
`tests/chart/entry-one-click-page.cjs`, `tests/chart/one-click-protection.cjs`,
`tests/chart/fast-entry-drag.cjs` and `tests/chart/order-line-drag.cjs`.
Cover One-click on/off, desktop/mobile, draft persistence across polling, delayed
confirmation and a click held through refresh. Preserve tick-level delivery and
the existing 1/2/3/4-chart layouts. Report mock/browser results separately from
broker acceptance; do not place real orders merely to verify UI changes.

## Protected TP/SL presentation after quantity changes

The user approved this behavior at commit
`454c63ea008336fb61e8eed149c0b4e508bd43f2`. Preserve it across computers,
new conversations and all future UI changes unless the user explicitly requests
a behavioral change.

- After a quantity change is confirmed, TP and SL must retain the same ordinary
  label style throughout submission, waiting and reconciliation. Neither line
  should flash, disappear and reappear, or jump merely because a replacement
  order is awaiting confirmation. Do not add an extra `…` to either label for
  this quantity-change waiting state.
- Show waiting/unknown outcomes through the existing page-level order status.
  Consistent label styling does not mean the broker has confirmed the change.
- Preserve the display-only pending-stop handling: use valid, consistent prices
  from pending stop rows in the current snapshot, not cached prices from another
  account, contract or order. Do not fabricate confirmed protection or retain
  canceled, filled, missing, unknown or conflicting stop rows to hide a flicker.
- Keep order submission, replacement, reconciliation, One-click trading,
  Confirm/Discard and no-replay guards unchanged. This presentation rule does
  not override genuine broker state changes or the shared price-drag in-flight
  indication outside quantity changes.

For related UI changes, run `tests/chart/stop-pending-display.cjs` and
`tests/chart/quantity-stop-recovery.cjs`. Verify desktop/mobile rendering,
matching TP/SL styles, stable line identity through pending-to-confirmed updates,
and exactly one intended quantity-change request with no automatic replay.

## Active iteration and branch cleanup

The active development branch is `Ben/wheel-1.8`. Verify the current GitHub and
local branch state before working; this branch contains the full 1.7 history.
After each iteration, the existing permission to clean up obsolete Wheel feature
branches applies only after verifying ancestry into the active branch, closed or
merged PRs, and no deployment, signing, automation or ongoing-work dependencies.
Keep branches with unique commits or unresolved dependencies, historical tags,
Releases and rollback points. Verify actual machine and workflow dependencies
before removing a branch; cleanup is not deployment authorization.
