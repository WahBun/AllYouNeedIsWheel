# 项目协作约定

## 红线 · 保护盘中图表订单操作

- **任何修改都必须保住原本可用的盘中交易操作。** 用户在图表上下单、拖线改价、调整数量和有效期、管理 TP／SL、撤单。行情、布局、性能、清理或其他无关改动不得顺带禁用这些操作。尊重用户主动设置的交易锁。
- 订单功能按已验证的稳定基线维护。普通问题只做局部修复。只有严重缺陷（如操作了错误订单、重复提交，或盘中无法管理已挂订单）才考虑调整订单流程；如果最小修复不足以解决，先说明证据、受影响的操作和回退方案，在用户明确同意后再大改。新增或扩大交易限制也需明确授权。
- **限制范围由券商证据决定。** 当前请求结果未知、订单身份有冲突、成交与撤单竞态，或所需的可执行报价已过期时，只暂停依赖该证据的操作。按账户、合约、订单组和具体订单核对，说明正在等待什么。行情加载、展示价格过期，或有完整成交和撤单证据的已平仓旧组，不得单独成为锁住当前挂单的理由。
- **恢复编辑必须走只读核对。** IB 确认原单仍在挂、身份和剩余可操作数量匹配后，自动恢复该单允许的操作。已成交、已撤销或仍有冲突的订单继续按各自状态处理。不得清空历史、强制解锁或重发原请求。用户主动改价时，沿用该动作既有的身份核验与确认流程。
- 涉及订单可用性时，从图表入口验证。保留这条回归用例：旧组已由券商证据证明平仓，新单已挂且未成交，图表自动恢复编辑，拖线改价只修改一次原单。按改动风险补测部分成交、撤单竞态、旧单重新出现和断线恢复。保留 One-click、Confirm／Discard 与 Paper／Live 隔离；Live 验证只读，真实交易由用户操作。

## GitHub · 唯一正式代码真源
所有项目的正式代码必须提交并推送到 GitHub。以指定仓库、目标分支和 commit SHA 判断版本，不能只看文件夹日期，也不能默认 main 最新。开工前核对本地改动、当前分支和远端状态；保护未提交内容，不覆盖、不丢弃。明确区分开发版、已验证版、已合并版和已部署版。密钥、账号凭证、私有环境配置、交易数据库和敏感日志不得提交。

## 授权原则 · 已授权的工作直接完成
“帮我修复”“照这个做”“继续”等明确行动指令，授权完成当前范围内的查因、最小修改、必要验证、Commit、Push，以及需要的 PR 创建或更新，不要在每一步重复询问。若我明确要求暂不推送、仅分析或先观察，以当前要求为准。
已有明确授权在相同任务和范围内持续有效。收到补充说明时，直接调整当前工作，不重开任务，不把已完成步骤重新来一遍。只有确实扩大范围、存在无法自行判断的冲突，或触及下文独立授权事项时才询问。

## 上下文接续 · 压缩后直接继续未完成任务
上下文压缩、会话恢复以及重新注入 AGENTS.md／环境信息都不代表新任务，不得仅回复“收到／按规则执行”就结束当前轮次，也不要求我再说“继续”。
恢复后先核对最近的实际用户目标、持续授权、已完成事项、未完成步骤和当前工作区状态；静默恢复任务记录或最近对话，直接执行下一个已授权步骤。旧的附件选择或工具交互不得覆盖后来的明确任务。
长任务在压缩前保存简短进度记录，注明目标、范围、分支和 SHA、已有改动、验证结果、未完成事项及下一步；记录放在临时或已忽略的位置，不包含密钥，不把内部接续记录混进正式代码。
进度记录缺失或某个恢复工具失效时，先利用仍可用的对话和工作区证据恢复；只有确实无法确定任务、遇到真实冲突或需要独立授权时才提问。不要重复已完成的分析、操作或规则说明，不把工具恢复故障当作任务完成。

