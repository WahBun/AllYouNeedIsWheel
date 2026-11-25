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

    func testTabSwitchRestoresOnlyTheSamePageAndAccount() {
        var cache = WatchPageCache()
        let first = snapshot(21700, 100)
        cache.store(first, section: .holdings, page: 0)
        cache.store(snapshot(21701, 115), section: .quotes, page: 0)
        XCTAssertEqual(cache.snapshot(for: .holdings, page: 0)?.sampledAt, 100)
        XCTAssertNil(cache.snapshot(for: .holdings, page: 1))
        cache.store(snapshot(21702, 130), section: .holdings, page: 1)
        XCTAssertNil(cache.snapshot(for: .holdings, page: 0))
        cache.store(snapshot(21703, 145, epoch: "two"), section: .quotes, page: 0)
        XCTAssertNil(cache.snapshot(for: .holdings, page: 1))
    }

    func testHoldingUSDPriceAlwaysUsesOnlyTheDollarSign() {
        func holding(_ price: Double?, currency: String = "USD") -> WatchHolding {
            WatchHolding(id: 1, symbol: "TEST", contract: "TEST", quantity: 1, price: price, currency: currency)
        }
        for region in ["zh_Hant_HK", "en_CA", "en_US"] {
            let locale = Locale(identifier: region)
            XCTAssertEqual(holding(145.43).priceText(locale: locale), "$145.43", region)
            XCTAssertEqual(holding(-1.5).priceText(locale: locale), "-$1.50", region)
            XCTAssertEqual(holding(0).priceText(locale: locale), "$0.00", region)
            XCTAssertEqual(holding(nil).priceText(locale: locale), "—", region)
            XCTAssertEqual(holding(10, currency: "CAD").priceText(locale: locale),
                           10.0.formatted(.currency(code: "CAD").locale(locale)), region)
        }
    }
}
