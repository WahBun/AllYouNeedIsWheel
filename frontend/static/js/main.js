/**
 * Auto-Trader Frontend
 * Main JavaScript file
 */

// Global utility functions
const translations = {
    en: {
        'app.name': 'All You Need Is Wheel',
        'nav.dashboard': 'Dashboard',
        'nav.portfolio': 'Portfolio',
        'nav.rollover': 'Rollover',
        'nav.strategyTrainer': 'Strategy Trainer',
        'nav.options': 'Options',
        'nav.recommendations': 'Recommendations',
        'theme.light': 'Light mode',
        'theme.dark': 'Dark mode',
        'theme.switchToLight': 'Switch to light mode',
        'theme.switchToDark': 'Switch to dark mode',
        'language.current': 'EN',
        'language.toggle': 'Switch language',
        'language.switchToEnglish': 'Switch to English',
        'language.switchToChinese': 'Switch to Chinese',
        'settings.trading': 'Trading settings',
        'settings.confirmBeforeExecute': 'Confirm before Execute',
        'settings.confirmEnabled': 'Confirmation on',
        'settings.confirmDisabled': 'Direct execution on',
        'page.dashboard.title': 'Dashboard',
        'page.dashboard.subtitle': 'Overview of your portfolio and trading activity',
        'page.portfolio.title': 'Portfolio',
        'page.portfolio.subtitle': 'View and manage your positions',
        'page.rollover.title': 'Rollover Options',
        'page.rollover.subtitle': 'Manage options approaching strike price',
        'common.refresh': 'Refresh',
        'common.loading': 'Loading...',
        'common.close': 'Close',
        'common.add': 'Add',
        'common.addAll': 'Add All',
        'common.cancel': 'Cancel',
        'common.cancelAll': 'Cancel All',
        'common.execute': 'Execute',
        'common.actions': 'Actions',
        'common.action': 'Action',
        'common.status': 'Status',
        'common.type': 'Type',
        'common.symbol': 'Symbol',
        'common.ticker': 'Ticker',
        'common.shares': 'Shares',
        'common.strike': 'Strike',
        'common.expiration': 'Expiration',
        'common.quantity': 'Quantity',
        'common.qty': 'Qty',
        'common.price': 'Price',
        'common.limitPrice': 'Limit Price',
        'common.contracts': 'Contracts',
        'common.delta': 'Delta',
        'common.iv': 'IV%',
        'common.na': 'N/A',
        'dashboard.portfolioSummary': 'Portfolio Summary',
        'dashboard.totalValue': 'Total Value',
        'dashboard.cashBalance': 'Cash Balance',
        'dashboard.marginMetrics': 'Margin Metrics',
        'dashboard.excessLiquidity': 'Excess Liquidity',
        'dashboard.initialMargin': 'Initial Margin',
        'dashboard.leverage': 'Leverage',
        'dashboard.leverageTooltip': 'Leverage % = (Initial Margin / Portfolio Value) × 100',
        'dashboard.weeklyEarnings': 'Weekly Earnings',
        'dashboard.positionsExpiring': 'positions expiring',
        'dashboard.thisFriday': 'this Friday',
        'dashboard.updated': 'Updated {time}',
        'dashboard.frozenData': 'FROZEN DATA',
        'dashboard.realTimeData': 'REAL-TIME',
        'dashboard.frozenTooltip': 'Using frozen data because market is closed',
        'dashboard.realTimeTooltip': 'Using real-time market data',
        'options.title': 'Option Opportunities',
        'options.loading': 'Loading options data...',
        'options.coveredCalls': 'Covered Calls',
        'options.cashSecuredPuts': 'Cash-Secured Puts',
        'options.stockPrice': 'Stock Price',
        'options.otm': 'OTM %',
        'options.midPrice': 'Mid Price',
        'options.totalPremium': 'Total Premium',
        'options.cashRequired': 'Cash Required',
        'options.refreshAllCalls': 'Refresh All Calls',
        'options.refreshAllPuts': 'Refresh All Puts',
        'options.addTickerPlaceholder': 'Add ticker (e.g., AAPL)',
        'options.noExpirations': 'No expirations available',
        'options.noCoveredCalls': 'No covered call opportunities found.',
        'options.noCashSecuredPuts': 'No cash secured put opportunities found.',
        'options.addTickerHint': 'Add a ticker to see put option opportunities.',
        'options.footer.left': 'Only showing stock positions with at least 100 shares (required for covered calls). Higher OTM % = lower premium but less risk.',
        'options.footer.right': 'Switch between tabs to see covered call and cash-secured put opportunities.',
        'options.noStockPositions': 'No stock positions available. Please add stock positions first.',
        'options.removeTicker': 'Remove ticker',
        'options.loadingTicker': 'Loading data for {ticker} ({current}/{total})...',
        'options.processingTicker': 'Processing {ticker}...',
        'options.errorLoadingTicker': 'Error loading data for {ticker}: {message}',
        'options.tickerAlreadyAdded': 'Ticker already added',
        'options.tickerAlreadyAddedMessage': '{ticker} is already in your cash-secured puts list.',
        'options.dataError': 'Data Error',
        'options.noExpirationForTicker': 'Could not find expiration dates for {ticker}.',
        'options.tickerAdded': 'Ticker Added',
        'options.tickerAddedMessage': '{ticker} has been added. Select an expiration and click refresh to load options.',
        'options.error': 'Error',
        'options.failedAddTicker': 'Failed to add {ticker}: {message}',
        'options.tickerRemoved': 'Ticker Removed',
        'options.tickerRemovedMessage': '{ticker} has been removed from your custom puts list.',
        'options.tickerExcluded': 'Ticker Excluded',
        'options.tickerExcludedMessage': '{ticker} has been excluded from your cash secured puts list.',
        'options.notWheelCandidate': 'Not a Wheel Candidate',
        'options.notWheelCandidateMessage': '{ticker} is hidden from both opportunity lists.',
        'options.quoteUnavailable': 'No reliable two-sided quote is available. Refresh or enter a limit price manually.',
        'options.coveredCapacityUsed': 'In Use',
        'options.coveredCapacityUsedHint': 'Covered CALL capacity is already used by short positions or active sell orders.',
        'earnings.estimatedSummary': 'Estimated Earnings Summary',
        'earnings.weeklyPremium': 'Selected Premium:',
        'earnings.calls': 'Calls:',
        'earnings.puts': 'Puts:',
        'earnings.total': 'Total:',
        'earnings.weeklyReturn': 'Premium / Account:',
        'earnings.annual': 'Annual:',
        'earnings.projectedIncome': 'Annualized Estimate:',
        'earnings.projectedNote': 'Estimate for quoted selections, not filled orders or profit. Each premium is annualized by 365 / calendar days to expiry (New York date), then summed; assumes repeatable premiums, no compounding, fees or losses. Mixed expiries have different horizons. Same-day or invalid expiry: N/A.',
        'orders.pendingTitle': 'Pending Option Orders',
        'orders.loadingPending': 'Loading pending orders...',
        'orders.noPending': 'No pending orders found',
        'orders.footer': 'Manage your pending option orders here. Click Execute to send an order to Interactive Brokers.',
        'orders.weeklyIncomeTitle': 'Weekly Option Income (This Friday Expiration)',
        'orders.avgPrice': 'Avg Price',
        'orders.totalIncome': 'Total Income',
        'orders.notionalValue': 'Notional Value',
        'orders.loadingWeekly': 'Loading short options expiring this Friday...',
        'orders.noWeekly': 'No positions expiring this coming Friday found',
        'orders.weeklyIncome': 'Weekly Income',
        'orders.positionCount': 'Position Count',
        'orders.averageIncomePosition': 'Average Income/Position',
        'orders.totalPutNotional': 'Total PUT Notional',
        'orders.weeklyFooter': 'Short option positions expiring this coming Friday and estimated income.',
        'orders.weeklyFooterWithDate': 'Short option positions expiring this coming Friday ({date}). Total PUT notional value if assigned: {notional}',
        'orders.callOptions': 'CALL OPTIONS',
        'orders.putOptions': 'PUT OPTIONS',
        'orders.ibId': 'IB ID:',
        'orders.ibStatus': 'Status:',
        'orders.fillPrice': 'Fill Price:',
        'orders.commission': 'Commission:',
        'orders.confirmCancelAll': 'Are you sure you want to cancel all {count} pending orders?',
        'orders.noPendingToCancel': 'No pending orders to cancel',
        'orders.cancelingOrders': 'Canceling {count} orders...',
        'orders.cancelNotConfirmed': 'Some cancellations failed or still await confirmation. Review Pending before taking further action.',
        'orders.canceledOrders': 'Successfully canceled {count} orders',
        'orders.externalCancelInIb': '{count} IB-managed order(s) must be canceled in IB. No web-owned orders were changed.',
        'orders.canceledWebOrders': 'Canceled {count} web-owned order(s). {externalCount} IB-managed order(s) were left unchanged.',
        'orders.sellToOpen': 'SELL TO OPEN',
        'orders.buyToOpen': 'BUY TO OPEN',
        'orders.coveredShares': 'Shares Required',
        'orders.timeInForce': 'Time in Force',
        'orders.ibManaged': 'IB Managed',
        'orders.ibManagedHelp': 'This order was entered outside the web app. Manage it in IB.',
        'orders.ibPermId': 'Perm ID:',
        'orders.limitPricePerShare': 'Limit price per share',
        'orders.saveLimitPrice': 'Save limit price',
        'orders.limitPriceUpdated': 'Limit price saved at ${price}',
        'orders.limitPriceUpdateFailed': 'Limit price was not saved: {error}',
        'portfolio.stockPositions': 'Stock Positions',
        'portfolio.optionPositions': 'Option Positions',
        'portfolio.avgCost': 'Avg Cost',
        'portfolio.currentPrice': 'Current Price',
        'portfolio.marketValue': 'Market Value',
        'portfolio.unrealizedPnl': 'Unrealized P&L',
        'portfolio.loadingStock': 'Loading stock positions...',
        'portfolio.loadingOptions': 'Loading option positions...',
        'portfolio.noStockPositions': 'No stock positions found',
        'portfolio.noOptionPositions': 'No option positions found',
        'portfolio.connecting': 'CONNECTING',
        'portfolio.liveStream': 'LIVE · 2s',
        'portfolio.frozenStream': 'FROZEN · 2s',
        'portfolio.reconnecting': 'RECONNECTING',
        'portfolio.paused': 'PAUSED',
        'portfolio.stockFooter': 'This table shows your current stock positions with unrealized profit/loss.',
        'portfolio.optionFooter': 'This table shows your current option positions with details about strikes, expiration dates, and unrealized profit/loss.',
        'close.button': 'Close',
        'close.unavailable': 'Exact IB contract details are unavailable',
        'close.title': 'Close Option Position',
        'close.subtitle': 'Build a limit order, then review it again in Pending Orders.',
        'close.loadingQuote': 'Loading the latest position and quote...',
        'close.account': 'IB Account',
        'close.marketQuote': 'Market Quote',
        'close.refreshQuote': 'Refresh quote',
        'close.bid': 'Bid',
        'close.mid': 'Mid',
        'close.ask': 'Ask',
        'close.spread': 'Bid/ask spread: {value}',
        'close.spreadUnavailable': 'Bid/ask spread is unavailable',
        'close.oneContract': '1 Contract',
        'close.half': 'Half',
        'close.leaveRunner': 'Leave 1 Runner',
        'close.all': 'All',
        'close.remaining': 'Remaining after fill: {count}',
        'close.limitPerShare': 'Limit Price / Share',
        'close.joinMid': 'Join Mid',
        'close.priceNote': 'This exact limit is used when the staged order is executed.',
        'close.estimatedTotal': 'Estimated Order Total',
        'close.estimatedPnl': 'Estimated P&L',
        'close.estimatedReturn': 'Estimated Return',
        'close.safetyNote': 'Adding this order does not send it to IB. Execute follows your confirmation preference.',
        'close.addPending': 'Add to Pending',
        'close.buyToClose': 'BUY TO CLOSE',
        'close.sellToClose': 'SELL TO CLOSE',
        'close.contractSummary': '{expiration} · {strike} strike · {count} contract(s)',
        'close.staged': 'Close order #{id} added to Pending Orders. It has not been sent to IB.',
        'close.orderTotal': 'Order Total',
        'rollover.strikeDifference': 'Strike Difference',
        'rollover.percentDifference': '% Difference',
        'rollover.suggestions': 'Rollover Suggestions',
        'rollover.orderType': 'Order Type',
        'rollover.selectOption': 'Select an option to roll to view suggested replacements.',
        'rollover.pendingOrders': 'Rollover Pending Orders',
        'rollover.loadingPending': 'Loading rollover pending orders...',
        'rollover.positionsFooter': 'This table shows all option positions. Rows highlighted in yellow or red are approaching their strike price (less than 10% difference).',
        'rollover.suggestionsFooter': 'This table shows suggested order pairs for rolling over positions. First row is to close the current position, second row is to open a new position.',
        'rollover.pendingFooter': 'This table only shows rollover-related option orders. For all pending orders, please visit the dashboard.',
        'modal.confirmOrderTitle': 'Confirm Order Execution',
        'modal.confirmOrderBody': 'Are you sure you want to execute this order?',
        'modal.executeOrder': 'Execute Order',
        'footer.rights': 'All Rights Reserved'
    },
    zh: {
        'app.name': 'All You Need Is Wheel',
        'nav.dashboard': '仪表盘',
        'nav.portfolio': '持仓',
        'nav.rollover': '移仓',
        'nav.strategyTrainer': '策略训练',
        'nav.options': '期权',
        'nav.recommendations': '推荐',
        'theme.light': '白天模式',
        'theme.dark': '深色模式',
        'theme.switchToLight': '切换到白天模式',
        'theme.switchToDark': '切换到深色模式',
        'language.current': '中文',
        'language.toggle': '切换语言',
        'language.switchToEnglish': '切换到英文',
        'language.switchToChinese': '切换到中文',
        'settings.trading': '交易设置',
        'settings.confirmBeforeExecute': '执行前再次确认',
        'settings.confirmEnabled': '确认页已开启',
        'settings.confirmDisabled': '直接执行已开启',
        'page.dashboard.title': '仪表盘',
        'page.dashboard.subtitle': '查看账户、持仓和期权交易机会',
        'page.portfolio.title': '持仓',
        'page.portfolio.subtitle': '查看和管理当前持仓',
        'page.rollover.title': '期权移仓',
        'page.rollover.subtitle': '管理接近行权价的期权仓位',
        'common.refresh': '刷新',
        'common.loading': '加载中...',
        'common.close': '关闭',
        'common.add': '添加',
        'common.addAll': '全部添加',
        'common.cancel': '取消',
        'common.cancelAll': '全部取消',
        'common.execute': '执行',
        'common.actions': '操作',
        'common.action': '操作',
        'common.status': '状态',
        'common.type': '类型',
        'common.symbol': '代码',
        'common.ticker': '代码',
        'common.shares': '股数',
        'common.strike': '行权价',
        'common.expiration': '到期日',
        'common.quantity': '数量',
        'common.qty': '数量',
        'common.price': '价格',
        'common.limitPrice': '限价',
        'common.contracts': '合约数',
        'common.delta': 'Delta',
        'common.iv': 'IV%',
        'common.na': 'N/A',
        'dashboard.portfolioSummary': '账户概览',
        'dashboard.totalValue': '总资产',
        'dashboard.cashBalance': '现金余额',
        'dashboard.marginMetrics': '保证金指标',
        'dashboard.excessLiquidity': '剩余流动性',
        'dashboard.initialMargin': '初始保证金',
        'dashboard.leverage': '杠杆',
        'dashboard.leverageTooltip': '杠杆 % = 初始保证金 / 账户总资产 × 100',
        'dashboard.weeklyEarnings': '本周期权收入',
        'dashboard.positionsExpiring': '个仓位到期于',
        'dashboard.thisFriday': '本周五',
        'dashboard.updated': '更新于 {time}',
        'dashboard.frozenData': '冻结数据',
        'dashboard.realTimeData': '实时数据',
        'dashboard.frozenTooltip': '市场休市，当前使用冻结数据',
        'dashboard.realTimeTooltip': '正在使用实时市场数据',
        'options.title': '期权机会',
        'options.loading': '正在加载期权数据...',
        'options.coveredCalls': '备兑看涨',
        'options.cashSecuredPuts': '现金担保看跌',
        'options.stockPrice': '股价',
        'options.otm': '价外 %',
        'options.midPrice': '中间价',
        'options.totalPremium': '总权利金',
        'options.cashRequired': '所需现金',
        'options.refreshAllCalls': '刷新全部看涨',
        'options.refreshAllPuts': '刷新全部看跌',
        'options.addTickerPlaceholder': '添加代码，例如 AAPL',
        'options.noExpirations': '暂无到期日',
        'options.noCoveredCalls': '暂无备兑看涨机会。',
        'options.noCashSecuredPuts': '暂无现金担保看跌机会。',
        'options.addTickerHint': '添加一个代码以查看看跌期权机会。',
        'options.footer.left': '仅显示至少 100 股的股票持仓。价外比例越高，权利金越低，风险也越低。',
        'options.footer.right': '切换标签查看备兑看涨和现金担保看跌机会。',
        'options.noStockPositions': '暂无股票持仓。请先添加股票持仓。',
        'options.removeTicker': '移除代码',
        'options.loadingTicker': '正在加载 {ticker} ({current}/{total})...',
        'options.processingTicker': '正在处理 {ticker}...',
        'options.errorLoadingTicker': '加载 {ticker} 失败：{message}',
        'options.tickerAlreadyAdded': '代码已添加',
        'options.tickerAlreadyAddedMessage': '{ticker} 已在现金担保看跌列表中。',
        'options.dataError': '数据错误',
        'options.noExpirationForTicker': '找不到 {ticker} 的期权到期日。',
        'options.tickerAdded': '代码已添加',
        'options.tickerAddedMessage': '{ticker} 已添加。请选择到期日并点击刷新加载期权。',
        'options.error': '错误',
        'options.failedAddTicker': '添加 {ticker} 失败：{message}',
        'options.tickerRemoved': '代码已移除',
        'options.tickerRemovedMessage': '{ticker} 已从自定义看跌列表移除。',
        'options.tickerExcluded': '代码已排除',
        'options.tickerExcludedMessage': '{ticker} 已从现金担保看跌列表排除。',
        'options.notWheelCandidate': '不属于 Wheel 候选',
        'options.notWheelCandidateMessage': '{ticker} 已从两个期权机会列表隐藏。',
        'options.quoteUnavailable': '暂无可靠的双边报价，请刷新或手动输入限价。',
        'options.coveredCapacityUsed': '已占用',
        'options.coveredCapacityUsedHint': '备兑 CALL 额度已被现有空头持仓或活动卖单占用。',
        'earnings.estimatedSummary': '预估收益汇总',
        'earnings.weeklyPremium': '所选权利金：',
        'earnings.calls': '看涨：',
        'earnings.puts': '看跌：',
        'earnings.total': '合计：',
        'earnings.weeklyReturn': '权利金 / 账户：',
        'earnings.annual': '年化：',
        'earnings.projectedIncome': '年化估算：',
        'earnings.projectedNote': '仅估算所选报价，并非已成交收入或利润。每笔权利金乘以 365 / 距到期自然日数（纽约日期）后汇总；假设可重复获得相同权利金，不计复利、费用及亏损。不同到期日对应不同周期；当日到期或日期无效时显示 N/A。',
        'orders.pendingTitle': '待处理期权订单',
        'orders.loadingPending': '正在加载待处理订单...',
        'orders.noPending': '暂无待处理订单',
        'orders.footer': '这里管理待处理期权订单。点击执行会把订单发送到 Interactive Brokers。',
        'orders.weeklyIncomeTitle': '本周五到期期权收入',
        'orders.avgPrice': '均价',
        'orders.totalIncome': '总收入',
        'orders.notionalValue': '名义价值',
        'orders.loadingWeekly': '正在加载本周五到期的空头期权...',
        'orders.noWeekly': '暂无本周五到期的期权仓位',
        'orders.weeklyIncome': '每周收入',
        'orders.positionCount': '仓位数量',
        'orders.averageIncomePosition': '单仓平均收入',
        'orders.totalPutNotional': 'PUT 总名义价值',
        'orders.weeklyFooter': '本周五到期的空头期权仓位和预估收入。',
        'orders.weeklyFooterWithDate': '本周五（{date}）到期的空头期权仓位。若 PUT 被指派，总名义价值：{notional}',
        'orders.callOptions': 'CALL 期权',
        'orders.putOptions': 'PUT 期权',
        'orders.ibId': 'IB 订单号：',
        'orders.ibStatus': '状态：',
        'orders.fillPrice': '成交价：',
        'orders.commission': '佣金：',
        'orders.confirmCancelAll': '确定要取消全部 {count} 个待处理订单吗？',
        'orders.noPendingToCancel': '没有可取消的待处理订单',
        'orders.cancelingOrders': '正在取消 {count} 个订单...',
        'orders.cancelNotConfirmed': '部分取消失败或仍待确认，请留在 Pending 核对状态后再操作。',
        'orders.canceledOrders': '已成功取消 {count} 个订单',
        'orders.externalCancelInIb': '{count} 个 IB 端订单需在 IB 中撤销；网页版未改动任何订单。',
        'orders.canceledWebOrders': '已撤销 {count} 个网页版订单；{externalCount} 个 IB 端订单保持不变。',
        'orders.sellToOpen': '卖出开仓',
        'orders.buyToOpen': '买入开仓',
        'orders.coveredShares': '所需覆盖股数',
        'orders.timeInForce': '订单有效期',
        'orders.ibManaged': 'IB 端管理',
        'orders.ibManagedHelp': '此订单并非由网页版创建，请在 IB 端管理。',
        'orders.ibPermId': '永久 ID：',
        'orders.limitPricePerShare': '每股限价',
        'orders.saveLimitPrice': '保存限价',
        'orders.limitPriceUpdated': '限价已保存为 ${price}',
        'orders.limitPriceUpdateFailed': '限价保存失败：{error}',
        'portfolio.stockPositions': '股票持仓',
        'portfolio.optionPositions': '期权持仓',
        'portfolio.avgCost': '平均成本',
        'portfolio.currentPrice': '当前价格',
        'portfolio.marketValue': '市值',
        'portfolio.unrealizedPnl': '未实现盈亏',
        'portfolio.loadingStock': '正在加载股票持仓...',
        'portfolio.loadingOptions': '正在加载期权持仓...',
        'portfolio.noStockPositions': '暂无股票持仓',
        'portfolio.noOptionPositions': '暂无期权持仓',
        'portfolio.connecting': '连接中',
        'portfolio.liveStream': '实时 · 2秒',
        'portfolio.frozenStream': '冻结 · 2秒',
        'portfolio.reconnecting': '重新连接中',
        'portfolio.paused': '已暂停',
        'portfolio.stockFooter': '此表显示当前股票持仓和未实现盈亏。',
        'portfolio.optionFooter': '此表显示当前期权持仓，包括行权价、到期日和未实现盈亏。',
        'close.button': '平仓',
        'close.unavailable': '缺少精确的 IB 合约信息',
        'close.title': '平掉期权仓位',
        'close.subtitle': '先创建限价单，再到待处理订单中进行二次确认。',
        'close.loadingQuote': '正在读取最新持仓和报价...',
        'close.account': 'IB 账户',
        'close.marketQuote': '市场报价',
        'close.refreshQuote': '刷新报价',
        'close.bid': '买价',
        'close.mid': '中间价',
        'close.ask': '卖价',
        'close.spread': '买卖价差：{value}',
        'close.spreadUnavailable': '暂时无法计算买卖价差',
        'close.oneContract': '1 张',
        'close.half': '一半',
        'close.leaveRunner': '保留 1 张 Runner',
        'close.all': '全部',
        'close.remaining': '预计成交后剩余：{count} 张',
        'close.limitPerShare': '每股期权限价',
        'close.joinMid': 'Join Mid',
        'close.priceNote': '执行待处理订单时，将严格使用这里选择的限价。',
        'close.estimatedTotal': '预计订单总额',
        'close.estimatedPnl': '预计盈亏',
        'close.estimatedReturn': '预计收益率',
        'close.safetyNote': '添加订单不会发送到 IB；执行时是否再次确认取决于交易设置。',
        'close.addPending': '加入待处理',
        'close.buyToClose': '买入平仓',
        'close.sellToClose': '卖出平仓',
        'close.contractSummary': '{expiration} · 行权价 {strike} · 当前 {count} 张',
        'close.staged': '平仓订单 #{id} 已加入待处理，尚未发送到 IB。',
        'close.orderTotal': '订单总额',
        'rollover.strikeDifference': '距行权价',
        'rollover.percentDifference': '差距 %',
        'rollover.suggestions': '移仓建议',
        'rollover.orderType': '订单类型',
        'rollover.selectOption': '选择一个期权仓位后查看移仓建议。',
        'rollover.pendingOrders': '移仓待处理订单',
        'rollover.loadingPending': '正在加载移仓待处理订单...',
        'rollover.positionsFooter': '此表显示全部期权持仓。黄色或红色行代表接近行权价（差距低于 10%）。',
        'rollover.suggestionsFooter': '此表显示移仓建议订单组合。第一行用于平掉当前仓位，第二行用于打开新仓位。',
        'rollover.pendingFooter': '此表只显示移仓相关期权订单。所有待处理订单请到仪表盘查看。',
        'modal.confirmOrderTitle': '确认执行订单',
        'modal.confirmOrderBody': '确定要执行这个订单吗？',
        'modal.executeOrder': '执行订单',
        'footer.rights': '保留所有权利'
    }
};

