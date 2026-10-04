import SwiftUI

struct PremiumValue: View {
    @Environment(\.customPalette) private var customPalette
    let amount: Double?
    var perSymbol = false
    @Environment(\.colorScheme) private var scheme
    private var premiumColor: Color {
        if perSymbol {
            return scheme == .dark ? Color(red: 1, green: 0.70, blue: 0.81) : Color(red: 0.70, green: 0.24, blue: 0.42)
        }
        return customPalette.color("gain", scheme: scheme, fallback: FinancialColors.gain)
    }
    var body: some View {
        Text(money(amount)).monospacedDigit()
            .foregroundStyle(amount.map { $0.isFinite && $0 > 0 } == true
                ? premiumColor
                : Color.secondary)
    }
}

struct OpportunityPrice: View {
    @Environment(\.customPalette) private var customPalette
    @Environment(\.scenePhase) private var phase
    @State private var visible = false
    @Environment(WheelStore.self) private var store
    let row: OpportunityRow?
    @Environment(\.colorScheme) private var scheme
    var body: some View {
        TimelineView(.animation(minimumInterval: 1, paused: !visible || phase != .active || store.selectedTab != "trade")) { context in
            let fresh = row?.stockQuoteIsFresh(at: context.date, batchFailed: store.opportunities.priceError != nil) == true
            let direction = fresh ? (row?.priceDirection ?? 0) : 0
            HStack(spacing: 6) {
                Text(money(row?.stockPrice)).monospacedDigit()
                    .foregroundStyle(direction > 0 ? customPalette.color("gain", scheme: scheme, fallback: FinancialColors.gain) : direction < 0 ? customPalette.color("loss", scheme: scheme, fallback: FinancialColors.loss) : Color.primary)
                if let change = TradingMath.dailyChange(price: row?.stockPrice, close: row?.previousClose) {
                    Text(String(format: "%+.2f%%", change))
                        .font(.caption).monospacedDigit()
                        .foregroundStyle(!fresh ? Color.secondary : change > 0 ? customPalette.color("gain", scheme: scheme, fallback: FinancialColors.gain) : change < 0 ? customPalette.color("loss", scheme: scheme, fallback: FinancialColors.loss) : Color.secondary)
                }
            }
        }
        .onAppear { visible = true }
        .onDisappear { visible = false }
    }
}

struct OpportunityContractSummary: View {
    let quote: ContractQuote
    let type: String
    let row: OpportunityRow?
    @Environment(\.customPalette) private var palette
    @Environment(\.colorScheme) private var scheme
    @Environment(\.scenePhase) private var phase
    @Environment(WheelStore.self) private var store
    @State private var visible = false
    var body: some View {
        let strike = quote.strike.formatted(.number.grouping(.never).precision(.fractionLength(0...4)))
        let mid = quote.mid.map { String(format: "%.2f", $0) } ?? "—"
        let suffix = TradingMath.daysToExpiration(quote.expiration).map { " · \(max(0, $0))" } ?? ""
        TimelineView(.animation(minimumInterval: 1, paused: !visible || phase != .active || store.selectedTab != "trade")) { context in
            let fresh = row?.error == nil && context.date.timeIntervalSince(row?.updated ?? .distantPast) < 30
            let direction = fresh ? (row?.midDirection ?? 0) : 0
            let color = direction > 0 ? palette.color("gain", scheme: scheme, fallback: FinancialColors.gain)
                : direction < 0 ? palette.color("loss", scheme: scheme, fallback: FinancialColors.loss) : Color.primary
            (Text(verbatim: strike + (type == "CALL" ? "C" : "P"))
             + Text(verbatim: "@" + mid).foregroundColor(color)
             + Text(verbatim: suffix))
        }
        .onAppear { visible = true }
        .onDisappear { visible = false }
    }
}

struct ContractQuote: Decodable, Identifiable {
    var strike: Double
    var expiration: String
    var bid: Double?
    var ask: Double?
    var delta: Double?
    var implied_volatility: Double?
    var id: String { "\(expiration)-\(strike)" }
    var mid: Double? { TradingMath.mid(bid, ask) }
    var spread: Double? { mid.map { ((ask ?? 0) - (bid ?? 0)) / $0 * 100 } }
}

enum TradingMath {
    static func orderedStrikes(_ values: [Double]) -> [Double] {
        Set(values.filter { $0.isFinite && $0 > 0 }).sorted()
    }
    static func dailyChange(price: Double?, close: Double?) -> Double? {
        guard let price, let close, price.isFinite, close.isFinite, price > 0, close > 0 else { return nil }
        let result = (price / close - 1) * 100
        return result.isFinite ? result : nil
    }
    static func priceDirection(previous: Double?, current: Double?) -> Int {
        guard let previous, let current, previous.isFinite, current.isFinite,
              previous > 0, current > 0 else { return 0 }
        return current > previous ? 1 : current < previous ? -1 : 0
    }
    static func mid(_ bid: Double?, _ ask: Double?) -> Double? {
        guard let bid, let ask, bid.isFinite, ask.isFinite, bid > 0, ask >= bid else { return nil }
        return (bid + ask) / 2
    }
    static func capacity(shares: Double, available: Int?) -> Int {
        guard shares.isFinite, shares >= 0, shares < Double(Int.max) else { return 0 }
        return max(0, min(Int(shares / 100), available ?? 0))
    }
    static func daysToExpiration(_ expiration: String, now: Date = Date()) -> Int? {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(identifier: "America/New_York")
        formatter.dateFormat = "yyyyMMdd"
        formatter.isLenient = false
        let compact = expiration.replacingOccurrences(of: "-", with: "")
        guard let expiry = formatter.date(from: compact), formatter.string(from: expiry) == compact else { return nil }
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = formatter.timeZone
        return calendar.dateComponents([.day], from: calendar.startOfDay(for: now), to: expiry).day
    }
    static func annualized(premium: Double, expiration: String, now: Date = Date()) -> Double? {
        guard let days = daysToExpiration(expiration, now: now), days > 0, premium.isFinite, premium >= 0 else { return nil }
        return premium * 365 / Double(days)
    }
    static func closePnL(entry: Double?, limit: Double?, quantity: Int, multiplier: Double, buy: Bool) -> Double? {
        guard let entry, let limit, entry > 0, limit > 0, quantity > 0, multiplier > 0 else { return nil }
        return (buy ? entry - limit : limit - entry) * Double(quantity) * multiplier
    }
}

