import XCTest
@testable import Wheel

@MainActor final class ChartFlatRecoveryTests: XCTestCase {
    private var state: [String: Any] {
        ["paper": true, "account_mode": "paper", "known": false, "enabled": true,
         "position": 0.0, "group_choices": [["id": "", "ref": "WheelPaper:old"]]]
    }
    func testRecoveryIsExplicitNewGroupWithoutTradeParameters() throws {
        let id = UUID().uuidString
        let body = try TradeRules.flatHistoryRecoveryRequest(state: state, groupID: id)
        XCTAssertEqual(body["action"] as? String, "reconcile_flat_history")
        XCTAssertEqual(body["group_id"] as? String, id)
        XCTAssertEqual(body["expected_refs"] as? [String], ["WheelPaper:old"])
        XCTAssertEqual(Set(body.keys), ["action", "group_id", "expected_refs"])
    }
    func testLivePositionUnknownContextAndSyncFailuresAreRejected() {
        let changes: [[String: Any]] = [["paper": false], ["account_mode": "live"], ["position": 1.0],
            ["position": Double.nan], ["account_position": -1.0], ["known": true], ["enabled": false],
            ["sync_error": true], ["sync_error": "Disconnected"], ["group_choices": []]]
        for change in changes {
            XCTAssertThrowsError(try TradeRules.flatHistoryRecoveryRequest(state: state.merging(change) { _, n in n }, groupID: UUID().uuidString))
        }
        XCTAssertThrowsError(try TradeRules.flatHistoryRecoveryRequest(state: state, groupID: ""))
    }
    func testRecoveryIncludesArchivedReferencesWhenProvided() throws {
        let value = state.merging(["group_attribution": ["recovery_refs": ["WheelPaper:older", "WheelPaper:old"]]]) { _, n in n }
        let body = try TradeRules.flatHistoryRecoveryRequest(state: value, groupID: UUID().uuidString)
        XCTAssertEqual(body["expected_refs"] as? [String], ["WheelPaper:old", "WheelPaper:older"])
    }
    func testUncertainRecoveryIsReconciledAfterRestartWithoutSecondPost() async throws {
        let saved = UserDefaults.standard.dictionary(forKey: "pendingPaperChartRequests")
        UserDefaults.standard.removeObject(forKey: "pendingPaperChartRequests")
        defer {
            UserDefaults.standard.set(saved, forKey: "pendingPaperChartRequests")
            MockProtocol.fail = false; MockProtocol.payload = nil
        }
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [MockProtocol.self]
        let client = TradingSession(session: URLSession(configuration: configuration)), id = UUID().uuidString
        client.accountEpoch = "test-epoch"
        let body = try TradeRules.flatHistoryRecoveryRequest(state: state, groupID: id)
        MockProtocol.requests = []; MockProtocol.statusCode = 200; MockProtocol.fail = true
        do { _ = try await client.paperChartWrite(base: "https://mock.invalid", conID: 7, body: body); XCTFail("Expected lost response") } catch { }
        XCTAssertTrue(client.paperPending(base: "https://mock.invalid", conID: 7, groupID: id))
        XCTAssertFalse(client.paperPending(base: "https://mock.invalid", conID: 7))
        let restarted = TradingSession(session: URLSession(configuration: configuration))
        MockProtocol.fail = false
        MockProtocol.payload = { _ in ["confirmed": true, "status": "reconciled"] }
        await restarted.reconcilePaper(base: "https://mock.invalid", conID: 7, groupID: id)
        XCTAssertFalse(restarted.paperPending(base: "https://mock.invalid", conID: 7, groupID: id))
        XCTAssertEqual(MockProtocol.requests.filter { $0.httpMethod == "POST" }.count, 1)
        XCTAssertTrue(MockProtocol.requests.allSatisfy { URLComponents(url: $0.url!, resolvingAgainstBaseURL: false)?.queryItems?.contains(where: { $0.name == "group_id" && $0.value == id }) == true })
    }
}
