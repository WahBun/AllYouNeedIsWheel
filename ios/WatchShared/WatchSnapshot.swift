import Foundation

enum WatchSection: String, Codable { case quotes, holdings }

/// Keep the most recent page of each tab while the watch app is open.
struct WatchPageCache {
    private var pages: [WatchSection: (page: Int, snapshot: WatchSnapshot)] = [:]

    mutating func store(_ snapshot: WatchSnapshot, section: WatchSection, page: Int) {
        if let old = pages.values.first?.snapshot, old.mode != snapshot.mode || old.epoch != snapshot.epoch {
            pages.removeAll()
        }
        pages[section] = (page, snapshot)
    }

    func snapshot(for section: WatchSection, page: Int) -> WatchSnapshot? {
        guard let saved = pages[section], saved.page == page else { return nil }
        return saved.snapshot
    }
}

struct WatchQuote: Codable, Identifiable {
    let symbol: String
    let contract: String
    var price: Double?
    var source: String?
    var dataType: Int?
    var sampledAt: Double?
    var id: String { symbol }
}

struct WatchHolding: Codable, Identifiable {
    let id: Int
    let symbol: String
    let contract: String
    let quantity: Double
    let price: Double?
    let currency: String

    func priceText(locale: Locale) -> String {
        guard let price else { return "—" }
        guard currency == "USD" else {
            return price.formatted(.currency(code: currency).locale(locale))
        }
        let amount = abs(price).formatted(.number.precision(.fractionLength(2)).locale(locale))
        return (price < 0 ? "-$" : "$") + amount
    }
}

struct WatchSnapshot: Codable {
    let mode: String
    let epoch: String
    let sampledAt: Double
    var positions: [WatchHolding]
    var quotes: [WatchQuote]
    var total: Int

    func directions(since previous: WatchSnapshot?) -> [String: Int] {
        guard let previous, previous.mode == mode, previous.epoch == epoch else { return [:] }
        var result: [String: Int] = [:]
        for row in quotes {
            guard let old = previous.quotes.first(where: { $0.symbol == row.symbol && $0.contract == row.contract }),
                  row.dataType == 1, old.dataType == 1, row.source == "last", old.source == "last",
                  let time = row.sampledAt, let prior = old.sampledAt, time > prior, time - prior < 60,
                  sampledAt - time < 60, let newPrice = row.price, let oldPrice = old.price else { continue }
            result[row.symbol] = newPrice == oldPrice ? 0 : newPrice > oldPrice ? 1 : -1
        }
        return result
    }
}

struct WatchTheme: Codable, Equatable {
    let dark: Bool
    let accent: Int
    let gain: Int
    let loss: Int

    static let initial = WatchTheme(dark: true, accent: 0xEDEBE3, gain: 0xB3FF4D, loss: 0xFF5E5E)
}
