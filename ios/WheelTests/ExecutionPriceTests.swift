import XCTest
import SwiftUI
@testable import Wheel

@MainActor final class ExecutionPriceTests: XCTestCase {
    private func order() throws -> Order {
        try JSONDecoder().decode(Order.self, from: Data(#"{"id":1,"ticker":"TQQQ","option_type":"PUT","strike":60,"expiration":"20261120","status":"executed","action":"SELL","fill_action":"SELL","filled":1,"quantity":1,"premium":2.5,"avg_fill_price":3.08,"commission":0.851645,"commission_currency":"USD","currency":"USD","contract_multiplier":100,"fill_time":"2026-10-22T17:54:54Z","tif":"DAY"}"#.utf8))
    }
    func testOuterPriceStaysGrossAndDetailSubtractsSellCommission() throws {
        var value = try order()
        XCTAssertEqual(value.fillPrice, 3.08)
        XCTAssertEqual(try XCTUnwrap(value.feeAdjustedFillPrice), 3.07148355, accuracy: 1e-10)
        value.commission = 20
        XCTAssertEqual(value.fillPrice, 3.08)
        XCTAssertEqual(try XCTUnwrap(value.feeAdjustedFillPrice), 2.88, accuracy: 1e-10)
        value.avg_fill_price = nil
        XCTAssertNil(value.fillPrice); XCTAssertNil(value.feeAdjustedFillPrice)
    }
    func testBuyPartialQuantityMultiplierZeroFeeAndRebate() throws {
        var value = try order()
        value.fill_action = "BUY"; value.filled = 2; value.quantity = 5; value.commission = 2
        XCTAssertEqual(try XCTUnwrap(value.feeAdjustedFillPrice), 3.09, accuracy: 1e-10)
        value.contract_multiplier = 10
        XCTAssertEqual(try XCTUnwrap(value.feeAdjustedFillPrice), 3.18, accuracy: 1e-10)
        value.commission = 0
        XCTAssertEqual(value.feeAdjustedFillPrice, value.fillPrice)
        value.commission = -2
        XCTAssertEqual(try XCTUnwrap(value.feeAdjustedFillPrice), 2.98, accuracy: 1e-10)
    }
    func testUnknownFeeCurrencyMultiplierOrSideDoesNotGuess() throws {
        let original = try order()
        for modify: (inout Order) -> Void in [
            { $0.commission = nil }, { $0.commission = .infinity },
            { $0.commission_currency = nil }, { $0.commission_currency = "EUR" },
            { $0.currency = nil }, { $0.contract_multiplier = nil }, { $0.contract_multiplier = 0 },
            { $0.contract_multiplier = .nan }, { $0.filled = 0 }, { $0.fill_action = "UNKNOWN" }
        ] {
            var value = original; modify(&value)
            XCTAssertNil(value.feeAdjustedFillPrice)
            XCTAssertEqual(value.fillPrice, 3.08)
        }
        let value = try JSONDecoder().decode(Order.self, from: Data(#"{"id":1,"status":"executed","contract_multiplier":"100"}"#.utf8))
        XCTAssertEqual(value.contract_multiplier, 100)
    }
    func testPriceRowsInBothThemes() async throws {
        let value = try order()
        let scene = try XCTUnwrap(UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first)
        for dark in [false, true] {
            let content = NavigationStack {
                List {
                    Section("Executed record") { CompactOrderRow(order: value, history: true) }
                    Section("Order details") {
                        OrderFillPrices(order: value)
                        LabeledContent("Commission", value: value.commissionLabel)
                    }
                }.navigationTitle("Orders")
            }.environment(\.locale, Locale(identifier: "en"))
            let host = UIHostingController(rootView: content)
            let window = UIWindow(windowScene: scene); window.frame = CGRect(x: 0, y: 0, width: 393, height: 852)
            window.overrideUserInterfaceStyle = dark ? .dark : .light
            window.rootViewController = host; window.makeKeyAndVisible(); host.view.frame = window.bounds
            host.view.layoutIfNeeded(); try await Task.sleep(for: .milliseconds(500))
            let image = UIGraphicsImageRenderer(bounds: window.bounds).image { _ in
                XCTAssertTrue(host.view.drawHierarchy(in: window.bounds, afterScreenUpdates: true))
            }
            let attachment = XCTAttachment(image: image); attachment.name = "ExecutionPrice-\(dark ? "dark" : "light")"; attachment.lifetime = .keepAlways; add(attachment)
            let url = URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("\(attachment.name!).png")
            try XCTUnwrap(image.pngData()).write(to: url)
            print("PRICE_PREVIEW \(url.path)")
            window.isHidden = true
        }
    }
}