struct OpportunityPreference: Codable, Equatable {
    var otm = 10
    var expiration = ""
    var quantity: Int?
    var strike: Double?
}

@MainActor @Observable
final class OpportunityBook {
    var preferences: [String: OpportunityPreference] = [:]
    var custom: [String] = []
    var excluded: [String] = []
    var removedPuts: [String] = []
    var rows: [String: OpportunityRow] = [:]
    var strikeLists: [String: (values: [Double], date: Date)] = [:]
    var marketOpen: Bool?
    var priceError: String?
    private var pricesLoading = false
    private var sessionExpires = Date.distantPast
    func invalidateMarketSession() { sessionExpires = .distantPast }
    func allowsAutomaticRefresh(_ store: WheelStore) async -> Bool {
        if store.demo { return true }
        if Date() < sessionExpires { return marketOpen == true }
        let token = generation
        do {
            let data = try await store.trading.get("api/options/market-session", base: store.address)
            guard !Task.isCancelled, token == generation else { return false }
            guard let open = data["is_open"] as? Bool,
                  let server = data["server_time"] as? Double,
                  let transition = data["next_transition"] as? Double,
                  server.isFinite, transition.isFinite, transition > server else {
                throw AppError.message("Market session unavailable")
            }
            marketOpen = open
            sessionExpires = Date().addingTimeInterval(min(30, transition - server))
            return open
        } catch {
            guard !Task.isCancelled, token == generation else { return false }
            marketOpen = nil
            sessionExpires = Date().addingTimeInterval(10)
            return false
        }
    }
    var loading = false
    var batchRunning = false
    private var generation = 0
    private var retryAfter: [String: Date] = [:]
    private var retryFailures: [String: Int] = [:]
    private var stockRecoveryRetried: Set<String> = []
    private var preferenceKey = ""
    struct Saved: Codable { var preferences: [String: OpportunityPreference]; var custom: [String]; var excluded: [String]; var removedPuts: [String]? }
    func configure(context: String) {
        generation += 1; rows = [:]; strikeLists = [:]; loading = false
        retryAfter = [:]; retryFailures = [:]; stockRecoveryRetried = []
        pricesLoading = false; priceError = nil
        marketOpen = nil; sessionExpires = .distantPast
        preferenceKey = "opportunities-v1-" + context
        let saved = UserDefaults.standard.data(forKey: preferenceKey).flatMap { try? JSONDecoder().decode(Saved.self, from: $0) }
        preferences = saved?.preferences ?? [:]; custom = saved?.custom ?? []; excluded = saved?.excluded ?? []
        removedPuts = saved?.removedPuts ?? []
    }
    func save() {
        guard !preferenceKey.isEmpty, let data = try? JSONEncoder().encode(Saved(preferences: preferences, custom: custom, excluded: excluded, removedPuts: removedPuts)) else { return }
        UserDefaults.standard.set(data, forKey: preferenceKey)
    }
    func key(_ ticker: String, _ type: String) -> String { ticker + ":" + type }
    func removePut(_ ticker: String) {
        custom.removeAll { $0 == ticker }
        if !removedPuts.contains(ticker) { removedPuts.append(ticker) }
        excluded.removeAll { $0 == key(ticker, "PUT") }
        save()
    }
    func hasHidden(type: String) -> Bool { excluded.contains { $0.hasSuffix(":" + type) } }
    func restoreHidden(type: String) {
        excluded.removeAll { $0.hasSuffix(":" + type) }
        save()
    }
    func symbols(_ store: WheelStore, type: String) -> [String] {
        let held = (store.portfolio?.positions ?? []).filter { $0.security_type == "STK" && $0.position >= 100 }.map(\.symbol)
        return Set(type == "CALL" ? held : held + custom).filter {
            $0 != "SGOV" && !excluded.contains(key($0, type)) && (type != "PUT" || !removedPuts.contains($0))
        }.sorted()
    }
    func defaultCallQuantity(_ ticker: String, store: WheelStore) -> Int {
        let positions = store.portfolio?.positions ?? []
        let shares = positions.filter { $0.symbol == ticker && $0.security_type == "STK" }.reduce(0) { $0 + $1.position }
        guard shares.isFinite, shares > 0 else { return 0 }
        let heldCalls = positions.filter {
            $0.symbol == ticker && $0.security_type == "OPT" && ["CALL", "C"].contains($0.option_type ?? "") && $0.position < 0
        }.reduce(0) { $0 + abs($1.position) }
        let reserved = store.orders.filter {
            $0.name == ticker && ["CALL", "C"].contains($0.option_type ?? "") && $0.action == "SELL"
                && !["filled", "executed", "cancelled", "canceled", "rejected", "inactive"].contains(($0.ib_status ?? $0.status).lowercased())
        }.reduce(0.0) { $0 + max(0, ($1.quantity ?? 0) - ($1.filled ?? 0)) }
        return max(0, Int(min(100, max(0, floor(shares / 100) - heldCalls - reserved))))
    }
    func load(_ ticker: String, type: String, store: WheelStore, background: Bool = false) async {
        let token = generation
        let tradeVersion = store.trading.version
        let key = key(ticker, type)
        guard rows[key]?.loading != true, !store.trading.busy else { return }
        let previous = rows[key]
        let originalPreference = preferences[key]
        var preference = originalPreference ?? OpportunityPreference()
        var row = previous ?? OpportunityRow(ticker: ticker, type: type)
        row.loading = true; rows[key] = row
        defer { if generation == token { rows[key]?.loading = false } }
        do {
            let dates: [[String: Any]]
            if background, !row.dates.isEmpty { dates = row.dates.map { ["value": $0] } }
            else if store.demo { dates = [["value": "20261016", "is_default": true], ["value": "20261120"]] }
            else { dates = try await store.trading.get("api/options/expirations", base: store.address, query: [URLQueryItem(name: "ticker", value: ticker)])["expirations"] as? [[String: Any]] ?? [] }
            guard generation == token, !Task.isCancelled else { return }
            row.dates = dates.compactMap { $0["value"] as? String }
            if !row.dates.contains(preference.expiration) {
                preference.expiration = (dates.first { $0["is_default"] as? Bool == true } ?? dates.first)?["value"] as? String ?? ""
                preference.strike = nil
            }
            guard !preference.expiration.isEmpty else { throw AppError.message("No expiration available.") }
            let shares = (store.portfolio?.positions ?? []).filter { $0.symbol == ticker && $0.security_type == "STK" }.reduce(0) { $0 + $1.position }
            row.shares = shares
            row.quote = nil
            if store.demo {
                row.stockPrice = ticker == "TSLL" ? 10.25 : 92.5
                row.previousClose = ticker == "TSLL" ? 10 : 94
                row.quote = ContractQuote(strike: preference.strike ?? (row.stockPrice! * (1 + (type == "CALL" ? 1 : -1) * Double(preference.otm) / 100)).rounded(), expiration: preference.expiration, bid: 0.25, ask: 0.29, delta: type == "CALL" ? 0.23 : -0.19, implied_volatility: 45)
                row.capacity = TradingMath.capacity(shares: shares, available: Int(shares / 100))
            } else {
                var query = [URLQueryItem(name: "tickers", value: ticker), URLQueryItem(name: "optionType", value: type), URLQueryItem(name: "otm", value: String(preference.otm)), URLQueryItem(name: "expiration", value: preference.expiration)]
                if let strike = preference.strike { query.append(URLQueryItem(name: "strike", value: String(strike))) }
                let result = try await store.trading.get("api/options/otm", base: store.address, query: query)
                guard let item = (result["data"] as? [String: [String: Any]])?[ticker] else { throw AppError.message("Option data unavailable.") }
                row.stockPrice = item["stock_price"] as? Double
                row.previousClose = item["previous_close"] as? Double
                row.capacity = TradingMath.capacity(shares: shares, available: item["covered_call_capacity"] as? Int)
                if let value = (item[type == "CALL" ? "calls" : "puts"] as? [[String: Any]])?.first {
                    row.quote = try JSONDecoder().decode(ContractQuote.self, from: JSONSerialization.data(withJSONObject: value))
                }
                guard row.quote != nil else { throw AppError.message(item["error"] as? String ?? "No matching option quote.") }
                if let strike = preference.strike {
                    guard row.quote?.strike == strike, row.quote?.expiration == preference.expiration else {
                        throw AppError.message("Selected contract unavailable. Refresh before staging.")
                    }
                }
            }
            guard generation == token, !Task.isCancelled, tradeVersion == store.trading.version,
                  !store.trading.busy, preferences[key] == originalPreference else { return }
            if previous?.quote?.id == row.quote?.id, previous?.manualPrice == true {
                row.price = previous?.price ?? ""; row.manualPrice = true
            } else { row.price = row.quote?.mid.map { String(format: "%.2f", $0) } ?? ""; row.manualPrice = false }
            row.quantity = type == "CALL" ? min(max(0, preference.quantity ?? row.capacity), min(100, row.capacity)) : max(1, min(100, preference.quantity ?? (shares >= 100 ? Int(shares / 100) : 1)))
            row.priceDirection = TradingMath.priceDirection(previous: previous?.stockPrice, current: row.stockPrice)
            row.midDirection = previous?.quote?.id == row.quote?.id
                ? TradingMath.priceDirection(previous: previous?.quote?.mid, current: row.quote?.mid) : 0
            row.updated = Date()
            if previous?.quote != nil, let latest = rows[key] {
                if type != "CALL" {
                    row.quantity = latest.quantity
                } else if latest.staged || preference.quantity != nil || latest.quantity != previous?.capacity {
                    // Preserve an edited/staged amount, while still respecting refreshed coverage.
                    row.quantity = min(max(0, latest.quantity), min(100, row.capacity))
                }
                row.staged = latest.staged
                if latest.manualPrice, latest.quote?.id == row.quote?.id {
                    row.price = latest.price; row.manualPrice = true
                }
            }
            if let latest = rows[key], latest.stockUpdated != nil {
                row.stockPrice = latest.stockPrice; row.previousClose = latest.previousClose
                row.priceDirection = latest.priceDirection; row.stockUpdated = latest.stockUpdated
            }
            row.staged = row.staged || hasActiveEntry(row, orders: store.orders)
            if row.staged { row.followMarketPrice() }
            row.error = nil
            preferences[key] = preference; save()
        } catch {
            row = rows[key] ?? row
            row.error = connectionMessage(error)
        }
        guard generation == token, !Task.isCancelled, tradeVersion == store.trading.version,
              !store.trading.busy else { return }
        row.loading = false; rows[key] = row
    }
    func refreshPrices(_ symbols: [String], type: String, store: WheelStore) async -> Bool {
        guard !pricesLoading, !symbols.isEmpty, !store.demo, !store.trading.busy else { return false }
        pricesLoading = true
        let token = generation
        defer { if token == generation { pricesLoading = false } }
        do {
            let result = try await store.trading.get("api/options/stock-quotes", base: store.address,
                query: [URLQueryItem(name: "tickers", value: symbols.joined(separator: ","))])
            guard token == generation, !Task.isCancelled else { return false }
            guard let data = result["data"] as? [String: [String: Any]] else {
                throw AppError.message("Stock quotes unavailable")
            }
            // Publish the whole batch together, without waiting for option quotes.
            let sampledAt = Date()
            for symbol in symbols {
                guard let item = data[symbol], let price = item["stock_price"] as? Double,
                      price.isFinite, price > 0 else { continue }
                let rowKey = key(symbol, type)
                var row = rows[rowKey] ?? OpportunityRow(ticker: symbol, type: type)
                row.priceDirection = TradingMath.priceDirection(previous: row.stockPrice, current: price)
                row.stockPrice = price
                row.previousClose = item["previous_close"] as? Double
                row.stockUpdated = sampledAt
                // Wake a missing-underlying failure once per error streak. Repeated
                // stock responses must not disable backoff for a persistent failure.
                if row.error == "Unable to obtain valid stock price",
                   stockRecoveryRetried.insert(rowKey).inserted {
                    retryAfter[rowKey] = nil
                }
                rows[rowKey] = row
            }
            priceError = nil
            return false
        } catch {
            guard token == generation, !Task.isCancelled else { return false }
            priceError = connectionMessage(error)
            return true
        }
    }
    func refreshAll(type: String, store: WheelStore, background: Bool = false) async {
        guard !loading else { return }; loading = true
        let token = generation
        defer { if token == generation { loading = false } }
        for symbol in symbols(store, type: type) {
            guard token == generation, !Task.isCancelled else { return }
            let rowKey = key(symbol, type)
            if background, let retry = retryAfter[rowKey], retry > Date() { continue }
            await load(symbol, type: type, store: store, background: background)
            guard token == generation, !Task.isCancelled else { return }
            if rows[rowKey]?.error == nil {
                retryAfter[rowKey] = nil
                retryFailures[rowKey] = nil
                stockRecoveryRetried.remove(rowKey)
            } else {
                let failures = min(5, (retryFailures[rowKey] ?? 0) + 1)
                retryFailures[rowKey] = failures
                retryAfter[rowKey] = Date().addingTimeInterval(RefreshLoop.delay(elapsed: 0, failed: true, consecutiveFailures: failures))
            }
        }
    }
    func stage(_ row: OpportunityRow, store: WheelStore) async -> Bool {
        guard !hasActiveEntry(row, orders: store.orders) else {
            rows[key(row.ticker, row.type)]?.staged = true
            rows[key(row.ticker, row.type)]?.followMarketPrice()
            return false
        }
        guard row.canStage, let current = rows[key(row.ticker, row.type)], current.canStage,
              current.quote?.id == row.quote?.id, current.price == row.price, current.quantity == row.quantity,
              let quote = row.quote, let price = TradeRules.price(row.price) else { return false }
        let result = await store.trading.write("api/options/order", body: ["ticker": row.ticker, "action": "SELL", "option_type": row.type, "strike": quote.strike, "expiration": quote.expiration, "quantity": row.quantity, "premium": price], store: store)
        if result {
            rows[key(row.ticker, row.type)]?.staged = true
            rows[key(row.ticker, row.type)]?.followMarketPrice()
        }
        return result
    }
    func hasActiveEntry(_ row: OpportunityRow, orders: [Order]) -> Bool {
        guard let quote = row.quote else { return false }
        return orders.contains {
            $0.name.uppercased() == row.ticker.uppercased() && $0.action?.uppercased() == "SELL" &&
            $0.intent?.uppercased() != "CLOSE" && $0.option_type?.uppercased() == row.type.uppercased() &&
            $0.strike == quote.strike && $0.expiration == quote.expiration &&
            !["canceled", "cancelled", "apicancelled", "rejected", "filled", "executed"].contains($0.status.lowercased())
        }
    }
    func synchronizeEntries(orders: [Order]) {
        for rowKey in Array(rows.keys) {
            guard var row = rows[rowKey], row.quote != nil else { continue }
            row.staged = hasActiveEntry(row, orders: orders)
            if row.staged { row.followMarketPrice() }
            rows[rowKey] = row
        }
    }
    func confirmCancellation(_ order: Order, remaining: [Order]) {
        guard order.action == "SELL", order.intent != "CLOSE", order.isRollover != true,
              let type = order.option_type else { return }
        let rowKey = key(order.name, type)
        guard let row = rows[rowKey], row.quote?.strike == order.strike,
              row.quote?.expiration == order.expiration else { return }
        let duplicate = remaining.contains {
            $0.id != order.id && $0.name == order.name && $0.action == "SELL" &&
            $0.option_type == type && $0.strike == order.strike && $0.expiration == order.expiration &&
            !["canceled", "cancelled", "rejected", "filled"].contains($0.status.lowercased())
        }
        if !duplicate { rows[rowKey]?.staged = false }
    }
    func stageAndOpenOrders(_ snapshots: [OpportunityRow], store: WheelStore) async {
        guard !batchRunning, !store.trading.busy, !snapshots.isEmpty else { return }
        batchRunning = true
        defer { batchRunning = false }
        let token = generation
        var added = false
        for row in snapshots {
            guard token == generation, await stage(row, store: store) else { break }
            added = true
        }
        if added, token == generation {
            store.selectedTab = "orders"
            await store.refreshOrders()
        }
    }
}

