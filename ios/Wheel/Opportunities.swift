import SwiftUI

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
}

@MainActor @Observable
final class OpportunityBook {
    var preferences: [String: OpportunityPreference] = [:]
    var custom: [String] = []
    var excluded: [String] = []
    var rows: [String: OpportunityRow] = [:]
    var loading = false
    var batchRunning = false
    private var generation = 0
    private var preferenceKey = ""
    struct Saved: Codable { var preferences: [String: OpportunityPreference]; var custom: [String]; var excluded: [String] }
    func configure(context: String) {
        generation += 1; rows = [:]; loading = false
        preferenceKey = "opportunities-v1-" + context
        let saved = UserDefaults.standard.data(forKey: preferenceKey).flatMap { try? JSONDecoder().decode(Saved.self, from: $0) }
        preferences = saved?.preferences ?? [:]; custom = saved?.custom ?? []; excluded = saved?.excluded ?? []
    }
    func save() {
        guard !preferenceKey.isEmpty, let data = try? JSONEncoder().encode(Saved(preferences: preferences, custom: custom, excluded: excluded)) else { return }
        UserDefaults.standard.set(data, forKey: preferenceKey)
    }
    func key(_ ticker: String, _ type: String) -> String { ticker + ":" + type }
    func symbols(_ store: WheelStore, type: String) -> [String] {
        let held = (store.portfolio?.positions ?? []).filter { $0.security_type == "STK" && $0.position >= 100 }.map(\.symbol)
        return Set(type == "CALL" ? held : held + custom).filter { $0 != "SGOV" && !excluded.contains(key($0, type)) }.sorted()
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
            if !row.dates.contains(preference.expiration) { preference.expiration = (dates.first { $0["is_default"] as? Bool == true } ?? dates.first)?["value"] as? String ?? "" }
            guard !preference.expiration.isEmpty else { throw AppError.message("No expiration available.") }
            let shares = (store.portfolio?.positions ?? []).filter { $0.symbol == ticker && $0.security_type == "STK" }.reduce(0) { $0 + $1.position }
            row.shares = shares
            row.quote = nil
            if store.demo {
                row.stockPrice = ticker == "TSLL" ? 10.25 : 92.5
                row.quote = ContractQuote(strike: (row.stockPrice! * (1 + (type == "CALL" ? 1 : -1) * Double(preference.otm) / 100)).rounded(), expiration: preference.expiration, bid: 0.25, ask: 0.29, delta: type == "CALL" ? 0.23 : -0.19, implied_volatility: 45)
                row.capacity = TradingMath.capacity(shares: shares, available: Int(shares / 100))
            } else {
                let result = try await store.trading.get("api/options/otm", base: store.address, query: [URLQueryItem(name: "tickers", value: ticker), URLQueryItem(name: "optionType", value: type), URLQueryItem(name: "otm", value: String(preference.otm)), URLQueryItem(name: "expiration", value: preference.expiration)])
                guard let item = (result["data"] as? [String: [String: Any]])?[ticker] else { throw AppError.message("Option data unavailable.") }
                row.stockPrice = item["stock_price"] as? Double
                row.capacity = TradingMath.capacity(shares: shares, available: item["covered_call_capacity"] as? Int)
                if let value = (item[type == "CALL" ? "calls" : "puts"] as? [[String: Any]])?.first {
                    row.quote = try JSONDecoder().decode(ContractQuote.self, from: JSONSerialization.data(withJSONObject: value))
                }
                guard row.quote != nil else { throw AppError.message(item["error"] as? String ?? "No matching option quote.") }
            }
            guard generation == token, !Task.isCancelled, tradeVersion == store.trading.version,
                  !store.trading.busy, preferences[key] == originalPreference else { return }
            if previous?.quote?.id == row.quote?.id, previous?.manualPrice == true {
                row.price = previous?.price ?? ""; row.manualPrice = true
            } else { row.price = row.quote?.mid.map { String(format: "%.2f", $0) } ?? ""; row.manualPrice = false }
            row.quantity = type == "CALL" ? min(max(1, preference.quantity ?? row.capacity), max(1, row.capacity)) : max(1, min(100, preference.quantity ?? (shares >= 100 ? Int(shares / 100) : 1)))
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
        guard row.canStage, rows[key(row.ticker, row.type)]?.staged != true,
              let quote = row.quote, let price = TradeRules.price(row.price) else { return false }
        let result = await store.trading.write("api/options/order", body: ["ticker": row.ticker, "action": "SELL", "option_type": row.type, "strike": quote.strike, "expiration": quote.expiration, "quantity": row.quantity, "premium": price], store: store)
        if result { rows[key(row.ticker, row.type)]?.staged = true }
        return result
    }
}

