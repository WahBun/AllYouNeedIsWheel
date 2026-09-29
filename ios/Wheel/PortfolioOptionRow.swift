import SwiftUI

/// Uses Trade's information hierarchy with held-position data, not entry estimates.
struct PortfolioOptionRow: View {
    let position: Position
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
        }.padding(.vertical, 4)
    }
}