struct OpportunityRow: Identifiable {
    var ticker: String
    var type: String
    var dates: [String] = []
    var quote: ContractQuote?
    var stockPrice: Double?
    var previousClose: Double?
    var midDirection = 0
    var priceDirection = 0
    var shares = 0.0
    var capacity = 0
    var quantity = 1
    var price = ""
    var manualPrice = false
    var error: String?
    var loading = false
    var staged = false
    var updated: Date?
    var stockUpdated: Date?
    var id: String { ticker + ":" + type }
    func stockQuoteIsFresh(at now: Date, batchFailed: Bool) -> Bool {
        guard !batchFailed, let price = stockPrice, price.isFinite, price > 0 else { return false }
        // Stock batches and option requests have independent success timestamps.
        if let stockUpdated { return (0..<30).contains(now.timeIntervalSince(stockUpdated)) }
        guard error == nil, let updated else { return false }
        return (0..<30).contains(now.timeIntervalSince(updated))
    }
    var canStage: Bool { !staged && error == nil && quote != nil && Date().timeIntervalSince(updated ?? .distantPast) < 30 && TradeRules.price(price) != nil && quantity > 0 && quantity <= 100 && (type != "CALL" || quantity <= capacity) }
    var total: Double? { TradeRules.price(price).map { $0 * 100 * Double(quantity) } }
    mutating func followMarketPrice() {
        manualPrice = false
        price = quote?.mid.map { String(format: "%.2f", $0) } ?? ""
    }
}