## PR 合并 · 默认允许管理员权限
当我明确要求“合并”“把 PR 合进去”或同意包含合并的完整方案时，默认授权执行该 PR 的合并，并在必要时使用 GitHub 管理员权限绕过 required review／缺少审批这一类限制，无需再次征求同意。
合并前核对仓库、目标分支、PR 范围和最新 head SHA，确认当前提交的相关验证结果。仅缺少人工审核不构成再次询问的理由；不要为了证明被阻止而反复尝试普通合并。
此授权允许本次管理员合并，不允许关闭或永久修改分支保护、伪造审核、忽略真实测试失败或未解决的代码问题。发现实质问题，先在当前范围内修复；确需我决策时一次说明。
合并后核实 GitHub 的实际 merged 状态及合并 commit SHA。网络超时或响应丢失时先查询结果，不能把未知状态当失败盲目重发。
“提交／推送”“合并”“发布 Release”“部署”分别判断；没有合并指令时，不擅自合并。GitHub 管理员授权不自动扩展为系统管理员操作、生产部署、服务重启或交易授权。

## REA · 先取得证据，再设计和修改
涉及 UI、交互、行情刷新、订单链、状态同步、断线恢复，或参考成熟项目实现时，必须主动优先使用 REA，不用等我提醒。设计或修改前确认 REA 可用，并完成针对当前问题的实际分析。
不能用“已经理解”“凭经验即可”、普通搜索或仅写在计划里的调用代替 REA。已有分析可复用，但须确认其对应的版本、运行环境和行为仍适用于当前问题；不要重复做无收益的分析。
参考产品的实际行为与 Wheel 自己的适配方案要明确区分，不能猜测参考实现。使用现有专用 REA 浏览器，先核对目标；不要切换、关闭或重启我的日常浏览器、视频页面及参考页面。
REA 不可用时，先在已有授权内排查；仍受阻就说明具体原因和可行替代方案，不默默跳过，也不擅自安装工具或修改系统配置。
取得证据后直接推进修复和相关验证，不能停在原因说明或建议列表。结束时简短说明实际分析了什么、采纳了什么、验证了什么。纯文案、格式等明显无关行为的小改动无需 REA。

## 开发方式 · 最小改动，完成闭环
先确认当前版本、真实复现路径和问题证据，再做最小必要修改。优先覆盖我实际使用的页面和操作，不擅自扩展功能、重构或引入新的常驻服务。
只运行与改动和风险相关的验证；检查通过后，不因“再保险”反复运行整套测试。只有新改动、新失败或明确疑点才扩大验证。
脚本通过不等于页面好用，编译成功不等于真机验证，模拟数据不等于券商验收。未验证部分明确说明。
性能优化先测量瓶颈、再修改，并比较相同条件下的结果。不要把市场活跃度、测试时段或网络条件变化直接归因于代码优化；证据不支持收益时，不为交差而改代码。

## 交易项目 · 保护已经稳定的基础
保护现有布局、1／2／3／4 图和已验证的 tick 级行情刷新能力，不因参考其他项目擅自重构。
已确认的 One-click、Confirm／Discard、订单拖动、报价新鲜度、止损修改和 Daily P&L 行为属于受保护基线；普通 UI 调整、清理和性能优化不得顺带改变。
订单状态以券商证据为依据，正确处理成交、撤单、重连和历史恢复；不能靠删记录、强制解锁或盲目重发掩盖问题。断线、超时或重启后先核对实际结果，再决定后续动作。
Paper 与 Live 严格隔离。测试仅处理当前任务明确授权的 Paper 测试订单，不擅自操作已有持仓、原订单或重启 Gateway。Live 交易由我本人操作。
期货交易时段使用 ETH／RTH，不套用股票盘前、盘后概念。

## Wheel 日常验证与预览同步

- 普通问题先收集归类；盘中不能管理订单或影响交易安全的问题优先处理。用户提供大概时间和标的即可开始追溯，按时区和合约定位已部署版本的日志及券商证据；问题已恢复时也可回查，无需等用户再次抓图。
- 高峰行情问题分段核对成交进入后端、行情推送和图表显示。保留逐笔 K 线与下单报价的各自来源。回放使用相同负载；开盘效果在相应时段验证。若出现性能回退，从用户确认流畅的基线逐项加回改动，每次用同一触发操作验证。
- 涉及 Superchart 共用界面或图表资源时，在正式 PR 合并前同步到现有蓝图预览，核对预览实际提供的文件，并保留预览工作区的本地改动。交付时分别说明预览、正式分支、Mini 和 iPhone 的状态。

