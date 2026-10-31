import XCTest
@testable import Wheel

@MainActor
final class ChartFavoriteMoveTests: XCTestCase {
    private func body(_ request: URLRequest) throws -> [String: Any] {
        var data = request.httpBody ?? Data()
        if let stream = request.httpBodyStream {
            stream.open(); defer { stream.close() }
            var buffer = [UInt8](repeating: 0, count: 4096)
            while stream.hasBytesAvailable {
                let count = stream.read(&buffer, maxLength: buffer.count)
                if count <= 0 { break }; data.append(buffer, count: count)
            }
        }
        return try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
    }
    private func settled(_ favorites: ChartFavorites) async throws {
        for _ in 0..<100 {
            if !favorites.busy { return }
            try await Task.sleep(for: .milliseconds(10))
        }
        XCTFail("Favorite request did not settle")
    }
    func testAnchoredMoveCachesConfirmedOrderAndReconcilesWithoutReplay() async throws {
        let name = "FavoriteMove-" + UUID().uuidString, defaults = UserDefaults(suiteName: name)!
        defer { defaults.removePersistentDomain(forName: name); MockProtocol.payload = nil; MockProtocol.fail = false }
        let config = URLSessionConfiguration.ephemeral; config.protocolClasses = [MockProtocol.self]
        let session = URLSession(configuration: config)
        MockProtocol.requests = []; MockProtocol.statusCode = 200; MockProtocol.fail = false
        var server: [[String: Any]] = (7...9).map { ["id": $0, "symbol": "TEST\($0)", "label": "TEST\($0)", "type": "STK", "exchange": "", "expiration": "", "right": ""] }
        var revision = 3, captured: [[String: Any]] = [], conflict = false
        MockProtocol.payload = { request in
            if request.httpMethod == "POST" {
                let op = try! self.body(request)["operations"] as! [[String: Any]]
                captured.append(contentsOf: op)
                if conflict { return ["revision": revision, "favorites": server, "conflicts": [["id": 7, "reason": "changed"]]] }
                let id = op[0]["id"] as! Int, item = server.remove(at: server.firstIndex { $0["id"] as? Int == id }!)
                let before = op[0]["before"] as? Int
                server.insert(item, at: before.flatMap { anchor in server.firstIndex { $0["id"] as? Int == anchor } } ?? server.count)
                revision += 1
            }
            return ["revision": revision, "favorites": server, "conflicts": []]
        }
        let phone = ChartFavorites(session: session, defaults: defaults)
        phone.configure(base: "https://fixture.invalid"); await phone.refresh()
        phone.move(from: IndexSet(integer: 2), to: 0)
        XCTAssertEqual(phone.items.map(\.id), [9,7,8]); XCTAssertTrue(phone.busy)
        phone.move(from: IndexSet(integer: 0), to: 3) // Busy: no second write.
        try await settled(phone)
        XCTAssertEqual(captured.count, 1)
        XCTAssertEqual(captured[0]["kind"] as? String, "move")
        XCTAssertEqual(captured[0]["id"] as? Int, 9)
        XCTAssertEqual(captured[0]["before"] as? Int, 7)
        XCTAssertEqual(captured[0]["base"] as? Int, 3)
        XCTAssertNil(captured[0]["value"])
        let reopened = ChartFavorites(session: session, defaults: defaults)
        reopened.configure(base: "https://fixture.invalid")
        XCTAssertEqual(reopened.items.map(\.id), [9,7,8])
        phone.move(from: IndexSet(integer: 0), to: 3); try await settled(phone)
        XCTAssertTrue(captured[1]["before"] is NSNull)
        XCTAssertEqual(phone.items.map(\.id), [7,8,9])
        conflict = true
        phone.move(from: IndexSet(integer: 0), to: 3); try await settled(phone)
        XCTAssertEqual(phone.items.map(\.id), [7,8,9]); XCTAssertNotNil(phone.message)
        conflict = false; MockProtocol.fail = true
        phone.move(from: IndexSet(integer: 0), to: 3); try await settled(phone)
        XCTAssertEqual(phone.items.map(\.id), [7,8,9]); XCTAssertFalse(phone.ready)
        let posts = MockProtocol.requests.filter { $0.httpMethod == "POST" }.count
        MockProtocol.fail = false; await phone.refresh()
        XCTAssertEqual(MockProtocol.requests.filter { $0.httpMethod == "POST" }.count, posts)
        XCTAssertTrue(phone.ready)
        phone.move(from: IndexSet(integer: 0), to: 1) // Unchanged drop.
        XCTAssertFalse(phone.busy)
        XCTAssertTrue(MockProtocol.requests.allSatisfy { $0.url?.path == "/api/chart-favorites" })
    }
}
