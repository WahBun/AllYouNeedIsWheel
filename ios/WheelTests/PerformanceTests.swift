import XCTest
import SwiftUI
@testable import Wheel

final class PerformanceTests: XCTestCase {
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

private final class PerformancePageProtocol: URLProtocol {
    private static let lock = NSLock()
    private static var reads = 0
    private static var independent = false
    private static var pnl = 25
    private static var staleFirst = false
    private static var readTimes: [Date] = []
    private static var firstFreshAt: Date?
    static var firstFreshDelay: TimeInterval { lock.withLock { guard let first = readTimes.first, let fresh = firstFreshAt else { return .infinity }; return fresh.timeIntervalSince(first) } }
    static var liveCount: Int { lock.withLock { reads } }
    static var independentHistoryRequested: Bool { lock.withLock { independent } }
    static func reset(staleFirst: Bool = false) { lock.withLock { reads = 0; independent = false; pnl = 25; Self.staleFirst = staleFirst; readTimes = []; firstFreshAt = nil } }
    static func setPnl(_ value: Int) { lock.withLock { pnl = value } }
    override class func canInit(with request: URLRequest) -> Bool { request.url?.host == "performance.invalid" }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        let data: Data
        if request.url?.lastPathComponent == "live" {
            let (pnl, fresh) = Self.lock.withLock {
                let now = Date.now
                Self.reads += 1; Self.readTimes.append(now)
                let fresh = !Self.staleFirst || now.timeIntervalSince(Self.readTimes[0]) >= 0.3
                if fresh && Self.firstFreshAt == nil { Self.firstFreshAt = now }
                return (Self.pnl, fresh)
            }
            let stamp = ISO8601DateFormatter().string(from: .now)
            data = try! JSONSerialization.data(withJSONObject: ["daily_pnl":pnl,"fresh":fresh,"received_at":stamp])
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
        client?.urlProtocol(self, didLoad: data)
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}
