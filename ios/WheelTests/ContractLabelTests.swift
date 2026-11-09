import XCTest
import SwiftUI
@testable import Wheel

final class ContractLabelTests: XCTestCase {
    func testLegacyNamesAndFallbacks() {
        for (raw, expected) in [
            ("TQQQ  261120P00060000", "TQQQ · 11/20/26 · 60P"),
            ("TSLL 20261218 13.5 CALL", "TSLL · 12/18/26 · 13.5C"),
            ("TSLL1  261218C00013500", "TSLL1 · 12/18/26 · 13.5C"),
            ("TQQQ 20260230 60 P", "TQQQ 20260230 60 P"),
            ("MSTR  261218C01250000 20261218 1,250 CALL", "MSTR · 12/18/26 · 1250C"),
            ("MESZ6", "MESZ6")
        ] { XCTAssertEqual(ContractLabel.compact(raw), expected) }
        XCTAssertEqual(ContractLabel.details(expiration: "20261120", strike: 60, right: "PUT"), "11/20/26 · 60P")
    }
    @MainActor func testOrderChartAndRestoredOptionUseCompactNamesAndUnderlyingQueries() async throws {
        for (ticker, root, date, strike, side, label) in [
            ("CRCL  261218P00060000", "CRCL", "20261218", 60.0, "PUT", "CRCL · 12/18/26 · 60P"),
            ("TQQQ", "TQQQ", "20261120", 60.0, "PUT", "TQQQ · 11/20/26 · 60P"),
            ("TSLL261218C00013500", "TSLL", "20261218", 13.5, "CALL", "TSLL · 12/18/26 · 13.5C")
        ] {
            let order = Order(id: 19, ticker: ticker, action: "SELL", option_type: side, strike: strike,
                              expiration: date, quantity: 1, status: "submitted", con_id: 75)
            let position = try XCTUnwrap(order.chartPosition)
            XCTAssertEqual(order.contractLabel, label)
            XCTAssertEqual(order.name, ticker)
            XCTAssertEqual(position.symbol, root)
            XCTAssertEqual(position.chartLabel, label)
            XCTAssertEqual(position.con_id, 75)
            let legacy = "\(ticker) \(date) \(strike) \(side)"
            for savedSymbol in ["", ticker] {
                let item = try XCTUnwrap(ChartInstrument(["con_id": 75, "security_type": "OPT",
                    "local_symbol": legacy, "symbol": savedSymbol]))
                XCTAssertEqual(item.displayLabel, label)
                XCTAssertEqual(item.symbol, root)
                XCTAssertEqual(item.contract["con_id"] as? Int, 75)
                XCTAssertEqual(item.contract["local_symbol"] as? String, legacy)
                let search = ChartInstrumentSearch()
                await search.openPicker(current: item) { path, query in
                    let args = Dictionary(uniqueKeysWithValues: query.map { ($0.name, $0.value ?? "") })
                    switch path {
                    case "api/portfolio/chart-contracts":
                        XCTAssertEqual(args, ["type": "OPT_DATES", "q": root])
                        return ["expirations": ["20261113", date]]
                    case "api/options/strikes":
                        XCTAssertEqual(args, ["ticker": root, "expiration": date, "optionType": side])
                        return ["strikes": [10.0, strike]]
                    default: XCTFail("Unexpected lookup: \(path)"); return [:]
                    }
                }
                XCTAssertTrue(search.canOpen)
                XCTAssertEqual(search.expiration, date)
                XCTAssertEqual(search.strike, strike)
            }
        }
        let conflict = "CRCL  261218P00060000 20261218 61 PUT"
        XCTAssertEqual(ContractLabel.compact(conflict), conflict)
    }
    @MainActor func testAdjustedOptionQueriesItsVerifiedUnderlying() async throws {
        let item = try XCTUnwrap(ChartInstrument(["con_id": 75, "security_type": "OPT",
            "local_symbol": "TSLL1  261218C00013500"]))
        let search = ChartInstrumentSearch()
        var calls: [String] = []
        await search.openPicker(current: item) { path, query in
            let args = Dictionary(uniqueKeysWithValues: query.map { ($0.name, $0.value ?? "") })
            calls.append(args["type"] ?? path)
            if args["type"] == "ID" {
                XCTAssertEqual(args["con_id"], "75")
                return ["contracts": [item.contract.merging(["symbol": "TSLL"]) { _, value in value }]]
            }
            if args["type"] == "OPT_DATES" {
                XCTAssertEqual(args["q"], "TSLL")
                return ["expirations": ["20261218"]]
            }
            XCTAssertEqual(args["ticker"], "TSLL")
            return ["strikes": [13.5]]
        }
        XCTAssertEqual(calls, ["ID", "OPT_DATES", "api/options/strikes"])
        XCTAssertEqual(item.displayLabel, "TSLL1 · 12/18/26 · 13.5C")
        XCTAssertEqual(search.query, "TSLL")
        XCTAssertTrue(search.canOpen)
        let reopened = await search.resolve { _, query in
            let args = Dictionary(uniqueKeysWithValues: query.map { ($0.name, $0.value ?? "") })
            XCTAssertEqual(args, ["type": "ID", "con_id": "75"])
            return ["contracts": [item.contract.merging(["symbol": "TSLL"]) { _, value in value }]]
        }
        XCTAssertEqual(reopened?.id, 75)
    }
    @MainActor func testDisplayDoesNotChangeContractPayload() throws {
        let item = try XCTUnwrap(ChartInstrument(["con_id": 7, "symbol": "TSLL", "local_symbol": "TSLL1  261218C00013500", "security_type": "OPT", "expiration": "20261218", "right": "C", "strike": 13.5]))
        XCTAssertEqual(item.displayLabel, "TSLL1 · 12/18/26 · 13.5C")
        XCTAssertEqual(item.contract["local_symbol"] as? String, "TSLL1  261218C00013500")
        XCTAssertEqual(item.contract["con_id"] as? Int, 7)
    }
    @MainActor func testCompactRowsInBothThemes() async throws {
        let scene = try XCTUnwrap(UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first)
        let previous = scene.windows.first { $0.isKeyWindow }
        let store = WheelStore(); store.demo = true
        let position = Position(symbol: "TQQQ", position: -1, market_price: 1.5, unrealized_pnl: -5,
            security_type: "OPT", strike: 60, expiration: "20261120", option_type: "PUT", con_id: 7, avg_cost: 123, multiplier: 100)
        let order = Order(id: 1, ticker: "TSLL", action: "SELL", option_type: "CALL", strike: 13.5,
            expiration: "20261218", premium: 1.5, quantity: 1, status: "processing")
        for (name, theme) in [("dark", ColorScheme.dark), ("light", ColorScheme.light)] {
            let view = NavigationStack { List {
                Section("Positions") { PortfolioOptionRow(position: position, showsRange: false) }
                Section("Orders") { CompactOrderRow(order: order, history: false) }
            }.navigationTitle("Contracts") }.environment(store).environment(\.locale, Locale(identifier: "en")).preferredColorScheme(theme)
            let controller = UIHostingController(rootView: view), window = UIWindow(windowScene: scene)
            window.rootViewController = controller; window.makeKeyAndVisible()
            try await Task.sleep(for: .milliseconds(500))
            let image = UIGraphicsImageRenderer(bounds: window.bounds).image { _ in window.drawHierarchy(in: window.bounds, afterScreenUpdates: true) }
            try image.pngData()!.write(to: URL(fileURLWithPath: "/tmp/wheel-native-labels-\(name).png"))
            let attachment = XCTAttachment(image: image); attachment.lifetime = .keepAlways; add(attachment)
            window.isHidden = true; window.rootViewController = nil
        }
        previous?.makeKeyAndVisible()
    }

}
