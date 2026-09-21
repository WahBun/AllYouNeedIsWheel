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
    func testHistoryRequiresActualFillNotExecutedFlag() throws {
        for status in ["canceled", "cancelled", "rejected", "pending", "processing"] {
            let order = try JSONDecoder().decode(Order.self, from: Data("{\"id\":1,\"status\":\"\(status)\",\"executed\":1,\"filled\":0}".utf8))
            XCTAssertFalse(order.hasFill)
        }
        XCTAssertTrue(Order(id: 1, status: "executed").hasFill)
        XCTAssertTrue(Order(id: 1, status: "processing", ib_status: "Filled").hasFill)
        XCTAssertTrue(Order(id: 1, status: "canceled", filled: 1).hasFill)
    }

    func testStagingPreservesOrderLimitAndRestoresMarketPrice() async {
        let store = WheelStore()
        await store.refreshPortfolio()
        let book = store.opportunities
        await book.load("TSLL", type: "PUT", store: store)
        book.rows["TSLL:PUT"]?.price = "0.83"
        book.rows["TSLL:PUT"]?.manualPrice = true
        let staged = await book.stage(book.rows["TSLL:PUT"]!, store: store)
        XCTAssertTrue(staged)
        XCTAssertEqual(store.orders.last!.premium!, 0.83, accuracy: 0.000001)
        XCTAssertFalse(book.rows["TSLL:PUT"]!.manualPrice)
        XCTAssertTrue(book.rows["TSLL:PUT"]!.staged)
        XCTAssertFalse(book.rows["TSLL:PUT"]!.canStage)
        var row = book.rows["TSLL:PUT"]!
        row.quote?.bid = 0.70; row.quote?.ask = 0.74
        row.followMarketPrice()
        XCTAssertEqual(row.price, "0.72")
        XCTAssertEqual(store.orders.last!.premium!, 0.83, accuracy: 0.000001)
        row.quote?.bid = nil
        row.followMarketPrice()
        XCTAssertEqual(row.price, "")
        XCTAssertNil(row.total)
    }

    func testBrokerIDsDecodeDatabaseStringsAndLiveNumbers() throws {
        for ids in [#""ib_order_id":"123","perm_id":"456""#, #""ib_order_id":123,"perm_id":456"#] {
            let data = Data("{\"id\":1,\"status\":\"processing\",\"executed\":0,\(ids)}".utf8)
            let order = try JSONDecoder().decode(Order.self, from: data)
            XCTAssertEqual(order.ib_order_id, 123)
            XCTAssertEqual(order.perm_id, 456)
            XCTAssertFalse(TradeRules.editable(order))
        }
        let absent = try JSONDecoder().decode(Order.self, from: Data(#"{"id":1,"status":"pending","perm_id":null}"#.utf8))
        XCTAssertNil(absent.ib_order_id)
        XCTAssertNil(absent.perm_id)
        XCTAssertThrowsError(try JSONDecoder().decode(Order.self, from: Data(#"{"id":1,"status":"processing","ib_order_id":"invalid"}"#.utf8)))
    }

    func testExecuteAcknowledgementSurvivesFailedOrderRefresh() async {
        let saved = UserDefaults.standard.object(forKey: "unresolvedTradingWrite")
        defer {
            MockProtocol.payload = nil; MockProtocol.fail = false
            UserDefaults.standard.set(saved, forKey: "unresolvedTradingWrite")
        }
        let store = WheelStore()
        store.demo = false; store.address = "https://mock.invalid"
        store.orders = [Order(id: 42, ticker: "TEST", premium: 0.83, quantity: 1, status: "pending")]
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [MockProtocol.self]
        store.trading = TradingSession(session: URLSession(configuration: config))
        store.trading.uncertain = false
        MockProtocol.fail = false
        MockProtocol.payload = { _ in ["success": true, "status": "processing", "execution_details": ["ib_status": "Submitted"]] }
        let success = await store.trading.write("api/options/execute/42", store: store)
        XCTAssertTrue(success)
        XCTAssertEqual(store.orders.first?.status, "processing")
        XCTAssertEqual(store.orders.first?.ib_status, "Submitted")
        MockProtocol.fail = true
        await store.refreshOrders()
        XCTAssertNotNil(store.orderError)
        XCTAssertEqual(store.orders.first?.status, "processing")
        XCTAssertFalse(TradeRules.editable(store.orders[0]))
        let repeated = await store.trading.executeWithPrice(store.orders[0], price: "0.83", store: store)
        XCTAssertFalse(repeated)
    }

    func testPriceChoicesUsePositiveCentSteps() {
        let prices = TradeRules.priceChoices(around: 4.88)
        XCTAssertEqual(prices.count, 41)
        XCTAssertEqual(prices.first, 4.68)
        XCTAssertEqual(prices.last, 5.08)
        XCTAssertTrue(prices.contains(4.88))
        XCTAssertEqual(TradeRules.priceChoices(around: 0.01).first, 0.01)
        XCTAssertTrue(TradeRules.priceChoices(around: .nan).isEmpty)
    }

    func testConfirmedCancellationReleasesOnlyMatchingEntry() async {
        let store = WheelStore()
        await store.refreshPortfolio()
        await store.opportunities.load("TSLL", type: "PUT", store: store)
        let book = store.opportunities
        let quote = book.rows["TSLL:PUT"]!.quote!
        let order = Order(id: 42, ticker: "TSLL", action: "SELL", option_type: "PUT", strike: quote.strike,
                          expiration: quote.expiration, premium: 0.4, quantity: 1, status: "pending")
        book.rows["TSLL:PUT"]?.staged = true
        var duplicate = order; duplicate.id = 43
        book.confirmCancellation(order, remaining: [duplicate])
        XCTAssertTrue(book.rows["TSLL:PUT"]!.staged)
        book.confirmCancellation(order, remaining: [])
        XCTAssertFalse(book.rows["TSLL:PUT"]!.staged)
        book.rows["TSLL:PUT"]?.staged = true
        var close = order; close.intent = "CLOSE"
        book.confirmCancellation(close, remaining: [])
        XCTAssertTrue(book.rows["TSLL:PUT"]!.staged)
    }

    func testPendingCancelDoesNotReleaseStagedEntryButConfirmedCancelDoes() async {
        let saved = UserDefaults.standard.object(forKey: "unresolvedTradingWrite")
        defer {
            MockProtocol.payload = nil
            UserDefaults.standard.set(saved, forKey: "unresolvedTradingWrite")
        }
        let store = WheelStore()
        await store.refreshPortfolio()
        await store.opportunities.load("TSLL", type: "PUT", store: store)
        let quote = store.opportunities.rows["TSLL:PUT"]!.quote!
        store.orders = [Order(id: 42, ticker: "TSLL", action: "SELL", option_type: "PUT",
            strike: quote.strike, expiration: quote.expiration, status: "processing")]
        store.opportunities.rows["TSLL:PUT"]?.staged = true
        store.demo = false; store.address = "https://mock.invalid"
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [MockProtocol.self]
        store.trading = TradingSession(session: URLSession(configuration: config))
        store.trading.uncertain = false
        MockProtocol.fail = false
        MockProtocol.payload = { _ in ["success": true, "status": "canceling"] }
        _ = await store.trading.write("api/options/cancel/42", store: store)
        XCTAssertTrue(store.opportunities.rows["TSLL:PUT"]!.staged)
        XCTAssertEqual(store.orders.count, 1)
        MockProtocol.payload = { _ in ["success": true, "status": "canceled"] }
        _ = await store.trading.write("api/options/cancel/42", store: store)
        XCTAssertFalse(store.opportunities.rows["TSLL:PUT"]!.staged)
        XCTAssertTrue(store.orders.isEmpty)
    }

    func testQuoteMetricColorBoundariesAndInvalidValues() {
        for sign in [-1.0, 1.0] {
            XCTAssertEqual(QuoteMetric.delta.level(sign * 0.30), .low)
            XCTAssertEqual(QuoteMetric.delta.level(sign * 0.31), .medium)
            XCTAssertEqual(QuoteMetric.delta.level(sign * 0.50), .medium)
            XCTAssertEqual(QuoteMetric.delta.level(sign * 0.51), .high)
            XCTAssertEqual(QuoteMetric.delta.level(sign * 1.01), .unavailable)
        }
        XCTAssertEqual(QuoteMetric.delta.formatted(-0.24), "-0.24")
        XCTAssertEqual(QuoteMetric.delta.level(0), .low)
        XCTAssertEqual(QuoteMetric.iv.level(50), .low)
        XCTAssertEqual(QuoteMetric.iv.level(50.1), .medium)
        XCTAssertEqual(QuoteMetric.iv.level(70), .medium)
        XCTAssertEqual(QuoteMetric.iv.level(70.1), .high)
        XCTAssertEqual(QuoteMetric.iv.formatted(74.8), "74.8%")
        for value: Double? in [nil, .nan, .infinity] {
            XCTAssertEqual(QuoteMetric.delta.level(value), .unavailable)
            XCTAssertEqual(QuoteMetric.iv.level(value), .unavailable)
        }
        XCTAssertEqual(QuoteMetric.iv.level(0), .unavailable)
        XCTAssertEqual(QuoteMetric.iv.level(-1), .unavailable)
    }

    func testOrdersDecodeSQLiteAndBrokerBooleanFlagsTogether() throws {
        let payload = Data(#"{"orders":[{"id":42,"ticker":"CRCL","action":"SELL","option_type":"PUT","strike":90,"expiration":"20261016","premium":4.9,"quantity":1,"status":"pending","executed":0,"isRollover":0,"ib_order_id":null},{"id":"ib-123","ticker":"TEST","status":"processing","external_ib":true,"executed":false,"isRollover":false},{"id":43,"status":"filled","executed":1,"isRollover":1},{"id":44,"status":"pending","executed":null}]}"#.utf8)
        let orders = try JSONDecoder().decode(Orders.self, from: payload).orders
        XCTAssertEqual(orders.count, 4)
        XCTAssertEqual(orders[0].executed, false)
        XCTAssertEqual(orders[0].isRollover, false)
        XCTAssertEqual(orders[0].premium, 4.9)
        XCTAssertTrue(TradeRules.editable(orders[0]))
        XCTAssertEqual(orders[1].external_ib, true)
        XCTAssertFalse(TradeRules.editable(orders[1]))
        XCTAssertEqual(orders[2].executed, true)
        XCTAssertEqual(orders[2].isRollover, true)
        XCTAssertNil(orders[3].executed)
        XCTAssertNil(orders[3].isRollover)
        for invalid in ["2", "-1", "\"false\""] {
            let data = Data("{\"id\":42,\"status\":\"pending\",\"executed\":\(invalid)}".utf8)
            XCTAssertThrowsError(try JSONDecoder().decode(Order.self, from: data))
        }
    }

    func testOrderRefreshAcceptsDatabaseFlagsWithoutAnyTradingWrite() async {
        let store = WheelStore()
        store.demo = false; store.address = "https://mock.invalid"
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [MockProtocol.self]
        store.trading = TradingSession(session: URLSession(configuration: config))
        MockProtocol.fail = false; MockProtocol.requests = []
        MockProtocol.payload = { _ in ["success": true, "orders": [[
            "id": 42, "ticker": "CRCL", "status": "pending", "executed": 0, "isRollover": 0
        ]]] }
        defer { MockProtocol.payload = nil }
        await store.refreshOrders()
        XCTAssertNil(store.orderError)
        XCTAssertEqual(store.orders.first?.name, "CRCL")
        XCTAssertNotNil(store.ordersUpdated)
        XCTAssertEqual(MockProtocol.requests.map { $0.url!.path }, ["/api/options/check-orders"])
        MockProtocol.payload = { _ in ["success": true, "orders": [["id": 43, "status": "pending", "executed": 2]]] }
        await store.refreshOrders()
        XCTAssertNotNil(store.orderError)
        XCTAssertEqual(store.orders.first?.name, "CRCL")
    }

    func testRefreshPicksUpAddedSymbolAndKeepsUpdatingExistingRows() async {
        let store = WheelStore()
        store.demo = false; store.address = "https://mock.invalid"
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [MockProtocol.self]
        store.trading = TradingSession(session: URLSession(configuration: config))
        let book = store.opportunities
        book.custom = ["CRCL"]; book.excluded = []; book.removedPuts = []; book.preferences = [:]
        MockProtocol.requests = []; MockProtocol.fail = false
        MockProtocol.payload = { request in
            if request.url!.path.hasSuffix("expirations") {
                return ["expirations": [["value": "20261016", "is_default": true]]]
            }
            let symbol = URLComponents(url: request.url!, resolvingAgainstBaseURL: false)!.queryItems!.first { $0.name == "tickers" }!.value!
            return ["data": [symbol: ["stock_price": 100, "previous_close": 95,
                "puts": [["strike": 90, "expiration": "20261016", "bid": 1, "ask": 1.2]]]]]
        }
        defer { MockProtocol.payload = nil }
        await book.refreshAll(type: "PUT", store: store, background: true)
        let firstUpdate = book.rows["CRCL:PUT"]?.updated
        book.custom.append("TSLL")
        await book.refreshAll(type: "PUT", store: store, background: true)
        await book.refreshAll(type: "PUT", store: store, background: true)
        XCTAssertGreaterThan(book.rows["CRCL:PUT"]!.updated!, firstUpdate!)
        XCTAssertNotNil(book.rows["TSLL:PUT"]?.updated)
        XCTAssertEqual(book.rows["TSLL:PUT"]?.previousClose, 95)
        XCTAssertFalse(book.loading)
        XCTAssertFalse(book.rows["CRCL:PUT"]!.loading)
        XCTAssertFalse(book.rows["TSLL:PUT"]!.loading)
        XCTAssertEqual(MockProtocol.requests.filter { $0.url!.path.hasSuffix("otm") }.count, 5)
        MockProtocol.payload = { _ in ["data": [
            "CRCL": ["stock_price": 102, "previous_close": 95],
            "TSLL": ["stock_price": 99, "previous_close": 98]]]
        }
        let priceFailed = await book.refreshPrices(["CRCL", "TSLL"], type: "PUT", store: store)
        XCTAssertFalse(priceFailed)
        XCTAssertEqual(book.rows["CRCL:PUT"]?.priceDirection, 1)
        XCTAssertEqual(book.rows["TSLL:PUT"]?.priceDirection, -1)
        XCTAssertEqual(book.rows["CRCL:PUT"]?.stockUpdated, book.rows["TSLL:PUT"]?.stockUpdated)
        XCTAssertEqual(book.rows["TSLL:PUT"]?.previousClose, 98)
        MockProtocol.payload = { request in
            if request.url!.query!.contains("TSLL") { return ["error": "Quote unavailable"] }
            return ["data": ["CRCL": ["stock_price": 101, "previous_close": 95,
                "puts": [["strike": 90, "expiration": "20261016", "bid": 1, "ask": 1.2]]]]]
        }
        await book.refreshAll(type: "PUT", store: store, background: true)
        XCTAssertNotNil(book.rows["TSLL:PUT"]?.error)
        MockProtocol.requests = []
        await book.refreshAll(type: "PUT", store: store, background: true)
        XCTAssertEqual(MockProtocol.requests.count, 1)
        XCTAssertTrue(MockProtocol.requests[0].url!.query!.contains("CRCL"))
        XCTAssertEqual(book.rows["CRCL:PUT"]?.stockPrice, 102)
    }

    func testMarketSessionGateCachesClosedAndRecoversOnRecheck() async {
        let store = WheelStore()
        store.demo = false; store.address = "https://mock.invalid"
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [MockProtocol.self]
        store.trading = TradingSession(session: URLSession(configuration: config))
        MockProtocol.fail = false; MockProtocol.requests = []
        MockProtocol.payload = { _ in ["is_open": false, "server_time": 100.0, "next_transition": 1000.0] }
        defer { MockProtocol.payload = nil; MockProtocol.fail = false }
        let first = await store.opportunities.allowsAutomaticRefresh(store)
        let second = await store.opportunities.allowsAutomaticRefresh(store)
        XCTAssertFalse(first); XCTAssertFalse(second)
        XCTAssertEqual(MockProtocol.requests.count, 1)
        XCTAssertEqual(store.opportunities.marketOpen, false)
        store.opportunities.invalidateMarketSession()
        MockProtocol.payload = { _ in ["is_open": true, "server_time": 100.0, "next_transition": 200.0] }
        let opened = await store.opportunities.allowsAutomaticRefresh(store)
        XCTAssertTrue(opened)
        store.opportunities.invalidateMarketSession()
        MockProtocol.fail = true
        let unavailable = await store.opportunities.allowsAutomaticRefresh(store)
        XCTAssertFalse(unavailable)
        XCTAssertNil(store.opportunities.marketOpen)
        store.demo = true
        let demo = await store.opportunities.allowsAutomaticRefresh(store)
        XCTAssertTrue(demo)
    }
    func testStrikeMenuPrioritizesMultiplesOfFiveWithoutDroppingOtherContracts() {
        XCTAssertEqual(TradingMath.orderedStrikes([77.5, 81, 80, 75, 80, .nan, -1]), [75, 77.5, 80, 81])
        XCTAssertEqual(TradingMath.orderedStrikes([10, 9, 11, 5, 8]), [5, 8, 9, 10, 11])
    }
    func testExecuteSavesEditedPriceFirstAndStopsOnSaveFailure() async {
        let savedLock = UserDefaults.standard.object(forKey: "unresolvedTradingWrite")
        defer {
            UserDefaults.standard.set(savedLock, forKey: "unresolvedTradingWrite")
            MockProtocol.payload = nil; MockProtocol.fail = false
        }
        let store = WheelStore()
        store.demo = false; store.address = "https://mock.invalid"
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [MockProtocol.self]
        store.trading = TradingSession(session: URLSession(configuration: config))
        store.trading.uncertain = false
        let order = Order(id: 42, ticker: "TEST", action: "SELL", option_type: "PUT", strike: 10, expiration: "20261016", premium: 0.2, quantity: 1, status: "pending")
        store.orders = [order]
        MockProtocol.requests = []; MockProtocol.fail = false
        MockProtocol.payload = { _ in ["success": true] }
        let success = await store.trading.executeWithPrice(order, price: "0.21", store: store)
        XCTAssertTrue(success)
        XCTAssertEqual(MockProtocol.requests.map { $0.url!.path }, ["/api/options/order/42/premium", "/api/options/execute/42"])
        XCTAssertEqual(MockProtocol.requests.map { $0.httpMethod! }, ["PUT", "POST"])
        // Start a separate draft for the save-failure scenario; the acknowledged
        // order above is intentionally no longer executable.
        store.orders = [order]
        MockProtocol.requests = []; MockProtocol.fail = true
        let failed = await store.trading.executeWithPrice(order, price: "0.22", store: store)
        XCTAssertFalse(failed)
        XCTAssertEqual(MockProtocol.requests.count, 1)
        XCTAssertTrue(store.trading.uncertain)
    }
    func testManualStrikeSelectionDoesNotAcceptNearbyQuote() async {
        let store = WheelStore()
        await store.refreshPortfolio()
        let book = store.opportunities
        book.preferences = [:]
        await book.load("TSLL", type: "PUT", store: store)
        book.preferences["TSLL:PUT"]?.strike = 8
        await book.load("TSLL", type: "PUT", store: store, background: true)
        XCTAssertEqual(book.rows["TSLL:PUT"]?.quote?.strike, 8)
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [MockProtocol.self]
        store.trading = TradingSession(session: URLSession(configuration: config))
        store.demo = false; store.address = "https://mock.invalid"
        MockProtocol.fail = false
        MockProtocol.payload = { request in
            XCTAssertTrue(request.url!.query!.contains("strike=8"))
            return ["data": ["TSLL": ["stock_price": 10, "puts": [["strike": 9, "expiration": "20261016", "bid": 0.2, "ask": 0.3]]]]]
        }
        defer { MockProtocol.payload = nil }
        await book.load("TSLL", type: "PUT", store: store, background: true)
        XCTAssertNotNil(book.rows["TSLL:PUT"]?.error)
        XCTAssertFalse(book.rows["TSLL:PUT"]!.canStage)
    }
    func testTradeRefreshPriorityPreservesInitialPortfolioLoad() {
        XCTAssertTrue(RefreshLoop.shouldRefreshPortfolio(tab: "trade", hasPortfolio: false))
        XCTAssertFalse(RefreshLoop.shouldRefreshPortfolio(tab: "trade", hasPortfolio: true))
        XCTAssertFalse(RefreshLoop.shouldRefreshPortfolio(tab: "trade", hasPortfolio: true, age: 10))
        XCTAssertFalse(RefreshLoop.shouldRefreshPortfolio(tab: "trade", hasPortfolio: true, age: 59.9))
        XCTAssertTrue(RefreshLoop.shouldRefreshPortfolio(tab: "trade", hasPortfolio: true, age: 60))
        XCTAssertFalse(RefreshLoop.shouldRefreshPortfolio(tab: "trade", hasPortfolio: true, age: 60, quotesLoading: true))
        XCTAssertTrue(RefreshLoop.shouldRefreshPortfolio(tab: "portfolio", hasPortfolio: true))
        XCTAssertTrue(RefreshLoop.shouldRefreshPortfolio(tab: "orders", hasPortfolio: true))
    }
    func testDailyChangeUsesPreviousCloseAndRejectsMissingBaseline() {
        XCTAssertEqual(TradingMath.dailyChange(price: 102, close: 100)!, 2, accuracy: 0.0001)
        XCTAssertEqual(TradingMath.dailyChange(price: 98, close: 100)!, -2, accuracy: 0.0001)
        XCTAssertEqual(TradingMath.dailyChange(price: 100, close: 100), 0)
        XCTAssertNil(TradingMath.dailyChange(price: 100, close: nil))
        XCTAssertNil(TradingMath.dailyChange(price: 100, close: 0))
        XCTAssertNil(TradingMath.dailyChange(price: .nan, close: 100))
    }
    func testQuoteDirectionComparesConsecutiveValidPrices() {
        XCTAssertEqual(TradingMath.priceDirection(previous: 10, current: 10.01), 1)
        XCTAssertEqual(TradingMath.priceDirection(previous: 10, current: 9.99), -1)
        XCTAssertEqual(TradingMath.priceDirection(previous: 10, current: 10), 0)
        XCTAssertEqual(TradingMath.priceDirection(previous: nil, current: 10), 0)
        XCTAssertEqual(TradingMath.priceDirection(previous: 10, current: .nan), 0)
        XCTAssertEqual(TradingMath.priceDirection(previous: 10, current: -1), 0)
    }
    func testRemovePutDoesNotHideCallOrReturnThroughRestore() async throws {
        let store = WheelStore()
        await store.refreshPortfolio()
        let book = OpportunityBook()
        let context = "test-" + UUID().uuidString
        defer { UserDefaults.standard.removeObject(forKey: "opportunities-v1-" + context) }
        book.configure(context: context)
        book.custom = ["TEST"]
        book.excluded = ["TSLL:PUT"]
        book.removePut("TSLL")
        book.removePut("TEST")
        book.restoreHidden(type: "PUT")
        XCTAssertFalse(book.symbols(store, type: "PUT").contains("TSLL"))
        XCTAssertFalse(book.custom.contains("TEST"))
        XCTAssertTrue(book.symbols(store, type: "CALL").contains("TSLL"))
        XCTAssertFalse(book.hasHidden(type: "PUT"))
        book.configure(context: context)
        XCTAssertTrue(book.removedPuts.contains("TSLL"))
        XCTAssertTrue(book.removedPuts.contains("TEST"))
        let old = Data(#"{"preferences":{},"custom":["TEST"],"excluded":[]}"#.utf8)
        let decoded = try JSONDecoder().decode(OpportunityBook.Saved.self, from: old)
        XCTAssertNil(decoded.removedPuts)
    }
    func testMarginTimestampUsesCompactLocalTime() {
        let zone = TimeZone(secondsFromGMT: 8 * 3600)!
        XCTAssertEqual(MarginImpact.displayTime("2026-09-21T02:22:26.044748+00:00", timeZone: zone), "09-21 10:22:26")
        XCTAssertEqual(MarginImpact.displayTime("2026-09-21T02:22:26Z", timeZone: zone), "09-21 10:22:26")
        XCTAssertEqual(MarginImpact.displayTime("2026-09-20T20:22:26Z", timeZone: zone), "09-21 04:22:26")
        XCTAssertEqual(MarginImpact.displayTime("invalid", timeZone: zone), "—")
    }

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
        XCTAssertEqual(RefreshLoop.delay(elapsed: 1, failed: true), 10)
        XCTAssertEqual(RefreshLoop.delay(elapsed: 30, failed: true), 10)
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
        XCTAssertEqual(book.rows["TSLL:CALL"]?.price, book.rows["TSLL:CALL"]?.quote?.mid.map { String(format: "%.2f", $0) })
        XCTAssertFalse(book.rows["TSLL:CALL"]!.manualPrice)
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
    func testOpportunityAutoRefreshFollowsMidUntilPriceIsEdited() async {
        let store = WheelStore()
        await store.refreshPortfolio()
        let book = store.opportunities
        book.preferences = [:]
        await book.load("TSLL", type: "PUT", store: store)
        let quote = book.rows["TSLL:PUT"]!.quote!
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [MockProtocol.self]
        store.trading = TradingSession(session: URLSession(configuration: config))
        store.demo = false; store.address = "https://mock.invalid"
        MockProtocol.fail = false
        MockProtocol.payload = { _ in ["data": ["TSLL": ["stock_price": 10.25, "puts": [[
            "strike": quote.strike, "expiration": quote.expiration, "bid": 0.4, "ask": 0.6
        ]]]]] }
        defer { MockProtocol.payload = nil }
        await book.load("TSLL", type: "PUT", store: store, background: true)
        XCTAssertEqual(book.rows["TSLL:PUT"]?.price, "0.50")
        book.rows["TSLL:PUT"]?.price = "0.48"
        book.rows["TSLL:PUT"]?.manualPrice = true
        book.rows["TSLL:PUT"]?.quantity = 2
        await book.load("TSLL", type: "PUT", store: store, background: true)
        XCTAssertEqual(book.rows["TSLL:PUT"]?.price, "0.48")
        XCTAssertEqual(book.rows["TSLL:PUT"]?.quantity, 2)
        XCTAssertEqual(book.rows["TSLL:PUT"]?.quote?.mid, 0.5)
        XCTAssertNil(book.rows["TSLL:PUT"]?.error)
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
