import SwiftUI

/// Uses Trade's information hierarchy with held-position data, not entry estimates.
struct PortfolioOptionRow: View {
    let position: Position
    var showsRange = true
    @Environment(\.locale) private var locale
    @Environment(WheelStore.self) private var store
    @Environment(\.scenePhase) private var phase
    @State private var quote: ContractQuote?
    @State private var frozen = false
    @State private var midMovement = OptionMidMovement()
    @State private var visible = false
    private var context: String { "\(visible)-\(store.demo)-\(store.address)-\(store.trading.accountEpoch ?? "")-\(position.id)-\(store.selectedTab)-\(phase == .active)-\(store.portfolio?.summary.is_frozen == true)" }
    private var emptyQuote: ContractQuote { ContractQuote(strike: position.strike ?? 0, expiration: position.expiration ?? "") }
    private var contractSummary: String {
        let code = ["PUT": "P", "CALL": "C", "P": "P", "C": "C"][position.option_type?.uppercased() ?? ""] ?? "—"
        let strike = position.strike.map { $0.formatted(.number.grouping(.never).precision(.fractionLength(0...4))) } ?? "—"
        let entry = position.optionAveragePrice.flatMap { value -> String? in
            guard value.isFinite, value > 0 else { return nil }
            return String(format: "%.2f", value)
        } ?? "—"
        var parts = ["\(strike)\(code)@\(entry)\(position.optionAverageUsesBrokerCost ? "*" : "")"]
        if let expiration = position.expiration, let days = TradingMath.daysToExpiration(expiration) {
            parts.append(String(max(0, days)))
        }
        return parts.joined(separator: " · ")
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .firstTextBaseline, spacing: 6) {
                SymbolText(symbol: position.symbol).font(.headline)
                Text(verbatim: position.position.formatted())
                    .font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                    .accessibilityLabel(Text("Quantity"))
                    .accessibilityValue(position.position.formatted())
                Text(verbatim: contractSummary)
                    .font(.caption).monospacedDigit()
                    .lineLimit(1).minimumScaleFactor(0.8)
                Spacer(minLength: 4)
                OptionMidPrice(value: quote?.mid, movement: midMovement,
                               active: visible && phase == .active && store.selectedTab == "portfolio")
            }
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                OpportunityMetrics(quote: quote ?? emptyQuote)
                Spacer(minLength: 0)
                PositionPnLMeter(position: position)
                    .accessibilityLabel(Text("Unrealized P&L"))
            }.font(.caption)
            if showsRange { PositionDayRange(position: position) }
        }.padding(.vertical, 4)
        .onAppear { visible = true }
        .onDisappear { visible = false }
        .task(id: context) {
            quote = nil
            frozen = false
            midMovement = OptionMidMovement()
            guard visible, phase == .active, store.selectedTab == "portfolio" else { return }
            if store.demo {
                quote = ContractQuote(strike: position.strike ?? 0, expiration: position.expiration ?? "", bid: 0.38, ask: 0.42, delta: position.option_type == "PUT" ? -0.25 : 0.25, implied_volatility: 45)
                return
            }
            guard let id = position.con_id, id > 0 else { return }
            var failures = 0
            var initialReads = 0
            while !Task.isCancelled {
                var missing = true
                var failed = false
                _ = await store.opportunities.allowsAutomaticRefresh(store)
                guard !Task.isCancelled else { return }
                let marketClosed = store.opportunities.marketOpen == false
                do {
                    let result = try await store.trading.get("api/portfolio/option-position/\(id)/quote", base: store.address, query: [URLQueryItem(name: "wait", value: "0")])
                    try Task.checkCancellation()
                    guard result["con_id"] as? Int == id else { throw AppError.message("Contract mismatch") }
                    initialReads += 1
                    quote = ContractQuote(strike: position.strike ?? 0, expiration: position.expiration ?? "", bid: result["bid"] as? Double, ask: result["ask"] as? Double, delta: result["delta"] as? Double, implied_volatility: result["implied_volatility"] as? Double)
                    frozen = result["is_frozen"] as? Bool ?? false
                    midMovement.update(quote?.mid, frozen: frozen)
                    missing = ["bid", "ask", "delta", "implied_volatility"].contains {
                        guard let value = result[$0] as? Double else { return true }
                        return !value.isFinite
                    }
                } catch {
                    guard !Task.isCancelled else { return }
                    failed = true
                    quote = nil
                    frozen = false
                    midMovement = OptionMidMovement()
                }
                let retrying = failed || (missing && !(frozen && marketClosed))
                failures = retrying ? min(5, failures + 1) : 0
                // A new subscription may not have its first tick yet. Retry twice
                // without making closed-market missing Greeks poll continuously.
                let warming = !failed && initialReads < 3 && quote?.mid == nil
                let delay = warming ? 1 : RefreshLoop.optionMetricsDelay(frozen: frozen, marketClosed: marketClosed, missing: missing, failed: failed, failures: failures)
                do { try await Task.sleep(for: .seconds(delay)) } catch { return }
            }
        }
    }
}

// Track changes in the displayed midpoint, never changes in the broker valuation.
struct OptionMidMovement {
    private(set) var value: Double?
    private(set) var updated: Date?
    private var direction = 0

    mutating func update(_ value: Double?, frozen: Bool, now: Date = .now) {
        let valid = value.flatMap { $0.isFinite && $0 > 0 ? $0 : nil }
        let fresh = updated.map { now.timeIntervalSince($0) >= 0 && now.timeIntervalSince($0) < 15 } ?? false
        direction = !frozen && fresh ? TradingMath.priceDirection(previous: self.value, current: valid) : 0
        self.value = valid
        updated = !frozen && valid != nil ? now : nil
    }

    func direction(at now: Date) -> Int {
        guard let updated, now.timeIntervalSince(updated) >= 0,
              now.timeIntervalSince(updated) < 15 else { return 0 }
        return direction
    }
}

struct OptionMidPrice: View {
    let value: Double?
    let movement: OptionMidMovement
    var active: Bool
    @Environment(\.customPalette) private var customPalette
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        TimelineView(.animation(minimumInterval: 1, paused: !active)) { context in
            let direction = active ? movement.direction(at: context.date) : 0
            HStack(alignment: .firstTextBaseline, spacing: 4) {
                Text(verbatim: "Mid").font(.caption).foregroundStyle(.secondary)
                Text(money(value)).monospacedDigit()
                    .foregroundStyle(direction > 0 ? customPalette.color("gain", scheme: scheme, fallback: FinancialColors.gain) : direction < 0 ? customPalette.color("loss", scheme: scheme, fallback: FinancialColors.loss) : Color.primary)
            }
            .lineLimit(1).fixedSize(horizontal: true, vertical: false)
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(Text(verbatim: "Mid price"))
            .accessibilityValue(Text(verbatim: money(value)))
        }
    }
}
