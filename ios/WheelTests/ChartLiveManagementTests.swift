import XCTest
@testable import Wheel

final class ChartLiveManagementTests: XCTestCase {
    private let now = Date(timeIntervalSince1970: 1000)
    private var packet: [String: Any] { ["con_id": 7, "account_epoch": "test", "server_time": 1000.0, "quote_expires_at": 1003.0, "bid": 2.1, "ask": 2.2, "price_rules": [["low": 0.0, "increment": 0.01]]] }
    private func state(_ position: Double = -4) -> [String: Any] { ["live_options_scope": true, "position": position, "order_ref": "owned"] }
    private func request(_ action: String, position: Double = -4, fields: [String: Any] = [:], quote: [String: Any]? = nil, received: Date? = nil) throws -> [String: Any] {
        try TradeRules.liveChartManagementRequest(["action": action, "quantity": 1, "expected_ref": "owned"].merging(fields) { _, new in new }, state: state(position), packet: quote ?? packet, conID: 7, epoch: "test", received: received ?? now, now: now)
    }
    func testNewScopeQuantityLimitsAndLegacyCompatibility() {
        for type in ["OPT", "FUT", "STK"] {
            XCTAssertEqual(TradeRules.chartQuantityLimit(securityType: type, state: state()), type == "STK" ? 1000 : 10)
            XCTAssertEqual(TradeRules.chartQuantityLimit(securityType: type, state: ["live_initial_scope": true]), 1)
        }
    }

    func testOptionsAndStocksUseMidpointOnBothSidesIncludingPaperAndExplicitInputs() throws {
        for kind in ["OPT", "STK"] { for position in [-4.0, 4.0] { for action in ["add", "trim", "close"] {
            let priceKey = action == "add" ? "entry" : "exit_price"
            let typeKey = action == "add" ? "entry_type" : "exit_type"
            let q = packet.merging(["security_type": kind, "bid": 2.10, "ask": 2.21]) { _, n in n }
            let body = try request(action, position: position, fields: [typeKey: "LMT", priceKey: 9.0], quote: q)
            let buy = action == "add" ? position > 0 : position < 0
            XCTAssertEqual(body[priceKey] as? Double, buy ? 2.15 : 2.16)
            XCTAssertEqual(body[typeKey] as? String, "LMT")
            let paper = try TradeRules.liveChartManagementRequest(["action": action, "expected_ref": "owned"], state: ["position": position, "order_ref": "owned"], packet: q, conID: 7, epoch: "test", received: now, now: now)
            XCTAssertEqual(paper[priceKey] as? Double, buy ? 2.15 : 2.16)
        } } }
    }

    func testMidpointNeverUsesCachedDisplayQuoteOrBypassesFreshnessWithExplicitPrice() throws {
        for changes in [["bid": NSNull()], ["ask": Double.nan], ["quote_expires_at": 999.0], ["price_rules": []], ["account_epoch": "other"]] as [[String: Any]] {
            let q = packet.merging(["security_type": "OPT", "option_display_quote": ["bid": 2.1, "ask": 2.2]]) { _, n in n }.merging(changes) { _, n in n }
            XCTAssertThrowsError(try request("close", fields: ["exit_type": "LMT", "exit_price": 2.1], quote: q))
        }
    }

