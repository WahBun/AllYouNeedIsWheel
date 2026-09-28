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
    let order: Order
    @Environment(\.colorScheme) private var scheme
    private var color: Color {
        guard let value = order.realizedProfit, value != 0 else { return .secondary }
        return value > 0 ? (scheme == .dark ? .green : Color(red: 0.05, green: 0.45, blue: 0.2)) : .red
    }
    var body: some View {
        Text(order.realizedProfitLabel).monospacedDigit().foregroundStyle(color)
            .accessibilityLabel(Text("Realized P&L") + Text(" " + order.realizedProfitLabel))
    }
}
