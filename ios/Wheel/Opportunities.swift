import SwiftUI

struct PremiumValue: View {
    let amount: Double?
    var perSymbol = false
    @Environment(\.colorScheme) private var scheme
    private var premiumColor: Color {
        if perSymbol {
            return scheme == .dark ? Color(red: 1, green: 0.70, blue: 0.81) : Color(red: 0.70, green: 0.24, blue: 0.42)
        }
        return scheme == .dark ? Color(red: 0.70, green: 1, blue: 0.30) : Color(red: 0.28, green: 0.46, blue: 0.02)
    }
    var body: some View {
        Text(money(amount)).monospacedDigit()
            .foregroundStyle(amount.map { $0.isFinite && $0 > 0 } == true
                ? premiumColor
                : Color.secondary)
    }
}

struct OpportunityPrice: View {
    let row: OpportunityRow?
    @Environment(\.colorScheme) private var scheme
    var body: some View {
        TimelineView(.periodic(from: .now, by: 1)) { context in
            let fresh = row?.error == nil && context.date.timeIntervalSince(row?.updated ?? .distantPast) < 30
            let direction = fresh ? (row?.priceDirection ?? 0) : 0
            HStack(spacing: 6) {
                Text(money(row?.stockPrice)).monospacedDigit()
                    .foregroundStyle(direction > 0 ? TradingColors.profit(scheme) : direction < 0 ? Color.red : Color.primary)
                if let change = TradingMath.dailyChange(price: row?.stockPrice, close: row?.previousClose) {
                    Text(String(format: "%+.2f%%", change))
                        .font(.caption).monospacedDigit()
                        .foregroundStyle(!fresh ? Color.secondary : change > 0 ? TradingColors.profit(scheme) : change < 0 ? Color.red : Color.secondary)
                }
            }
        }
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
        func rank(_ value: Double) -> Int {
            value.truncatingRemainder(dividingBy: 5) == 0 ? 0 : value.rounded() == value ? 1 : 2
        }
        return Set(values.filter { $0.isFinite && $0 > 0 }).sorted {
            rank($0) == rank($1) ? $0 < $1 : rank($0) < rank($1)
        }
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
    static func annualized(premium: Double, expiration: String, now: Date = Date()) -> Double? {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(identifier: "America/New_York")
        formatter.dateFormat = "yyyyMMdd"
        formatter.isLenient = false
        let compact = expiration.replacingOccurrences(of: "-", with: "")
        guard let expiry = formatter.date(from: compact), formatter.string(from: expiry) == compact else { return nil }
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = formatter.timeZone
        let days = calendar.dateComponents([.day], from: calendar.startOfDay(for: now), to: expiry).day ?? 0
        guard days > 0, premium.isFinite, premium >= 0 else { return nil }
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
    var loading = false
    var batchRunning = false
    private var generation = 0
    private var preferenceKey = ""
    struct Saved: Codable { var preferences: [String: OpportunityPreference]; var custom: [String]; var excluded: [String]; var removedPuts: [String]? }
    func configure(context: String) {
        generation += 1; rows = [:]; strikeLists = [:]; loading = false
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
            row.quantity = type == "CALL" ? min(max(1, preference.quantity ?? row.capacity), max(1, row.capacity)) : max(1, min(100, preference.quantity ?? (shares >= 100 ? Int(shares / 100) : 1)))
            row.priceDirection = TradingMath.priceDirection(previous: previous?.stockPrice, current: row.stockPrice)
            row.updated = Date()
            if previous?.quote != nil, let latest = rows[key] {
                row.quantity = latest.quantity
                row.staged = latest.staged
                if latest.manualPrice, latest.quote?.id == row.quote?.id {
                    row.price = latest.price; row.manualPrice = true
                }
            }
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
    func refreshAll(type: String, store: WheelStore, background: Bool = false) async {
        guard !loading else { return }; loading = true
        let token = generation
        defer { if token == generation { loading = false } }
        for symbol in symbols(store, type: type) {
            guard token == generation, !Task.isCancelled else { return }
            await load(symbol, type: type, store: store, background: background)
        }
    }
    func stage(_ row: OpportunityRow, store: WheelStore) async -> Bool {
        guard row.canStage, let current = rows[key(row.ticker, row.type)], current.canStage,
              current.quote?.id == row.quote?.id, current.price == row.price, current.quantity == row.quantity,
              let quote = row.quote, let price = TradeRules.price(row.price) else { return false }
        let result = await store.trading.write("api/options/order", body: ["ticker": row.ticker, "action": "SELL", "option_type": row.type, "strike": quote.strike, "expiration": quote.expiration, "quantity": row.quantity, "premium": price], store: store)
        if result { rows[key(row.ticker, row.type)]?.staged = true }
        return result
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
            await store.refreshOrders()
            if token == generation { store.selectedTab = "orders" }
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
    var id: String { ticker + ":" + type }
    var canStage: Bool { !staged && error == nil && quote != nil && Date().timeIntervalSince(updated ?? .distantPast) < 30 && TradeRules.price(price) != nil && quantity > 0 && quantity <= 100 && (type != "CALL" || quantity <= capacity) }
    var total: Double? { TradeRules.price(price).map { $0 * 100 * Double(quantity) } }
}

struct OpportunitiesView: View {
    @Environment(\.scenePhase) private var phase
    @State private var visible = false
    @Environment(\.locale) private var locale
    @Environment(WheelStore.self) private var store
    @State private var type = "CALL"
    @State private var ticker = ""
    private var book: OpportunityBook { store.opportunities }
    private var symbols: [String] { book.symbols(store, type: type) }
    private var ready: [OpportunityRow] { symbols.compactMap { book.rows[book.key($0, type)] }.filter(\.canStage) }
    private var autoRefresh: Bool { visible && phase == .active && store.selectedTab == "trade" && !book.batchRunning && !store.trading.busy }
    var body: some View {
        List {
            Section {
                Picker("Strategy", selection: $type) { Text("Covered calls").tag("CALL"); Text("Cash-secured puts").tag("PUT") }.pickerStyle(.segmented)
                if type == "PUT" {
                    HStack {
                        TextField("Add ticker", text: $ticker).textInputAutocapitalization(.characters).autocorrectionDisabled()
                        Button("Add", systemImage: "plus") {
                            let symbol = ticker.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
                            guard symbol != "SGOV", symbol.range(of: "^[A-Z0-9.-]{1,15}$", options: .regularExpression) != nil else { return }
                            book.custom = Array(Set(book.custom + [symbol])).sorted()
                            book.excluded.removeAll { $0 == book.key(symbol, type) }
                            book.removedPuts.removeAll { $0 == symbol }; book.save(); ticker = ""
                            Task { await book.load(symbol, type: type, store: store) }
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
                NavigationLink { OpportunityDetail(ticker: symbol, type: type) } label: {
                    VStack(alignment: .leading, spacing: 8) {
                        HStack { Text(symbol).font(.headline); Spacer(); OpportunityPrice(row: row) }
                        if let quote = row?.quote {
                            HStack { Text("\(money(quote.strike)) · \(quote.expiration)"); Spacer(); PremiumValue(amount: row?.total, perSymbol: true) }.font(.caption)
                            if type == "CALL" && row?.capacity == 0 {
                                HStack(alignment: .firstTextBaseline, spacing: 4) {
                                    Image(systemName: "exclamationmark.triangle.fill").accessibilityHidden(true)
                                    Text("Coverage already reserved")
                                }
                                    .font(.caption).foregroundStyle(.orange)
                            } else {
                                Text(row?.staged == true ? LocalizedStringKey("Staged in Orders") : "\(row?.quantity ?? 1) contracts · \(money(TradeRules.price(row?.price ?? "")))").font(.caption).foregroundStyle(.secondary)
                            }
                        } else if row?.loading == true { ProgressView() }
                        else { Text(LocalizedStringKey(row?.error ?? "Quote not loaded")).font(.caption).foregroundStyle(.secondary) }
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
                Button("Stage all (\(ready.count))", systemImage: "plus.circle") {
                    let snapshot = ready
                    Task { await book.stageAndOpenOrders(snapshot, store: store) }
                }.disabled(ready.isEmpty)
            }
            Section { TradingNotice() }
        }.navigationTitle(localizedLabel("Trade", locale: locale))
        .toolbar {
            if book.hasHidden(type: type) {
                Button("Restore hidden opportunity tickers", systemImage: "eye") {
                    book.restoreHidden(type: type)
                }.labelStyle(.iconOnly)
                    .help("Restore hidden opportunity tickers")
            }
        }
        .refreshable { await book.refreshAll(type: type, store: store) }
        .onAppear { visible = true }
        .onDisappear { visible = false }
        .task(id: "\(autoRefresh)-\(store.demo)-\(store.address)-\(type)-\(symbols.joined(separator: ","))") {
            guard autoRefresh else { return }
            await RefreshLoop.run {
                await book.refreshAll(type: type, store: store, background: true)
                return symbols.contains { book.rows[book.key($0, type)]?.error != nil }
            }
        }
        .disabled(store.trading.busy || book.batchRunning || (!store.demo && store.trading.uncertain))
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
    @Environment(WheelStore.self) private var store
    private var book: OpportunityBook { store.opportunities }
    private var key: String { book.key(ticker, type) }
    private var row: OpportunityRow { book.rows[key] ?? OpportunityRow(ticker: ticker, type: type) }
    private var preference: OpportunityPreference { book.preferences[key] ?? OpportunityPreference() }
    private var autoRefresh: Bool { visible && !showStrikes && phase == .active && store.selectedTab == "trade" && !book.batchRunning && !store.trading.busy }
    var body: some View {
        Form {
            Section(LocalizedStringKey(type == "CALL" ? "Covered call" : "Cash-secured put")) {
                LabeledContent("Stock price") { OpportunityPrice(row: row) }
                Stepper("OTM \(preference.otm)%", value: Binding(get: { preference.otm }, set: { value in updatePreference { $0.otm = value; $0.strike = nil } }), in: 0...80)
                Picker("Expiration", selection: Binding(get: { preference.expiration }, set: { value in updatePreference { $0.expiration = value; $0.strike = nil } })) {
                    ForEach(row.dates, id: \.self) { Text($0).tag($0) }
                }
                LabeledContent("Strike") {
                    Button { showStrikes = true } label: {
                        HStack(spacing: 5) {
                            Text(money(preference.strike ?? row.quote?.strike))
                            Image(systemName: "chevron.up.chevron.down").font(.caption)
                        }
                    }.disabled(preference.expiration.isEmpty)
                }
                Button("Refresh quote", systemImage: "arrow.clockwise") { Task { await book.load(ticker, type: type, store: store) } }.disabled(row.loading)
                if row.loading && row.quote == nil { ProgressView() }
                if let error = row.error { Text(error).foregroundStyle(.orange) }
            }
            if let quote = row.quote {
                Section("SELL TO OPEN") {
                    LabeledContent("Strike", value: money(quote.strike))
                    LabeledContent("Bid / Ask", value: "\(money(quote.bid)) / \(money(quote.ask))")
                    LabeledContent("Spread") { SpreadValue(percentage: quote.spread) }
                    LabeledContent("Delta", value: quote.delta.map { String(format: "%.2f", $0) } ?? "—")
                    LabeledContent("IV", value: quote.implied_volatility.flatMap { $0 > 0 ? String(format: "%.1f%%", $0) : nil } ?? "—")
                    if let updated = row.updated { LabeledContent("Retrieved", value: updated.formatted(.dateTime.hour().minute().second())) }
                    Text(LocalizedStringKey(store.demo ? "Demo quote" : store.portfolio?.summary.is_frozen == true ? "Frozen portfolio · verify quote" : "Snapshot quote · verify before execution")).font(.caption).foregroundStyle(.secondary)
                    TextField("Limit per share", text: Binding(get: { row.price }, set: { book.rows[key]?.price = $0; book.rows[key]?.manualPrice = true })).keyboardType(.decimalPad)
                    Button("Use mid", systemImage: "equal") { book.rows[key]?.price = quote.mid.map { String(format: "%.2f", $0) } ?? ""; book.rows[key]?.manualPrice = true }.disabled(quote.mid == nil)
                    Stepper("Contracts: \(row.quantity)", value: Binding(get: { row.quantity }, set: { value in
                        book.rows[key]?.quantity = value; var pref = preference; pref.quantity = value; book.preferences[key] = pref; book.save()
                    }), in: 1...max(1, min(100, type == "CALL" ? row.capacity : 100)))
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
                    if type == "PUT" { LabeledContent("Cash required", value: money(quote.strike * 100 * Double(row.quantity))) }
                    LabeledContent("Annualized premium estimate", value: money(row.total.flatMap { TradingMath.annualized(premium: $0, expiration: quote.expiration) }))
                    LabeledContent("Time in force", value: "DAY")
                    Button(LocalizedStringKey(row.staged ? "Staged in Orders" : "Stage entry"), systemImage: "plus.circle") {
                        let snapshot = row
                        Task { await book.stageAndOpenOrders([snapshot], store: store) }
                    }.disabled(!row.canStage)
                }
            }
            Section { TradingNotice() }
        }.navigationTitle(ticker)
        .modifier(KeyboardDismissal())
        .onAppear { visible = true }
        .onDisappear { visible = false }
        .task(id: "\(autoRefresh)-\(store.demo)-\(store.address)-\(key)-\(preference.otm)-\(preference.expiration)-\(preference.strike ?? 0)") {
            guard autoRefresh else { return }
            await RefreshLoop.run {
                await book.load(ticker, type: type, store: store, background: true)
                return row.error != nil
            }
        }
        .sheet(isPresented: $showStrikes) {
            NavigationStack {
                List {
                    if strikesLoading { ProgressView() }
                    if let strikeError {
                        Text(LocalizedStringKey(strikeError)).foregroundStyle(.orange)
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
                        }
                    }
                }.navigationTitle("Strike")
                    .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Done") { showStrikes = false } } }
            }.presentationDetents([.medium, .large])
        }
        .task(id: "strikes-\(showStrikes)-\(strikeRetry)-\(store.demo)-\(store.address)-\(key)-\(preference.expiration)") {
            strikes = []; strikeError = nil
            guard showStrikes, !preference.expiration.isEmpty else { return }
            strikesLoading = true
            defer { strikesLoading = false }
            do {
                let cacheKey = key + ":" + preference.expiration
                if let cached = book.strikeLists[cacheKey], Date().timeIntervalSince(cached.date) < 1800 {
                    strikes = cached.values
                    return
                }
                // Let the initial quote finish before requesting contract metadata.
                while row.loading || book.loading {
                    try await Task.sleep(for: .milliseconds(100))
                }
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
                if !strikes.isEmpty { book.strikeLists[cacheKey] = (strikes, Date()) }
            } catch {
                guard !Task.isCancelled else { return }
                strikeError = connectionMessage(error)
            }
        }
        .disabled(store.trading.busy || store.opportunities.batchRunning || (!store.demo && store.trading.uncertain))
    }
    private func updatePreference(_ change: (inout OpportunityPreference) -> Void) {
        var next = preference; change(&next); book.preferences[key] = next; book.save()
        book.rows[key]?.quote = nil; book.rows[key]?.price = ""; book.rows[key]?.staged = false
    }
}
