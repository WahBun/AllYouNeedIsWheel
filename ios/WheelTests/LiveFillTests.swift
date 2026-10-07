import XCTest
@testable import Wheel

@MainActor
final class LiveFillTests: XCTestCase {
    func order(_ id: Int = 1, _ filled: Double = 0) -> Order {
        Order(id: OrderID(id), ticker: "TEST", action: "SELL", option_type: "PUT", strike: 10,
              quantity: 2, status: filled >= 2 ? "executed" : "processing", filled: filled, avg_fill_price: 0.48)
    }
    func testBaselineAndMonotonicPartialThenComplete() {
        var tracker = FillTracker()
        XCTAssertTrue(tracker.ingest([order(1), order(2, 2)]).isEmpty)
        let partial = tracker.ingest([order(1, 1), order(2, 2)])
        XCTAssertEqual(partial.count, 1)
        XCTAssertFalse(partial[0].complete)
        XCTAssertEqual(partial[0].quantityLabel, "1/2")
        XCTAssertTrue(tracker.ingest([order(1, 0)]).isEmpty)
        XCTAssertTrue(tracker.ingest([order(1, 1)]).isEmpty)
        let full = tracker.ingest([order(1, 2)])
        XCTAssertEqual(full.count, 1)
        XCTAssertTrue(full[0].complete)
        var fees = order(1, 2); fees.commission = 0.8
        XCTAssertTrue(tracker.ingest([fees]).isEmpty)
    }
    func testDisappearanceAndOldUnseenHistoryAreNotFills() {
        var tracker = FillTracker()
        _ = tracker.ingest([order()])
        XCTAssertTrue(tracker.ingest([]).isEmpty)
        XCTAssertTrue(tracker.ingest([order(5, 2)]).isEmpty)
        XCTAssertEqual(tracker.ingest([order(1, 2)]).count, 1)
    }
    func testBrokerAndLocalAliasesDoNotDuplicate() {
        var tracker = FillTracker()
        var local = order(); local.perm_id = 99
        _ = tracker.ingest([local])
        var broker = order(2, 1); broker.perm_id = 99
        local.filled = 1
        XCTAssertEqual(tracker.ingest([broker, local]).count, 1)
        XCTAssertTrue(tracker.ingest([local, broker]).isEmpty)
    }
    func testFastFillBetweenPollsRequiresRecentBrokerTimestamp() {
        var tracker = FillTracker(started: ISO8601DateFormatter().date(from: "2026-09-28T14:00:00Z")!)
        _ = tracker.ingest([])
        var fresh = order(9, 2); fresh.fill_time = "2026-09-28T14:01:00.123Z"
        XCTAssertEqual(tracker.ingest([fresh]).count, 1)
        XCTAssertTrue(tracker.ingest([fresh]).isEmpty)
        var old = order(10, 2); old.fill_time = "2026-09-27T14:01:00Z"
        XCTAssertTrue(tracker.ingest([old]).isEmpty)
    }
    func testQueueAndStaleDismissalAndModeClear() {
        let preview = FillPreview()
        preview.enqueue([FillNotice(order: order(1, 1)), FillNotice(order: order(2, 2))])
        let first = preview.notice!
        preview.detail = first
        preview.dismiss(first.id)
        XCTAssertNil(preview.notice)
        preview.detail = nil; preview.advance()
        XCTAssertEqual(preview.notice?.order.id, OrderID(2))
        preview.dismiss(first.id)
        XCTAssertEqual(preview.notice?.order.id, OrderID(2))
        preview.clear()
        XCTAssertNil(preview.notice)
        preview.advance()
        XCTAssertNil(preview.notice)
    }
    func testStoreFetchesHistoryWhenPendingOrderDisappearsAcrossTabs() async {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [MockProtocol.self]
        MockProtocol.requests = []; MockProtocol.fail = false; MockProtocol.statusCode = 200
        var completed = false
        MockProtocol.payload = { request in
            let row: [String: Any] = ["id": 1, "ticker": "TEST", "status": completed ? "executed" : "processing",
                                      "quantity": 2, "filled": completed ? 2 : 0, "avg_fill_price": 0.48]
            if request.url?.lastPathComponent == "check-orders" {
                return ["success": true, "orders": completed ? [] : [row]]
            }
            return ["orders": completed ? [row] : []]
        }
        defer { MockProtocol.payload = nil; MockProtocol.requests = [] }
        let store = WheelStore()
        store.demo = false; store.address = "https://example.test"
        store.trading = TradingSession(session: URLSession(configuration: config))
        await store.refreshOrders()
        XCTAssertNil(store.fillPreview.notice)
        completed = true; store.selectedTab = "portfolio"
        await store.refreshOrders()
        XCTAssertEqual(store.fillPreview.notice?.filled, 2)
        let noticeID = store.fillPreview.notice?.id
        await store.refreshOrders()
        XCTAssertEqual(store.fillPreview.notice?.id, noticeID)
        XCTAssertEqual(MockProtocol.requests.filter { $0.url?.lastPathComponent == "pending-orders" }.count, 2)
        store.changeMode()
        XCTAssertNil(store.fillPreview.notice)
    }
    func testLargeExecutionHistoryKeepsCompleteCountAndBoundedPage() {
        let now = ISO8601DateFormatter().date(from: "2026-10-08T03:00:00Z")!
        let rows = (1...10000).map { id in
            var row = order(id, 2)
            row.fill_time = "2026-10-07T18:30:00.000Z"
            return row
        }
        let started = Date()
        let first = ExecutionHistoryPage.build(rows, days: 1, asset: "ALL", search: "", limit: 50, now: now)
        print("History 10000-row projection seconds: \(Date().timeIntervalSince(started))")
        XCTAssertEqual(first.total, 10000)
        XCTAssertEqual(first.orders.count, 50)
        XCTAssertEqual(first.headings.count, 1)
        let next = ExecutionHistoryPage.build(rows, days: 1, asset: "OPTION", search: "test", limit: 100, now: now)
        XCTAssertEqual(next.total, 10000)
        XCTAssertEqual(next.orders.prefix(50).map(\.id), first.orders.map(\.id))
        XCTAssertEqual(next.orders.count, 100)
        XCTAssertTrue(ExecutionHistoryPage.build(rows, days: 1, asset: "STOCK", search: "", limit: 50, now: now).orders.isEmpty)
    }
    func testExecutionHistoryNewYorkBoundaryAndDuplicateIdentity() {
        let now = ISO8601DateFormatter().date(from: "2026-10-08T03:00:00Z")!
        var today = order(1, 2); today.fill_time = "2026-10-08T02:59:59Z"
        var yesterday = order(2, 2); yesterday.fill_time = "2026-10-07T03:59:59Z"
        var invalid = order(3, 2); invalid.fill_time = "invalid"
        let page = ExecutionHistoryPage.build([today,today,yesterday,invalid], days: 1, asset: "ALL", search: "", limit: 50, now: now)
        XCTAssertEqual(page.total, 1)
        XCTAssertEqual(page.orders.map(\.id), [today.id])
        let week = ExecutionHistoryPage.build([today,yesterday], days: 7, asset: "ALL", search: "", limit: 50, now: now)
        XCTAssertEqual(week.total, 2)
        XCTAssertEqual(week.headings.count, 2)
    }

}