    func testStockAndFutureScopeIncludesProtectionSnapshotForQuoteAdd() throws {
        for kind in ["STK", "FUT"] {
            let state: [String: Any] = ["live_chart_scope": true, "position": 3.0, "order_ref": "owned", "tp": 3.0, "sl": 1.0]
            let body = try TradeRules.liveChartManagementRequest(["action": "add", "quantity": 1, "expected_ref": "owned"], state: state, packet: packet.merging(["security_type": kind]) { _, new in new }, conID: 7, epoch: "test", received: now, now: now)
            XCTAssertEqual(body["entry_type"] as? String, "LMT")
            XCTAssertEqual(body["side"] as? Int, 1)
            XCTAssertEqual(body["expected_tp"] as? Double, 3)
            XCTAssertEqual(body["expected_sl"] as? Double, 1)
        }
    }
    func testLiveLongAndShortActionsUseCorrectFreshQuoteLimits() throws {
        for position in [-4.0, 4.0] {
            for action in ["add", "trim", "close"] {
                let body = try request(action, position: position)
                XCTAssertEqual(body[action == "add" ? "entry_type" : "exit_type"] as? String, "LMT")
                let ask = action == "add" ? position > 0 : position < 0
                XCTAssertEqual(body[action == "add" ? "entry" : "exit_price"] as? Double, ask ? 2.2 : 2.1)
                XCTAssertEqual(body["expected_position"] as? Double, position)
                XCTAssertEqual(body["expected_ref"] as? String, "owned")
            }
        }
    }
    func testStaleWrongAccountWrongContractAndCrossedQuotesReject() {
        for changes in [["quote_expires_at": 999.0], ["account_epoch": "other"], ["con_id": 8], ["bid": 2.3], ["ask": Double.nan]] as [[String: Any]] {
            XCTAssertThrowsError(try request("close", quote: packet.merging(changes) { _, new in new }))
        }
        XCTAssertThrowsError(try request("add", received: now.addingTimeInterval(-4)))
    }
    func testChangedPositionIdentityCannotBeOverwritten() {
        for fields in [["expected_ref": "foreign"], ["expected_position": -3.0], ["con_id": 8]] as [[String: Any]] {
            XCTAssertThrowsError(try request("close", fields: fields))
        }
    }
    func testChosenLimitCloseAndStopAddKeepExactUserPrice() throws {
        let close = try request("close", fields: ["exit_type": "LMT", "exit_price": 1.75])
        XCTAssertEqual(close["exit_price"] as? Double, 1.75)
        let add = try request("add", fields: ["entry_type": "STP", "entry": 2.5])
        XCTAssertEqual(add["entry"] as? Double, 2.5)
        XCTAssertEqual(add["entry_type"] as? String, "STP")
        XCTAssertThrowsError(try request("close", fields: ["exit_type": "MKT", "exit_price": 1.75]))
        XCTAssertThrowsError(try request("close", fields: ["exit_type": "LMT", "exit_price": "bad"]))
        XCTAssertThrowsError(try request("add", fields: ["entry_type": "STP"]))
    }
    func testPaperProtectedGroupAndOtherActionsRemainUnchanged() throws {
        let incoming: [String: Any] = ["action": "close", "expected_ref": "paper"]
        let result = try TradeRules.liveChartManagementRequest(incoming, state: ["position": 3.0, "scalable": true], packet: [:], conID: 7, epoch: nil, received: nil)
        XCTAssertNil(result["exit_type"])
        XCTAssertEqual(result["expected_ref"] as? String, "paper")
        let pending = TradeRules.chartCloseRequest(["position": 0.0, "entry_editable": true, "order_ref": "owned", "edit_snapshot": []])
        let unchanged = try TradeRules.liveChartManagementRequest(pending, state: state(0), packet: [:], conID: 7, epoch: nil, received: nil)
        XCTAssertEqual(unchanged["action"] as? String, "edit_entry")
        XCTAssertEqual(unchanged["cancel"] as? Bool, true)
    }
}

extension ChartLiveManagementTests {
    func testProfitAmountUsesWholePositionAndTickRounding() {
        XCTAssertNil(ChartProtectionMath.multiplier(packet: ["security_type": "OPT"]))
        XCTAssertNil(ChartProtectionMath.multiplier(packet: ["security_type": "FUT", "multiplier": 0.0]))
        XCTAssertEqual(ChartProtectionMath.multiplier(packet: ["security_type": "STK"]), 1)
        XCTAssertEqual(ChartProtectionMath.multiplier(packet: ["security_type": "OPT", "multiplier": 100.0]), 100)
        let rules: [[String: Any]] = [["low": 0.0, "increment": 0.25]]
        XCTAssertEqual(ChartProtectionMath.target(entry: 100, side: 1, value: 300, mode: "profit", quantity: 3, multiplier: 2, rules: rules), 150)
        XCTAssertEqual(ChartProtectionMath.target(entry: 100, side: -1, value: 300, mode: "profit", quantity: 3, multiplier: 2, rules: rules), 50)
        XCTAssertEqual(ChartProtectionMath.target(entry: 100, side: 1, value: 300, mode: "profit", quantity: 4, multiplier: 2, rules: rules), 137.5)
        XCTAssertEqual(ChartProtectionMath.target(entry: 100, side: 1, value: 302, mode: "profit", quantity: 3, multiplier: 2, rules: rules), 150.25)
        XCTAssertEqual(ChartProtectionMath.target(entry: 10, side: -1, value: 300, mode: "profit", quantity: 3, multiplier: 100, rules: rules), 9)
        for (quantity, multiplier, amount) in [(0.0, 2.0, 300.0), (3, 0, 300), (3, 2, 0.001), (3, 2, Double.nan)] {
            XCTAssertNil(ChartProtectionMath.target(entry: 100, side: 1, value: amount, mode: "profit", quantity: quantity, multiplier: multiplier, rules: rules))
        }
        XCTAssertNil(ChartProtectionMath.target(entry: 1, side: -1, value: 300, mode: "profit", quantity: 1, multiplier: 100, rules: rules))
    }
}