## UI 语言 · iPhone 新文字同步汉化
- **iPhone App 新增或修改可见文字时，同一次修改必须补齐英文、简体中文和繁体中文**，不留到发版前集中补译。范围包括按钮、菜单、标题、提示、占位文本、错误信息、说明、通知及无障碍标签。
- 使用现有本地化资源并跟随 App 的语言设置；动态提示在显示时翻译，不强制页面使用英文。保留标的代码、券商标识、品牌名和必要交易缩写；不得为了翻译改动订单状态值、请求参数或券商原始数据。无法识别的券商诊断保留原文。
- 验证新增文案的简繁翻译、插值与数量格式，并检查常用手机宽度下的排版。运行 `python3 ops/audit_ios_localization.py`；有编译提取目录时用 `--extracted-dir` 检查漏项。
- 其他页面的新 UI 默认使用英文，按当前任务要求本地化。与我的日常沟通仍使用中文。

## MacBook Pro · 主开发机
日常开发、代码修改、UI 调整、Xcode、SwiftUI、Simulator、签名与 iOS 构建默认在 Pro。Wheel iOS 通过 GitHub 同步代码。
- **合并确认后主动同步 Xcode，不等用户再次提醒。** 当前任务获知相关 PR 已合并（包括用户告知已合并／已部署）时，立即核实 GitHub 合并 SHA，确认 Xcode 实际打开的工程，保护本地改动后同步，并完成下述 iphoneos 构建与包内验证；将结果作为本次交付的一部分。无需等待 Mini 部署完成，也不重复请求更新工程或本地构建的许可。
- **Merge、Mini 部署与 iPhone Run 不设一刀切的先后关系。** 用户要先试开发版时，可在合并前准备其指定 PR／分支的已核实 head 和构建包，明确标注开发版；使用正式版时同步已核实的合并提交。部署与 Run 的顺序由接口兼容性决定：只有新 App 的对应功能依赖新增或不兼容后端接口时，才先部署后端再使用该功能，并说明具体依赖。手机实际安装／启动仍遵守当前任务的设备授权。

本地构建与模拟器验证可在任务范围内直接完成。真实 iPhone 的 Run、安装和启动默认由我操作；只有我在当前任务明确要求代为执行时才操作，不能沿用以前的一次性授权。
每次准备让我在 iPhone 上 Run 已合并的 Wheel 改动前，先从 GitHub 核实本次目标分支与合并 SHA，再读取 Pro 上 Xcode 实际打开的工程或工作区路径，核对该工作区的 HEAD 和本地改动。若版本不符，先保护未提交内容，再同步到已核实的 SHA；有冲突或本地改动会影响本次验证时，先说明并解决。
从该工程按本次 Run 的 scheme 和配置重新构建 iPhone 设备版（iphoneos），核实产出的 .app 来源及版本／构建号，并验证本次改动已进入包内；图表脚本等原样打包的资源应与合并提交逐一比对本次涉及的文件。只有工程和构建包都核实后才提示我按 ⌘R。Mini 已部署、模拟器构建成功或版本号相同，都不能代替这两项核对。

## Mac mini · 长期运行与后端机
IB Gateway、Wheel Backend、API 和常驻服务运行在 Mini。Pro 与 iPhone 通过 Tailscale 访问。优先从 Pro 经现有 SSH 做必要的只读排查，不为了操作 Mini 强制使用屏幕共享。
部署和 Backend 重启默认由我操作。修复、Push、PR 合并、管理员合并授权和部署建议，都不自动授权部署或重启。Gateway 重启必须另外获得当前任务的明确授权。
避免在运行目录临时改代码；获准热修时，保留回退点并同步回 GitHub，不能留下仅 Mini 才有的版本。

## Codex Cloud 与额外任务 · 按环境需要选择
不依赖本机环境的独立开发、审查和测试可以考虑 Cloud；涉及 Xcode、证书、Simulator 或本地 Gateway 时优先 Local。普通修复不随意迁移环境。
跨设备接续依靠 GitHub 和简短任务记录，不假设 Cloud 自动同步本地文件、对话和运行状态。
未经同意，不新开额外 Codex 聊天、不启动子代理或并行代理、不创建持续任务或定时监控。当前任务内的普通工具调用无需逐项确认。

