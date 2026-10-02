import XCTest
@testable import Wheel

final class FillTimeTests: XCTestCase {
    func testMixedFillsSortNewestFirstWithStableTiesAndUnknownLast() throws {
        let payload = """
        [{"id":1,"status":"filled","fill_time":"2026-10-02T12:35:07Z"},
         {"id":2,"status":"filled","fill_time":"2026-10-02T20:36:14+08:00"},
         {"id":3,"status":"filled","fill_time":"2026-10-02T12:36:14.500Z"},
         {"id":4,"status":"filled","fill_time":"invalid"},
         {"id":5,"status":"filled","fill_time":"2026-10-02T12:36:14.500Z"}]
        """
        let orders = try JSONDecoder().decode([Order].self, from: Data(payload.utf8))
        XCTAssertEqual(Order.latestFillsFirst(orders).map { $0.id.local }, [5, 3, 2, 1, 4])
        XCTAssertEqual(Order.latestFillsFirst(orders.reversed()).map { $0.id.local }, [5, 3, 2, 1, 4])
    }
    func testEasternTimeUsesSeasonalOffsetAndNotDeviceZone() throws {
        for (stamp, expected) in [
            ("2026-09-28T14:06:16Z", "2026-09-28 10:06:16 EDT"),
            ("2026-09-28T22:06:16+08:00", "2026-09-28 10:06:16 EDT"),
            ("2026-01-15T15:06:16.123Z", "2026-01-15 10:06:16 EST"),
            ("2026-09-28T01:06:16Z", "2026-09-27 21:06:16 EDT")
        ] {
            let payload = "{\"id\":1,\"status\":\"executed\",\"fill_time\":\"\(stamp)\"}"
            let order = try JSONDecoder().decode(Order.self, from: Data(payload.utf8))
            XCTAssertEqual(order.fillTimeLabel, expected)
        }
    }
}
