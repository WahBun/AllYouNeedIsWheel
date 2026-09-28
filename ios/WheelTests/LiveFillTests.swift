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
}