struct OpportunitiesView: View {
    @Environment(\.scenePhase) private var phase
    @State private var visible = false
    @Environment(\.locale) private var locale
    @Environment(WheelStore.self) private var store
    @State private var type = "PUT"
    @State private var ticker = ""
    private var book: OpportunityBook { store.opportunities }
    private var symbols: [String] { book.symbols(store, type: type) }
    private var ready: [OpportunityRow] { symbols.compactMap { book.rows[book.key($0, type)] }.filter(\.canStage) }
    private var autoRefresh: Bool { visible && phase == .active && store.selectedTab == "trade" && !book.batchRunning && !store.trading.busy }
    var body: some View {
        List {
            MarketSessionNotice()
            if let error = book.priceError { NoticeText(error).font(.caption).foregroundStyle(.orange) }
            Section {
                Picker("Strategy", selection: $type) { Text("Cash-secured puts").tag("PUT"); Text("Covered calls").tag("CALL") }.pickerStyle(.segmented)
                if type == "PUT" {
                    HStack {
                        TextField("Add ticker", text: $ticker).textInputAutocapitalization(.characters).autocorrectionDisabled()
                        Button("Add", systemImage: "plus") {
                            let symbol = ticker.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
                            guard symbol != "SGOV", symbol.range(of: "^[A-Z0-9.-]{1,15}$", options: .regularExpression) != nil else { return }
                            book.custom = Array(Set(book.custom + [symbol])).sorted()
                            book.excluded.removeAll { $0 == book.key(symbol, type) }
                            book.removedPuts.removeAll { $0 == symbol }; book.save(); ticker = ""
                            if book.marketOpen == false {
                                Task { await book.load(symbol, type: "PUT", store: store) }
                            }
                        }.labelStyle(.iconOnly)
                            .frame(minWidth: 44, minHeight: 44)
                            .help("Add")
                            .disabled(ticker.isEmpty)
                    }
                }
                if book.loading && symbols.allSatisfy({ book.rows[book.key($0, type)]?.quote == nil }) { ProgressView("Loading opportunities…") }
            }
            ForEach(symbols, id: \.self) { symbol in
                let row = book.rows[book.key(symbol, type)]
                let displayQuantity = type == "CALL" && row?.quote == nil
                    ? min(book.preferences[book.key(symbol, type)]?.quantity ?? book.defaultCallQuantity(symbol, store: store), book.defaultCallQuantity(symbol, store: store))
                    : (row?.quantity ?? 1)
                ArrowlessNavigationLink { OpportunityDetail(ticker: symbol, type: type) } label: {
                    VStack(alignment: .leading, spacing: 8) {
                        Grid(horizontalSpacing: 10, verticalSpacing: 8) {
                            GridRow(alignment: .firstTextBaseline) {
                        HStack(alignment: .firstTextBaseline, spacing: 6) {
                            SymbolText(symbol: symbol).font(.headline)
                            Text(verbatim: String(-abs(displayQuantity)))
                                .font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                                .accessibilityLabel(Text("Quantity"))
                                .accessibilityValue(String(-abs(displayQuantity)))
                            if let quote = row?.quote {
                                OpportunityContractSummary(quote: quote, type: type, row: row)
                                    .font(.caption).monospacedDigit()
                                    .lineLimit(1).minimumScaleFactor(0.8)
                            }
                        }.frame(maxWidth: .infinity, alignment: .leading)
                                OpportunityPrice(row: row)
                                    .fixedSize(horizontal: true, vertical: false)
                                    .gridColumnAlignment(.center)
                            }
                            if let quote = row?.quote {
                                GridRow(alignment: .firstTextBaseline) {
                                    OpportunityMetrics(quote: quote)
                                        .frame(maxWidth: .infinity, alignment: .leading)
                                    PremiumValue(amount: row?.total, perSymbol: true)
                                        .font(.body.weight(.semibold)).monospacedDigit().fixedSize(horizontal: true, vertical: false)
                                }
                            }
                        }
                        if row?.quote != nil {
                            if type == "CALL" && row?.capacity == 0 {
                                HStack(alignment: .firstTextBaseline, spacing: 4) {
                                    Image(systemName: "exclamationmark.triangle.fill").accessibilityHidden(true)
                                    Text("Coverage already reserved")
                                }
                                    .font(.caption).foregroundStyle(.orange)
                            } else if row?.staged == true {
                                Text("Staged in Orders").font(.caption).foregroundStyle(.secondary)
                            }
                        } else if row?.loading == true { ProgressView() }
                        else { NoticeText(row?.error ?? "Quote not loaded").font(.caption).foregroundStyle(.secondary) }
                        if row?.quote != nil, row?.error != nil {
                            Label("STALE", systemImage: "exclamationmark.triangle").font(.caption).foregroundStyle(.orange)
                        }
                    }.padding(.vertical, 4)
                }
                .swipeActions(edge: .leading, allowsFullSwipe: false) {
                    Button("Hide", systemImage: "eye.slash") { book.excluded.append(book.key(symbol, type)); book.save() }.tint(.gray)
                    if type == "PUT" {
                        Button(role: .destructive) { book.removePut(symbol) } label: {
                            Label("Remove", systemImage: "trash")
                        }.tint(.red)
                    }
                }
                .swipeActions(edge: .trailing, allowsFullSwipe: false) {
                    if let row, row.canStage {
                        Button("Stage entry", systemImage: "plus.circle") {
                            Task { await book.stageAndOpenOrders([row], store: store) }
                        }.tint(.teal)
                    }
                }
            }
            if symbols.isEmpty { ContentUnavailableView("No opportunities", systemImage: "list.bullet.rectangle") }
            Section("Selected-contract estimates") {
                LabeledContent("Premium") { PremiumValue(amount: ready.reduce(0) { $0 + ($1.total ?? 0) }) }
                if type == "PUT" { LabeledContent("Cash required", value: money(ready.reduce(0) { $0 + ($1.quote?.strike ?? 0) * 100 * Double($1.quantity) })) }
                Button {
                    let snapshot = ready
                    Task { await book.stageAndOpenOrders(snapshot, store: store) }
                } label: {
                    HStack {
                        Text("Stage all (\(ready.count))")
                        Spacer()
                        Image(systemName: "plus.circle").accessibilityHidden(true)
                    }.contentShape(Rectangle())
                }.disabled(ready.isEmpty)
            }
            Section { TradingNotice() }
        }.navigationTitle(localizedLabel("Trade", locale: locale))
        .toolbar {
            Button {
                store.openTradeChart(store.portfolio?.positions.first(where: { $0.security_type == "STK" && ($0.con_id ?? 0) > 0 }) ?? Position(symbol: "Chart", position: 0, security_type: "STK"), resumeLast: true)
            } label: {
                Image(systemName: "chart.xyaxis.line").frame(width: 36, height: 36)
            }.accessibilityLabel("Open recent chart")

            if book.hasHidden(type: type) {
                Button("Restore hidden opportunity tickers", systemImage: "eye") {
                    book.restoreHidden(type: type)
                }.labelStyle(.iconOnly)
                    .help("Restore hidden opportunity tickers")
            }
        }
        .refreshable {
            _ = await book.refreshPrices(symbols, type: type, store: store)
            await book.refreshAll(type: type, store: store)
        }
        .onAppear { visible = true }
        .onDisappear { visible = false }
        .task(id: "prices-\(autoRefresh)-\(store.demo)-\(store.address)-\(type)") {
            guard autoRefresh, !store.demo else { return }
            var lastSample = Date.distantPast
            await RefreshLoop.run {
                let marketOpen = await book.allowsAutomaticRefresh(store)
                guard marketOpen || Date().timeIntervalSince(lastSample) >= 30 else { return false }
                lastSample = Date()
                return await book.refreshPrices(book.symbols(store, type: type), type: type, store: store)
            }
        }
        .task(id: "\(autoRefresh)-\(store.demo)-\(store.address)-\(type)") {
            guard autoRefresh else { return }
            book.invalidateMarketSession()
            await RefreshLoop.run {
                guard await book.allowsAutomaticRefresh(store) else { return false }
                await book.refreshAll(type: type, store: store, background: true)
                return false
            }
        }
        .disabled(store.trading.busy || book.batchRunning || (!store.demo && store.trading.uncertain))
    }
}

