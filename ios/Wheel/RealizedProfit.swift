import SwiftUI

extension Order {
    var realizedProfit: Double? {
        guard intent == "CLOSE", hasFill, commission_currency == "USD",
              let value = realized_pnl, value.isFinite, abs(value) < 1e100 else { return nil }
        return value
    }
    var realizedProfitLabel: String {
        guard let value = realizedProfit else { return "—" }
        return (value > 0 ? "+" : "") + money(value)
    }
}

struct RealizedProfit: View {
    @Environment(\.customPalette) private var customPalette
    let order: Order
    @Environment(\.colorScheme) private var scheme
    private var color: Color {
        guard let value = order.realizedProfit, value != 0 else { return .secondary }
        return customPalette.color(value > 0 ? "gain" : "loss", scheme: scheme, fallback: value > 0 ? FinancialColors.gain : FinancialColors.loss)
    }
    var body: some View {
        Text(order.realizedProfitLabel).monospacedDigit().foregroundStyle(color)
            .accessibilityLabel(Text("Realized P&L") + Text(" " + order.realizedProfitLabel))
    }
}

struct FuturesProfit: View {
    let order: Order
    @Environment(\.customPalette) private var palette
    @Environment(\.colorScheme) private var scheme
    private var value: Double? { order.net_pnl ?? order.gross_pnl ?? order.realizedProfit }
    var body: some View {
        if order.intent == "OPEN" {
            Text("Entry fill · P&L shown on exit").font(.caption).foregroundStyle(.secondary)
        } else if let value, value.isFinite {
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text(order.net_pnl != nil ? "Net P&L" : order.gross_pnl != nil ? "Gross P&L" : "Realized P&L")
                    Spacer()
                    Text((value > 0 ? "+" : "") + money(value)).monospacedDigit().bold()
                        .foregroundStyle(value == 0 ? Color.secondary : palette.color(value > 0 ? "gain" : "loss", scheme: scheme, fallback: value > 0 ? FinancialColors.gain : FinancialColors.loss))
                }.font(.headline)
                if let fee = order.round_trip_commission {
                    Text("Gross \(money(order.gross_pnl)) · Entry + exit fees \(money(fee))").font(.caption).foregroundStyle(.secondary)
                } else if order.gross_pnl != nil {
                    Text("Before fees · commission confirmation pending").font(.caption).foregroundStyle(.secondary)
                }
            }
        } else {
            Text("P&L awaiting matched entry / broker report").font(.caption).foregroundStyle(.secondary)
        }
    }
}