function getInitialLanguage() {
    const savedLanguage = localStorage.getItem('language');
    const languagePreference = localStorage.getItem('languagePreference');
    if (languagePreference === 'manual' && (savedLanguage === 'zh' || savedLanguage === 'en')) {
        return savedLanguage;
    }

    return 'en';
}

function getCurrentLanguage() {
    const language = document.documentElement.getAttribute('data-lang') || localStorage.getItem('language') || getInitialLanguage();
    return language === 'zh' ? 'zh' : 'en';
}

function translate(key, replacements = {}) {
    const language = getCurrentLanguage();
    const text = translations[language]?.[key] || translations.en[key] || key;

    return Object.entries(replacements).reduce((result, [name, value]) => {
        return result.replaceAll(`{${name}}`, value);
    }, text);
}

function applyLanguage(language, options = {}) {
    const normalizedLanguage = language === 'zh' ? 'zh' : 'en';
    const shouldPersist = options.persist !== false;
    const shouldDispatch = options.dispatch !== false;

    document.documentElement.setAttribute('lang', normalizedLanguage === 'zh' ? 'zh-CN' : 'en');
    document.documentElement.setAttribute('data-lang', normalizedLanguage);
    if (shouldPersist) {
        localStorage.setItem('language', normalizedLanguage);
        localStorage.setItem('languagePreference', 'manual');
    }

    document.querySelectorAll('[data-i18n]').forEach(element => {
        element.textContent = translate(element.dataset.i18n);
    });
    document.querySelectorAll('[data-i18n-html]').forEach(element => {
        element.innerHTML = translate(element.dataset.i18nHtml);
    });
    document.querySelectorAll('[data-i18n-placeholder]').forEach(element => {
        element.setAttribute('placeholder', translate(element.dataset.i18nPlaceholder));
    });
    document.querySelectorAll('[data-i18n-title]').forEach(element => {
        element.setAttribute('title', translate(element.dataset.i18nTitle));
        element.setAttribute('data-bs-title', translate(element.dataset.i18nTitle));
    });
    document.querySelectorAll('[data-i18n-aria-label]').forEach(element => {
        element.setAttribute('aria-label', translate(element.dataset.i18nAriaLabel));
    });

    const languageToggle = document.getElementById('language-toggle');
    if (languageToggle) {
        const label = languageToggle.querySelector('.language-toggle-label');
        if (label) {
            label.textContent = translate('language.current');
        }
        const nextLanguageKey = normalizedLanguage === 'zh' ? 'language.switchToEnglish' : 'language.switchToChinese';
        const nextLanguageLabel = translate(nextLanguageKey);
        languageToggle.setAttribute('aria-label', nextLanguageLabel);
        languageToggle.setAttribute('data-bs-title', nextLanguageLabel);

        const tooltip = bootstrap.Tooltip.getInstance(languageToggle);
        if (tooltip) {
            tooltip.setContent({ '.tooltip-inner': nextLanguageLabel });
        }
    }

    if (window.bootstrap?.Tooltip) {
        document.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(element => {
            const tooltip = bootstrap.Tooltip.getInstance(element);
            if (tooltip) {
                tooltip.dispose();
                new bootstrap.Tooltip(element);
            }
        });
    }

    if (shouldDispatch) {
        document.dispatchEvent(new CustomEvent('languageChanged', { detail: { language: normalizedLanguage } }));
    }
}

