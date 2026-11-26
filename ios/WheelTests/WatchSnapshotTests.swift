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

    func testLatestQuoteTimeUsesPricedRowsEvenWhenTheVIXMinuteIsOlder() {
        var page = snapshot(21700, 500)
        let indexBar = WatchQuote(symbol: "VIX", contract: "VIX", price: 28.29, source: "indexBar", sampledAt: 100)
        let awaiting = WatchQuote(symbol: "MES", contract: "MES", sampledAt: 450)
        page.quotes[0].sampledAt = 400
        page.quotes.insert(indexBar, at: 0)
        page.quotes.append(awaiting)
        XCTAssertEqual(page.latestQuoteSampleTime, 400)
        page.quotes = [indexBar, awaiting]
        XCTAssertEqual(page.latestQuoteSampleTime, 100)
        page.quotes = [awaiting]
        XCTAssertNil(page.latestQuoteSampleTime)
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

    func testHoldingDetailFollowsTheExactContractAndAccount() throws {
        let old = Data(#"{"id":10,"symbol":"TEST","contract":"TEST","currency":"USD","quantity":1,"price":30}"#.utf8)
        let stock = try JSONDecoder().decode(WatchHolding.self, from: old)
        XCTAssertNil(stock.averageCost)
        let option = WatchHolding(id: 11, symbol: "TEST", contract: "TEST 50P", quantity: -1,
                                  price: 3, currency: "USD", averageCost: 2.5)
        var page = snapshot(1, 100)
        page.positions = [stock, option]
        let selected = WatchAssetSelection(mode: page.mode, epoch: page.epoch, symbol: "TEST")
        XCTAssertEqual(selected.holdings(in: page).map(\.id), [10, 11])
        page.positions[1].averageCost = 2.75
        XCTAssertEqual(selected.holdings(in: page).last?.averageCost, 2.75)
        XCTAssertTrue(WatchAssetSelection(mode: "live", epoch: page.epoch, symbol: "TEST").holdings(in: page).isEmpty)
        XCTAssertTrue(WatchAssetSelection(mode: page.mode, epoch: "another", symbol: "TEST").holdings(in: page).isEmpty)
        XCTAssertTrue(WatchAssetSelection(mode: page.mode, epoch: page.epoch, symbol: nil).holdings(in: page).isEmpty)
        page.positions = [stock]
        XCTAssertEqual(selected.holdings(in: page).map(\.id), [10])
    }

    func testRingTapMatchesPositiveSectorAndKeepsShortsSeparate() throws {
        let wire = Data(#"{"net":95,"cash":25,"positions":[{"symbol":"B","value":70},{"symbol":"A","value":5},{"symbol":"A","value":-5},{"symbol":"SHORT","value":-10},{"symbol":"UNKNOWN","value":null}]}"#.utf8)
        let data = AllocationData(snapshot: try JSONDecoder().decode(AllocationSnapshot.self, from: wire))
        XCTAssertEqual(data.total, 100)
        XCTAssertEqual(data.net, 95)
        XCTAssertEqual(data.missingCount, 1)
        XCTAssertEqual(data.liabilities.map(\.name), ["SHORT", "A"])
        let slices = data.slices
        XCTAssertEqual(slices.map(\.id), ["asset:B", "cash", "asset:A"])
        XCTAssertEqual(AllocationSlice.at(clockwiseDegrees: 90, in: slices)?.id, "asset:B")
        XCTAssertEqual(AllocationSlice.at(clockwiseDegrees: -30, in: slices)?.id, "cash")
        XCTAssertEqual(AllocationSlice.at(clockwiseDegrees: -1, in: slices)?.id, "asset:A")
        XCTAssertEqual(AllocationSlice.at(clockwiseDegrees: 360, in: slices)?.id, "asset:B")
    }

    func testReportedAverageSurvivesPhoneRelayAndRequiresAnIdentifiedSource() throws {
        let payload = Data(#"{"id":7,"symbol":"TEST","contract":"TEST","quantity":3,"price":60,"currency":"USD","costSource":"report","averageCost":37.75,"reportDate":"2026-01-02","reportedShares":2}"#.utf8)
        let phone = try JSONDecoder().decode(WatchHolding.self, from: payload)
        var watch = try JSONDecoder().decode(WatchHolding.self, from: JSONEncoder().encode(phone))
        let locale = Locale(identifier: "zh_Hant_HK")
        XCTAssertEqual(watch.averageCostText(locale: locale), "$37.75")
        XCTAssertEqual(watch.reportDate, "2026-01-02")
        XCTAssertEqual(watch.reportedShares, 2)
        XCTAssertEqual(watch.priceText(locale: locale), "$60.00")
        watch.reportDate = nil
        XCTAssertEqual(watch.averageCostText(locale: locale), "—")
        watch.costSource = nil
        XCTAssertEqual(watch.averageCostText(locale: locale), "—")
        watch.costSource = "position"
        XCTAssertEqual(watch.averageCostText(locale: locale), "$37.75")
    }
}
