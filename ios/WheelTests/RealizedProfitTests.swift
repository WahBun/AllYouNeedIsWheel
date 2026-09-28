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
