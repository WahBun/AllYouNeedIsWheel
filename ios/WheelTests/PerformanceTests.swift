import XCTest
import SwiftUI
@testable import Wheel

final class PerformanceTests: XCTestCase {
    @MainActor
    func testColdBootstrapHasFullYearBeforeNavigationWithoutHistoryNetwork() async throws {
        PerformancePageProtocol.reset()
        PerformancePageProtocol.bootstrapHistory = true
        PerformancePageProtocol.holdHistory = true
        URLProtocol.registerClass(PerformancePageProtocol.self)
        let savedMode = UserDefaults.standard.object(forKey: "selectedBrokerMode")
        UserDefaults.standard.set("live", forKey: "selectedBrokerMode")
        defer {
            PerformancePageProtocol.bootstrapHistory = false
            PerformancePageProtocol.holdHistory = false
            URLProtocol.unregisterClass(PerformancePageProtocol.self)
            UserDefaults.standard.set(savedMode, forKey: "selectedBrokerMode")
        }
        let config = URLSessionConfiguration.ephemeral; config.protocolClasses = [PerformancePageProtocol.self]
        let store = WheelStore(session: URLSession(configuration: config))
        store.address = "https://performance.invalid"; store.selectedTab = "settings"
        try await store.completeAccountConnection(to: store.address, mode: "live", epoch: "first")
        XCTAssertEqual(store.selectedTab, "portfolio")
        let key = store.performanceCacheKey("YTD")
        XCTAssertEqual(store.performanceHistoryCache[key]?.points.count, 210)
        await store.warmPerformanceHistory()
        XCTAssertEqual(PerformancePageProtocol.historyCount, 0, "Bootstrap must already carry the history; no warm request is needed")
        let route = PerformanceTestRoute()
        let controller = UIHostingController(rootView: PerformanceTestNavigation(route: route)
            .environment(store).environment(\.scenePhase, .active).environment(\.locale, Locale(identifier: "en")))
        let scene = try XCTUnwrap(UIApplication.shared.connectedScenes.first as? UIWindowScene)
        let window = UIWindow(windowScene: scene)
        window.rootViewController = controller; window.makeKeyAndVisible()
        defer { window.rootViewController = nil; window.isHidden = true }
        try await Task.sleep(for: .milliseconds(100))
        let start = Date.now
        route.path = ["performance"]
        try await Task.sleep(for: .milliseconds(450))
        controller.view.layoutIfNeeded()
        let elapsed = Date.now.timeIntervalSince(start)
        print("BOOTSTRAP_HISTORY_ENTRY_SECONDS \(elapsed)")
        XCTAssertLessThan(elapsed, 1)
        XCTAssertEqual(store.performanceHistoryCache[key]?.points.count, 210)
        try await Task.sleep(for: .milliseconds(400)) // Capture after the native push animation settles.
        capture(controller, "Performance-full-year-on-entry-network-held")
    }

    @MainActor
    func testFullYearEntryRenderTiming() async throws {
        PerformancePageProtocol.reset()
        PerformancePageProtocol.fullYear = true
        URLProtocol.registerClass(PerformancePageProtocol.self)
        defer { PerformancePageProtocol.fullYear = false; URLProtocol.unregisterClass(PerformancePageProtocol.self) }
        let store = WheelStore(); store.demo = false; store.address = "https://performance.invalid"
        store.selectedTab = "portfolio"
        store.portfolio = Bootstrap(summary: Summary(account_value: 1000, cash_balance: 500), positions: [])
        let warmStart = Date.now
        await store.warmPerformanceHistory()
        print("FULL_YEAR_WARM_SECONDS \(Date.now.timeIntervalSince(warmStart))")
        XCTAssertEqual(store.performanceHistoryCache[store.performanceCacheKey("YTD")]?.points.count, 210)
        let controller = UIHostingController(rootView: NavigationStack { PerformanceView() }
            .environment(store).environment(\.scenePhase, .active).environment(\.locale, Locale(identifier: "en")))
        let scene = try XCTUnwrap(UIApplication.shared.connectedScenes.first as? UIWindowScene)
        let window = UIWindow(windowScene: scene)
        let start = Date.now
        window.rootViewController = controller; window.makeKeyAndVisible()
        try await Task.sleep(for: .milliseconds(100))
        controller.view.layoutIfNeeded()
        print("FULL_YEAR_RENDER_SECONDS \(Date.now.timeIntervalSince(start))")
        capture(controller, "Performance-full-year")
        window.rootViewController = nil; window.isHidden = true
    }