window.t = translate;
window.applyLanguage = applyLanguage;
window.getCurrentLanguage = getCurrentLanguage;

function applyTheme(theme) {
    const normalizedTheme = theme === 'dark' ? 'dark' : 'light';
    document.documentElement.setAttribute('data-theme', normalizedTheme);
    document.documentElement.setAttribute('data-bs-theme', normalizedTheme);
    localStorage.setItem('theme', normalizedTheme);

    const toggleButton = document.getElementById('theme-toggle');
    if (!toggleButton) return;

    const icon = toggleButton.querySelector('i');
    if (icon) {
        icon.className = normalizedTheme === 'dark' ? 'bi bi-sun-fill' : 'bi bi-moon-stars-fill';
    }
    toggleButton.setAttribute('aria-label', normalizedTheme === 'dark' ? translate('theme.switchToLight') : translate('theme.switchToDark'));
    toggleButton.setAttribute('data-bs-title', normalizedTheme === 'dark' ? translate('theme.light') : translate('theme.dark'));

    const tooltip = bootstrap.Tooltip.getInstance(toggleButton);
    if (tooltip) {
        tooltip.setContent({ '.tooltip-inner': normalizedTheme === 'dark' ? translate('theme.light') : translate('theme.dark') });
    }
}

function getInitialTheme() {
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme === 'dark' || savedTheme === 'light') {
        return savedTheme;
    }

    return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

