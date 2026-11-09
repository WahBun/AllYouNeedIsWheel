import XCTest
@testable import Wheel

@MainActor
final class RealizedProfitTests: XCTestCase {
    func testBrokerProfitLossZeroAndUnavailable() throws {
        var order = try JSONDecoder().decode(Order.self, from: Data(#"{"id":1,"status":"executed","intent":"CLOSE","filled":2,"commission_currency":"USD","realized_pnl":24.8}"#.utf8))
        XCTAssertEqual(order.realizedProfitLabel, "+$24.80")
        order.realized_pnl = -12.3
        XCTAssertEqual(order.realizedProfitLabel, "-$12.30")
        order.realized_pnl = 0
        XCTAssertEqual(order.realizedProfitLabel, "$0.00")
        order.realized_pnl = nil
        XCTAssertEqual(order.realizedProfitLabel, "—")
        order.realized_pnl = 5; order.commission_currency = "EUR"
        XCTAssertNil(order.realizedProfit)
        order.commission_currency = "USD"; order.intent = "OPEN"
        XCTAssertNil(order.realizedProfit)
    }
    func testDailyClosedNetUsesNewYorkDayAndExcludesOpenGrossAndDuplicates() throws {
        let payload = """
        [{"id":1,"status":"filled","intent":"CLOSE","filled":1,"fill_time":"2026-10-02T12:36:14Z","net_pnl":8.78},
         {"id":2,"status":"filled","intent":"CLOSE","filled":1,"fill_time":"2026-10-02T13:00:00Z","net_pnl":-2.5},
         {"id":3,"status":"filled","intent":"OPEN","filled":1,"fill_time":"2026-10-02T13:00:00Z","net_pnl":100},
         {"id":4,"status":"filled","intent":"CLOSE","filled":1,"fill_time":"2026-10-02T03:59:59Z","net_pnl":200},
         {"id":5,"status":"filled","intent":"CLOSE","filled":1,"fill_time":"2026-10-02T14:00:00Z","gross_pnl":10}]
        """
        let orders = try JSONDecoder().decode([Order].self, from: Data(payload.utf8))
        let now = ISO8601DateFormatter().date(from: "2026-10-02T15:00:00Z")!
        let total = DailyClosedProfit.calculate(orders + [orders[0]], now: now)
        XCTAssertEqual(total.amount, 6.28, accuracy: 0.00001)
        XCTAssertEqual(total.pending, 1)
        XCTAssertEqual(orders[3].fillDayLabel, "Oct 1, 2026")
        XCTAssertEqual(orders[0].fillClockLabel, "08:36:14")
        XCTAssertEqual(DailyClosedProfit.calculate([], now: now).amount, 0)
    }

    func testSevenDaysAndMonthUseHistoryBoundaries() throws {
        let now = ISO8601DateFormatter().date(from: "2026-10-08T15:00:00Z")!
        let dates = ["2026-10-01T16:00:00Z", "2026-10-02T03:59:59Z", "2026-10-02T04:00:00Z", "2026-10-08T16:00:00Z", "2026-10-09T04:00:00Z"]
        let orders = try dates.enumerated().map { index, date in
            try JSONDecoder().decode(Order.self, from: Data("{\"id\":\(index),\"status\":\"filled\",\"intent\":\"CLOSE\",\"filled\":1,\"fill_time\":\"\(date)\",\"net_pnl\":10}".utf8))
        }
        XCTAssertEqual(DailyClosedProfit.calculate(orders, days: 1, now: now).amount, 10)
        XCTAssertEqual(DailyClosedProfit.calculate(orders + [orders[2]], days: 7, now: now).amount, 20)
        XCTAssertEqual(DailyClosedProfit.calculate(orders, days: 0, now: now).amount, 40)
        XCTAssertEqual(DailyClosedProfit.calculate(orders, days: 30, now: now).amount, 40)
    }

    func testLatePnlUpdatesSameBannerWithoutNewNotification() {
        let preview = FillPreview()
        var order = Order(id: 1, quantity: 2, status: "executed", intent: "CLOSE", filled: 2)
        preview.enqueue([FillNotice(order: order)])
        let id = preview.notice!.id
        order.realized_pnl = 12.3; order.commission_currency = "USD"
        preview.updateMetadata([order])
        XCTAssertEqual(preview.notice?.id, id)
        XCTAssertEqual(preview.notice?.order.realizedProfitLabel, "+$12.30")
        preview.dismiss(id)
        XCTAssertNil(preview.notice)
    }
}
