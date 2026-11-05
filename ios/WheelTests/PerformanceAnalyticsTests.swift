import XCTest
import SwiftUI
@testable import Wheel

final class PerformanceAnalyticsTests: XCTestCase {
    override func setUp() { AnalyticsProtocol.fail = false }
    static func payload(offset: Int = 0, version: String = "verified-1") -> Data {
        let days: [[String: Any]] = (1...30).map { day in
            ["date": String(format: "2026-10-%02d", day), "executions": day == 30 ? 51 : 0, "book_entries": day == 30 ? 1 : 0,
             "realized_pnl": day == 30 ? 156.11 : 0, "missing_pnl": 0]
        }
        let trades: [[String: Any]] = (offset..<min(offset + 50, 52)).map { index in
            ["id": "fill-\(index)", "ticker": "TQQQ", "option_type": "PUT", "expiration": "20261030", "strike": 60,
             "action": "BUY", "quantity": 1, "avg_fill_price": index == 0 ? 0 : 2.25, "fill_time": "2026-10-30T15:38:29+00:00",
             "currency": "USD", "commission": index == 0 ? 0 : 1.04, "commission_currency": "USD", "realized_pnl": 3.0021, "intent": "CLOSE",
             "record_type": index == 0 ? "Expiration" : "Execution"]
        }
        let body: [String: Any] = ["month": "2026-10", "months": ["2026-10", "2026-09"], "currency": "USD", "currencies": ["USD", "HKD"],
            "days": days, "summary": ["executions": 51, "book_entries": 1, "realized_pnl": 156.11, "missing_pnl": 0],
            "contributions": [["ticker": "TQQQ", "executions": 39, "book_entries": 1, "realized_pnl": 206.11], ["ticker": "TSLL", "executions": 12, "book_entries": 0, "realized_pnl": -50]],
            "trades": trades, "trade_count": 52, "next_offset": offset == 0 ? 50 : NSNull(),
            "report_through": "2026-10-30", "report_version": version, "refreshing": false]
        return try! JSONSerialization.data(withJSONObject: body)
    }
    private func session() -> URLSession {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [AnalyticsProtocol.self]
        return URLSession(configuration: config)
    }

    @MainActor func testPaginationEpochAndChangedSnapshot() async throws {
        AnalyticsProtocol.version = "verified-1"
        let model = PerformanceAnalyticsModel()
        let session = session()
        await model.load(base: "https://analytics.invalid", epoch: "live-epoch", month: "2026-10", currency: "USD", day: "2026-10-30", session: session)
        XCTAssertEqual(model.trades.count, 50)
        XCTAssertEqual(AnalyticsProtocol.lastRequest?.value(forHTTPHeaderField: "X-Wheel-Account-Epoch"), "live-epoch")
        await model.load(base: "https://analytics.invalid", epoch: "live-epoch", month: "2026-10", currency: "USD", day: "2026-10-30", offset: 50, session: session)
        XCTAssertEqual(model.trades.count, 52)
        XCTAssertNil(model.report?.next_offset)
        AnalyticsProtocol.version = "corrected-2"
        await model.load(base: "https://analytics.invalid", epoch: "live-epoch", month: "2026-10", currency: "USD", day: "2026-10-30", offset: 50, session: session)
        XCTAssertEqual(model.trades.count, 52)
        XCTAssertNotNil(model.error)
        await model.load(base: "https://analytics.invalid", epoch: "paper-epoch", session: session)
        XCTAssertEqual(model.trades.count, 50)
        XCTAssertEqual(model.report?.report_version, "corrected-2")
        XCTAssertNil(model.error)
    }

