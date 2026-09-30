import XCTest
@testable import Wheel
final class MetricPaletteTests: XCTestCase {
    func testThirtySeventyBands() {
        XCTAssertEqual(DemoMetricColors.band(30), 0)
        XCTAssertEqual(DemoMetricColors.band(30.01), 0.5)
        XCTAssertEqual(DemoMetricColors.band(70), 0.5)
        XCTAssertEqual(DemoMetricColors.band(70.01), 1)
        XCTAssertEqual(QuoteMetric.delta.level(-0.48), .medium)
        XCTAssertEqual(QuoteMetric.delta.level(-0.72), .high)
        XCTAssertEqual(QuoteMetric.iv.level(80), .high)
        XCTAssertEqual(SpreadBand.classify(9.2), .tight)
        XCTAssertEqual(SpreadBand.classify(50), .medium)
    }
}
