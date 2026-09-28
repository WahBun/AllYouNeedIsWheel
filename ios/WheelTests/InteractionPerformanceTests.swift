import XCTest
@testable import Wheel

@MainActor
final class InteractionPerformanceTests: XCTestCase {
    func testTradingReadsUseCacheOnlyForContractLists() async throws {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [MockProtocol.self]
        MockProtocol.requests = []; MockProtocol.fail = false; MockProtocol.statusCode = 200
        MockProtocol.payload = { request in
            if request.url?.lastPathComponent == "expirations" { return ["expirations": [["value": "20261016"]]] }
            if request.url?.lastPathComponent == "strikes" { return ["strikes": [10.0, 11.0]] }
            return ["data": [:]]
        }
        defer { MockProtocol.payload = nil; MockProtocol.requests = [] }
        let trading = TradingSession(session: URLSession(configuration: config))
        for _ in 0..<5 {
            _ = try await trading.get("api/options/expirations", base: "https://example.test")
            _ = try await trading.get("api/options/strikes", base: "https://example.test")
        }
        XCTAssertEqual(MockProtocol.requests.count, 2)
        for _ in 0..<2 { _ = try await trading.get("api/options/otm", base: "https://example.test") }
        XCTAssertEqual(MockProtocol.requests.count, 4)
        trading.resetContext()
        _ = try await trading.get("api/options/strikes", base: "https://example.test")
        XCTAssertEqual(MockProtocol.requests.count, 5)
    }

    func testRepeatedMetadataUsesOneReadAndExpires() async throws {
        var date = Date(timeIntervalSince1970: 1_790_000_000)
        let cache = ContractMetadataCache(now: { date })
        let url = URL(string: "https://example.test/api/options/strikes?ticker=TEST&expiration=20261016")!
        var calls = 0
        for _ in 0..<10 {
            _ = try await cache.load(url) { calls += 1; return ["strikes": [10.0, 11.0]] }
        }
        XCTAssertEqual(calls, 1)
        date.addTimeInterval(301)
        _ = try await cache.load(url) { calls += 1; return ["strikes": [12.0]] }
        XCTAssertEqual(calls, 2)
        cache.clear()
        _ = try await cache.load(url) { calls += 1; return ["strikes": [13.0]] }
        XCTAssertEqual(calls, 3)
    }

    func testQuotesNeverUseMetadataCache() async throws {
        let cache = ContractMetadataCache()
        var calls = 0
        for _ in 0..<3 {
            _ = try await cache.load(URL(string: "https://example.test/api/options/otm")!) { calls += 1; return ["strikes": [10.0]] }
        }
        XCTAssertEqual(calls, 3)
    }

    func testDifferentContractAndBackendAreIsolated() async throws {
        let cache = ContractMetadataCache()
        var calls = 0
        for address in ["https://a.test/strikes?expiration=20261016", "https://a.test/strikes?expiration=20261120", "https://b.test/strikes?expiration=20261016"] {
            _ = try await cache.load(URL(string: address)!) { calls += 1; return ["strikes": [10.0]] }
        }
        XCTAssertEqual(calls, 3)
    }

    func testEmptyAndFailedResponsesAreNotCached() async throws {
        let cache = ContractMetadataCache()
        let url = URL(string: "https://example.test/expirations")!
        var calls = 0
        do { _ = try await cache.load(url) { calls += 1; throw URLError(.timedOut) }; XCTFail() } catch {}
        _ = try await cache.load(url) { calls += 1; return ["expirations": []] }
        _ = try await cache.load(url) { calls += 1; return ["expirations": [["value": "20261016"]]] }
        XCTAssertEqual(calls, 3)
    }

    func testNewYorkDayBoundaryInvalidatesMetadata() async throws {
        var date = ISO8601DateFormatter().date(from: "2026-09-29T03:59:59Z")!
        let cache = ContractMetadataCache(now: { date })
        let url = URL(string: "https://example.test/expirations")!
        var calls = 0
        _ = try await cache.load(url) { calls += 1; return ["expirations": [["value": "20261016"]]] }
        date.addTimeInterval(2)
        _ = try await cache.load(url) { calls += 1; return ["expirations": [["value": "20261016"]]] }
        XCTAssertEqual(calls, 2)
    }

    func testConcurrentMetadataReadsShareFetch() async throws {
        let cache = ContractMetadataCache()
        let url = URL(string: "https://example.test/strikes")!
        var calls = 0
        let first = Task { try await cache.load(url) {
            calls += 1
            try await Task.sleep(for: .milliseconds(50))
            return ["strikes": [10.0]]
        } }
        let second = Task { try await cache.load(url) { calls += 1; return ["strikes": [11.0]] } }
        let a = try await first.value
        let b = try await second.value
        XCTAssertEqual(calls, 1)
        XCTAssertEqual(a["strikes"] as? [Double], b["strikes"] as? [Double])
    }
}