    @MainActor func testRefreshFailureRetainsSameAccountButNeverLeaksAcrossEpochs() async {
        let model = PerformanceAnalyticsModel()
        let session = session()
        await model.load(base: "https://analytics.invalid", epoch: "live", session: session)
        XCTAssertNotNil(model.report)
        AnalyticsProtocol.fail = true
        await model.load(base: "https://analytics.invalid", epoch: "live", refresh: true, session: session)
        XCTAssertNotNil(model.report)
        XCTAssertNotNil(model.error)
        await model.load(base: "https://analytics.invalid", epoch: "paper", session: session)
        XCTAssertNil(model.report)
        XCTAssertTrue(model.trades.isEmpty)
    }

    func testCalendarLeapYearAndUnknownValues() throws {
        let slots = AnalyticsCalendar.slots(month: "2028-02")
        XCTAssertEqual(slots.compactMap { $0 }.count, 29)
        XCTAssertEqual(slots.first!, nil)
        XCTAssertEqual(AnalyticsCalendar.amount(nil, currency: "USD"), "—")
        let report = try JSONDecoder().decode(PerformanceAnalytics.self, from: Self.payload())
        XCTAssertEqual(report.trades[0].contract, "TQQQ · 2026-10-30 · 60P")
        XCTAssertEqual(report.trades[0].time, "11:38:29")
        XCTAssertEqual(report.trades[0].record_type, "Expiration")
        XCTAssertEqual(report.trades[0].avg_fill_price, 0)
        XCTAssertEqual(report.days.last?.activityCount, 52)
        XCTAssertEqual(PerformanceAnalytics.activityLabel(51, report.summary.book_entries), "51 executions · 1 book entry")
    }

    @MainActor func testNativeCalendarAndExecutionLayouts() async throws {
        AnalyticsProtocol.version = "verified-1"
        URLProtocol.registerClass(AnalyticsProtocol.self)
        defer { URLProtocol.unregisterClass(AnalyticsProtocol.self) }
        let scene = try XCTUnwrap(UIApplication.shared.connectedScenes.first as? UIWindowScene)
        for dark in [false, true] {
            for width in [320.0, 393.0, 834.0] {
                for detail in [false, true] {
                    let root = Group {
                        if detail {
                            PerformanceExecutionView(base: "https://analytics.invalid", epoch: "test", month: "2026-10", currency: "USD", day: "2026-10-30")
                        } else {
                            PerformanceAnalyticsScreen(base: "https://analytics.invalid", epoch: "test").navigationTitle("Trade review")
                        }
                    }
                    let host = UIHostingController(rootView: NavigationStack { root }
                        .environment(\.scenePhase, .active).environment(\.locale, Locale(identifier: "en_US")))
                    let window = UIWindow(windowScene: scene)
                    window.frame = CGRect(x: 0, y: 0, width: width, height: 1000)
                    window.overrideUserInterfaceStyle = dark ? .dark : .light
                    window.rootViewController = host; window.makeKeyAndVisible(); host.view.frame = window.bounds
                    try await Task.sleep(for: .milliseconds(400))
                    host.view.layoutIfNeeded()
                    let image = UIGraphicsImageRenderer(bounds: host.view.bounds).image { _ in host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true) }
                    let attachment = XCTAttachment(image: image); attachment.name = "Analytics-\(detail ? "executions" : "calendar")-\(Int(width))-\(dark ? "dark" : "light")"; attachment.lifetime = .keepAlways
                    add(attachment)
                    window.rootViewController = nil; window.isHidden = true
                }
            }
        }
    }
}

private final class AnalyticsProtocol: URLProtocol {
    static var fail = false
    static var version = "verified-1"
    static var lastRequest: URLRequest?
    override class func canInit(with request: URLRequest) -> Bool { request.url?.host == "analytics.invalid" }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        Self.lastRequest = request
        if Self.fail {
            client?.urlProtocol(self, didFailWithError: URLError(.notConnectedToInternet))
            return
        }
        let offset = URLComponents(url: request.url!, resolvingAgainstBaseURL: false)?.queryItems?.first(where: { $0.name == "offset" })?.value.flatMap(Int.init) ?? 0
        client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: PerformanceAnalyticsTests.payload(offset: offset, version: Self.version))
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}