    @MainActor
    func testRootWarmsPerformanceAfterPortfolioArrives() async throws {
        PerformancePageProtocol.reset()
        URLProtocol.registerClass(PerformancePageProtocol.self)
        let savedMode = UserDefaults.standard.object(forKey: "selectedBrokerMode")
        UserDefaults.standard.set("live", forKey: "selectedBrokerMode")
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [PerformancePageProtocol.self]
        let store = WheelStore(session: URLSession(configuration: configuration))
        store.demo = false; store.address = "https://performance.invalid"; store.selectedTab = "portfolio"
        let controller = UIHostingController(rootView: RootView().environment(store)
            .environment(\.scenePhase, .active).environment(\.locale, Locale(identifier: "en")))
        let scene = try XCTUnwrap(UIApplication.shared.connectedScenes.first as? UIWindowScene)
        let window = UIWindow(windowScene: scene)
        window.rootViewController = controller; window.makeKeyAndVisible()
        defer {
            window.rootViewController = nil; window.isHidden = true
            UserDefaults.standard.set(savedMode, forKey: "selectedBrokerMode")
            URLProtocol.unregisterClass(PerformancePageProtocol.self)
        }
        for _ in 0..<40 {
            if store.performanceHistoryCache[store.performanceCacheKey("YTD")] != nil { break }
            try await Task.sleep(for: .milliseconds(50))
        }
        XCTAssertNotNil(store.portfolio)
        XCTAssertEqual(store.performanceHistoryCache[store.performanceCacheKey("YTD")]?.points.count, 3)
        XCTAssertEqual(PerformancePageProtocol.historyCount, 1)
        capture(controller, "Portfolio-connected-with-performance-preloaded")
    }

    @MainActor
    func testPortfolioTitleSurvivesScrolling() async throws {
        let store = WheelStore(); store.demo = false; store.updated = .now
        store.portfolio = Bootstrap(summary: Summary(account_value: 1000, cash_balance: 500),
            positions: (0..<20).map { Position(symbol: "TEST\($0)", position: 1, market_price: 10, security_type: "STK", con_id: $0 + 1) },
            connection: AccountConnection(mode: "live", execution_enabled: false, chart_execution_enabled: false))
        let controller = UIHostingController(rootView: NavigationStack { PortfolioView() }
            .environment(store).environment(\.locale, Locale(identifier: "en")))
        let scene = try XCTUnwrap(UIApplication.shared.connectedScenes.first as? UIWindowScene)
        let window = UIWindow(windowScene: scene)
        window.rootViewController = controller; window.makeKeyAndVisible()
        defer { window.rootViewController = nil; window.isHidden = true }
        try await Task.sleep(for: .milliseconds(300))
        func descendants(_ view: UIView) -> [UIView] { [view] + view.subviews.flatMap(descendants) }
        let scroll = try XCTUnwrap(descendants(controller.view).compactMap { $0 as? UICollectionView }.first)
        scroll.setContentOffset(CGPoint(x: 0, y: 400), animated: false)
        try await Task.sleep(for: .milliseconds(200))
        capture(controller, "Portfolio-scrolled-title-preserved")
        XCTAssertGreaterThan(scroll.contentOffset.y, 300)
    }

