import SwiftUI

/// Uses Trade's information hierarchy with held-position data, not entry estimates.
struct PortfolioOptionRow: View {
    let position: Position
    @Environment(WheelStore.self) private var store
    @Environment(\.scenePhase) private var phase
    @State private var quote: ContractQuote?
    @State private var frozen = false
    private var context: String { "\(store.demo)-\(store.address)-\(position.id)-\(store.selectedTab)-\(phase == .active)" }
    private var emptyQuote: ContractQuote { ContractQuote(strike: position.strike ?? 0, expiration: position.expiration ?? "") }
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .firstTextBaseline) {
                SymbolText(symbol: position.symbol).font(.headline)
                Text(position.option_type ?? "—")
                    .font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                Spacer(minLength: 8)
            }
            HStack(alignment: .top, spacing: 8) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("\(money(position.strike)) · \(position.expiration ?? "—")")
                        .monospacedDigit()
                    HStack(spacing: 4) {
                        Text(position.position.formatted())
                        Text("·")
                        PositionMarketPrice(position: position)
                    }.foregroundStyle(.secondary)
                        .accessibilityElement(children: .ignore)
                        .accessibilityLabel(Text("Quantity"))
                        .accessibilityValue("\(position.position.formatted()) · \(money(position.market_price))")
                }
                Spacer(minLength: 0)
                PositionPnLMeter(position: position)
                    .accessibilityLabel(Text("Unrealized P&L"))
            }.font(.caption)
            OpportunityMetrics(quote: quote ?? emptyQuote)
            if frozen { Text("Frozen").font(.caption2).foregroundStyle(.secondary) }
        }.padding(.vertical, 4)
        .task(id: context) {
            quote = nil
            frozen = false
            guard phase == .active, store.selectedTab == "portfolio" else { return }
            if store.demo {
                quote = ContractQuote(strike: position.strike ?? 0, expiration: position.expiration ?? "", bid: 0.38, ask: 0.42, delta: position.option_type == "PUT" ? -0.25 : 0.25, implied_volatility: 45)
                return
            }
            guard let id = position.con_id, id > 0 else { return }
            while !Task.isCancelled {
                do {
                    let result = try await store.trading.get("api/portfolio/option-position/\(id)/quote", base: store.address)
                    try Task.checkCancellation()
                    guard result["con_id"] as? Int == id else { throw AppError.message("Contract mismatch") }
                    quote = ContractQuote(strike: position.strike ?? 0, expiration: position.expiration ?? "", bid: result["bid"] as? Double, ask: result["ask"] as? Double, delta: result["delta"] as? Double, implied_volatility: result["implied_volatility"] as? Double)
                    frozen = result["is_frozen"] as? Bool ?? false
                } catch {
                    guard !Task.isCancelled else { return }
                    quote = nil
                    frozen = false
                }
                do { try await Task.sleep(for: .seconds(frozen ? 30 : 15)) } catch { return }
            }
        }
    }
}
