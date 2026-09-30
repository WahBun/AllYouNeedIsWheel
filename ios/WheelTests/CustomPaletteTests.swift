import XCTest
import SwiftUI
@testable import Wheel
final class CustomPaletteTests: XCTestCase {
    func testHexValidationAndCorruptPreferences() {
        XCTAssertEqual(CustomPalette.normalized(" #39ff14 "), "#39FF14")
        XCTAssertNil(CustomPalette.normalized("GG0000"))
        XCTAssertNil(CustomPalette.normalized("123"))
        XCTAssertTrue(CustomPalette(json: "broken").values.isEmpty)
    }
    func testOverridesAreIndependentAndDefaultPaletteUnaffected() {
        let custom = CustomPalette(json: ##"{"delta.low.dark":"#123456","gain.light":"#654321"}"##)
        XCTAssertEqual(custom.color("delta.low", scheme: .dark, fallback: .red), CustomPalette.color("#123456"))
        XCTAssertEqual(custom.color("delta.low", scheme: .light, fallback: .red), .red)
        XCTAssertEqual(custom.color("iv.low", scheme: .dark, fallback: .blue), .blue)
        XCTAssertEqual(CustomPalette().color("gain", scheme: .light, fallback: FinancialColors.gain), FinancialColors.gain)
    }
}