struct OpportunityRow: Identifiable {
    var ticker: String
    var type: String
    var dates: [String] = []
    var quote: ContractQuote?
    var stockPrice: Double?
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
    @State private var batch = false
    private var book: OpportunityBook { store.opportunities }
    private var symbols: [String] { book.symbols(store, type: type) }
    private var ready: [OpportunityRow] { symbols.compactMap { book.rows[book.key($0, type)] }.filter(\.canStage) }
    private var autoRefresh: Bool { visible && phase == .active && store.selectedTab == "trade" && !batch && !book.batchRunning && !store.trading.busy }
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
                            book.custom = Array(Set(book.custom + [symbol])).sorted(); book.excluded.removeAll { $0 == book.key(symbol, type) }; book.save(); ticker = ""
                            Task { await book.load(symbol, type: type, store: store) }
                        }.disabled(ticker.isEmpty)
                    }
                }
                if book.loading && symbols.allSatisfy({ book.rows[book.key($0, type)]?.quote == nil }) { ProgressView("Loading opportunities…") }
            }
            ForEach(symbols, id: \.self) { symbol in
                let row = book.rows[book.key(symbol, type)]
                NavigationLink { OpportunityDetail(ticker: symbol, type: type) } label: {
                    VStack(alignment: .leading, spacing: 8) {
                        HStack { Text(symbol).font(.headline); Spacer(); Text(money(row?.stockPrice)) }
                        if let quote = row?.quote {
                            HStack { Text("\(money(quote.strike)) · \(quote.expiration)"); Spacer(); Text(money(row?.total)) }.font(.caption)
                            Text(row?.staged == true ? LocalizedStringKey("Staged in Orders") : type == "CALL" && row?.capacity == 0 ? LocalizedStringKey("Coverage already reserved") : "\(row?.quantity ?? 1) contracts · \(money(TradeRules.price(row?.price ?? "")))").font(.caption).foregroundStyle(.secondary)
                        } else if row?.loading == true { ProgressView() }
                        else { Text(LocalizedStringKey(row?.error ?? "Quote not loaded")).font(.caption).foregroundStyle(.secondary) }
                        if row?.quote != nil, row?.error != nil {
                            Label("STALE", systemImage: "exclamationmark.triangle").font(.caption).foregroundStyle(.orange)
                        }
                    }.padding(.vertical, 4)
                }.swipeActions { Button("Hide", role: .destructive) { book.excluded.append(book.key(symbol, type)); book.save() } }
            }
            if symbols.isEmpty { ContentUnavailableView("No opportunities", systemImage: "list.bullet.rectangle") }
            Section("Selected-contract estimates") {
                LabeledContent("Premium", value: money(ready.reduce(0) { $0 + ($1.total ?? 0) }))
                if type == "PUT" { LabeledContent("Cash required", value: money(ready.reduce(0) { $0 + ($1.quote?.strike ?? 0) * 100 * Double($1.quantity) })) }
                Button("Stage all (\(ready.count))", systemImage: "plus.circle") { batch = true }.disabled(ready.isEmpty)
            }
            Section { TradingNotice() }
        }.navigationTitle(localizedLabel("Trade", locale: locale))
        .toolbar {
            if !book.excluded.isEmpty {
                Button("Restore hidden opportunity tickers", systemImage: "eye") {
                    book.excluded = []
                    book.save()
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
        .confirmationDialog("Stage \(ready.count) local drafts?", isPresented: $batch, titleVisibility: .visible) {
            Button("Stage drafts") {
                let snapshot = ready
                Task {
                    book.batchRunning = true
                    defer { book.batchRunning = false }
                    for row in snapshot { if !(await book.stage(row, store: store)) { break } }
                    await store.refresh(); store.selectedTab = "orders"
                }
            }
        } message: { Text("Orders are not sent to IB until Execute. Stops on the first failure; completed drafts remain in Orders.") }
    }
}

struct OpportunityDetail: View {
    let ticker: String
    let type: String
    @Environment(WheelStore.self) private var store
    @State private var confirm = false
    private var book: OpportunityBook { store.opportunities }
    private var key: String { book.key(ticker, type) }
    private var row: OpportunityRow { book.rows[key] ?? OpportunityRow(ticker: ticker, type: type) }
    private var preference: OpportunityPreference { book.preferences[key] ?? OpportunityPreference() }
    var body: some View {
        Form {
            Section(LocalizedStringKey(type == "CALL" ? "Covered call" : "Cash-secured put")) {
                LabeledContent("Stock price", value: money(row.stockPrice))
                Stepper("OTM \(preference.otm)%", value: Binding(get: { preference.otm }, set: { value in updatePreference { $0.otm = value } }), in: 0...80)
                Picker("Expiration", selection: Binding(get: { preference.expiration }, set: { value in updatePreference { $0.expiration = value } })) {
                    ForEach(row.dates, id: \.self) { Text($0).tag($0) }
                }
                Button("Refresh quote", systemImage: "arrow.clockwise") { Task { await book.load(ticker, type: type, store: store) } }
                if row.loading { ProgressView() }
                if let error = row.error { Text(error).foregroundStyle(.orange) }
            }
            if let quote = row.quote {
                Section("SELL TO OPEN") {
                    LabeledContent("Strike", value: money(quote.strike))
                    LabeledContent("Bid / Ask", value: "\(money(quote.bid)) / \(money(quote.ask))")
                    LabeledContent("Spread", value: quote.spread.map { String(format: "%.1f%%", $0) } ?? "—")
                    LabeledContent("Delta", value: quote.delta.map { String(format: "%.2f", $0) } ?? "—")
                    LabeledContent("IV", value: quote.implied_volatility.flatMap { $0 > 0 ? String(format: "%.1f%%", $0) : nil } ?? "—")
                    if let updated = row.updated { LabeledContent("Retrieved") { Text(updated, style: .time) } }
                    Text(LocalizedStringKey(store.demo ? "Demo quote" : store.portfolio?.summary.is_frozen == true ? "Frozen portfolio · verify quote" : "Snapshot quote · verify before execution")).font(.caption).foregroundStyle(.secondary)
                    TextField("Limit per share", text: Binding(get: { row.price }, set: { book.rows[key]?.price = $0; book.rows[key]?.manualPrice = true })).keyboardType(.decimalPad)
                    Button("Use mid", systemImage: "equal") { book.rows[key]?.price = quote.mid.map { String(format: "%.2f", $0) } ?? ""; book.rows[key]?.manualPrice = true }.disabled(quote.mid == nil)
                    Stepper("Contracts: \(row.quantity)", value: Binding(get: { row.quantity }, set: { value in
                        book.rows[key]?.quantity = value; var pref = preference; pref.quantity = value; book.preferences[key] = pref; book.save()
                    }), in: 1...max(1, min(100, type == "CALL" ? row.capacity : 100)))
                    if type == "CALL" {
                        LabeledContent("Available coverage", value: String(row.capacity))
                        if row.capacity == 0 { Text("Coverage already reserved").foregroundStyle(.orange) }
                    }
                    LabeledContent("Premium", value: money(row.total))
                    if type == "PUT" { LabeledContent("Cash required", value: money(quote.strike * 100 * Double(row.quantity))) }
                    LabeledContent("Annualized premium estimate", value: money(row.total.flatMap { TradingMath.annualized(premium: $0, expiration: quote.expiration) }))
                    LabeledContent("Time in force", value: "DAY")
                    Button(LocalizedStringKey(row.staged ? "Staged in Orders" : "Stage entry"), systemImage: "plus.circle") { confirm = true }.disabled(!row.canStage)
                }
            }
            Section { TradingNotice() }
        }.navigationTitle(ticker)
        .modifier(KeyboardDismissal())
        .disabled(row.loading || store.trading.busy || store.opportunities.batchRunning || (!store.demo && store.trading.uncertain))
        .confirmationDialog("Stage SELL \(row.quantity) \(ticker) \(type)?", isPresented: $confirm, titleVisibility: .visible) {
            Button("Stage draft") { Task { if await book.stage(row, store: store) { await store.refresh(); store.selectedTab = "orders" } } }
        } message: { Text("\(row.quote?.expiration ?? "") · \(money(row.quote?.strike)) · Limit \(money(TradeRules.price(row.price))) · DAY") }
    }
    private func updatePreference(_ change: (inout OpportunityPreference) -> Void) {
        var next = preference; change(&next); book.preferences[key] = next; book.save()
        book.rows[key]?.quote = nil; book.rows[key]?.price = ""; book.rows[key]?.staged = false
    }
}
