import XCTest
import SwiftUI
@testable import Wheel

private final class MaintenanceProtocol: URLProtocol {
    static let receipt = String(repeating: "a", count: 32)
    static var requests: [URLRequest] = []
    static var state = "ready"
    static var failSave = false
    static var statusCode = 200
    static var hold = false
    static var pending: MaintenanceProtocol?
    static var status: [String: Any] = [:]
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        Self.requests.append(request)
        if Self.hold { Self.pending = self; return }
        finish()
    }
    func finish() {
        let path = request.url!.path
        var reply: [String: Any] = Self.status
        if path.hasSuffix("/validate") { reply = ["id": Self.receipt, "state": "validating"] }
        if path.contains("/validation/") { reply = ["id": Self.receipt, "state": Self.state, "report_through": "2026-10-29"] }
        if path.hasSuffix("/save") {
            Self.state = "saved"
            if Self.failSave { client?.urlProtocol(self, didFailWithError: URLError(.timedOut)); return }
            reply = ["state": "saved"]
        }
        client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: Self.statusCode, httpVersion: nil, headerFields: nil)!, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: try! JSONSerialization.data(withJSONObject: reply))
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

@MainActor
final class BackendMaintenanceTests: XCTestCase {
    private let account = NotificationAccount(address: "https://mock.invalid", mode: "live", epoch: "epoch")
    private func makeModel() -> BackendMaintenanceModel {
        MaintenanceProtocol.requests = []; MaintenanceProtocol.state = "ready"
        MaintenanceProtocol.failSave = false; MaintenanceProtocol.statusCode = 200
        MaintenanceProtocol.hold = false; MaintenanceProtocol.pending = nil
        MaintenanceProtocol.status = ["backend": "reachable", "mode": "live", "gateway_connected": true, "epoch": "epoch",
            "performance": ["configured": true, "can_replace": true, "source": "IBKR Flex", "history_through": "2026-10-29",
                "last_success": "2026-10-30T08:00:00+00:00", "token_expires_on": "2026-11-20", "days_remaining": 20]]
        let config = URLSessionConfiguration.ephemeral; config.protocolClasses = [MaintenanceProtocol.self]
        return BackendMaintenanceModel(session: URLSession(configuration: config))
    }
    private func body(_ request: URLRequest) throws -> [String: Any] {
        if let data = request.httpBody { return try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any]) }
        let stream = try XCTUnwrap(request.httpBodyStream); stream.open(); defer { stream.close() }
        var data = Data(); var buffer = [UInt8](repeating: 0, count: 4096)
        while stream.hasBytesAvailable { let count = stream.read(&buffer, maxLength: buffer.count); if count <= 0 { break }; data.append(buffer, count: count) }
        return try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
    }
    func testValidationNeverSavesUntilExplicitSaveAndOnlyReceiptIsSent() async throws {
        let model = makeModel(); model.select(account); await model.refresh()
        model.token = "  private-fixture-token  "
        await model.validate()
        XCTAssertEqual(model.validationState, "ready"); XCTAssertEqual(model.token, "")
        XCTAssertEqual(model.reportThrough, "2026-10-29")
        XCTAssertFalse(MaintenanceProtocol.requests.contains { $0.url?.path.hasSuffix("/save") == true })
        let validation = try XCTUnwrap(MaintenanceProtocol.requests.first { $0.url?.path.hasSuffix("/validate") == true })
        XCTAssertEqual(try body(validation)["token"] as? String, "private-fixture-token")
        XCTAssertNil(try body(validation)["expires_on"])
        await model.save()
        let writes = MaintenanceProtocol.requests.filter { $0.httpMethod == "POST" }
        XCTAssertEqual(writes.count, 2)
        XCTAssertEqual(Set(try body(XCTUnwrap(writes.last)).keys), ["id"])
        XCTAssertNil(model.validationID); XCTAssertNil(model.error)
        XCTAssertEqual(model.message, "Token saved on Mini. No restart is needed.")
        XCTAssertTrue(MaintenanceProtocol.requests.allSatisfy {
            $0.value(forHTTPHeaderField: "X-Wheel-Account-Epoch") == "epoch" &&
            $0.value(forHTTPHeaderField: "X-All-You-Need-Is-Wheel") == "1" && $0.url?.query == nil
        })
    }
    func testLostSaveResponseRequiresReadReconciliationWithoutReplay() async {
        let model = makeModel(); model.select(account); await model.refresh()
        model.token = "fixture"; await model.validate()
        MaintenanceProtocol.failSave = true
        await model.save()
        XCTAssertEqual(model.validationState, "unknown"); XCTAssertNotNil(model.error)
        await model.save()
        XCTAssertEqual(MaintenanceProtocol.requests.filter { $0.url?.path.hasSuffix("/save") == true }.count, 1)
        await model.refresh()
        XCTAssertNil(model.validationID); XCTAssertNil(model.error)
        XCTAssertEqual(model.message, "Token saved on Mini. No restart is needed.")
        XCTAssertEqual(MaintenanceProtocol.requests.filter { $0.url?.path.hasSuffix("/save") == true }.count, 1)
    }
    func testAccountChangeClearsSecretsAndRejectsStaleStatus() async throws {
        let model = makeModel(); model.select(account); model.token = "private-draft"
        MaintenanceProtocol.hold = true
        let old = Task { await model.refresh() }
        for _ in 0..<100 where MaintenanceProtocol.pending == nil { try await Task.sleep(for: .milliseconds(10)) }
        let pending = try XCTUnwrap(MaintenanceProtocol.pending)
        model.select(NotificationAccount(address: account.address, mode: "paper", epoch: "other"))
        pending.finish(); await old.value
        XCTAssertNil(model.status); XCTAssertNil(model.error); XCTAssertFalse(model.busy)
        XCTAssertEqual(model.token, ""); XCTAssertNil(model.validationID)
        model.select(nil); await model.refresh(); await model.validate(); await model.save()
        XCTAssertEqual(MaintenanceProtocol.requests.count, 1)
    }
    func testUnsupportedBackendAndWrongEpochNeverEnableReplacement() async {
        let model = makeModel(); model.select(account)
        MaintenanceProtocol.statusCode = 404
        await model.refresh(); XCTAssertNil(model.status)
        XCTAssertTrue(model.error?.contains("Deploy") == true)
        MaintenanceProtocol.statusCode = 200; MaintenanceProtocol.status["epoch"] = "changed"
        await model.refresh(); XCTAssertNil(model.status); XCTAssertNotNil(model.error)
        await model.validate(); XCTAssertEqual(MaintenanceProtocol.requests.count, 2)
    }
    func testMaintenanceScreensRenderInThemesLargeTextAndWideLayout() async throws {
        let config = URLSessionConfiguration.ephemeral; config.protocolClasses = [MaintenanceProtocol.self]
        let store = WheelStore(session: URLSession(configuration: config))
        store.address = account.address; store.demo = false; store.trading.accountEpoch = account.epoch
        store.portfolio = Bootstrap(summary: Summary(account_value: 1000, cash_balance: 1000), positions: [],
            connection: AccountConnection(account_epoch: account.epoch, mode: "live", execution_enabled: false, chart_execution_enabled: false))
        let scene = try XCTUnwrap(UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first)
        for page in ["status-light", "status-dark", "expanded", "entry-light", "entry-dark", "large", "wide"] {
            let model = makeModel()
            model.select(account); await model.refresh()
            let root = NavigationStack { TradingAccessView(maintenanceModel: model, editingToken: page.hasPrefix("entry"), expandedPerformance: page == "expanded") }
                .environment(store).environment(\.locale, Locale(identifier: "en"))
                .environment(\.dynamicTypeSize, page == "large" ? .accessibility2 : .large)
            let host = UIHostingController(rootView: root)
            let window = UIWindow(windowScene: scene)
            window.frame = CGRect(x: 0, y: 0, width: page == "wide" ? 844 : 393, height: page == "wide" ? 650 : 852)
            window.overrideUserInterfaceStyle = page.hasSuffix("dark") ? .dark : .light
            window.rootViewController = host; window.makeKeyAndVisible()
            host.view.frame = window.bounds; host.view.layoutIfNeeded()
            try await Task.sleep(for: .milliseconds(450))
            XCTAssertNotNil(model.status)
            if page.hasPrefix("entry") {
                func scrollView(_ view: UIView) -> UIScrollView? {
                    if let scroll = view as? UIScrollView { return scroll }
                    return view.subviews.lazy.compactMap { scrollView($0) }.first
                }
                let scroll = try XCTUnwrap(scrollView(host.view))
                scroll.setContentOffset(CGPoint(x: 0, y: max(-scroll.adjustedContentInset.top, scroll.contentSize.height - scroll.bounds.height + scroll.adjustedContentInset.bottom)), animated: false)
                try await Task.sleep(for: .milliseconds(200))
            }
            let image = UIGraphicsImageRenderer(bounds: window.bounds).image { _ in
                XCTAssertTrue(host.view.drawHierarchy(in: window.bounds, afterScreenUpdates: true))
            }
            let data = try XCTUnwrap(image.pngData()); XCTAssertGreaterThan(data.count, 20000)
            let url = URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("maintenance-\(page).png")
            try data.write(to: url); print("MAINTENANCE_PREVIEW=\(url.path)")
            window.isHidden = true
            window.rootViewController = nil
            try await Task.sleep(for: .milliseconds(50))
        }
        XCTAssertTrue(MaintenanceProtocol.requests.allSatisfy { $0.httpMethod == "GET" })
    }
}
