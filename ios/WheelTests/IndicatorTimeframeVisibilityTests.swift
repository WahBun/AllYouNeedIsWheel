import XCTest
import SwiftUI
@testable import Wheel

@MainActor
final class IndicatorTimeframeVisibilityTests: XCTestCase {
    func testDefaultsAndInclusiveUnitBoundaries() throws {
        let intervals = [1, 3, 5, 10, 15, 60, 480, 1440, 10080, 43200]
        var visibility = IndicatorTimeframeVisibility()
        XCTAssertTrue(intervals.allSatisfy(visibility.allows))
        XCTAssertEqual(intervals.filter(visibility.allowsAdditionalIndicators), [1, 3, 5, 10, 15, 60])
        XCTAssertFalse(visibility.allowsAdditionalIndicators(61))
        XCTAssertTrue(visibility.allows(480), "Primary EMA remains available above 1h")
        visibility.minutes = .init(min: 3, max: 10)
        visibility.hours = .init(enabled: false, max: 24)
        visibility.days = .init(enabled: false, max: 366)
        XCTAssertEqual(intervals.filter(visibility.allows), [3, 5, 10, 10080, 43200])
        visibility.hours = .init(min: 8, max: 8)
        XCTAssertFalse(visibility.allows(60)); XCTAssertTrue(visibility.allows(480))
        XCTAssertEqual(IndicatorTimeframeVisibility(json: visibility.json), visibility)
        // The filter does not rewrite a component's own visibility preference.
        let showEMA = false
        XCTAssertFalse(showEMA && visibility.allows(480))
    }
    func testLegacyPartialAndMalformedPreferences() throws {
        XCTAssertEqual(IndicatorTimeframeVisibility(json: ""), IndicatorTimeframeVisibility())
        var visibility = IndicatorTimeframeVisibility(json: #"{"hours":{"enabled":false},"minutes":{"min":15,"max":3}}"#)
        XCTAssertFalse(visibility.allows(480))
        XCTAssertTrue(visibility.allows(3)); XCTAssertTrue(visibility.allows(15)); XCTAssertFalse(visibility.allows(1))
        visibility.set(.init(min: -9, max: 200), for: .minutes)
        XCTAssertEqual(visibility.minutes.min, 1); XCTAssertEqual(visibility.minutes.max, 59)
        XCTAssertTrue(visibility.allows(5))
        XCTAssertTrue(IndicatorTimeframeVisibility(json: #"{"days":null,"months":{"min":"bad"}}"#).allows(43200))
    }
    func testLegacyIndicatorTemplatesRemainDecodable() throws {
        let old: [String: Any] = ["showEMA": true, "emaLength": 20, "emaSource": "close", "emaOffset": 0, "emaFrame": 0,
            "emaDynamic": true, "emaColor": "#ffffff", "emaWidth": 1, "emaStyle": 0, "extraEMAJSON": "",
            "showATR": true, "atrLength": 4, "showBarCount": true, "barCountFrame": 1440, "barCountSize": "tiny",
            "barCountColor": "#ffffff", "barCountOpacity": 66, "barCountLimit": true, "barCountBars": 162, "indicatorVisible": true]
        var template = try JSONDecoder().decode(IndicatorSettingsSnapshot.self, from: JSONSerialization.data(withJSONObject: old))
        XCTAssertNil(template.timeframeVisibilityJSON)
        var visibility = IndicatorTimeframeVisibility(); visibility.hours.enabled = false
        template.timeframeVisibilityJSON = visibility.json
        let restored = try JSONDecoder().decode(IndicatorSettingsSnapshot.self, from: JSONEncoder().encode(template))
        XCTAssertFalse(IndicatorTimeframeVisibility(json: restored.timeframeVisibilityJSON ?? "").allows(480))
        XCTAssertTrue(restored.showEMA)
    }
    func testVisibilityPageRendersInBothThemes() async throws {
        for dark in [false, true] {
            let root = NavigationStack {
                Form { IndicatorTimeframeVisibilitySection(settings: .constant(IndicatorTimeframeVisibility())) }
                    .navigationTitle("Visibility").navigationBarTitleDisplayMode(.inline)
            }.environment(\.locale, Locale(identifier: "en"))
            let host = UIHostingController(rootView: root)
            let scene = try XCTUnwrap(UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first)
            let window = UIWindow(windowScene: scene)
            window.frame = CGRect(x: 0, y: 0, width: 393, height: 852)
            window.overrideUserInterfaceStyle = dark ? .dark : .light
            window.rootViewController = host; window.makeKeyAndVisible()
            host.view.frame = window.bounds; host.view.layoutIfNeeded()
            try await Task.sleep(for: .milliseconds(400))
            let image = UIGraphicsImageRenderer(bounds: window.bounds).image { _ in
                XCTAssertTrue(host.view.drawHierarchy(in: window.bounds, afterScreenUpdates: true))
            }
            XCTAssertGreaterThan(try XCTUnwrap(image.pngData()).count, 20000, "Visibility page must render content")
            let url = URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("indicator-visibility-\(dark ? "dark" : "light").png")
            try XCTUnwrap(image.pngData()).write(to: url)
            print("VISIBILITY_PREVIEW_PATH=\(url.path)")
            window.isHidden = true
        }
    }
}
