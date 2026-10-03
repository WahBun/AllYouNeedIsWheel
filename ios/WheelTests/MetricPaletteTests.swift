import XCTest
import SwiftUI
@testable import Wheel
final class MetricPaletteTests: XCTestCase {
    func testSpreadUsesDedicatedBandsAndPreservesCustomColors() {
        let palette = CustomPalette(json: ##"{"spread.low.dark":"#123456","spread.medium.dark":"#654321","spread.high.dark":"#ABCDEF"}"##)
        for (value, key) in [(0.0,"low"),(10.0,"low"),(10.01,"medium"),(19.99,"medium"),(20.0,"high"),(50.0,"high")] {
            XCTAssertEqual(palette.metric("spread", value: value, scheme: .dark), palette.color("spread." + key, scheme: .dark, fallback: .clear))
        }
        for scheme: ColorScheme in [.light, .dark] {
            XCTAssertEqual(CustomPalette().metric("spread", value: 20, scheme: scheme), DemoMetricColors.color(1, scheme: scheme))
        }
    }
    func testThirtySeventyBands() {
        XCTAssertEqual(DemoMetricColors.band(30), 0)
        XCTAssertEqual(DemoMetricColors.band(30.01), 0.5)
        XCTAssertEqual(DemoMetricColors.band(70), 0.5)
        XCTAssertEqual(DemoMetricColors.band(70.01), 1)
        XCTAssertEqual(QuoteMetric.delta.level(-0.48), .medium)
        XCTAssertEqual(QuoteMetric.delta.level(-0.72), .high)
        XCTAssertEqual(QuoteMetric.iv.level(80), .high)
        XCTAssertEqual(SpreadBand.classify(9.2), .tight)
        XCTAssertEqual(SpreadBand.classify(15), .medium)
    }
}
