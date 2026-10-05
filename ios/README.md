# Wheel iOS

原生 SwiftUI iPhone 客户端，最低 iOS 18.0，无外部 Swift 包依赖。项目定位、Docker Gateway、Mini 后端、Tailscale HTTPS、Flex 和手机安装的完整流程见[主 README](../README.md)。

## 构建与签名

打开 `Wheel.xcodeproj`，选择模拟器即可使用 Demo。真机签名在被忽略的 `Signing.local.xcconfig` 中配置：

```xcconfig
DEVELOPMENT_TEAM = YOUR_TEAM_ID
PRODUCT_BUNDLE_IDENTIFIER = com.yourname.wheel
```

该文件与 `Signing.xcconfig` 位于同一目录。不要把个人签名写入公共项目文件，也不要把后端地址硬编码进源码。

| Scheme | 用途 |
| --- | --- |
| Wheel | 开发、断点与模拟器测试，Run 附加 LLDB。 |
| Wheel Wireless | 日常真机体验，Debug 构建但 Run 不附加 LLDB；不是 Release 包，也不负责建立无线配对。 |

有线配对与签名正常后再启用无线 Run。App 的 Tailscale 后端访问和 Xcode 无线调试是两条独立链路。

## 页面与操作

- **Portfolio**：点击净资产金额进入 Allocation，Performance 打开收益图，Initial margin 打开保证金详情；金额右侧的隐藏点击区展开／收起现金与流动性。股票／期权支持详情、平仓与适用的移仓流程。
- **Performance**：MTD／YTD／ALL，Portfolio 始终显示，SPX／NQ100 对比可选；浮框随手指移动，停止操作 3 秒隐藏。图表保留 0% 线、日期及百分比刻度。Demo 显示需要真实后端历史的提示。
- **Trade**：CSP 在前、CC 在后；报价使用独立的股票批量读取与期权请求。mid 会随刷新更新，用户手动修改的限价和数量不会被行情覆盖。
- **Orders**：草稿与成交历史分开，外部订单只读；滑动展示操作按钮，不使用整段滑动直接执行。执行／撤单确认默认启用，可调整已有偏好。
- **Settings**：连接、语言、主题与自定义颜色。Demo 操作仅在本地模拟；未确认的真实提交结果需要人工核实后解除锁定。

SGOV、VTI、QQQ、SPY、VOO 有专属字体、流光和 Allocation 扇区铺色。VTI／QQQ／SPY／VOO 保留 Trade 使用资格，只有 SGOV 被排除。动画遵守减少动态效果和前后台状态。设置签名使用红／亮金／暗金流光。

## 数据边界

- 持仓 `entry_fill_price` 来自后端可靠匹配的 `avg_fill_price`；无法确认时显示空值。它与 Trade 的当前 mid、委托限价及持仓成本不同。
- CC 数量扣除已有空头 CALL 和活动卖单占用；暂存不会提交 IB。
- 平仓需要精确合约、数量与账户校验。移仓暂存两个独立订单，不具备组合单的原子性。
- 保证金详情由手动触发的 IB what-if 返回，模拟关闭整笔精确持仓；结果不是可相加的保证金分摊。
- 收益历史按 Flex 每日 TWR 复利计算；SPX／NQ100 使用 FRED 价格指数。盘中 P&L 与延长曲线只是估算，见[收益数据说明](../docs/PERFORMANCE.md)。
- 已知提示在显示时按 App 语言翻译；错误码、诊断后缀和未知券商返回保留，避免丢失排错依据。

## 刷新与交互

Portfolio 与订单读取分别串行运行，正常目标间隔约两秒、失败退避；慢请求结束后才发起下一次，不补发积压轮询。账户汇总、隐藏页面和休市行情采用较低频率。

Trade 自动报价参考后端 NYSE 日历，处理假期、提前收盘和夏令时。休市保留已知报价并提示，仍支持手动刷新；市场状态不明时暂停自动报价。订单核对不依赖开盘状态。

到期日与行权价元数据缓存五分钟、按纽约日期过期，并合并相同未完成请求；价格、订单和可用覆盖数量不由该缓存提供。报价过期会限制暂存。

图表手势状态隔离在浮框层，用二分查找定位历史日期；装饰动画限定刷新频率，并按可见性、标签页、后台和减少动态效果设置暂停。上述设计降低不必要工作，不是帧率或响应时间保证。

## 验证

```sh
# 从仓库根目录执行；用实际模拟器 ID 替换占位符
xcrun simctl list devices available
xcodebuild -project ios/Wheel.xcodeproj -scheme Wheel \
  -destination 'platform=iOS Simulator,id=SIMULATOR_ID' test
```

测试使用 mocked transport／Demo，覆盖数据有效性、过期报价、刷新退避、用户编辑保留、订单权限和不确定提交等路径。2026-10-01 本地开发版本通过 89 项模拟器回归；这个记录不代表任意 GitHub 提交都已通过同样检查。

