import SwiftUI
import Observation

struct ChartInstrument: Codable, Identifiable, Equatable {
    let id: Int
    let symbol: String
    let label: String
    let type: String
    let exchange: String
    let expiration: String
    let right: String
    let strike: Double?

    init?(_ value: [String: Any]) {
        guard let id = value["con_id"] as? Int, id > 0,
              let type = value["security_type"] as? String, ["STK", "FUT", "OPT"].contains(type),
              let label = value["local_symbol"] as? String, !label.isEmpty else { return nil }
        self.id = id; self.type = type; self.label = label
        symbol = value["symbol"] as? String ?? ""
        exchange = value["exchange"] as? String ?? ""
        expiration = value["expiration"] as? String ?? ""
        right = value["right"] as? String ?? ""
        strike = (value["strike"] as? Double).flatMap { $0 > 0 && $0.isFinite ? $0 : nil }
    }
    var contract: [String: Any] {
        var result: [String: Any] = ["con_id": id, "symbol": symbol, "local_symbol": label,
            "security_type": type, "exchange": exchange, "expiration": expiration, "right": right]
        if let strike { result["strike"] = strike }
        return result
    }
}

@MainActor @Observable
final class ChartInstrumentSearch {
    typealias Read = (String, [URLQueryItem]) async throws -> [String: Any]
    var query = "QQQ"
    var options = false
    var expiration = ""
    var right = "C"
    var strike: Double?
    private(set) var expirations: [String] = []
    private(set) var strikes: [Double] = []
    private(set) var results: [ChartInstrument] = []
    private(set) var busy = false
    private(set) var message: String?
    private var revision = 0
    private var loadedSymbol = ""
    var ticker: String { query.trimmingCharacters(in: .whitespacesAndNewlines).uppercased() }
    var canOpen: Bool { !busy && !loadedSymbol.isEmpty && loadedSymbol == ticker && expirations.contains(expiration) && strike.map { strikes.contains($0) } == true }

    func invalidate(clearDates: Bool = true) {
        revision += 1; busy = false; message = nil; results = []; strike = nil; strikes = []
        if clearDates { loadedSymbol = ""; expiration = ""; expirations = [] }
    }
    private func items(_ values: [String: String]) -> [URLQueryItem] {
        values.map { URLQueryItem(name: $0.key, value: $0.value) }
    }
    func search(read: Read) async {
        guard !busy, !ticker.isEmpty else { return }
        invalidate(); let token = revision, name = ticker; busy = true
        defer { if token == revision { busy = false } }
        do {
            let response = try await read("api/portfolio/chart-contracts", items(["q": name]))
            guard token == revision else { return }
            results = (response["contracts"] as? [[String: Any]] ?? []).compactMap(ChartInstrument.init)
            if results.isEmpty { message = "No matching contract." }
        } catch { if token == revision { message = connectionMessage(error) } }
    }
    func loadDates(read: Read) async {
        guard !busy, !ticker.isEmpty else { return }
        invalidate(); let token = revision, name = ticker; busy = true
        defer { if token == revision { busy = false } }
        do {
            let response = try await read("api/portfolio/chart-contracts", items(["type": "OPT_DATES", "q": name]))
            guard token == revision else { return }
            expirations = (response["expirations"] as? [String] ?? []).filter { $0.count == 8 && $0.allSatisfy(\.isNumber) }.sorted()
            loadedSymbol = name; expiration = expirations.first ?? ""
            if expiration.isEmpty { message = "No available expirations."; return }
            await loadStrikes(read: read)
        } catch { if token == revision { message = connectionMessage(error) } }
    }
    func loadStrikes(read: Read) async {
        invalidate(clearDates: false)
        guard loadedSymbol == ticker, !expiration.isEmpty else { return }
        let token = revision, name = ticker, date = expiration, side = right; busy = true
        defer { if token == revision { busy = false } }
        do {
            let response = try await read("api/options/strikes", items(["ticker": name, "expiration": date, "optionType": side == "C" ? "CALL" : "PUT"]))
            guard token == revision else { return }
            strikes = Array(Set((response["strikes"] as? [Double] ?? []).filter { $0.isFinite && $0 > 0 })).sorted()
            guard !strikes.isEmpty else { message = "No contracts for this expiration and type."; return }
            let priceResponse = try? await read("api/options/stock-price", items(["tickers": name]))
            guard token == revision else { return }
            if let price = (priceResponse?["data"] as? [String: Double])?[name], price.isFinite, price > 0 {
                strike = strikes.min { abs($0 - price) < abs($1 - price) }
                message = String(format: "Underlying $%.2f · Nearest strike selected.", price)
            } else { message = "Underlying price unavailable. Choose a strike." }
        } catch { if token == revision { message = connectionMessage(error) } }
    }
    func resolveFavorite(_ item: ChartInstrument, read: Read) async -> ChartInstrument? {
        revision += 1; let token = revision; busy = true; message = "Finding exact contract…"
        defer { if token == revision { busy = false } }
        do {
            let response = try await read("api/portfolio/chart-contracts", items(["type": "ID", "con_id": String(item.id)]))
            guard token == revision else { return nil }
            let found = (response["contracts"] as? [[String: Any]] ?? []).compactMap(ChartInstrument.init)
            guard found.count == 1, let contract = found.first, contract.id == item.id else {
                message = "Saved contract unavailable. Search for another instrument."; return nil
            }
            message = nil; return contract
        } catch { if token == revision { message = connectionMessage(error) }; return nil }
    }
    func resolve(read: Read) async -> ChartInstrument? {
        guard canOpen, let chosen = strike else { return nil }
        revision += 1; let token = revision, name = ticker, date = expiration, side = right
        busy = true; message = "Finding exact contract…"
        defer { if token == revision { busy = false } }
        do {
            let response = try await read("api/portfolio/chart-contracts", items(["type": "OPT", "q": name,
                "expiration": date, "right": side, "strike": String(chosen)]))
            guard token == revision else { return nil }
            let found = (response["contracts"] as? [[String: Any]] ?? []).compactMap(ChartInstrument.init)
            guard found.count == 1, let contract = found.first, contract.type == "OPT", contract.symbol == name,
                  contract.expiration == date, contract.right == side, contract.strike == chosen else {
                message = "Exact contract unavailable. Choose another contract."; return nil
            }
            message = nil; return contract
        } catch { if token == revision { message = connectionMessage(error) }; return nil }
    }
}

