import SwiftUI

struct MarginImpact: Decodable {
    let con_id: Int
    let position: Double
    let currency: String
    let initial_change: Double
    let maintenance_change: Double
    let estimated: Bool
    let additive: Bool
    let scenario: String
    let warning: String?
    let retrieved_at: String

    static func displayTime(_ timestamp: String, timeZone: TimeZone = .current) -> String {
        let parser = ISO8601DateFormatter()
        parser.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        var date = parser.date(from: timestamp)
        if date == nil {
            parser.formatOptions = [.withInternetDateTime]
            date = parser.date(from: timestamp)
        }
        guard let date else { return "—" }
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = timeZone
        formatter.dateFormat = "MM-dd HH:mm:ss"
        return formatter.string(from: date)
    }

    func matches(_ holding: Position) -> Bool {
        con_id == holding.con_id && position == holding.position && currency == "USD" &&
        estimated && !additive && scenario == "close_entire_position" &&
        initial_change.isFinite && maintenance_change.isFinite
    }
}

struct MarginOverview: View {
    @Environment(WheelStore.self) private var store
    private var positions: [Position] { (store.portfolio?.positions ?? []).filter { $0.position != 0 } }
    private var symbols: [String] { Array(Set(positions.map(\.symbol))).sorted() }
    var body: some View {
        List {
            Section("Account") {
                StatusView()
                LabeledContent("Initial margin", value: money(store.portfolio?.summary.initial_margin))
                LabeledContent("Excess liquidity", value: money(store.portfolio?.summary.excess_liquidity))
            }
            Section {
                Text("IB reports account-level margin, not an exact allocation per holding. Position estimates are hypothetical changes and must not be added together.")
                    .font(.footnote).foregroundStyle(.secondary)
            }
            ForEach(symbols, id: \.self) { symbol in
                Section(symbol) {
                    ForEach(positions.filter { $0.symbol == symbol }) { position in
                        NavigationLink { PositionMarginView(position: position) } label: {
                            VStack(alignment: .leading, spacing: 4) {
                                Text(position.detail)
                                Text("Estimated closing impact").font(.caption).foregroundStyle(.secondary)
                            }
                        }
                    }
                }
            }
        }.navigationTitle("Margin details")
    }
}

struct PositionMarginView: View {
    let position: Position
    @Environment(WheelStore.self) private var store
    @State private var impact: MarginImpact?
    @State private var loading = false
    @State private var error: String?
    @State private var request: Task<Void, Never>?
    private var latest: Position? { store.portfolio?.positions.first { $0.id == position.id && $0.position != 0 } }
    private var context: String { "\(store.demo)-\(store.address)" }
    var body: some View {
        Form {
            Section(position.symbol) {
                Text(position.detail)
                LabeledContent("Quantity", value: latest?.position.formatted() ?? "—")
                Text("Scenario: close this entire holding while leaving all other positions unchanged.")
                    .font(.footnote).foregroundStyle(.secondary)
            }
            Section("Estimated closing impact") {
                if let impact, let latest, impact.matches(latest) {
                    LabeledContent("Initial margin change", value: signedMoney(impact.initial_change))
                    LabeledContent("Maintenance margin change", value: signedMoney(impact.maintenance_change))
                    LabeledContent("Retrieved", value: MarginImpact.displayTime(impact.retrieved_at))
                    if let warning = impact.warning, !warning.isEmpty { Text(warning).foregroundStyle(.orange) }
                }
                Text("Negative means less required margin; positive means more. Closing a hedge can increase margin. This is not the holding's actual margin allocation.")
                    .font(.footnote).foregroundStyle(.secondary)
                if latest?.con_id ?? 0 > 0 {
                    Button("Estimate margin impact", systemImage: "calculator") { estimate() }
                        .disabled(loading || store.trading.busy)
                } else {
                    Text("Update the backend to enable position margin estimates.").foregroundStyle(.orange)
                }
                if loading { ProgressView() }
                if let error { Text(LocalizedStringKey(error)).foregroundStyle(.orange) }
                if store.demo { Text("Demo estimate · not broker data").font(.caption).foregroundStyle(.secondary) }
            }
        }.navigationTitle("Margin impact")
        .onDisappear { request?.cancel(); request = nil }
        .onChange(of: context) { request?.cancel(); impact = nil; error = nil }
        .onChange(of: latest?.position) { request?.cancel(); impact = nil }
        .onChange(of: store.trading.version) { request?.cancel(); impact = nil }
    }
    private func signedMoney(_ value: Double) -> String { (value > 0 ? "+" : "") + money(value) }
    private func estimate() {
        guard !loading, let latest, let id = latest.con_id, id > 0 else { return }
        let requestedContext = context
        let version = store.trading.version
        loading = true; error = nil; impact = nil
        request = Task {
            defer { loading = false }
            do {
                let result: MarginImpact
                if store.demo {
                    result = MarginImpact(con_id: id, position: latest.position, currency: "USD",
                        initial_change: -100, maintenance_change: -80, estimated: true,
                        additive: false, scenario: "close_entire_position", warning: nil,
                        retrieved_at: Date().ISO8601Format())
                } else {
                    let payload = try await store.trading.get("api/portfolio/position/\(id)/margin-impact", base: store.address)
                    result = try JSONDecoder().decode(MarginImpact.self, from: JSONSerialization.data(withJSONObject: payload))
                }
                guard !Task.isCancelled, requestedContext == context, version == store.trading.version,
                      let current = self.latest, result.matches(current) else { return }
                impact = result
            } catch {
                guard !Task.isCancelled, requestedContext == context else { return }
                self.error = error.localizedDescription.contains("HTTP 404")
                    ? "Update the backend to enable position margin estimates." : connectionMessage(error)
            }
        }
    }
}