struct OpportunityMetrics: View {
    let quote: ContractQuote
    var body: some View {
        ViewThatFits(in: .horizontal) {
            HStack(spacing: 12) { metrics }.fixedSize(horizontal: true, vertical: false)
            VStack(alignment: .leading, spacing: 4) { metrics }
        }.font(.caption).monospacedDigit()
    }
    @ViewBuilder private var metrics: some View {
        delta
        spread
        iv
    }
    private var spread: some View {
        SpreadValue(percentage: quote.spread)
            .accessibilityLabel(Text("Spread"))
            .accessibilityValue(quote.spread.map { String(format: "%.1f%%", $0) } ?? "—")
    }
    private var delta: some View {
        QuoteMetricValue(metric: .delta, value: quote.delta)
            .accessibilityLabel(Text("Delta"))
            .accessibilityValue(QuoteMetric.delta.formatted(quote.delta))
    }
    private var iv: some View {
        QuoteMetricValue(metric: .iv, value: quote.implied_volatility)
            .accessibilityLabel(Text("IV"))
            .accessibilityValue(QuoteMetric.iv.formatted(quote.implied_volatility))
    }
}

struct OpportunityDetail: View {
    let ticker: String
    let type: String
    @Environment(\.scenePhase) private var phase
    @State private var visible = false
    @State private var strikes: [Double] = []
    @State private var strikeError: String?
    @State private var showStrikes = false
    @State private var strikesLoading = false
    @State private var strikeRetry = 0
    @State private var strikeInput = ""
    @Environment(WheelStore.self) private var store
    private var book: OpportunityBook { store.opportunities }
    private var key: String { book.key(ticker, type) }
    private var row: OpportunityRow { book.rows[key] ?? OpportunityRow(ticker: ticker, type: type) }
    private var preference: OpportunityPreference { book.preferences[key] ?? OpportunityPreference() }
    private var autoRefresh: Bool { visible && !showStrikes && phase == .active && store.selectedTab == "trade" && !book.batchRunning && !store.trading.busy }
    var body: some View {
        Form {
            MarketSessionNotice()
            if let error = book.priceError { NoticeText(error).font(.caption).foregroundStyle(.orange) }
            Section(LocalizedStringKey(type == "CALL" ? "Covered call" : "Cash-secured put")) {
                LabeledContent("Stock price") { OpportunityPrice(row: row) }
                Picker("Expiration", selection: Binding(get: { preference.expiration }, set: { value in updatePreference { $0.expiration = value; $0.strike = nil } })) {
                    ForEach(row.dates, id: \.self) { Text($0).tag($0) }
                }
                LabeledContent("Strike") {
                    Button {
                        strikeInput = (preference.strike ?? row.quote?.strike).map { String(format: "%.2f", $0) } ?? ""
                        showStrikes = true
                    } label: {
                        HStack(spacing: 5) {
                            Text(money(preference.strike ?? row.quote?.strike))
                            Image(systemName: "chevron.up.chevron.down").font(.caption)
                        }
                    }.disabled(preference.expiration.isEmpty)
                }
                Button("Refresh quote", systemImage: "arrow.clockwise") { Task { await book.load(ticker, type: type, store: store) } }.disabled(row.loading)
                if row.loading && row.quote == nil { ProgressView() }
                if let error = row.error { NoticeText(error).foregroundStyle(.orange) }
            }
            if let quote = row.quote {
                Section("SELL TO OPEN") {
                    LabeledContent("Strike", value: money(quote.strike))
                    LabeledContent("Bid / Ask", value: "\(money(quote.bid)) / \(money(quote.ask))")
                    LabeledContent("Spread") { SpreadValue(percentage: quote.spread) }
                    LabeledContent("Delta") { QuoteMetricValue(metric: .delta, value: quote.delta) }
                    LabeledContent("IV") { QuoteMetricValue(metric: .iv, value: quote.implied_volatility) }
                    if let updated = row.updated { LabeledContent("Retrieved", value: updated.formatted(.dateTime.hour().minute().second())) }
                    Text(LocalizedStringKey(store.demo ? "Demo quote" : store.portfolio?.summary.is_frozen == true ? "Frozen portfolio · verify quote" : "Snapshot quote · verify before execution")).font(.caption).foregroundStyle(.secondary)
                    HStack(spacing: 16) {
                        PriceInput(title: "Limit per share", text: Binding(get: { row.price }, set: { book.rows[key]?.price = $0; book.rows[key]?.manualPrice = true }))
                            .frame(width: 76)
                        Button("Use mid") {
                            book.rows[key]?.price = quote.mid.map { String(format: "%.2f", $0) } ?? ""
                            book.rows[key]?.manualPrice = true
                        }.font(.subheadline).buttonStyle(.borderless)
                            .fixedSize(horizontal: true, vertical: false).disabled(quote.mid == nil)
                        HStack(spacing: 2) {
                            Text("×").foregroundStyle(.secondary).accessibilityHidden(true)
                            Picker("Contracts", selection: Binding(get: { row.quantity }, set: { value in
                                book.rows[key]?.quantity = value
                                var pref = preference; pref.quantity = value
                                book.preferences[key] = pref; book.save()
                            })) {
                                ForEach(1...max(1, min(100, type == "CALL" ? row.capacity : 100)), id: \.self) { count in
                                    Text(count.formatted()).tag(count)
                                }
                            }.labelsHidden().pickerStyle(.menu)
                                .accessibilityLabel(Text("Contracts"))
                                .fixedSize(horizontal: true, vertical: false)
                        }
                    }.frame(maxWidth: .infinity, alignment: .center)
                    if type == "CALL" {
                        LabeledContent("Available coverage", value: String(row.capacity))
                        if row.capacity == 0 {
                            HStack(alignment: .firstTextBaseline, spacing: 4) {
                                Image(systemName: "exclamationmark.triangle.fill").accessibilityHidden(true)
                                Text("Coverage already reserved")
                            }.foregroundStyle(.orange)
                        }
                    }
                    LabeledContent("Premium") { PremiumValue(amount: row.total, perSymbol: true) }
                    if type == "PUT" {
                        LabeledContent("Cash required", value: money(quote.strike * 100 * Double(row.quantity)))
                        EntryMarginRow(ticker: ticker, expiration: quote.expiration, strike: quote.strike, quantity: row.quantity, price: row.price)
                    }
                    LabeledContent("Annualized premium estimate", value: money(row.total.flatMap { TradingMath.annualized(premium: $0, expiration: quote.expiration) }))
                    LabeledContent("Time in force", value: "DAY")
                    Button {
                        let snapshot = row
                        Task { await book.stageAndOpenOrders([snapshot], store: store) }
                    } label: {
                        HStack {
                            Text(LocalizedStringKey(row.staged ? "Staged in Orders" : "Stage entry"))
                            Spacer()
                            Image(systemName: "plus.circle").accessibilityHidden(true)
                        }.contentShape(Rectangle())
                    }.disabled(!row.canStage)
                }
            }
            Section { TradingNotice() }
        }.symbolTitle(ticker)
        .modifier(KeyboardDismissal())
        .onAppear { visible = true }
        .onDisappear { visible = false }
        .task(id: "prices-\(autoRefresh)-\(store.demo)-\(store.address)-\(key)") {
            guard autoRefresh, !store.demo else { return }
            await RefreshLoop.run(interval: 1) {
                guard await book.allowsAutomaticRefresh(store) else { return false }
                return await book.refreshPrices([ticker], type: type, store: store)
            }
        }
        .task(id: "\(autoRefresh)-\(store.demo)-\(store.address)-\(key)-\(preference.otm)-\(preference.expiration)-\(preference.strike ?? 0)") {
            guard autoRefresh else { return }
            book.invalidateMarketSession()
            await RefreshLoop.run(interval: 1) {
                guard await book.allowsAutomaticRefresh(store) else { return false }
                await book.load(ticker, type: type, store: store, background: true)
                return row.error != nil
            }
        }
        .sheet(isPresented: $showStrikes) {
            NavigationStack {
                ScrollViewReader { proxy in
                VStack(spacing: 0) {
                    HStack {
                        TextField("Strike", text: $strikeInput).keyboardType(.decimalPad)
                        Button("Done") {
                            guard let value = TradeRules.price(strikeInput), strikes.contains(value) else { return }
                            updatePreference { $0.strike = value }
                            showStrikes = false
                        }.disabled(TradeRules.price(strikeInput).map { !strikes.contains($0) } ?? true)
                    }.padding()
                List {
                    if strikesLoading { ProgressView() }
                    if let strikeError {
                        NoticeText(strikeError).foregroundStyle(.orange)
                        Button("Retry", systemImage: "arrow.clockwise") { strikeRetry += 1 }
                    }
                    ForEach(TradingMath.orderedStrikes(strikes), id: \.self) { value in
                        Button {
                            updatePreference { $0.strike = value }
                            showStrikes = false
                        } label: {
                            HStack {
                                Text(money(value)); Spacer()
                                if value == (preference.strike ?? row.quote?.strike) { Image(systemName: "checkmark") }
                            }
                        }.id(value)
                    }
                }
                }.navigationTitle("Strike")
                    .onAppear { scrollToStrike(proxy) }
                    .onChange(of: strikes) { _, _ in scrollToStrike(proxy) }
                    .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Done") { showStrikes = false } } }
                }
            }.presentationDetents([.medium, .large])
        }
        .task(id: "strikes-\(showStrikes)-\(strikeRetry)-\(store.demo)-\(store.address)-\(key)-\(preference.expiration)") {
            strikes = []; strikeError = nil
            guard showStrikes, !preference.expiration.isEmpty else { return }
            strikesLoading = true
            defer { strikesLoading = false }
            do {
                try Task.checkCancellation()
                let next: [Double]
                if store.demo { next = ticker == "TSLL" ? Array(1...30).map(Double.init) : stride(from: 50.0, through: 150.0, by: 5).map { $0 } }
                else {
                    let payload = try await store.trading.get("api/options/strikes", base: store.address, query: [URLQueryItem(name: "ticker", value: ticker), URLQueryItem(name: "optionType", value: type), URLQueryItem(name: "expiration", value: preference.expiration)])
                    next = payload["strikes"] as? [Double] ?? []
                }
                guard !Task.isCancelled else { return }
                strikes = next.filter { $0.isFinite && $0 > 0 }
                if strikes.isEmpty { strikeError = "No matching option quote." }
            } catch {
                guard !Task.isCancelled else { return }
                strikeError = connectionMessage(error)
            }
        }
        .disabled(store.trading.busy || store.opportunities.batchRunning || (!store.demo && store.trading.uncertain))
    }
    private func scrollToStrike(_ proxy: ScrollViewProxy) {
        guard let target = preference.strike ?? row.quote?.strike ?? row.stockPrice,
              let nearest = strikes.min(by: { abs($0 - target) < abs($1 - target) }) else { return }
        proxy.scrollTo(nearest, anchor: .center)
    }
    private func updatePreference(_ change: (inout OpportunityPreference) -> Void) {
        var next = preference; change(&next); book.preferences[key] = next; book.save()
        book.rows[key]?.quote = nil; book.rows[key]?.price = ""; book.rows[key]?.staged = false
    }
}

struct MarketSessionNotice: View {
    @Environment(WheelStore.self) private var store
    var body: some View {
        if !store.demo && store.opportunities.marketOpen != true {
            Label(LocalizedStringKey(store.opportunities.marketOpen == false
                ? "Market closed · quotes are not live"
                : "Market hours unavailable · automatic quotes paused"), systemImage: "clock")
                .font(.caption).foregroundStyle(.secondary)
        }
    }
}
