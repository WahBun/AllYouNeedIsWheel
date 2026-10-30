import XCTest
import SwiftUI
@testable import Wheel

final class OptionPositionOrderTests: XCTestCase {
    private func row(_ id: Int, _ symbol: String, _ expiry: String?, _ right: String?, _ strike: Double?) -> Position {
        Position(symbol: symbol, position: -1, security_type: "OPT", strike: strike, expiration: expiry, option_type: right, con_id: id)
    }
    func testGroupsSymbolThenExpiryPutCallStrikeAndIdentity() {
        let rows = [row(60,"TQQQ","20261120","PUT",60), row(13,"TSLL","20261218","CALL",13),
                    row(55,"TQQQ","20261120","P",55), row(10,"TQQQ","20261113","CALL",65),
                    row(20,"TQQQ","20261120","CALL",50), row(56,"TQQQ","2026-11-20","PUT",55),
                    row(90,"TQQQ",nil,nil,nil)]
        let expected = [10,55,56,60,20,90,13]
        XCTAssertEqual(OptionPositionOrder.sorted(rows).compactMap(\.con_id), expected)
        XCTAssertEqual(OptionPositionOrder.sorted(rows.reversed()).compactMap(\.con_id), expected)
        var updated = rows
        updated[0].position = 100; updated[0].unrealized_pnl = 999
        XCTAssertEqual(OptionPositionOrder.sorted(updated).compactMap(\.con_id), expected)
        XCTAssertEqual(rows.compactMap(\.con_id), [60,13,55,10,20,56,90])
    }
    @MainActor func testGroupedRowsRenderInBothThemes() async throws {
        let scene = try XCTUnwrap(UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first)
        let previous = scene.windows.first { $0.isKeyWindow }
        let store = WheelStore(); store.demo = true
        let positions = [row(60,"TQQQ","20261120","PUT",60), row(13,"TSLL","20261218","CALL",13), row(55,"TQQQ","20261120","PUT",55)]
        for (name, theme) in [("dark", ColorScheme.dark), ("light", ColorScheme.light)] {
            let view = NavigationStack { List { Section("Options") {
                ForEach(OptionPositionOrder.sorted(positions)) { position in PortfolioOptionRow(position: position, showsRange: false) }
            } }.navigationTitle("Portfolio") }.environment(store).environment(\.locale, Locale(identifier: "en")).preferredColorScheme(theme)
            let controller = UIHostingController(rootView: view), window = UIWindow(windowScene: scene)
            window.rootViewController = controller; window.makeKeyAndVisible()
            try await Task.sleep(for: .milliseconds(500))
            let image = UIGraphicsImageRenderer(bounds: window.bounds).image { _ in window.drawHierarchy(in: window.bounds, afterScreenUpdates: true) }
            try image.pngData()!.write(to: URL(fileURLWithPath: "/tmp/wheel-option-grouping-native-\(name).png"))
            window.isHidden = true; window.rootViewController = nil
        }
        previous?.makeKeyAndVisible()
    }

}
