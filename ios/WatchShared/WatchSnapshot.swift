import Foundation

enum WatchSection: String, Codable { case quotes, holdings }

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
