import XCTest
@testable import Wheel

final class WatchSnapshotTests: XCTestCase {
    private func snapshot(_ price: Double, _ time: Double, epoch: String = "one", contract: String = "MNQZ6",
                          type: Int = 1, source: String = "last") -> WatchSnapshot {
        WatchSnapshot(mode: "paper", epoch: epoch, sampledAt: time, positions: [],
                      quotes: [WatchQuote(symbol: "MNQ", contract: contract, price: price, source: source,
                                          dataType: type, sampledAt: time)], total: 0)
    }

    func testQuoteColorsOnlyCompareFreshSamplesOfSameContractAndAccount() {
        let first = snapshot(21700, 100)
        XCTAssertEqual(snapshot(21701, 125).directions(since: first)["MNQ"], 1)
        XCTAssertEqual(snapshot(21699, 125).directions(since: first)["MNQ"], -1)
        XCTAssertTrue(snapshot(21701, 125, epoch: "two").directions(since: first).isEmpty)
        XCTAssertTrue(snapshot(21701, 125, contract: "MNQH7").directions(since: first).isEmpty)
        XCTAssertTrue(snapshot(21701, 125, type: 3).directions(since: first).isEmpty)
        XCTAssertTrue(snapshot(21701, 125, source: "close").directions(since: first).isEmpty)
        XCTAssertTrue(snapshot(21701, 180).directions(since: first).isEmpty)
    }
}
