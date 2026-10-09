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
    @State private var visible = false
    private var context: String { "\(visible)-\(store.demo)-\(store.address)-\(position.id)-\(store.selectedTab)-\(phase == .active)-\(store.portfolio?.summary.is_frozen == true)" }
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
                PositionMarketPrice(position: position)
            }
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                OpportunityMetrics(quote: quote ?? emptyQuote)
                Spacer(minLength: 0)
                PositionPnLMeter(position: position)
                    .accessibilityLabel(Text("Unrealized P&L"))
            }.font(.caption)
            if showsRange { PositionDayRange(position: position) }
            if frozen && position.day_range_status != "frozen" { Text("Frozen").font(.caption2).foregroundStyle(.secondary) }
        }.padding(.vertical, 4)
        .onAppear { visible = true }
        .onDisappear { visible = false }
        .task(id: context) {
            quote = nil
            frozen = false
            guard visible, phase == .active, store.selectedTab == "portfolio" else { return }
            if store.demo {
                quote = ContractQuote(strike: position.strike ?? 0, expiration: position.expiration ?? "", bid: 0.38, ask: 0.42, delta: position.option_type == "PUT" ? -0.25 : 0.25, implied_volatility: 45)
                return
            }
            guard let id = position.con_id, id > 0 else { return }
            var failures = 0
            while !Task.isCancelled {
                var missing = true
                var failed = false
                _ = await store.opportunities.allowsAutomaticRefresh(store)
                guard !Task.isCancelled else { return }
                let marketClosed = store.opportunities.marketOpen == false
                do {
                    let result = try await store.trading.get("api/portfolio/option-position/\(id)/quote", base: store.address)
                    try Task.checkCancellation()
                    guard result["con_id"] as? Int == id else { throw AppError.message("Contract mismatch") }
                    quote = ContractQuote(strike: position.strike ?? 0, expiration: position.expiration ?? "", bid: result["bid"] as? Double, ask: result["ask"] as? Double, delta: result["delta"] as? Double, implied_volatility: result["implied_volatility"] as? Double)
                    frozen = result["is_frozen"] as? Bool ?? false
                    missing = ["bid", "ask", "delta", "implied_volatility"].contains {
                        guard let value = result[$0] as? Double else { return true }
                        return !value.isFinite
                    }
                } catch {
                    guard !Task.isCancelled else { return }
                    failed = true
                    quote = nil
                    frozen = false
                }
                let retrying = failed || (missing && !(frozen && marketClosed))
                failures = retrying ? min(5, failures + 1) : 0
                let delay = RefreshLoop.optionMetricsDelay(frozen: frozen, marketClosed: marketClosed, missing: missing, failed: failed, failures: failures)
                do { try await Task.sleep(for: .seconds(delay)) } catch { return }
            }
        }
    }
}