    @MainActor
    func testPortfolioStatusPreview() async throws {
        let store = WheelStore(); store.demo = false; store.address = "https://performance.invalid"
        store.selectedTab = "portfolio"; store.updated = .now
        store.portfolio = Bootstrap(summary: Summary(account_value: 23500, cash_balance: 1000, is_frozen: true,
            initial_margin: 6900, leverage_percentage: 29.6), positions: [],
            connection: AccountConnection(mode: "live", execution_enabled: false, chart_execution_enabled: false))
        let scene = try XCTUnwrap(UIApplication.shared.connectedScenes.first as? UIWindowScene)
        for dark in [false, true] {
            for width in [320.0, 393.0, 768.0] {
                let controller = UIHostingController(rootView: NavigationStack { PortfolioView() }
                    .environment(store).environment(\.locale, Locale(identifier: "en"))
                    .environment(\.scenePhase, .active))
                let window = UIWindow(windowScene: scene)
                window.frame = CGRect(x: 0, y: 0, width: width, height: 852)
                window.overrideUserInterfaceStyle = dark ? .dark : .light
                window.rootViewController = controller; window.makeKeyAndVisible(); controller.view.frame = window.bounds
                try await Task.sleep(for: .milliseconds(300))
                capture(controller, "Portfolio-status-\(Int(width))-\(dark ? "dark" : "light")")
                window.rootViewController = nil; window.isHidden = true
            }
        }
    }

    @MainActor
    func testPortfolioWarmHistorySurvivesNavigationAndDelayedRefresh() async throws {
        PerformancePageProtocol.reset()
        URLProtocol.registerClass(PerformancePageProtocol.self)
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [PerformancePageProtocol.self]
        let store = WheelStore(session: URLSession(configuration: configuration))
        store.demo = false; store.address = "https://performance.invalid"; store.selectedTab = "portfolio"
        store.trading.accountEpoch = "first"
        store.portfolio = Bootstrap(summary: Summary(account_value: 1000, cash_balance: 500), positions: [])
        await store.warmPerformanceHistory()
        let key = store.performanceCacheKey("YTD")
        XCTAssertEqual(store.performanceHistoryCache[key]?.points.count, 3)
        await store.warmPerformanceHistory()
        XCTAssertEqual(PerformancePageProtocol.historyCount, 1, "Portfolio refresh must not repeatedly warm the same cache")
        PerformancePageProtocol.holdHistory = true
        let route = PerformanceTestRoute()
        let controller = UIHostingController(rootView: PerformanceTestNavigation(route: route)
            .environment(store).environment(\.scenePhase, .active).environment(\.locale, Locale(identifier: "en")))
        let scene = try XCTUnwrap(UIApplication.shared.connectedScenes.first as? UIWindowScene)
        let window = UIWindow(windowScene: scene)
        window.rootViewController = controller; window.makeKeyAndVisible()
        defer {
            window.rootViewController = nil; window.isHidden = true
            PerformancePageProtocol.holdHistory = false
            URLProtocol.unregisterClass(PerformancePageProtocol.self)
        }
        try await Task.sleep(for: .milliseconds(100))
        for entry in 1...2 {
            route.path = ["performance"]
            try await Task.sleep(for: .milliseconds(500))
            XCTAssertEqual(store.performanceHistoryCache[key]?.points.last?.portfolio, 12)
            capture(controller, "Performance-cached-entry-\(entry)-while-network-held")
            route.path = []
            try await Task.sleep(for: .milliseconds(400))
        }
        XCTAssertGreaterThanOrEqual(PerformancePageProtocol.historyCount, 3)
        // An old backend/account cache cannot be selected after a context change.
        store.trading.accountEpoch = "second"
        XCTAssertNil(store.performanceHistoryCache[store.performanceCacheKey("YTD")])
        store.changeMode()
        XCTAssertTrue(store.performanceHistoryCache.isEmpty)
    }