安装新版本前先确保 Mini 后端具备对应接口。模拟器测试不能代替真机的语言／主题、点击区域、无线安装、盘中行情与成交验收。推送代码不会自动部署 Mini，也不会自动更新手机。

### Stock sell timing

Long-stock close tickets support DAY, GTC (default), and OVT. OVT is stored as
`OVERNIGHT` and submitted through the TWS `OVERNIGHT` exchange with `DAY` validity;
it requires an eligible USD stock and the account's overnight permissions. Quotes
use the same overnight route and never fall back to a SMART portfolio price.
Option timing remains unchanged. Stock buying is outside this feature.

Update the backend together with the app before using DAY or OVT in live mode.
Startup migrates the orders table with a nullable `tif` column; existing close
orders retain GTC. The app blocks new timing choices when backend support is
missing. Broker preflight and covered-call share reservations still apply.
Future exchange schedule changes require a separate review; no calendar-triggered
order-rule change is built in.

### Working-order edits and Portfolio shortcuts

Orders placed by Wheel can be amended after IB confirms Submitted/PreSubmitted:
total quantity (including fills), limit price, and DAY/GTC. CC opening quantity
and paired rollover quantity remain locked. Overnight route changes require a
separate cancellation and new ticket; an existing OVT order retains its route.
The backend rechecks account/client/order identity, fills, close capacity and
stock reserves, then modifies the existing IB order ID. An unconfirmed amendment
persists across restarts and blocks repeat amendments; broker confirmation is
required before local terms change. No automatic cancel/recreate or write retry.

Portfolio trailing swipe actions open Close for supported stock/option holdings
and Rollover for short options. Full-swipe execution is disabled. Existing
covered-call protections and ticket confirmation flows still apply.

### Stock report cost

Stock details show an optional **IBKR reported cost** snapshot from the configured
Flex query’s Open Positions summary (CSV POST or XML OpenPosition). Cost basis
divided by reported shares matches the official report; no historical premium or
dividend is subtracted again. Account, contract ID and currency must match the
live position. The report date and reported quantity remain visible because this
is not an intraday cost calculation. Live Gateway average cost, unrealized P&L
and close-ticket calculations retain their existing broker basis. Report loading
uses the performance background worker and private archive, without blocking on
a report download during portfolio requests. If the query omits Open Positions,
the optional section is unavailable.

### Refresh and recovery behavior

Portfolio and the Trade list keep their two-second cadence. Single-symbol Trade
and close-ticket quotes target one second, without overlapping a loop's requests.
Read failures retry after 1, 2, 4, 8, then 10 seconds; successful reads reset the
backoff. Trade rows have their own bounded backoff, and a valid stock quote can
wake a missing-underlying failure once per error streak. Missing portfolio option
metrics retry sooner; complete metrics retain their 15-second cadence (30 seconds
for frozen data). This never retries order submission, modification or cancellation.

Performance history is cached in memory for the current app session, by backend
and period, and cleared when connection context changes. Cached curves remain
visible during refresh. Canceled or superseded history tasks cannot publish into
a new period's state. Live P&L is cleared when its refresh context changes.

The portfolio/order status time represents a successful backend read, not an
exchange tick. The status explanation distinguishes backend access from quote
freshness, and order explanations distinguish drafts, working orders, uncertain
modifications, pending cancellations and fills. These descriptions do not change
broker execution rules or establish a fill independently of returned order data.

CSP details provide an on-demand initial-margin-change estimate through IB
what-if, for the exact standard USD put, quantity and limit price. The estimate
is separate from cash collateral, can be negative, and is invalidated when the
request context changes. The client requires an explicit estimated response,
matching terms, USD currency and a finite non-sentinel amount. Each request has
an independent identity so an old canceled request cannot clear a newer request's
loading state. No quote poll requests a what-if calculation automatically.

Daytime regression verification (2026-10-02): 96 iOS tests, 232 Python tests and
39 JavaScript tests passed. Added coverage for cancellation arriving during
amendment review, missing amendment acknowledgement after a partial fill, and
entry-margin response mismatches. Broker execution was mocked; this does not
constitute live-order validation or a long-duration phone battery measurement.

## 2026-10-05 图表同步验证

网页和 WKWebView 共同加载 `ChartAssets/chart-add-orders.js`，挂单加仓、取消和订单身份校验共用同一实现。原生加仓数量可直接输入，不再限制合计持仓；减仓仍需保留持仓。保留动态翻译键，清理无引用的旧翻译，并使用百分比 FormatStyle。项目没有 App Intents，关闭该项元数据提取，不关闭编译警告。

验证：后端 460 项、iOS 模拟器 121 项通过；移动触控加仓、20 手数量、取消、旧订单引用、明暗主题，以及网页提交/修改/撤销、OVT 500 股与未知请求恢复交互通过。干净模拟器构建及真机构建没有编译警告。以上订单测试使用模拟数据，不代表 IB 成交验收。
