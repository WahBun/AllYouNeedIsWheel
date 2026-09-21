import SwiftUI

struct RolloverTicket: View {
    @Environment(\.locale) private var locale
    let position: Position
    @Environment(WheelStore.self) private var store
    @State private var dates: [String] = []
    @State private var expiration = ""
    @State private var otm = 10
    @State private var quantity = 1
    @State private var held = 0
    @State private var closing: [String: Any]?
    @State private var candidates: [ContractQuote] = []
    @State private var selected: String = ""
    @State private var closePrice = ""
    @State private var openPrice = ""
    @State private var loading = false
    @State private var error: String?
    @State private var staged = false
    @State private var confirm = false
    private var quote: ContractQuote? { candidates.first { $0.id == selected } }
    private var valid: Bool { !staged && held >= quantity && quantity > 0 && closing != nil && quote != nil && TradeRules.price(closePrice) != nil && TradeRules.price(openPrice) != nil }
    var body: some View {
        Form {
            Section("Current short option") {
                Text("\(position.symbol) · \(position.detail)")
                LabeledContent("BUY TO CLOSE · GTC", value: money(TradeRules.price(closePrice)))
                LabeledContent("Bid / Ask", value: "\(money(closing?["bid"] as? Double)) / \(money(closing?["ask"] as? Double))")
                PriceInput(title: "Close limit per share", text: $closePrice)
                if held > 0 { Stepper("Contracts: \(quantity) of \(held)", value: $quantity, in: 1...held) }
            }
            Section("New option · SELL TO OPEN · DAY") {
                Stepper("OTM \(otm)%", value: $otm, in: 0...80)
                Picker("Expiration", selection: $expiration) { Text("Select date").tag(""); ForEach(dates, id: \.self) { Text($0).tag($0) } }
                Button("Refresh both quotes", systemImage: "arrow.clockwise") { Task { await loadQuotes() } }.disabled(expiration.isEmpty)
                Picker("Strike", selection: $selected) { Text("Select contract").tag(""); ForEach(candidates) { Text(money($0.strike)).tag($0.id) } }
                if let quote {
                    LabeledContent("Bid / Ask", value: "\(money(quote.bid)) / \(money(quote.ask))")
                    LabeledContent("Delta", value: quote.delta.map { String(format: "%.2f", $0) } ?? "—")
                }
                PriceInput(title: "Open limit per share", text: $openPrice)
            }
            Section("Net premium before fees") {
                if let buy = TradeRules.price(closePrice), let sell = TradeRules.price(openPrice) {
                    LabeledContent(LocalizedStringKey(sell >= buy ? "Credit" : "Debit"), value: money(abs(sell - buy) * Double(quantity) * 100))
                }
                Text("Two independent orders, not an atomic spread. Close the old position and verify its fill before executing the new leg.").font(.footnote).foregroundStyle(.orange)
                Button(LocalizedStringKey(staged ? "Staged in Orders" : "Stage rollover pair"), systemImage: "arrow.triangle.2.circlepath") { confirm = true }.disabled(!valid)
            }
            if loading { ProgressView() }
            if let error { Text(error).foregroundStyle(.orange) }
            TradingNotice()
        }.navigationTitle(localizedLabel("Rollover", locale: locale))
        .modifier(KeyboardDismissal())
        .disabled(loading || store.trading.busy || (!store.demo && store.trading.uncertain))
        .task { await loadDates() }
        .onChange(of: expiration) { invalidate() }
        .onChange(of: otm) { invalidate() }
        .onChange(of: selected) { openPrice = quote?.mid.map { String(format: "%.2f", $0) } ?? "" }
        .confirmationDialog("Stage two \(position.symbol) orders?", isPresented: $confirm, titleVisibility: .visible) {
            Button("Stage pair") {
                guard valid, let quote, let id = position.con_id, let buy = TradeRules.price(closePrice), let sell = TradeRules.price(openPrice) else { return }
                Task {
                    staged = await store.trading.write("api/options/rollover", body: ["current_con_id": id, "new_strike": quote.strike, "new_expiration": quote.expiration, "quantity": quantity, "current_limit_price": buy, "new_limit_price": sell], store: store)
                    await store.refresh(); if staged { store.selectedTab = "orders" }
                }
            }
        } message: { Text("BUY \(quantity) \(position.detail) at \(closePrice)\nSELL \(quantity) \(quote?.expiration ?? "") · \(money(quote?.strike)) \(position.option_type ?? "") at \(openPrice)\nExecution is separate in Orders.") }
    }
    private func invalidate() { candidates = []; selected = ""; openPrice = ""; closing = nil; closePrice = ""; staged = false }
    private func loadDates() async {
        loading = true; defer { loading = false }
        do {
            if store.demo { dates = ["20261120", "20261218"] }
            else { dates = (try await store.trading.get("api/options/expirations", base: store.address, query: [URLQueryItem(name: "ticker", value: position.symbol)])["expirations"] as? [[String: Any]] ?? []).compactMap { $0["value"] as? String }.filter { $0 > (position.expiration ?? "") } }
            expiration = dates.first ?? ""
        } catch { self.error = error.localizedDescription }
    }
    private func loadQuotes() async {
        loading = true; error = nil; invalidate(); defer { loading = false }
        do {
            guard position.position < 0, let id = position.con_id else { throw AppError.message("Only exact short option positions can be rolled.") }
            if store.demo {
                closing = ["position": position.position, "close_action": "BUY", "bid": 0.17, "ask": 0.19, "multiplier": 100.0]
                candidates = [ContractQuote(strike: position.strike ?? 9, expiration: expiration, bid: 0.25, ask: 0.29)]
            } else {
                closing = try await store.trading.get("api/portfolio/option-position/\(id)/quote", base: store.address)
                let response = try await store.trading.get("api/options/otm", base: store.address, query: [URLQueryItem(name: "tickers", value: position.symbol), URLQueryItem(name: "optionType", value: position.option_type), URLQueryItem(name: "otm", value: String(otm)), URLQueryItem(name: "expiration", value: expiration)])
                let item = (response["data"] as? [String: [String: Any]])?[position.symbol]
                let values = item?[position.option_type == "CALL" ? "calls" : "puts"] as? [[String: Any]] ?? []
                candidates = try JSONDecoder().decode([ContractQuote].self, from: JSONSerialization.data(withJSONObject: values))
            }
            guard closing?["close_action"] as? String == "BUY", (closing?["multiplier"] as? Double ?? 100) == 100 else { throw AppError.message("Unsupported rollover contract.") }
            held = Int(abs(closing?["position"] as? Double ?? 0)); quantity = held
            selected = candidates.first?.id ?? ""
            closePrice = (closing?["ask"] as? Double).flatMap { $0 > 0 ? String(format: "%.2f", $0) : nil } ?? ""
            openPrice = quote?.mid.map { String(format: "%.2f", $0) } ?? ""
        } catch { closing = nil; candidates = []; self.error = error.localizedDescription }
    }
}