    @MainActor
    func testDelayedWarmResponseCannotRepopulateChangedAccount() async throws {
        PerformancePageProtocol.reset()
        PerformancePageProtocol.holdHistory = true
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [PerformancePageProtocol.self]
        let store = WheelStore(session: URLSession(configuration: configuration))
        store.demo = false; store.address = "https://performance.invalid"
        store.trading.accountEpoch = "old"
        store.portfolio = Bootstrap(summary: Summary(account_value: 1000, cash_balance: 500), positions: [])
        let task = Task { await store.warmPerformanceHistory() }
        defer { task.cancel(); PerformancePageProtocol.holdHistory = false }
        for _ in 0..<20 {
            if PerformancePageProtocol.historyCount > 0 { break }
            try await Task.sleep(for: .milliseconds(25))
        }
        XCTAssertEqual(PerformancePageProtocol.historyCount, 1)
        store.changeMode(); store.trading.accountEpoch = "new"
        PerformancePageProtocol.releaseHistory()
        await task.value
        XCTAssertTrue(store.performanceHistoryCache.isEmpty)
    }

    @MainActor
    private func capture(_ controller: UIViewController, _ name: String) {
        controller.view.layoutIfNeeded()
        let image = UIGraphicsImageRenderer(bounds: controller.view.bounds).image { _ in
            controller.view.drawHierarchy(in: controller.view.bounds, afterScreenUpdates: true)
        }
        let attachment = XCTAttachment(image: image); attachment.name = name; attachment.lifetime = .keepAlways
        add(attachment)
    }

    @MainActor
    func testPageContinuesLiveReadsWhileBenchmarkIsMissing() async throws {
        PerformancePageProtocol.reset(staleFirst: true)
        URLProtocol.registerClass(PerformancePageProtocol.self)
        let store = WheelStore()
        store.demo = false; store.address = "https://performance.invalid"; store.selectedTab = "portfolio"
        let controller = UIHostingController(rootView: NavigationStack {
            PerformanceView().environment(store).environment(\.scenePhase, .active)
        }.environment(\.locale, Locale(identifier: "en")))
        let scene = try XCTUnwrap(UIApplication.shared.connectedScenes.first as? UIWindowScene)
        let window = UIWindow(windowScene: scene)
        window.rootViewController = controller; window.makeKeyAndVisible()
        defer { window.rootViewController = nil; window.isHidden = true; URLProtocol.unregisterClass(PerformancePageProtocol.self) }
        for _ in 0..<20 {
            if PerformancePageProtocol.liveCount >= 1 { break }
            try await Task.sleep(for: .milliseconds(100))
        }
        for _ in 0..<15 {
            if PerformancePageProtocol.firstFreshDelay.isFinite { break }
            try await Task.sleep(for: .milliseconds(100))
        }
        XCTAssertLessThan(PerformancePageProtocol.firstFreshDelay, 1.5, "Cold subscription must not wait five seconds")
        print("Performance first fresh value seconds: \(PerformancePageProtocol.firstFreshDelay)")
        try await Task.sleep(for: .milliseconds(300))
        func capture(_ name: String) {
            controller.view.layoutIfNeeded()
            let image = UIGraphicsImageRenderer(bounds: controller.view.bounds).image { _ in
                controller.view.drawHierarchy(in: controller.view.bounds, afterScreenUpdates: true)
            }
            let attachment = XCTAttachment(image: image); attachment.name = name; attachment.lifetime = .keepAlways
            add(attachment)
        }
        capture("Performance-positive-live-PnL")
        let firstReadCount = PerformancePageProtocol.liveCount
        PerformancePageProtocol.setPnl(-10)
        for _ in 0..<18 {
            if PerformancePageProtocol.liveCount > firstReadCount { break }
            try await Task.sleep(for: .milliseconds(100))
        }
        try await Task.sleep(for: .milliseconds(300))
        capture("Performance-next-live-PnL")
        XCTAssertGreaterThan(PerformancePageProtocol.liveCount, firstReadCount)
        XCTAssertTrue(PerformancePageProtocol.independentHistoryRequested)
    }

