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
    func testEnabledLiveAssetCanStartAnIndependentGroup() throws {
        let live = state.merging(["paper": false, "account_mode": "live", "live_chart_scope": true]) { _, n in n }
        let id = UUID().uuidString
        let request = try TradeRules.flatHistoryRecoveryRequest(state: live, groupID: id)
        XCTAssertEqual(request["expected_refs"] as? [String], ["WheelPaper:old"])
        XCTAssertEqual(request["group_id"] as? String, id)
        XCTAssertEqual(Set(request.keys), ["action", "group_id", "expected_refs"])
        for key in ["enabled", "live_chart_scope"] {
            XCTAssertThrowsError(try TradeRules.flatHistoryRecoveryRequest(state: live.merging([key: false]) { _, n in n }, groupID: id))
        }
    }
    func testReturnFromHistoricalGroupUsesTheExistingDraft() async throws {
        let id = UUID().uuidString.lowercased(), checkpoint = UUID().uuidString.lowercased()
        let historical = state.merging(["sync_error": "Group ownership requires reconciliation: Historical group is read-only",
            "flat_draft": ["checkpoint": checkpoint, "group_id": id]]) { _, n in n }
        let body = try TradeRules.flatHistoryRecoveryRequest(state: historical, groupID: id)
        XCTAssertEqual(body["resume_checkpoint"] as? String, checkpoint)
        XCTAssertThrowsError(try TradeRules.flatHistoryRecoveryRequest(state: historical, groupID: UUID().uuidString))
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [MockProtocol.self]
        let session = TradingSession(session: URLSession(configuration: config))
        session.accountEpoch = "fixture"
        MockProtocol.requests = []; MockProtocol.fail = false; MockProtocol.statusCode = 200
        MockProtocol.payload = { _ in ["success": true, "status": "acknowledged",
            "state": ["group_id": id, "known": true, "active": false]] }
        defer { MockProtocol.payload = nil }
        let result = try await session.paperChartWrite(base: "https://mock.invalid", conID: 42, body: body, expectedEpoch: "fixture")
        XCTAssertEqual((result["state"] as? [String: Any])?["group_id"] as? String, id)
        XCTAssertEqual(MockProtocol.requests.count, 1)
        let request = try XCTUnwrap(MockProtocol.requests.first)
        XCTAssertEqual(request.url?.query, "group_id=" + id)
        XCTAssertEqual(request.value(forHTTPHeaderField: "X-Wheel-Account-Epoch"), "fixture")
        XCTAssertEqual(body["action"] as? String, "reconcile_flat_history")
    }
    func testPositionUnknownContextAndSyncFailuresAreRejected() {
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