/**
 * Format a number as currency
 * @param {number|string} value - The value to format
 * @returns {string} - Formatted currency string
 */
function formatCurrency(value) {
    if (value === undefined || value === null) {
        return '$0.00';
    }
    return '$' + parseFloat(value).toFixed(2).replace(/\d(?=(\d{3})+\.)/g, '$&,');
}

/**
 * Format a number as percentage
 * @param {number|string} value - The value to format
 * @returns {string} - Formatted percentage string
 */
function formatPercentage(value) {
    if (value === undefined || value === null) {
        return '0.00%';
    }
    const numValue = parseFloat(value);
    return (numValue >= 0 ? '+' : '') + numValue.toFixed(2) + '%';
}

/**
 * Format a date string
 * @param {string} dateString - Date string in any valid format
 * @param {string} format - Format option ('short', 'medium', 'long')
 * @returns {string} - Formatted date string
 */
function formatDate(dateString, format = 'medium') {
    if (!dateString) return 'N/A';
    
    try {
        const date = new Date(dateString);
        
        // Check if date is valid
        if (isNaN(date.getTime())) {
            return dateString;
        }
        
        let options;
        switch (format) {
            case 'short':
                options = { month: 'numeric', day: 'numeric', year: '2-digit' };
                break;
            case 'long':
                options = { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' };
                break;
            case 'medium':
            default:
                options = { year: 'numeric', month: 'short', day: 'numeric' };
                break;
        }
        
        return date.toLocaleDateString('en-US', options);
    } catch (e) {
        console.error('Error formatting date:', e);
        return dateString;
    }
}

/**
 * Add class to element based on value
 * @param {Element} element - DOM element to modify
 * @param {number} value - Value to evaluate
 * @param {string} positiveClass - Class to add for positive values
 * @param {string} negativeClass - Class to add for negative values
 */
function addValueClass(element, value, positiveClass = 'text-success', negativeClass = 'text-danger') {
    if (value > 0) {
        element.classList.add(positiveClass);
        element.classList.remove(negativeClass);
    } else if (value < 0) {
        element.classList.add(negativeClass);
        element.classList.remove(positiveClass);
    } else {
        element.classList.remove(positiveClass);
        element.classList.remove(negativeClass);
    }
}

/**
 * Show loading spinner
 * @param {string} targetId - ID of element to show spinner in
 * @param {string} message - Optional loading message
 */
function showLoading(targetId, message = 'Loading...') {
    const targetElement = document.getElementById(targetId);
    if (targetElement) {
        targetElement.innerHTML = `
            <div class="text-center p-3">
                <div class="spinner-border text-primary" role="status">
                    <span class="visually-hidden">Loading...</span>
                </div>
                <p class="mt-2">${message}</p>
            </div>
        `;
    }
}

/**
 * Show error message
 * @param {string} targetId - ID of element to show error in
 * @param {string} message - Error message
 */
function showError(targetId, message = 'An error occurred. Please try again.') {
    const targetElement = document.getElementById(targetId);
    if (targetElement) {
        targetElement.innerHTML = `
            <div class="alert alert-danger" role="alert">
                <i class="bi bi-exclamation-triangle-fill me-2"></i>
                ${message}
            </div>
        `;
    }
}

// Initialize tooltips and popovers when page loads
document.addEventListener('DOMContentLoaded', function() {
    const themeToggle = document.getElementById('theme-toggle');
    const languageToggle = document.getElementById('language-toggle');
    applyLanguage(getInitialLanguage(), { dispatch: false, persist: false });
    applyTheme(getInitialTheme());

    if (themeToggle) {
        themeToggle.addEventListener('click', function() {
            const currentTheme = document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
            applyTheme(currentTheme === 'dark' ? 'light' : 'dark');
        });
    }

    if (languageToggle) {
        languageToggle.addEventListener('click', function() {
            const currentLanguage = getCurrentLanguage();
            applyLanguage(currentLanguage === 'zh' ? 'en' : 'zh');
            applyTheme(document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light');
        });
    }

    // Initialize Bootstrap tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
    
    // Initialize Bootstrap popovers
    const popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
    popoverTriggerList.map(function (popoverTriggerEl) {
        return new bootstrap.Popover(popoverTriggerEl);
    });
});

// Set the current year in the footer
document.addEventListener('DOMContentLoaded', function() {
    const currentYearElement = document.getElementById('current-year');
    if (currentYearElement) {
        currentYearElement.textContent = new Date().getFullYear();
    }
    
    // Add a content container for alerts if it doesn't exist
    const mainContainer = document.querySelector('main');
    if (mainContainer && !document.querySelector('.content-container')) {
        const contentContainer = document.createElement('div');
        contentContainer.className = 'content-container';
        mainContainer.prepend(contentContainer);
    }
});

// Add CustomEvent polyfill for older browsers
(function() {
    if (typeof window.CustomEvent === 'function') return false;
    
    function CustomEvent(event, params) {
        params = params || { bubbles: false, cancelable: false, detail: null };
        const evt = document.createEvent('CustomEvent');
        evt.initCustomEvent(event, params.bubbles, params.cancelable, params.detail);
        return evt;
    }
    
    window.CustomEvent = CustomEvent;
})();

// Add Array.from polyfill for older browsers
if (!Array.from) {
    Array.from = function(arrayLike) {
        return [].slice.call(arrayLike);
    };
}

// Add Promise polyfill for older browsers (minimal implementation)
if (!window.Promise) {
    window.Promise = function(executor) {
        this.then = function(onFulfilled) {
            this.onFulfilled = onFulfilled;
            return this;
        };
        this.catch = function(onRejected) {
            this.onRejected = onRejected;
            return this;
        };
        
        const resolve = (value) => {
            setTimeout(() => {
                if (this.onFulfilled) this.onFulfilled(value);
            }, 0);
        };
        
        const reject = (reason) => {
            setTimeout(() => {
                if (this.onRejected) this.onRejected(reason);
            }, 0);
        };
        
        executor(resolve, reject);
    };
    
    window.Promise.all = function(promises) {
        return new Promise((resolve, reject) => {
            let results = [];
            let completedCount = 0;
            
            promises.forEach((promise, index) => {
                promise.then(value => {
                    results[index] = value;
                    completedCount++;
                    
                    if (completedCount === promises.length) {
                        resolve(results);
                    }
                }).catch(reject);
            });
        });
    };
}

// Add fetch polyfill (minimal implementation, for modern browsers that don't support fetch)
if (!window.fetch) {
    console.warn('Fetch API not available. Using XMLHttpRequest polyfill. Consider updating your browser.');
    
    window.fetch = function(url, options) {
        return new Promise((resolve, reject) => {
            const xhr = new XMLHttpRequest();
            xhr.open(options?.method || 'GET', url);
            
            if (options?.headers) {
                Object.keys(options.headers).forEach(key => {
                    xhr.setRequestHeader(key, options.headers[key]);
                });
            }
            
            xhr.onload = function() {
                const response = {
                    ok: xhr.status >= 200 && xhr.status < 300,
                    status: xhr.status,
                    json: function() {
                        return Promise.resolve(JSON.parse(xhr.responseText));
                    },
                    text: function() {
                        return Promise.resolve(xhr.responseText);
                    }
                };
                resolve(response);
            };
            
            xhr.onerror = function() {
                reject(new Error('Network error'));
            };
            
            xhr.send(options?.body || null);
        });
    };
} 
