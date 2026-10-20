import XCTest
import SwiftUI
@testable import Wheel

@MainActor
final class ChartInstrumentTests: XCTestCase {
    private let exact: [String: Any] = ["con_id": 899193475, "symbol": "TSLL", "local_symbol": "TSLL 20261120 11 CALL",
        "security_type": "OPT", "exchange": "SMART", "expiration": "20261120", "right": "C", "strike": 11.0]
    func testTradeDetailChartUsesSelectedCallAndPutContract() throws {
        for type in ["CALL", "PUT"] {
            var row = OpportunityRow(ticker: "TSLL", type: type)
            row.quote = ContractQuote(strike: 10, expiration: "20261120")
            var preference = OpportunityPreference()
            preference.expiration = "20261120"; preference.strike = 11
            let selected = try XCTUnwrap(OpportunityChartContract(row: row, preference: preference))
            let right = type == "CALL" ? "C" : "P"
            XCTAssertEqual(Dictionary(uniqueKeysWithValues: selected.query.map { ($0.name, $0.value ?? "") }),
                           ["type": "OPT", "q": "TSLL", "expiration": "20261120", "right": right, "strike": "11.0"])
            var contract = exact; contract["right"] = right
            let position = try selected.resolve(["contracts": [contract]])
            XCTAssertEqual(position.con_id, 899193475)
            XCTAssertEqual(position.symbol, "TSLL")
            XCTAssertEqual(position.security_type, "OPT")
            XCTAssertEqual(position.strike, 11)
            XCTAssertEqual(position.expiration, "20261120")
            XCTAssertEqual(position.option_type, right)
            XCTAssertEqual(position.position, 0)
        }
    }
    func testTradeDetailChartRejectsWrongOrAmbiguousContracts() throws {
        var row = OpportunityRow(ticker: "TSLL", type: "CALL")
        row.quote = ContractQuote(strike: 11, expiration: "20261120")
        var preference = OpportunityPreference(); preference.expiration = "20261120"
        let selected = try XCTUnwrap(OpportunityChartContract(row: row, preference: preference))
        for (key, value) in [("symbol", "TQQQ"), ("expiration", "20261218"), ("right", "P"), ("security_type", "STK")] {
            var wrong = exact; wrong[key] = value
            XCTAssertThrowsError(try selected.resolve(["contracts": [wrong]]))
        }
        var wrongStrike = exact; wrongStrike["strike"] = 12.0
        var invalidID = exact; invalidID["con_id"] = 0
        for contracts in [[], [exact, exact], [wrongStrike], [invalidID]] {
            XCTAssertThrowsError(try selected.resolve(["contracts": contracts]))
        }
    }
    func testTradeDetailChartWaitsForSelectionAndRejectsOldExpiration() {
        var row = OpportunityRow(ticker: "TSLL", type: "PUT")
        var preference = OpportunityPreference(); preference.expiration = "20261120"
        XCTAssertNil(OpportunityChartContract(row: row, preference: preference))
        row.quote = ContractQuote(strike: 11, expiration: "20261120")
        XCTAssertNotNil(OpportunityChartContract(row: row, preference: preference))
        preference.expiration = "20261218"
        XCTAssertNil(OpportunityChartContract(row: row, preference: preference))
        preference.expiration = "20261120"; preference.strike = .nan
        XCTAssertNil(OpportunityChartContract(row: row, preference: preference))
    }
    private func read(_ path: String, _ items: [URLQueryItem]) async throws -> [String: Any] {
        let query = Dictionary(uniqueKeysWithValues: items.map { ($0.name, $0.value ?? "") })
        if query["type"] == "OPT_DATES" { return ["expirations": ["20261120", "20261218"]] }
        if path.hasSuffix("strikes") { return ["strikes": [10.0, 11.0, 12.0]] }
        if path.hasSuffix("stock-price") { return ["data": ["TSLL": 11.2]] }
        return ["contracts": [exact]]
    }
    func testOptionSelectionResolvesExactIdentityAndRejectsMismatch() async {
        let model = ChartInstrumentSearch(); model.query = "tsll"; model.options = true
        await model.loadDates(read: read)
        XCTAssertEqual(model.strike, 11)
        XCTAssertEqual(model.expiration, "20261120")
        XCTAssertTrue(model.canOpen)
        var exactQuery: [String: String] = [:]
        let result = await model.resolve { path, items in
            exactQuery = Dictionary(uniqueKeysWithValues: items.map { ($0.name, $0.value ?? "") })
            return ["contracts": [self.exact]]
        }
        XCTAssertEqual(result?.id, 899193475)
        XCTAssertEqual(exactQuery, ["type": "OPT", "q": "TSLL", "expiration": "20261120", "right": "C", "strike": "11.0"])
        model.right = "P"; model.invalidate(clearDates: false); await model.loadStrikes(read: read)
        let wrong = await model.resolve(read: read)
        XCTAssertNil(wrong)
        XCTAssertEqual(model.message, "Exact contract unavailable. Choose another contract.")
    }
    func testChangedQueryDiscardsLateDates() async {
        let model = ChartInstrumentSearch(); model.query = "TSLL"
        var pending: CheckedContinuation<[String: Any], Error>?
        let task = Task { await model.loadDates { _, _ in try await withCheckedThrowingContinuation { pending = $0 } } }
        while pending == nil { await Task.yield() }
        model.invalidate(); model.query = "QQQ"
        pending?.resume(returning: ["expirations": ["20261120"]]); await task.value
        XCTAssertTrue(model.expirations.isEmpty)
        XCTAssertFalse(model.canOpen)
        XCTAssertFalse(model.busy)
    }
    func testDiscoveryIgnoresRepeatedAndBlankSubmissionsButAllowsRetry() async {
        for options in [false, true] {
            let model = ChartInstrumentSearch(); model.query = "TSLL"; model.options = options
            var requests = 0
            var pending: CheckedContinuation<[String: Any], Error>?
            let read: ChartInstrumentSearch.Read = { _, _ in
                requests += 1
                return try await withCheckedThrowingContinuation { pending = $0 }
            }
            let first = Task {
                if options { await model.loadDates(read: read) } else { await model.search(read: read) }
            }
            while pending == nil { await Task.yield() }
            let duplicate: ChartInstrumentSearch.Read = { _, _ in requests += 1; return [:] }
            if options { await model.loadDates(read: duplicate) } else { await model.search(read: duplicate) }
            XCTAssertEqual(requests, 1)
            XCTAssertTrue(model.busy)
            pending?.resume(throwing: URLError(.timedOut)); await first.value
            XCTAssertFalse(model.busy); XCTAssertNotNil(model.message)
            if options { await model.loadDates(read: self.read) } else { await model.search(read: self.read) }
            XCTAssertFalse(model.busy)
            if options { XCTAssertTrue(model.canOpen) } else { XCTAssertEqual(model.results.first?.id, 899193475) }
            model.invalidate(); model.query = "  \n "
            if options { await model.loadDates(read: duplicate) } else { await model.search(read: duplicate) }
            XCTAssertEqual(requests, 1)
            XCTAssertFalse(model.busy); XCTAssertNil(model.message)
        }
    }
    func testEditedQueryCanReplacePendingSearchWithoutOldFailure() async {
        let model = ChartInstrumentSearch(); model.query = "QQQ"
        var pending: CheckedContinuation<[String: Any], Error>?
        let first = Task { await model.search { _, _ in try await withCheckedThrowingContinuation { pending = $0 } } }
        while pending == nil { await Task.yield() }
        model.invalidate(); model.query = "TSLL"
        await model.search(read: read)
        pending?.resume(throwing: URLError(.timedOut)); await first.value
        XCTAssertEqual(model.results.first?.id, 899193475)
        XCTAssertFalse(model.busy); XCTAssertNil(model.message)
    }
    func testPriceUnavailableRequiresManualStrikeAndFavoriteKeepsID() async {
        let model = ChartInstrumentSearch(); model.query = "TSLL"
        await model.loadDates { path, items in
            if path.hasSuffix("stock-price") { throw URLError(.timedOut) }
            return try await self.read(path, items)
        }
        XCTAssertNil(model.strike); XCTAssertFalse(model.canOpen)
        model.strike = 12; XCTAssertTrue(model.canOpen)
        let favorite = ChartInstrument(exact)!
        var query: [String: String] = [:]
        let result = await model.resolveFavorite(favorite) { _, items in
            query = Dictionary(uniqueKeysWithValues: items.map { ($0.name, $0.value ?? "") })
            return ["contracts": [self.exact]]
        }
        XCTAssertEqual(query, ["type": "ID", "con_id": "899193475"])
        XCTAssertEqual(result?.id, favorite.id)
        let wrong = await model.resolveFavorite(favorite) { _, _ in ["contracts": [self.exact.merging(["con_id": 42]) { _, new in new }]] }
        XCTAssertNil(wrong)
    }
    func testFavoritesRoundTripAndNoReplayAfterUnknownResponse() async throws {
        let name = "ChartFavoritesTests-" + UUID().uuidString
        let defaults = UserDefaults(suiteName: name)!
        defer { defaults.removePersistentDomain(forName: name); MockProtocol.payload = nil; MockProtocol.fail = false }
        let config = URLSessionConfiguration.ephemeral; config.protocolClasses = [MockProtocol.self]
        let session = URLSession(configuration: config)
        MockProtocol.requests = []; MockProtocol.statusCode = 200; MockProtocol.fail = false
        var server: [[String: Any]] = []; var revision = 0
        MockProtocol.payload = { request in
            if request.httpMethod == "POST" {
                let body: Data
                if let data = request.httpBody { body = data }
                else if let stream = request.httpBodyStream {
                    stream.open(); defer { stream.close() }
                    var collected = Data(), buffer = [UInt8](repeating: 0, count: 4096)
                    while stream.hasBytesAvailable { let count = stream.read(&buffer, maxLength: buffer.count); if count <= 0 { break }; collected.append(buffer, count: count) }
                    body = collected
                } else { body = Data() }
                let payload = (try? JSONSerialization.jsonObject(with: body)) as? [String: Any]
                let operations = payload?["operations"] as? [[String: Any]] ?? []
                for op in operations {
                    revision += 1
                    if op["kind"] as? String == "delete" { server = [] }
                    else if let value = op["value"] as? [String: Any] { server = [value] }
                }
            }
            return ["revision": revision, "favorites": server, "conflicts": []]
        }
        let phone = ChartFavorites(session: session, defaults: defaults), second = ChartFavorites(session: session, defaults: defaults)
        phone.configure(base: "https://backend.example"); second.configure(base: "https://backend.example")
        await phone.refresh(); await second.refresh()
        let item = ChartInstrument(exact)!
        await phone.toggle(item); await second.refresh()
        XCTAssertEqual(second.items.first?.id, item.id)
        await second.toggle(item); await phone.refresh()
        XCTAssertTrue(phone.items.isEmpty)
        MockProtocol.fail = true
        await phone.toggle(item)
        XCTAssertFalse(phone.ready)
        let posts = MockProtocol.requests.filter { $0.httpMethod == "POST" }.count
        MockProtocol.fail = false
        await phone.refresh()
        XCTAssertEqual(MockProtocol.requests.filter { $0.httpMethod == "POST" }.count, posts)
        XCTAssertTrue(MockProtocol.requests.allSatisfy { $0.url?.path == "/api/chart-favorites" })
        XCTAssertTrue(MockProtocol.requests.filter { $0.httpMethod == "POST" }.allSatisfy { $0.value(forHTTPHeaderField: "X-All-You-Need-Is-Wheel") == "1" })
    }
    func testPickerRendersOptionsAndFavoritesInBothThemes() async throws {
        let name = "ChartPickerRender-" + UUID().uuidString
        let defaults = UserDefaults(suiteName: name)!
        defer { defaults.removePersistentDomain(forName: name); MockProtocol.payload = nil }
        let config = URLSessionConfiguration.ephemeral; config.protocolClasses = [MockProtocol.self]
        let session = URLSession(configuration: config)
        MockProtocol.fail = false; MockProtocol.statusCode = 200
        let item = ChartInstrument(exact)!
        let value = try JSONSerialization.jsonObject(with: JSONEncoder().encode(item))
        MockProtocol.payload = { _ in ["revision": 1, "favorites": [value], "conflicts": []] }
        let store = WheelStore(session: session); store.address = "https://fixture.invalid"
        let scene = try XCTUnwrap(UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first)
        let previous = scene.windows.first { $0.isKeyWindow }
        for (name, theme) in [("dark", ColorScheme.dark), ("light", ColorScheme.light)] {
            let model = ChartInstrumentSearch(); model.query = "TSLL"; model.options = true
            await model.loadDates(read: read)
            let favorites = ChartFavorites(session: session, defaults: defaults)
            favorites.configure(base: store.address); await favorites.refresh()
            let view = ChartInstrumentPicker(current: item, canSelect: true, search: model, favorites: favorites) { _ in }
                .environment(store).preferredColorScheme(theme)
            let controller = UIHostingController(rootView: view)
            let window = UIWindow(windowScene: scene)
            window.rootViewController = controller; window.makeKeyAndVisible()
            controller.view.setNeedsLayout(); controller.view.layoutIfNeeded()
            try await Task.sleep(for: .milliseconds(500))
            let image = UIGraphicsImageRenderer(bounds: window.bounds).image { _ in window.drawHierarchy(in: window.bounds, afterScreenUpdates: true) }
            let path = "/tmp/wheel-native-picker-\(name).png"
            try image.pngData()!.write(to: URL(fileURLWithPath: path))
            print("PICKER_SNAPSHOT=\(path)")
            let attachment = XCTAttachment(image: image); attachment.lifetime = .keepAlways; add(attachment)
            XCTAssertGreaterThan(image.size.width, 300)
            window.isHidden = true; window.rootViewController = nil
        }
        previous?.makeKeyAndVisible()
    }

}