    private func history() throws -> PerformanceHistory {
        try JSONDecoder().decode(PerformanceHistory.self, from: Data("""
        {"points":[{"date":"2026-10-15","portfolio":10,"spx":5,"nq100":6},
                   {"date":"2026-10-16","portfolio":12,"spx":7,"nq100":null}],
         "start":"2025-12-31","end":"2026-10-16","limited_history":false,"stale":false,
         "latest":{"date":"2026-10-16","nav":1000}}
        """.utf8))
    }

    func testDelayedBenchmarkDoesNotFreezeIntradayAccountReturn() throws {
        let history = try history()
        let now = try XCTUnwrap(ISO8601DateFormatter().date(from: "2026-10-19T17:30:00Z"))
        let gain = PerformanceLive(daily_pnl: 25, fresh: true, received_at: "2026-10-19T17:30:00Z")
        let loss = PerformanceLive(daily_pnl: -10, fresh: true, received_at: "2026-10-19T17:30:05Z")
        XCTAssertNil(history.points.last?.nq100, "A missing close must not become zero or a carried-forward price")
        XCTAssertEqual(history.points.last?.spx, 7)
        XCTAssertEqual(try XCTUnwrap(history.intradayEstimate(gain, now: now)), 14.8, accuracy: 0.00001)
        XCTAssertEqual(try XCTUnwrap(history.intradayEstimate(loss, now: now.addingTimeInterval(5))), 10.88, accuracy: 0.00001)
    }

    func testEstimateStillRejectsStalePnlAndOutsideSession() throws {
        let history = try history()
        let now = try XCTUnwrap(ISO8601DateFormatter().date(from: "2026-10-19T17:30:00Z"))
        XCTAssertNil(history.intradayEstimate(PerformanceLive(daily_pnl: 25, fresh: false, received_at: "2026-10-19T17:30:00Z"), now: now))
        XCTAssertNil(history.intradayEstimate(PerformanceLive(daily_pnl: 25, fresh: true, received_at: "2026-10-16T17:30:00Z"), now: now))
        XCTAssertNil(history.intradayEstimate(PerformanceLive(daily_pnl: 25, fresh: true, received_at: "2026-10-19T21:00:00Z"), now: now.addingTimeInterval(12600)))
        XCTAssertNil(history.intradayEstimate(nil, now: now))
    }
}

@MainActor @Observable private final class PerformanceTestRoute { var path: [String] = [] }
private struct PerformanceTestNavigation: View {
    @Bindable var route: PerformanceTestRoute
    var body: some View {
        NavigationStack(path: $route.path) {
            Text("Portfolio").navigationTitle("Portfolio")
                .navigationDestination(for: String.self) { _ in PerformanceView() }
        }
    }
}

