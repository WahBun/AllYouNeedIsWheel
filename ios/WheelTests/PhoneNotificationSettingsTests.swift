import XCTest
import SwiftUI
@testable import Wheel

private final class NotificationProtocol: URLProtocol {
    static var requests: [URLRequest] = []
    static var reply: [String: Any] = ["enabled": true]
    static var status = 200
    static var fail = false
    static var hold = false
    static var pending: NotificationProtocol?
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        Self.requests.append(request)
        if Self.hold { Self.pending = self; return }
        finish()
    }
    func finish() {
        if Self.fail { client?.urlProtocol(self, didFailWithError: URLError(.timedOut)); return }
        client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: Self.status, httpVersion: nil, headerFields: nil)!, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: try! JSONSerialization.data(withJSONObject: Self.reply))
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

@MainActor
final class PhoneNotificationSettingsTests: XCTestCase {
    private let paper = NotificationAccount(address: "https://mock.invalid", mode: "paper", epoch: "paper-epoch")
    private func model() -> PhoneNotificationSettingsModel {
        NotificationProtocol.requests = []; NotificationProtocol.reply = ["enabled": true]
        NotificationProtocol.status = 200; NotificationProtocol.fail = false
        NotificationProtocol.hold = false; NotificationProtocol.pending = nil
        let config = URLSessionConfiguration.ephemeral; config.protocolClasses = [NotificationProtocol.self]
        return PhoneNotificationSettingsModel(session: URLSession(configuration: config))
    }
    private func body(_ request: URLRequest) throws -> [String: Any] {
        if let data = request.httpBody { return try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any]) }
        let stream = try XCTUnwrap(request.httpBodyStream); stream.open(); defer { stream.close() }
        var data = Data(); var buffer = [UInt8](repeating: 0, count: 4096)
        while stream.hasBytesAvailable { let count = stream.read(&buffer, maxLength: buffer.count); if count <= 0 { break }; data.append(buffer, count: count) }
        return try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
    }
    func testBarkReadEnableTestAndDisableUseExistingAccountScopedRoutes() async throws {
        let settings = model(); settings.select(paper)
        NotificationProtocol.reply = ["enabled": false]
        await settings.refresh(); XCTAssertEqual(settings.enabled, false)
        XCTAssertEqual(NotificationProtocol.requests.last?.httpMethod, "GET")
        settings.pushAddress = "  https://api.day.app/temporaryDeviceKey123  "
        NotificationProtocol.reply = ["enabled": true]
        await settings.save()
        XCTAssertEqual(settings.enabled, true); XCTAssertEqual(settings.pushAddress, "")
        XCTAssertEqual(try body(XCTUnwrap(NotificationProtocol.requests.last))["url"] as? String, "https://api.day.app/temporaryDeviceKey123")
        NotificationProtocol.reply = ["status": "queued"]
        await settings.sendTest()
        XCTAssertEqual(NotificationProtocol.requests.last?.url?.path, "/api/notifications/bark/test")
        XCTAssertNotNil(UUID(uuidString: try XCTUnwrap(body(XCTUnwrap(NotificationProtocol.requests.last))["id"] as? String)))
        XCTAssertEqual(settings.message, "Test queued. Check Bark on your iPhone.")
        NotificationProtocol.reply = ["enabled": false]
        await settings.disable(); XCTAssertEqual(settings.enabled, false)
        XCTAssertEqual(try body(XCTUnwrap(NotificationProtocol.requests.last))["enabled"] as? Bool, false)
        XCTAssertEqual(NotificationProtocol.requests.count, 4)
        XCTAssertTrue(NotificationProtocol.requests.allSatisfy {
            $0.value(forHTTPHeaderField: "X-Wheel-Account-Epoch") == paper.epoch &&
            $0.value(forHTTPHeaderField: "X-All-You-Need-Is-Wheel") == "1" && $0.url?.host == "mock.invalid"
        })
    }
    func testAccountChangeRejectsOldResponseAndClearsPrivateDraft() async throws {
        let settings = model(); settings.select(paper); settings.pushAddress = "private-old-address"
        NotificationProtocol.hold = true
        let old = Task { await settings.refresh() }
        for _ in 0..<100 where NotificationProtocol.pending == nil { try await Task.sleep(for: .milliseconds(10)) }
        let pending = try XCTUnwrap(NotificationProtocol.pending)
        let live = NotificationAccount(address: paper.address, mode: "live", epoch: "live-epoch")
        settings.select(live)
        pending.finish(); await old.value
        XCTAssertNil(settings.enabled); XCTAssertNil(settings.error); XCTAssertFalse(settings.busy)
        XCTAssertEqual(settings.pushAddress, "")
        NotificationProtocol.hold = false; NotificationProtocol.reply = ["enabled": false]
        await settings.refresh()
        XCTAssertEqual(settings.enabled, false)
        XCTAssertEqual(NotificationProtocol.requests.last?.value(forHTTPHeaderField: "X-Wheel-Account-Epoch"), live.epoch)
    }
    func testUncertainWritesAreNotRetriedOrReportedAsOff() async throws {
        let settings = model(); settings.select(paper); await settings.refresh()
        NotificationProtocol.fail = true
        await settings.disable()
        XCTAssertNil(settings.enabled); XCTAssertNotNil(settings.error)
        XCTAssertEqual(NotificationProtocol.requests.count, 2)
        settings.select(nil); await settings.refresh(); await settings.sendTest(); await settings.disable()
        XCTAssertEqual(NotificationProtocol.requests.count, 2)
        XCTAssertNil(settings.enabled)
    }
    func testBadStatusAndMalformedResponseStayUnavailable() async {
        let settings = model(); settings.select(paper)
        for status in [200, 409, 503] {
            NotificationProtocol.status = status; NotificationProtocol.reply = [:]
            await settings.refresh()
            XCTAssertNil(settings.enabled); XCTAssertNotNil(settings.error); XCTAssertFalse(settings.busy)
        }
        XCTAssertEqual(NotificationProtocol.requests.count, 3)
    }
    func testNotificationPagesRenderInBothThemesAndLargeText() async throws {
        let settings = model(); settings.select(paper); await settings.refresh()
        let config = URLSessionConfiguration.ephemeral; config.protocolClasses = [NotificationProtocol.self]
        let store = WheelStore(session: URLSession(configuration: config))
        store.address = paper.address; store.demo = false; store.trading.accountEpoch = paper.epoch
        store.portfolio = Bootstrap(summary: Summary(account_value: 1000, cash_balance: 1000), positions: [],
                                    connection: AccountConnection(account_epoch: paper.epoch, mode: "paper", execution_enabled: false, chart_execution_enabled: false))
        let scene = try XCTUnwrap(UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first)
        for dark in [false, true] {
            for page in ["home", "enabled", "setup", "large"] {
                NotificationProtocol.reply = ["enabled": page != "setup"]
                await settings.refresh()
                let root = NavigationStack {
                    if page == "home" {
                        SettingsView(notificationSettings: settings)
                    } else { PhoneNotificationDetails(settings: settings) }
                }.environment(store).environment(\.locale, Locale(identifier: "en"))
                    .environment(\.dynamicTypeSize, page == "large" ? .accessibility2 : .large)
                let host = UIHostingController(rootView: root)
                let window = UIWindow(windowScene: scene); window.frame = CGRect(x: 0, y: 0, width: 393, height: 852)
                window.overrideUserInterfaceStyle = dark ? .dark : .light
                window.rootViewController = host; window.makeKeyAndVisible()
                host.view.frame = window.bounds; host.view.layoutIfNeeded()
                try await Task.sleep(for: .milliseconds(400))
                let image = UIGraphicsImageRenderer(bounds: window.bounds).image { _ in
                    XCTAssertTrue(host.view.drawHierarchy(in: window.bounds, afterScreenUpdates: true))
                }
                let data = try XCTUnwrap(image.pngData()); XCTAssertGreaterThan(data.count, 20000)
                let url = URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("phone-notifications-\(page)-\(dark ? "dark" : "light").png")
                try data.write(to: url); print("PHONE_NOTIFICATIONS_PREVIEW=\(url.path)")
                window.isHidden = true
            }
        }
    }
}