## 发布与换机 · 代码可追溯，部署可核实
Wheel 新建开发、修复和发布准备分支统一使用 `ben/` 前缀，不使用 `codex/`。除非我在当前任务明确指定其他名称，否则始终遵循此规则。正式分支 `Ben/wheel-1.8` 保持原名和大小写，不因前缀规则改名。
换机前检查改动 → Commit → Push；另一台先确认工作区无冲突 → Fetch／Pull 正确分支 → 开工。禁止为同步而强制覆盖未提交内容。
每次交付说明目标分支、准确 commit SHA，以及是否已推送、已合并、已部署。分别核实后端、网页和手机 App 的实际版本，不能把 Push 或 Merge 当作用户端更新。
Wheel 每次改动后明确建议选择 Deploy only 或 Deploy & Restart Backend，并说明是否需要刷新网页或重新 Run iPhone；由我选择用电脑还是手机执行。
Release 按当前任务要求创建，不能把普通 Push／Merge 自动扩展为发版。Wheel Release 标题使用 Wheel: v<version>，保留历史 Releases、tags 和必要回退点。
清理分支前核对合并关系、独有提交和部署／签名／自动化依赖，只在已获清理授权的范围内删除。
我明确指定项目迭代到新版本时，同步修改当前 Codex 聊天标题。

## 沟通与额度 · 简短、准确、少打断
先说结果，再说必要证据、验证范围和真正阻塞；不堆砌过程、不重复计划、不用大量术语代替结论。
优先复用仍有效的分析，只读取当前任务相关材料。长任务只在出现新发现、方向变化或阻塞时做简短更新。
必须询问时，先完成所有不依赖该授权的工作，给出具体可审阅的方案，并说明为什么已有授权不覆盖这一步。多个相关问题一次说清。
遇到必须由我另行授权的步骤，五分钟未回复就暂停依赖该授权的部分，不反复催问、重试或自行视为同意。
如平台或工具权限仍阻止执行，如实说明实际拦截和剩余工作；不要把既有授权重新包装成同一个确认问题。

## Wheel repository-specific constraints

- Read `docs/HANDOFF.md` and `docs/MAC_MINI_TAILSCALE.md` before deployment changes.
- Iterate the web version first. Build or update the Mac App/DMG only when explicitly requested.
- Keep one server process and one stable IB client identity. HTTP threads are safe only with the dedicated serialized API dispatcher in place.
- Verify account routing, exact contracts, quantities and prices when changing execution code.
- Check mobile and desktop layouts and light/dark themes for UI changes.
- Inspect actual deployed state; conversation history and folder names are not deployment evidence.
- During version updates, verify the iOS marketing/build version shown in Settings against the intended release, including all Xcode build configurations. Report the installed iPhone version separately; a backend deployment does not update it. Physical iPhone Run/install remains user-operated.

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

## Active iteration and post-release branch cleanup

The active development branch is `Ben/wheel-1.8`. Verify the current GitHub and
local branch state before working; this branch contains the full 1.7 history.

After every successfully published new Wheel GitHub Release, clean up completed
PR source branches as part of the same authorized release task, without asking
again for routine cleanup. This means deleting eligible remote feature branches
and safe local counterparts, not deleting PR records, Releases or tags.

Before deletion, verify the released target SHA, the PR's actual merged state,
its latest merged head SHA, and the current branch tip. Confirm that the branch
has no unmerged work (including after squash/rebase merges), no open PR, and no
deployment, signing, automation, worktree or ongoing-work dependency. Inspect
current Pro/Mini configuration and checkouts; do not infer safety from age or name.
Use expected-SHA checks for remote deletion and preserve dirty local worktrees.

Keep active/default/protected branches, branches with unique unmerged changes or
unresolved dependencies, historical Releases/tags and rollback points. Report
what was removed and why any candidate was retained. Cleanup does not authorize
deployment, Backend/Gateway restarts or physical iPhone installation.
