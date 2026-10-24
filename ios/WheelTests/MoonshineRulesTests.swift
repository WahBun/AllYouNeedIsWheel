import XCTest
@testable import Wheel

private final class RulesProtocol: URLProtocol {
    static var requests: [URLRequest] = []
    static var rules: [String: Any] = ["version": 1, "inner": 0.5, "outer": 0.8, "spx": "VIX", "ndx": "VXN"]
    static var reject = false
    static var hold = false
    static var pending: RulesProtocol?
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        Self.requests.append(request)
        if Self.hold { Self.pending = self; return }
        finish()
    }
    func finish() {
        let failed = request.httpMethod == "POST" && Self.reject
        let payload: [String: Any] = failed ? ["error": "Rules changed on another device."] : ["rules": Self.rules, "epoch": request.value(forHTTPHeaderField: "X-Wheel-Account-Epoch") ?? ""]
        client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: failed ? 409 : 200, httpVersion: nil, headerFields: nil)!, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: try! JSONSerialization.data(withJSONObject: payload))
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

@MainActor
final class MoonshineRulesTests: XCTestCase {
    let paper = NotificationAccount(address: "https://mock.invalid", mode: "paper", epoch: "paper")
    let live = NotificationAccount(address: "https://mock.invalid", mode: "live", epoch: "live")
    func model() -> MoonshineRulesModel {
        RulesProtocol.requests = []; RulesProtocol.reject = false; RulesProtocol.hold = false; RulesProtocol.pending = nil
        RulesProtocol.rules = ["version": 1, "inner": 0.5, "outer": 0.8, "spx": "VIX", "ndx": "VXN"]
        let config = URLSessionConfiguration.ephemeral; config.protocolClasses = [RulesProtocol.self]
        return MoonshineRulesModel(session: URLSession(configuration: config))
    }
    func testReadsDoNotUploadLocalPreferencesAndSaveUsesSharedResponse() async throws {
        let model = model(); model.select(paper); await model.refresh()
        XCTAssertEqual(RulesProtocol.requests.map(\.httpMethod), ["GET"])
        var local = VolatilitySettings(); local.inner = 8; local.width = 3; local.up1 = "#123456"
        let display = try XCTUnwrap(model.rules).applying(to: local)
        XCTAssertEqual(display.inner, 0.5); XCTAssertEqual(display.width, 3); XCTAssertEqual(display.up1, "#123456")
        var edited = display; edited.inner = 0.6
        RulesProtocol.rules["inner"] = 0.6; RulesProtocol.rules["version"] = 2
        await model.save(edited, account: paper, version: 1)
        XCTAssertEqual(model.rules?.inner, 0.6)
        let request = try XCTUnwrap(RulesProtocol.requests.last)
        XCTAssertEqual(request.httpMethod, "POST"); XCTAssertEqual(request.url?.path, "/api/notifications/moonshine-rules")
        XCTAssertEqual(request.value(forHTTPHeaderField: "X-Wheel-Account-Epoch"), "paper")
        XCTAssertEqual(request.value(forHTTPHeaderField: "X-All-You-Need-Is-Wheel"), "1")
    }
    func testConflictReconcilesWithoutReplayAndStaleAccountCannotSave() async throws {
        let model = model(); model.select(paper); await model.refresh()
        var edited = VolatilitySettings(); edited.inner = 0.6
        RulesProtocol.reject = true; RulesProtocol.rules["inner"] = 0.7; RulesProtocol.rules["version"] = 2
        await model.save(edited, account: paper, version: 1)
        XCTAssertEqual(RulesProtocol.requests.map(\.httpMethod), ["GET", "POST", "GET"])
        XCTAssertEqual(model.rules?.inner, 0.7); XCTAssertTrue(model.message.contains("another device"))
        model.select(live); await model.refresh()
        let count = RulesProtocol.requests.count
        await model.save(edited, account: paper, version: 2)
        XCTAssertEqual(RulesProtocol.requests.count, count)
    }
    func testLateOldAccountReadCannotPublish() async throws {
        let model = model(); model.select(paper); RulesProtocol.hold = true
        let old = Task { await model.refresh() }
        for _ in 0..<100 where RulesProtocol.pending == nil { try await Task.sleep(for: .milliseconds(10)) }
        let held = try XCTUnwrap(RulesProtocol.pending)
        model.select(live); RulesProtocol.hold = false
        await model.refresh(); let expected = model.rules
        RulesProtocol.rules["inner"] = 9
        held.finish(); await old.value
        XCTAssertEqual(model.account, live); XCTAssertEqual(model.rules, expected); XCTAssertFalse(model.busy)
    }
}
