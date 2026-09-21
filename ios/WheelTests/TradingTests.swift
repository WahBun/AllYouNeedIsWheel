import XCTest
@testable import Wheel

final class MockProtocol: URLProtocol {
    static var requests: [URLRequest] = []
    static var fail = false
    static var payload: ((URLRequest) -> [String: Any])?
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        Self.requests.append(request)
        if Self.fail { client?.urlProtocol(self, didFailWithError: URLError(.timedOut)); return }
        let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        let body = Self.payload?(request) ?? ["success": true, "status": "processing"]
        client?.urlProtocol(self, didLoad: try! JSONSerialization.data(withJSONObject: body))
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

@MainActor
final class TradingTests: XCTestCase {
    func testMarginImpactRequiresExactPositionAndEstimateSemantics() {
        let position = Position(symbol: "TEST", position: -2, security_type: "OPT", con_id: 42)
        let impact = MarginImpact(con_id: 42, position: -2, currency: "USD", initial_change: -200,
            maintenance_change: 50, estimated: true, additive: false, scenario: "close_entire_position", warning: nil, retrieved_at: "Demo")
        XCTAssertTrue(impact.matches(position))
        var changed = position; changed.position = -1
        XCTAssertFalse(impact.matches(changed))
        changed = position; changed.con_id = 99
        XCTAssertFalse(impact.matches(changed))
        XCTAssertFalse(MarginImpact(con_id: 42, position: -2, currency: "HKD", initial_change: -200,
            maintenance_change: 50, estimated: true, additive: false, scenario: "close_entire_position", warning: nil, retrieved_at: "Demo").matches(position))
    }
    func testConnectionFeedbackRequiresFreshDataFromMatchingBackend() async {
        let store = WheelStore()
        await store.refreshPortfolio()
        store.address = "https://mock.invalid"
        XCTAssertFalse(store.isConnected(to: store.address))
        store.demo = false
        XCTAssertTrue(store.isConnected(to: " https://mock.invalid "))
        XCTAssertFalse(store.isConnected(to: "https://other.invalid"))
        store.error = "Offline"
        XCTAssertFalse(store.isConnected(to: store.address))
        store.error = nil; store.updated = Date(timeIntervalSinceNow: -20)
        XCTAssertFalse(store.isConnected(to: store.address))
        store.changeMode()
        XCTAssertFalse(store.isConnected(to: store.address))
    }
    func testHiddenTickersAreScopedToStrategy() {
        let book = OpportunityBook()
        book.excluded = [book.key("TSLL", "PUT")]
        XCTAssertTrue(book.hasHidden(type: "PUT"))
        XCTAssertFalse(book.hasHidden(type: "CALL"))
        book.restoreHidden(type: "CALL")
        XCTAssertEqual(book.excluded, ["TSLL:PUT"])
        book.excluded.append(book.key("CRCL", "CALL"))
        book.restoreHidden(type: "PUT")
        XCTAssertEqual(book.excluded, ["CRCL:CALL"])
        XCTAssertFalse(book.hasHidden(type: "PUT"))
        XCTAssertTrue(book.hasHidden(type: "CALL"))
        book.restoreHidden(type: "CALL")
        XCTAssertTrue(book.excluded.isEmpty)
    }
    func testQuickStageCreatesOnlyDraftAndPreventsDuplicate() async {
        let store = WheelStore()
        await store.refreshPortfolio()
        let book = store.opportunities
        book.preferences = [:]
        await book.load("TSLL", type: "CALL", store: store)
        let snapshot = book.rows["TSLL:CALL"]!
        let count = store.trading.demoOrders.count
        await book.stageAndOpenOrders([snapshot], store: store)
        XCTAssertEqual(store.trading.demoOrders.count, count + 1)
        XCTAssertEqual(store.trading.demoOrders.last?.status, "pending")
        XCTAssertEqual(store.trading.demoOrders.last?.quantity, 3)
        XCTAssertEqual(store.selectedTab, "orders")
        XCTAssertFalse(book.batchRunning)
        await book.stageAndOpenOrders([snapshot], store: store)
        XCTAssertEqual(store.trading.demoOrders.count, count + 1)
    }
    func testQuickStageRejectsChangedQuoteOrFailedRefresh() async {
        let store = WheelStore()
        await store.refreshPortfolio()
        let book = store.opportunities
        await book.load("TSLL", type: "CALL", store: store)
        let snapshot = book.rows["TSLL:CALL"]!
        let count = store.trading.demoOrders.count
        book.rows["TSLL:CALL"]?.price = "0.35"
        await book.stageAndOpenOrders([snapshot], store: store)
        XCTAssertEqual(store.trading.demoOrders.count, count)
        book.rows["TSLL:CALL"] = snapshot
        book.rows["TSLL:CALL"]?.error = "Offline"
        await book.stageAndOpenOrders([snapshot], store: store)
        XCTAssertEqual(store.trading.demoOrders.count, count)
        XCTAssertFalse(book.batchRunning)
    }
    func testSpreadBandsMatchWebBoundaries() {
        XCTAssertEqual(SpreadBand.classify(0), .tight)
        XCTAssertEqual(SpreadBand.classify(10), .tight)
        XCTAssertEqual(SpreadBand.classify(10.01), .medium)
        XCTAssertEqual(SpreadBand.classify(20), .medium)
        XCTAssertEqual(SpreadBand.classify(20.01), .wide)
        for value: Double? in [nil, .nan, .infinity, -1] {
            XCTAssertEqual(SpreadBand.classify(value), .unavailable)
        }
    }
    func testQuickActionRevalidation() {
        let original = Order(id: 8, ticker: "TEST", action: "SELL", option_type: "CALL", strike: 10, expiration: "20261016", premium: 0.5, quantity: 2, status: "pending", tif: "DAY", intent: "OPEN")
        XCTAssertTrue(TradeRules.unchanged(original, since: original))
        XCTAssertTrue(TradeRules.editable(original))
        var changed = original
        changed.premium = 0.6
        XCTAssertFalse(TradeRules.unchanged(changed, since: original))
        changed = original; changed.quantity = 1
        XCTAssertFalse(TradeRules.unchanged(changed, since: original))
        changed = original; changed.status = "processing"
        XCTAssertFalse(TradeRules.editable(changed))
        XCTAssertTrue(TradeRules.cancelable(changed))
        changed.status = "unknown"
        XCTAssertFalse(TradeRules.cancelable(changed))
        changed = original; changed.external_ib = true
        XCTAssertFalse(TradeRules.editable(changed))
        XCTAssertFalse(TradeRules.cancelable(changed))
    }
    private func closeQuote(_ mid: Double = 0.6, held: Double = -3) -> [String: Any] {
        ["position": held, "close_action": held < 0 ? "BUY" : "SELL", "bid": mid - 0.01, "mid": mid, "ask": mid + 0.01, "quote_time": "Frozen snapshot", "is_frozen": true]
    }
    func testRefreshCadenceAccountsForRequestTimeAndBackoff() {
        XCTAssertEqual(RefreshLoop.delay(elapsed: 0.4, failed: false), 1.6, accuracy: 0.001)
        XCTAssertEqual(RefreshLoop.delay(elapsed: 8, failed: false), 0.25)
        XCTAssertEqual(RefreshLoop.delay(elapsed: 1, failed: true), 9)
    }
    func testQuoteRefreshPreservesManualPriceQuantityAndBlankInput() async {
        let state = CloseQuoteState()
        await state.refresh { self.closeQuote() }
        XCTAssertEqual(state.price, "0.60")
        state.markPriceEdited("0.51"); state.quantity = 2
        await state.refresh { self.closeQuote(0.7) }
        XCTAssertEqual(state.price, "0.51"); XCTAssertEqual(state.quantity, 2)
        XCTAssertEqual(state.quote?["mid"] as? Double, 0.7)
        XCTAssertNotNil(state.receivedAt); XCTAssertTrue(state.valid)
        state.markPriceEdited("")
        await state.refresh { self.closeQuote(0.8) }
        XCTAssertEqual(state.price, ""); XCTAssertFalse(state.valid)
    }
    func testFailureRetainsQuoteButDisablesStageUntilRecovery() async {
        let state = CloseQuoteState()
        await state.refresh { self.closeQuote() }
        let timestamp = state.receivedAt
        await state.refresh { throw URLError(.timedOut) }
        XCTAssertNotNil(state.quote); XCTAssertEqual(state.receivedAt, timestamp)
        XCTAssertNotNil(state.error); XCTAssertFalse(state.valid)
        await state.refresh { self.closeQuote() }
        XCTAssertNil(state.error); XCTAssertTrue(state.valid)
    }
    func testPositionShrinkDoesNotSilentlyChangeQuantity() async {
        let state = CloseQuoteState()
        await state.refresh { self.closeQuote() }
        state.quantity = 3
        await state.refresh { self.closeQuote(0.6, held: -1) }
        XCTAssertEqual(state.quantity, 3); XCTAssertEqual(state.held, 1)
        XCTAssertFalse(state.valid)
        state.receivedAt = Date(timeIntervalSinceNow: -30)
        state.quantity = 1
        XCTAssertFalse(state.valid)
    }
    func testQuoteSingleFlightAndDiscardAfterLeavingPage() async {
        let state = CloseQuoteState()
        var resume: CheckedContinuation<[String: Any], Never>?
        let request = Task {
            await state.refresh { await withCheckedContinuation { resume = $0 } }
        }
        while resume == nil { await Task.yield() }
        var extraRequest = false
        await state.refresh { extraRequest = true; return self.closeQuote() }
        XCTAssertFalse(extraRequest)
        state.invalidate()
        resume?.resume(returning: closeQuote())
        await request.value
        XCTAssertNil(state.quote); XCTAssertNil(state.receivedAt)
        XCTAssertFalse(state.loading)
    }
    func testPausedReadDoesNotFetchAndUnsavedChangesBlockExecution() async {
        let state = CloseQuoteState()
        var fetched = false
        await state.refresh(fetch: { fetched = true; return self.closeQuote() }, allowed: { false })
        XCTAssertFalse(fetched)
        let order = Order(id: 5, premium: 0.5, quantity: 2, status: "pending", intent: "OPEN")
        XCTAssertFalse(TradeRules.hasUnsavedEdits(order, price: "0.50", quantity: 2))
        XCTAssertTrue(TradeRules.hasUnsavedEdits(order, price: "0.51", quantity: 2))
        XCTAssertTrue(TradeRules.hasUnsavedEdits(order, price: "0.50", quantity: 1))
    }
    func testLanguageLabelsPreserveTradingTermsAndBrand() {
        XCTAssertEqual(localizedLabel("Portfolio", locale: Locale(identifier: "zh-Hans")), "持仓")
        XCTAssertEqual(localizedLabel("Portfolio", locale: Locale(identifier: "zh-Hant")), "持倉")
        XCTAssertEqual(localizedLabel("Portfolio", locale: Locale(identifier: "en")), "Portfolio")
        for value in ["Wheel", "Call", "Put", "OTM", "Delta", "IV", "GTC", "DAY", "TSLL"] {
            XCTAssertEqual(localizedLabel(value, locale: Locale(identifier: "zh-Hans")), value)
        }
    }
    func testQuotesAndCoveredCapacity() {
        XCTAssertNil(TradingMath.mid(nil, 1))
        XCTAssertNil(TradingMath.mid(0, 1))
        XCTAssertNil(TradingMath.mid(2, 1))
        XCTAssertEqual(TradingMath.mid(0.25, 0.29)!, 0.27, accuracy: 0.00001)
        XCTAssertEqual(TradingMath.capacity(shares: 300, available: 2), 2)
        XCTAssertEqual(TradingMath.capacity(shares: 300, available: nil), 0)
        XCTAssertEqual(TradingMath.capacity(shares: 199, available: 9), 1)
        XCTAssertEqual(TradingMath.capacity(shares: .nan, available: 9), 0)
    }
    func testContractEditsAndOccupiedCoverage() {
        var row = OpportunityRow(ticker: "TEST", type: "CALL")
        row.quote = ContractQuote(strike: 10, expiration: "20261016", bid: 0.25, ask: 0.29)
        row.price = "0.27"
        XCTAssertFalse(row.canStage)
        row.capacity = 2; row.quantity = 2
        row.updated = Date()
        XCTAssertTrue(row.canStage)
        row.quantity = 3
        XCTAssertFalse(row.canStage)
        row.quantity = 1; row.staged = true
        XCTAssertFalse(row.canStage)
    }
    func testClosePnLAndDates() {
        XCTAssertEqual(TradingMath.closePnL(entry: 0.5, limit: 0.2, quantity: 2, multiplier: 100, buy: true)!, 60, accuracy: 0.001)
        XCTAssertEqual(TradingMath.closePnL(entry: 0.5, limit: 0.2, quantity: 2, multiplier: 100, buy: false)!, -60, accuracy: 0.001)
        XCTAssertNil(TradingMath.annualized(premium: 10, expiration: "20260230"))
        XCTAssertNil(TradingMath.annualized(premium: 10, expiration: "20000101"))
    }
    func testDemoRolloverCreatesIndependentExactLegs() async {
        let store = WheelStore()
        await store.refresh()
        let result = await store.trading.write("api/options/rollover", body: ["current_con_id": 1, "new_strike": 8.0, "new_expiration": "20261120", "quantity": 1, "current_limit_price": 0.19, "new_limit_price": 0.27], store: store)
        XCTAssertTrue(result)
        let pair = Array(store.orders.suffix(2))
        XCTAssertEqual(pair.map(\.action), ["BUY", "SELL"])
        XCTAssertEqual(pair.map(\.intent), ["CLOSE", "OPEN"])
        XCTAssertEqual(pair.map(\.tif), ["GTC", "DAY"])
        XCTAssertEqual(pair.map(\.strike), [9, 8])
    }
    func testPriceValidation() {
        for text in ["", "-1", "0", "NaN", "1.001", "1x", "1e3"] { XCTAssertNil(TradeRules.price(text)) }
        XCTAssertEqual(TradeRules.price("0.01"), 0.01)
    }
    func testDollarFormattingAndDemoBalances() async {
        XCTAssertEqual(money(1234.5), "$1,234.50")
        XCTAssertEqual(money(-12.3), "-$12.30")
        XCTAssertEqual(money(.nan), "—")
        let store = WheelStore()
        await store.refreshPortfolio()
        let portfolio = store.portfolio!
        XCTAssertEqual(portfolio.summary.account_value, portfolio.summary.cash_balance + portfolio.positions.reduce(0) { $0 + ($1.market_value ?? 0) }, accuracy: 0.01)
        XCTAssertTrue(portfolio.positions.allSatisfy { $0.avg_cost != nil })
    }
    func testBackgroundOpportunityDefaultsAndEditsSurviveRefresh() async {
        let store = WheelStore()
        await store.refreshPortfolio()
        let book = store.opportunities
        book.preferences = [:]
        await book.load("TSLL", type: "CALL", store: store, background: true)
        XCTAssertEqual(book.rows["TSLL:CALL"]?.quantity, 3)
        book.rows["TSLL:CALL"]?.price = ""
        book.rows["TSLL:CALL"]?.manualPrice = true
        book.rows["TSLL:CALL"]?.quantity = 2
        book.rows["TSLL:CALL"]?.staged = true
        await book.load("TSLL", type: "CALL", store: store, background: true)
        XCTAssertEqual(book.rows["TSLL:CALL"]?.quantity, 2)
        XCTAssertEqual(book.rows["TSLL:CALL"]?.price, "")
        XCTAssertEqual(book.rows["TSLL:CALL"]?.staged, true)
        XCTAssertFalse(book.rows["TSLL:CALL"]!.canStage)
    }
    func testOpportunityMissingQuoteDoesNotReuseOldQuoteAsFresh() async {
        let store = WheelStore()
        await store.refreshPortfolio()
        let book = store.opportunities
        await book.load("TSLL", type: "CALL", store: store)
        let previous = book.rows["TSLL:CALL"]!
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [MockProtocol.self]
        store.trading = TradingSession(session: URLSession(configuration: config))
        store.demo = false; store.address = "https://mock.invalid"
        MockProtocol.fail = false
        MockProtocol.payload = { _ in ["data": ["TSLL": ["calls": []]]] }
        defer { MockProtocol.payload = nil }
        await book.load("TSLL", type: "CALL", store: store, background: true)
        XCTAssertNotNil(book.rows["TSLL:CALL"]?.error)
        XCTAssertEqual(book.rows["TSLL:CALL"]?.updated, previous.updated)
        XCTAssertEqual(book.rows["TSLL:CALL"]?.quote?.id, previous.quote?.id)
        XCTAssertFalse(book.rows["TSLL:CALL"]!.canStage)
        XCTAssertFalse(book.rows["TSLL:CALL"]!.loading)
    }
    func testStaleOpportunityCannotStage() {
        var row = OpportunityRow(ticker: "TEST", type: "PUT")
        row.quote = ContractQuote(strike: 10, expiration: "20261016", bid: 0.2, ask: 0.3)
        row.price = "0.25"; row.updated = Date(timeIntervalSinceNow: -60)
        XCTAssertFalse(row.canStage)
        row.updated = Date(); row.loading = true
        XCTAssertTrue(row.canStage)
        row.error = "Offline"
        XCTAssertFalse(row.canStage)
    }
    func testDemoCloseUsesExactLongContract() async {
        let store = WheelStore()
        await store.refreshPortfolio()
        store.portfolio?.positions.append(Position(symbol: "TEST", position: 2, security_type: "OPT", strike: 20, expiration: "20261120", option_type: "CALL", con_id: 42))
        let result = await store.trading.write("api/options/close-order", body: ["con_id": 42, "quantity": 1, "limit_price": 0.5], store: store)
        XCTAssertTrue(result)
        let order = store.orders.last!
        XCTAssertEqual(order.ticker, "TEST"); XCTAssertEqual(order.action, "SELL")
        XCTAssertEqual(order.strike, 20); XCTAssertEqual(order.option_type, "CALL")
        XCTAssertEqual(order.expiration, "20261120")
    }
    func testExternalOrderDecodingAndPermissions() throws {
        let order = try JSONDecoder().decode(Order.self, from: Data(#"{"id":"ib-123","ticker":"TEST","status":"processing","external_ib":true}"#.utf8))
        XCTAssertNil(order.id.local)
        XCTAssertFalse(TradeRules.editable(order))
        XCTAssertFalse(TradeRules.cancelable(order))
    }
    func testUnknownOrderCannotExecuteOrCancel() {
        let order = Order(id: 3, status: "unknown")
        XCTAssertFalse(TradeRules.editable(order))
        XCTAssertFalse(TradeRules.cancelable(order))
    }
    func testDemoOrderLifecycleWithoutNetwork() async {
        let store = WheelStore()
        let client = store.trading
        let staged = await client.write("api/options/order", body: ["ticker": "TEST", "quantity": 2, "premium": 0.20], store: store)
        XCTAssertTrue(staged)
        let id = client.demoOrders.last!.id.local!
        let changed = await client.write("api/options/order/\(id)/premium", method: "PUT", body: ["premium": 0.25], store: store)
        XCTAssertTrue(changed)
        XCTAssertEqual(client.demoOrders.last?.premium, 0.25)
        let executed = await client.write("api/options/execute/\(id)", store: store)
        XCTAssertTrue(executed)
        XCTAssertEqual(client.demoOrders.last?.status, "processing")
        let canceled = await client.write("api/options/cancel/\(id)", store: store)
        XCTAssertTrue(canceled)
        XCTAssertFalse(client.demoOrders.contains { $0.id.local == id })
    }
    func testWriteHeaderAndTimeoutLocksWithoutRetry() async {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [MockProtocol.self]
        let client = TradingSession(session: URLSession(configuration: config))
        client.acknowledgeReview()
        let store = WheelStore()
        store.demo = false
        store.address = "https://mock.invalid"
        MockProtocol.requests = []; MockProtocol.fail = false
        let success = await client.write("api/options/execute/3", store: store)
        XCTAssertTrue(success)
        XCTAssertEqual(MockProtocol.requests.count, 1)
        XCTAssertEqual(MockProtocol.requests.first?.value(forHTTPHeaderField: "X-All-You-Need-Is-Wheel"), "1")
        MockProtocol.fail = true
        let failed = await client.write("api/options/execute/4", store: store)
        XCTAssertFalse(failed)
        XCTAssertTrue(client.uncertain)
        let blocked = await client.write("api/options/execute/4", store: store)
        XCTAssertFalse(blocked)
        XCTAssertEqual(MockProtocol.requests.count, 2)
        client.acknowledgeReview()
    }
}