@MainActor
struct ChartInstrumentPicker: View {
    let current: ChartInstrument?
    let canSelect: Bool
    let onSelect: (ChartInstrument) -> Void
    @Environment(WheelStore.self) private var store
    @Environment(\.dismiss) private var dismiss
    @State private var search: ChartInstrumentSearch
    @State private var favorites: ChartFavorites
    @Environment(\.scenePhase) private var phase
    init(current: ChartInstrument?, canSelect: Bool, search: ChartInstrumentSearch? = nil,
         favorites: ChartFavorites? = nil, onSelect: @escaping (ChartInstrument) -> Void) {
        self.current = current; self.canSelect = canSelect; self.onSelect = onSelect
        _search = State(initialValue: search ?? ChartInstrumentSearch()); _favorites = State(initialValue: favorites ?? ChartFavorites())
    }
    private var read: ChartInstrumentSearch.Read { { path, query in try await store.trading.get(path, base: store.address, query: query) } }
    private var context: String { "\(store.address)|\(store.demo)|\(store.trading.accountEpoch ?? "")" }

    private func choose(_ item: ChartInstrument) {
        guard canSelect else { return }
        onSelect(item); dismiss()
    }
    private func row(_ item: ChartInstrument, selectable: Bool = true, saved: Bool = false) -> some View {
        HStack {
            Button {
                if saved { Task { if let resolved = await search.resolveFavorite(item, read: read) { choose(resolved) } } }
                else { choose(item) }
            } label: {
                VStack(alignment: .leading, spacing: 4) {
                    Text(item.label).foregroundStyle(.primary)
                    Text([item.type, item.exchange].filter { !$0.isEmpty }.joined(separator: " · ")).font(.caption).foregroundStyle(.secondary)
                }.frame(maxWidth: .infinity, alignment: .leading).contentShape(Rectangle())
            }.buttonStyle(.plain).disabled(!canSelect || !selectable || search.busy)
            Button { Task { await favorites.toggle(item) } } label: {
                Image(systemName: favorites.items.contains { $0.id == item.id } ? "star.fill" : "star")
                    .foregroundStyle(.yellow).frame(width: 44, height: 44)
            }.buttonStyle(.plain).disabled(!favorites.ready || favorites.busy).accessibilityLabel((favorites.items.contains { $0.id == item.id } ? "Remove favorite " : "Favorite ") + item.label)
        }
    }
    var body: some View {
        NavigationStack {
            Form {
                if let current { Section("Current instrument") { row(current, selectable: false) } }
                Section {
                    Picker("Instrument type", selection: Binding(get: { search.options }, set: { search.invalidate(); search.options = $0; if $0 { load() } })) {
                        Text("Stocks / Futures").tag(false)
                        Text("Options").tag(true)
                    }.pickerStyle(.segmented)
                    HStack {
                        TextField(search.options ? "Underlying" : "Symbol", text: Binding(get: { search.query }, set: { search.invalidate(); search.query = $0 }))
                            .textInputAutocapitalization(.characters).autocorrectionDisabled().submitLabel(.search)
                            .onSubmit { load() }
                        if !search.query.isEmpty {
                            Button { search.invalidate(); search.query = "" } label: { Image(systemName: "xmark.circle.fill") }
                                .buttonStyle(.plain).foregroundStyle(.secondary).accessibilityLabel("Clear symbol")
                        }
                        Button(search.options ? "Load dates" : "Search") { load() }.disabled(search.busy || search.ticker.isEmpty)
                    }
                    if search.options { optionFields }
                    if search.busy { ProgressView("Loading…") }
                    if let message = search.message { Text(message).font(.caption).foregroundStyle(.secondary) }
                    if !canSelect { Text("Wait for the current order request to finish.").font(.caption).foregroundStyle(.orange) }
                }
                if !search.results.isEmpty { Section("Search results") { ForEach(search.results) { row($0) } } }
                Section("Favorites") {
                    if favorites.items.isEmpty { Text("Tap a star to save an instrument across web and iOS.").font(.caption).foregroundStyle(.secondary) }
                    ForEach(favorites.items) { row($0, saved: true) }
                    if favorites.busy { ProgressView("Syncing favorites…") }
                    if let message = favorites.message { Text(message).font(.caption).foregroundStyle(.orange) }
                    Button("Refresh favorites") { Task { await favorites.refresh() } }.disabled(favorites.busy)
                }
            }
            .navigationTitle("Select instrument").navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
        }
        .environment(\.locale, Locale(identifier: "en"))
        .onAppear {
            if let current { search.query = current.symbol.isEmpty ? "QQQ" : current.symbol; search.options = current.type == "OPT" }
            if search.options && search.expirations.isEmpty { load() }
        }
        .onDisappear { search.invalidate() }
        .onChange(of: context) { search.invalidate() }
        .task(id: context + "|" + String(phase == .active)) {
            favorites.configure(base: store.address)
            guard phase == .active else { return }
            while !Task.isCancelled {
                await favorites.refresh()
                do { try await Task.sleep(for: .seconds(15)) } catch { return }
            }
        }
    }
    private func load() {
        guard !search.busy, !search.ticker.isEmpty else { return }
        Task { if search.options { await search.loadDates(read: read) } else { await search.search(read: read) } }
    }
    private var optionFields: some View {
        Group {
            Picker("Expiration", selection: Binding(get: { search.expiration }, set: { search.expiration = $0; search.invalidate(clearDates: false); Task { await search.loadStrikes(read: read) } })) {
                Text("Select expiration").tag("")
                ForEach(search.expirations, id: \.self) { date in Text("\(date.prefix(4))-\(date.dropFirst(4).prefix(2))-\(date.suffix(2))").tag(date) }
            }.disabled(search.expirations.isEmpty || search.busy)
            Picker("Type", selection: Binding(get: { search.right }, set: { search.right = $0; search.invalidate(clearDates: false); Task { await search.loadStrikes(read: read) } })) {
                Text("Call").tag("C"); Text("Put").tag("P")
            }.disabled(search.busy)
            Picker("Strike", selection: $search.strike) {
                Text("Select strike").tag(Optional<Double>.none)
                ForEach(search.strikes, id: \.self) { value in Text(value.formatted(.number.precision(.fractionLength(0...4)))).tag(Optional(value)) }
            }.disabled(search.strikes.isEmpty || search.busy)
            Button("Open chart") {
                Task { if let item = await search.resolve(read: read) { choose(item) } }
            }.disabled(!search.canOpen || !canSelect)
        }
    }
}