private final class PerformancePageProtocol: URLProtocol {
    private static let lock = NSLock()
    static var bootstrapHistory = false
    static var fullYear = false
    private static var reads = 0
    private static var independent = false
    private static var pnl = 25
    private static var staleFirst = false
    private static var readTimes: [Date] = []
    private static var firstFreshAt: Date?
    private static var historyReads = 0
    private static var held: [PerformancePageProtocol] = []
    private static var holding = false
    static var holdHistory: Bool {
        get { lock.withLock { holding } }
        set { lock.withLock { holding = newValue } }
    }
    static var historyCount: Int { lock.withLock { historyReads } }
    static func releaseHistory() {
        let pending = lock.withLock { let pending = held; held = []; holding = false; return pending }
        for request in pending { request.respond() }
    }
    static var firstFreshDelay: TimeInterval { lock.withLock { guard let first = readTimes.first, let fresh = firstFreshAt else { return .infinity }; return fresh.timeIntervalSince(first) } }
    static var liveCount: Int { lock.withLock { reads } }
    static var independentHistoryRequested: Bool { lock.withLock { independent } }
    static func reset(staleFirst: Bool = false) { lock.withLock { reads = 0; independent = false; pnl = 25; Self.staleFirst = staleFirst; readTimes = []; firstFreshAt = nil; historyReads = 0; holding = false; held = [] } }
    static func setPnl(_ value: Int) { lock.withLock { pnl = value } }
    override class func canInit(with request: URLRequest) -> Bool { request.url?.host == "performance.invalid" }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        if request.url?.lastPathComponent == "history" {
            let held = Self.lock.withLock {
                Self.historyReads += 1
                if Self.holding { Self.held.append(self); return true }
                return false
            }
            if held { return }
        }
        respond()
    }
    private func respond() {
        let data: Data
        if request.url?.path.contains("/performance/") != true {
            data = Data("""
            {"summary":{"account_value":23500,"cash_balance":1000,"is_frozen":true},
             "positions":[],"is_frozen":true,"connection":{"mode":"live","account_epoch":"first",
             "execution_enabled":false,"chart_execution_enabled":false},
             "orders":[],"success":true,"total_income":0,"positions_count":0}
            """.utf8)
        } else if request.url?.lastPathComponent == "live" {
            let (pnl, fresh) = Self.lock.withLock {
                let now = Date.now
                Self.reads += 1; Self.readTimes.append(now)
                let fresh = !Self.staleFirst || now.timeIntervalSince(Self.readTimes[0]) >= 0.3
                if fresh && Self.firstFreshAt == nil { Self.firstFreshAt = now }
                return (Self.pnl, fresh)
            }
            let stamp = ISO8601DateFormatter().string(from: .now)
            data = try! JSONSerialization.data(withJSONObject: ["daily_pnl":pnl,"fresh":fresh,"received_at":stamp])
        } else if Self.fullYear {
            data = Self.fullYearData()
        } else {
            Self.lock.withLock { Self.independent = request.url?.query?.contains("include_unmatched=1") == true }
            data = Data("""
            {"points":[{"date":"2025-12-31","portfolio":0,"spx":0,"nq100":0},
                       {"date":"2026-10-15","portfolio":10,"spx":5,"nq100":6},
                       {"date":"2026-10-16","portfolio":12,"spx":7,"nq100":null}],
             "start":"2025-12-31","end":"2026-10-16","limited_history":false,"stale":false,
             "warning":"Benchmark history is delayed; portfolio history includes the latest report.",
             "latest":{"date":"2026-10-16","nav":1000}}
            """.utf8)
        }
        client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: ["Content-Type":"application/json"])!, cacheStoragePolicy: .notAllowed)
        var delivered = data
        if Self.bootstrapHistory, request.url?.path.hasSuffix("/bootstrap") == true {
            var payload = try! JSONSerialization.jsonObject(with: data) as! [String: Any]
            payload["performance_history"] = try! JSONSerialization.jsonObject(with: Self.fullYearData())
            delivered = try! JSONSerialization.data(withJSONObject: payload)
        }
        client?.urlProtocol(self, didLoad: delivered)
        client?.urlProtocolDidFinishLoading(self)
    }
    static func fullYearData() -> Data {
            let start = ISO8601DateFormatter().date(from: "2026-01-01T16:00:00Z")!
            let formatter = DateFormatter(); formatter.dateFormat = "yyyy-MM-dd"; formatter.timeZone = TimeZone(secondsFromGMT: 0)
            var points: [[String: Any]] = []
            for i in 0..<210 {
                let value = Double(i)
                let stamp = formatter.string(from: start.addingTimeInterval(value * 86400))
                points.append(["date": stamp, "portfolio": value / 10 - 5, "spx": value / 20, "nq100": value / 15])
            }
            return try! JSONSerialization.data(withJSONObject: ["points": points, "start": points.first!["date"]!, "end": points.last!["date"]!, "limited_history": false, "stale": false])
    }
    override func stopLoading() { Self.lock.withLock { Self.held.removeAll { $0 === self } } }
}
