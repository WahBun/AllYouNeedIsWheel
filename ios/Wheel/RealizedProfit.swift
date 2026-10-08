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

struct DailyClosedProfit {
    let amount: Double
    let pending: Int
    static func calculate(_ orders: [Order], now: Date = .now) -> DailyClosedProfit {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "America/New_York")!
        var seen: Set<OrderID> = []
        var amount = 0.0, pending = 0
        for order in orders where order.intent == "CLOSE" && order.hasFill {
            guard seen.insert(order.id).inserted, let date = order.fillDate,
                  calendar.isDate(date, inSameDayAs: now) else { continue }
            if let net = order.closedNetProfit { amount += net }
            else { pending += 1 }
        }
        return DailyClosedProfit(amount: amount, pending: pending)
    }
}

struct OrdersDailyProfit: View {
    @Environment(WheelStore.self) private var store
    @Environment(\.customPalette) private var palette
    @Environment(\.colorScheme) private var scheme
    var body: some View {
        TimelineView(.periodic(from: .now, by: 30)) { clock in
            let total = DailyClosedProfit.calculate(store.filledOrders, now: clock.date)
            let ready = store.filledError == nil && store.filledUpdated != nil
            VStack(alignment: .trailing, spacing: 3) {
                Text("Daily P&L").font(.caption).foregroundStyle(.secondary)
                Text(ready ? (total.amount > 0 ? "+" : "") + money(total.amount) : "—")
                    .font(.title3.weight(.semibold)).monospacedDigit()
                    .foregroundStyle(!ready || total.amount == 0 ? Color.secondary : palette.color(total.amount > 0 ? "gain" : "loss", scheme: scheme, fallback: total.amount > 0 ? FinancialColors.gain : FinancialColors.loss))
                if total.pending > 0 {
                    Text("\(total.pending) awaiting P&L").font(.caption2).foregroundStyle(.secondary)
                }
            }.accessibilityElement(children: .combine)
                .help("Today's confirmed closed-order net P&L · New York date")
        }
    }
}


extension Order {
    private func fillLabel(_ format: String) -> String {
        guard let date = fillDate else { return "—" }
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(identifier: "America/New_York")
        formatter.dateFormat = format
        return formatter.string(from: date)
    }
    var fillDayLabel: String { fillDate == nil ? "Unknown date" : fillLabel("MMM d, yyyy") }
    var fillClockLabel: String { fillLabel("HH:mm:ss") }
    var closedNetProfit: Double? {
        guard intent == "CLOSE", hasFill else { return nil }
        guard let value = net_pnl ?? realizedProfit, value.isFinite, abs(value) < 1e100 else { return nil }
        return value
    }
}

struct CompactOrderRow: View {
    let order: Order
    let history: Bool
    @Environment(\.customPalette) private var palette
    @Environment(\.colorScheme) private var scheme
    private var action: String { (history ? order.fill_action ?? order.action : order.action) ?? "—" }
    private var isBuy: Bool { action.uppercased() == "BUY" || action.uppercased() == "BOT" }
    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            HStack(alignment: .top, spacing: 10) {
                VStack(alignment: .leading, spacing: 4) {
                    SymbolText(symbol: order.name).font(.headline)
                    if order.option_type != "STOCK" && order.option_type != "FUTURE" {
                        Text("\(order.expiration ?? "") \(money(order.strike)) \(order.option_type ?? "")")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    Text("\(history ? (isBuy ? "Bought" : "Sold") : action) \((history ? order.filledQuantity : order.quantity)?.formatted() ?? "—")")
                        .font(.subheadline).foregroundStyle(isBuy ? Color.blue : Color.red)
                    Text("\(order.order_type ?? "LMT") · \(order.timingLabel)")
                        .font(.caption).foregroundStyle(.secondary)
                }.frame(maxWidth: .infinity, alignment: .leading)
                VStack(alignment: .trailing, spacing: 4) {
                    Text(money(history ? order.fillPrice : order.premium)).font(.headline)
                    if history {
                        NoticeText(order.commissionLabel).font(.caption2).foregroundStyle(.secondary)
                    }
                }.monospacedDigit()
                VStack(alignment: .trailing, spacing: 6) {
                    Text(history ? order.fillClockLabel : order.status)
                        .font(.caption).foregroundStyle(.secondary)
                    if history && order.intent == "CLOSE" {
                        if let value = order.closedNetProfit {
                            Text((value > 0 ? "+" : "") + money(value)).font(.subheadline.weight(.semibold))
                                .foregroundStyle(value == 0 ? Color.secondary : palette.color(value > 0 ? "gain" : "loss", scheme: scheme, fallback: value > 0 ? FinancialColors.gain : FinancialColors.loss))
                        } else {
                            Text("P&L —").font(.caption).foregroundStyle(.secondary)
                        }
                    }
                }.monospacedDigit().frame(minWidth: 65, alignment: .trailing)
            }
            if !history && (order.amendment_pending != nil || ["unknown", "rejected", "inactive"].contains(order.status.lowercased())) {
                Text(LocalizedStringKey(order.statusExplanation)).font(.caption).foregroundStyle(.orange)
            }
            if !history, let filled = order.filledQuantity, filled > 0 {
                Text("Filled \(filled.formatted()) / \(order.quantity?.formatted() ?? "—")")
                    .font(.caption).foregroundStyle(.secondary)
            }
            if order.isRollover == true {
                Text("Rollover leg · independent order").font(.caption).foregroundStyle(.orange)
            }
        }.padding(.vertical, 4)
    }
}
