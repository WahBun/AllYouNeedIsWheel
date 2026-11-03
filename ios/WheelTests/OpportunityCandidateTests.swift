import XCTest
@testable import Wheel

@MainActor
final class OpportunityCandidateTests: XCTestCase {
    private func setUpBook() async -> (WheelStore, String) {
        let store = WheelStore()
        await store.refreshPortfolio()
        let context = UUID().uuidString
        store.opportunities.configure(context: context)
        addTeardownBlock { UserDefaults.standard.removeObject(forKey: "opportunities-v1-" + context) }
        return (store, context)
    }

    func testPinnedContractsPersistAndOnlySelectedContractStages() async throws {
        let (store, context) = await setUpBook()
        let book = store.opportunities
        await book.load("TSLL", type: "PUT", store: store)
        let group = book.key("TSLL", "PUT")
        let auto = try XCTUnwrap(book.rows[group]?.quote)
        XCTAssertEqual(book.pin("TSLL", "PUT", expiration: auto.expiration, strike: auto.strike), group)
        let first = book.pin("TSLL", "PUT", expiration: auto.expiration, strike: auto.strike - 1)
        let second = book.pin("TSLL", "PUT", expiration: "20261120", strike: auto.strike)
        XCTAssertEqual(book.pin("TSLL", "PUT", expiration: "20261120", strike: auto.strike), second)
        await book.refreshAll(type: "PUT", store: store)
        XCTAssertEqual(book.selectedRows(store, type: "PUT").filter { $0.ticker == "TSLL" }.map(\.id), [group])
        book.toggleSelection(group); book.toggleSelection(second)
        book.configure(context: context)
        await book.refreshAll(type: "PUT", store: store)
        let selection = book.selectedRows(store, type: "PUT").filter { $0.ticker == "TSLL" }
        XCTAssertEqual(selection.map(\.id), [second])
        XCTAssertEqual(book.rows[first]?.quote?.strike, auto.strike - 1)
        XCTAssertEqual(selection.first?.quote?.expiration, "20261120")
        let before = store.trading.demoOrders.count
        await book.stageAndOpenOrders(selection, store: store)
        XCTAssertEqual(store.trading.demoOrders.count, before + 1)
        XCTAssertEqual(store.trading.demoOrders.last?.expiration, "20261120")
        XCTAssertEqual(store.trading.demoOrders.last?.strike, auto.strike)
        let pin = try XCTUnwrap(book.pins[group]?.first)
        book.removePin(pin, group: group)
        XCTAssertNil(book.rows[first]); XCTAssertNotNil(book.rows[second])
    }

    func testExistingSavedWatchlistMigratesWithPrimarySelected() {
        let context = UUID().uuidString
        let key = "opportunities-v1-" + context
        UserDefaults.standard.set(Data(#"{"preferences":{"TQQQ:PUT":{"otm":8,"expiration":"20261120","strike":60}},"custom":["TQQQ"],"excluded":[]}"#.utf8), forKey: key)
        defer { UserDefaults.standard.removeObject(forKey: key) }
        let book = OpportunityBook()
        book.configure(context: context)
        XCTAssertTrue(book.pins.isEmpty)
        XCTAssertTrue(book.unselected.isEmpty)
        XCTAssertEqual(book.custom, ["TQQQ"])
        XCTAssertEqual(book.preferences["TQQQ:PUT"]?.strike, 60)
    }

    func testMultipleCallsCannotStageBeyondSharedCoverage() async throws {
        let (store, _) = await setUpBook()
        let book = store.opportunities
        await book.load("TSLL", type: "CALL", store: store)
        let group = book.key("TSLL", "CALL")
        let id = book.pin("TSLL", "CALL", expiration: "20261120", strike: 12)
        await book.refreshAll(type: "CALL", store: store)
        book.toggleSelection(id)
        let both = book.selectedRows(store, type: "CALL").filter { $0.ticker == "TSLL" }
        XCTAssertEqual(both.count, 2)
        XCTAssertFalse(book.hasCoverage(both, store: store))
        let before = store.trading.demoOrders.count
        await book.stageAndOpenOrders(both, store: store)
        XCTAssertEqual(store.trading.demoOrders.count, before)
        book.rows[group]?.quantity = 2
        let covered = book.selectedRows(store, type: "CALL").filter { $0.ticker == "TSLL" }
        XCTAssertTrue(book.hasCoverage(covered, store: store))
        await book.stageAndOpenOrders(covered, store: store)
        XCTAssertEqual(store.trading.demoOrders.count, before + 2)
    }

    func testStaleSecondSelectionCannotStageTheFirstDraft() async throws {
        let (store, _) = await setUpBook()
        let book = store.opportunities
        let second = book.pin("TSLL", "PUT", expiration: "20261120", strike: 8)
        await book.refreshAll(type: "PUT", store: store)
        book.toggleSelection(second)
        let selection = book.selectedRows(store, type: "PUT").filter { $0.ticker == "TSLL" }
        XCTAssertEqual(selection.count, 2)
        book.rows[second]?.error = "Offline"
        let before = store.trading.demoOrders.count
        await book.stageAndOpenOrders(selection, store: store)
        XCTAssertEqual(store.trading.demoOrders.count, before)
    }

    func testUnavailablePinnedExpiryNeverRollsAndAutoCollisionKeepsPin() async throws {
        let (store, _) = await setUpBook()
        let book = store.opportunities
        let group = book.key("TSLL", "PUT")
        let stale = book.pin("TSLL", "PUT", expiration: "20260101", strike: 8)
        let pin = book.pin("TSLL", "PUT", expiration: "20261120", strike: 9)
        book.preferences[group] = OpportunityPreference(expiration: "20261120", strike: 9)
        await book.refreshAll(type: "PUT", store: store)
        XCTAssertNil(book.rows[stale]?.quote)
        XCTAssertFalse(try XCTUnwrap(book.rows[stale]).canStage)
        XCTAssertFalse(book.showsPrimary(group))
        book.toggleSelection(pin)
        XCTAssertEqual(book.selectedRows(store, type: "PUT").filter { $0.ticker == "TSLL" }.map(\.id), [pin])
    }
}
