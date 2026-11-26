import SwiftUI

private func dollars(_ value: Double?) -> String {
    guard let value, value.isFinite else { return "—" }
    return value.formatted(.currency(code: "USD").locale(Locale(identifier: "en_US")))
}

private struct RingSector: Shape {
    let slice: AllocationSlice
    func path(in rect: CGRect) -> Path {
        let radius = min(rect.width, rect.height) / 2
        let center = CGPoint(x: rect.midX, y: rect.midY)
        let gap = min(0.7, (slice.end - slice.start) * 0.12)
        let a = Angle.degrees(slice.start - 90 + gap)
        let b = Angle.degrees(slice.end - 90 - gap)
        var path = Path()
        path.addArc(center: center, radius: radius, startAngle: a, endAngle: b, clockwise: false)
        path.addArc(center: center, radius: radius * 0.72, startAngle: b, endAngle: a, clockwise: true)
        path.closeSubpath()
        return path
    }
}

struct WatchAllocationOverview: View {
    let snapshot: WatchSnapshot
    let open: (WatchAssetSelection) -> Void
    @Environment(\.colorScheme) private var scheme

    private func select(_ symbol: String?) {
        open(WatchAssetSelection(mode: snapshot.mode, epoch: snapshot.epoch, symbol: symbol))
    }

    private func style(_ slice: AllocationSlice, data: AllocationData) -> AnyShapeStyle {
        let item = slice.item
        if item.name == "SGOV" {
            let gold = Color(red: 0.66, green: 0.36, blue: 0.07)
            return AnyShapeStyle(LinearGradient(colors: [data.color(item, scheme: scheme), gold],
                                                 startPoint: .topLeading, endPoint: .bottomTrailing))
        }
        if CoreAssetStyle.contains(item.name) {
            return AnyShapeStyle(AngularGradient(colors: [CoreAssetStyle.red, CoreAssetStyle.brightGold, CoreAssetStyle.darkGold],
                                                 center: .center, startAngle: .degrees(slice.start - 90), endAngle: .degrees(slice.end - 90)))
        }
        return AnyShapeStyle(data.color(item, scheme: scheme))
    }

    var body: some View {
        let data = AllocationData(snapshot: snapshot.allocation)
        let slices = data.slices
        let symbols = Set((snapshot.allocation?.positions.map(\.symbol) ?? snapshot.positions.map(\.symbol)).map { $0.uppercased() })
        let positive = data.assets.filter { $0.id != "cash" }.map(\.name)
        if snapshot.allocation != nil {
            GeometryReader { proxy in
                let size = min(proxy.size.width, proxy.size.height)
                ZStack {
                    Circle().strokeBorder(.secondary.opacity(0.18), lineWidth: size * 0.14)
                    ForEach(slices) { slice in
                        if CoreAssetStyle.usesTealApricot(slice.item.name) {
                            TealApricotFlow().mask(RingSector(slice: slice))
                        } else {
                            RingSector(slice: slice).fill(style(slice, data: data))
                        }
                    }
                    VStack(spacing: 1) {
                        Text("Net liquidation").font(.caption2).foregroundStyle(.secondary)
                            .lineLimit(1).minimumScaleFactor(0.65)
                        Text(verbatim: dollars(data.net)).font(.headline).monospacedDigit()
                            .lineLimit(1).minimumScaleFactor(0.55)
                    }.frame(width: size * 0.66)
                }
                .frame(width: size, height: size)
                .contentShape(Circle())
                .onTapGesture { point in
                    let x = point.x - size / 2, y = point.y - size / 2
                    guard hypot(x, y) >= size * 0.36, hypot(x, y) <= size * 0.5,
                          let slice = AllocationSlice.at(clockwiseDegrees: atan2(x, -y) * 180 / .pi, in: slices) else { return }
                    select(slice.item.id == "cash" ? nil : slice.item.name)
                }
                .accessibilityElement(children: .ignore)
                .accessibilityLabel("Net liquidation")
                .accessibilityValue(dollars(data.net))
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }.frame(height: 132)
            if data.missingCount > 0 {
                Text("Partial allocation").font(.caption2).foregroundStyle(.secondary)
            } else if slices.isEmpty {
                Text("No positive assets").font(.caption2).foregroundStyle(.secondary)
            }
        } else {
            Text("Allocation unavailable").font(.footnote).foregroundStyle(.secondary)
        }
        LazyVGrid(columns: [GridItem(.adaptive(minimum: 54), spacing: 3)], spacing: 3) {
            ForEach(positive + symbols.subtracting(positive).sorted(), id: \.self) { symbol in
                chip(symbol, color: data.symbolColor(symbol, scheme: scheme))
            }
            if let cash = snapshot.allocation?.cash, cash != 0 { chip(nil, color: .gray) }
        }
    }

    private func chip(_ symbol: String?, color: Color) -> some View {
        Button { select(symbol) } label: {
            HStack(spacing: 3) {
                Circle().fill(color).frame(width: 5, height: 5)
                if let symbol { SymbolText(symbol: symbol, textStyle: .caption1) } else { Text("Cash") }
            }.font(.caption).lineLimit(1).minimumScaleFactor(0.65)
                .padding(.horizontal, 3).frame(maxWidth: .infinity, minHeight: 30)
                .background(.secondary.opacity(0.12), in: Capsule()).contentShape(Capsule())
        }.buttonStyle(.plain).accessibilityLabel(symbol ?? "Cash")
    }
}

struct WatchAssetDetail: View {
    let asset: WatchAssetSelection
    let snapshot: WatchSnapshot
    @Binding var page: Int
    @Environment(\.locale) private var locale

    var body: some View {
        let data = AllocationData(snapshot: snapshot.allocation)
        let assetID = asset.symbol.map { "asset:" + $0 } ?? "cash"
        let liabilityID = asset.symbol.map { "liability:" + $0 } ?? "cash"
        VStack(alignment: .leading, spacing: 8) {
            if let symbol = asset.symbol {
                SymbolText(symbol: symbol, textStyle: .headline).font(.headline)
            } else {
                Text("Cash").font(.headline)
            }
            if let symbol = asset.symbol {
                let rows = asset.holdings(in: snapshot)
                ForEach(rows) { row in
                    if row.contract != row.symbol {
                        Text(verbatim: row.contract).font(.footnote.bold())
                    }
                    metric(row.costSource == "report" ? "IBKR reported average cost" : "Average cost",
                           row.averageCostText(locale: locale))
                    if let date = row.reportDate {
                        Text("Report date · \(date)").font(.caption2).foregroundStyle(.secondary)
                        if let shares = row.reportedShares, abs(shares - row.quantity) > 0.000001 {
                            Text("Reported shares: \(shares.formatted())").font(.caption2).foregroundStyle(.orange)
                        }
                    } else if row.costSource == "report" {
                        Text("No report available").font(.caption2).foregroundStyle(.secondary)
                    }
                    LabeledContent("Quantity", value: row.quantity.formatted())
                    LabeledContent("Price", value: row.priceText(locale: locale))
                    Divider()
                }
                if snapshot.symbolFilter == symbol {
                    if rows.isEmpty { Text("No current position").font(.footnote) }
                    if page > 0 { Button("Previous") { page -= 1 } }
                    if (page + 1) * 30 < snapshot.total { Button("Next") { page += 1 } }
                }
            }
            if let item = data.assets.first(where: { $0.id == assetID }) {
                metric(asset.symbol == nil ? "Cash balance" : "Positive market value", dollars(item.value))
                metric("Of positive assets", (item.value / data.total).formatted(.percent.precision(.fractionLength(1))))
            }
            if let item = data.liabilities.first(where: { $0.id == liabilityID }) {
                metric(asset.symbol == nil ? "Cash balance" : "Short market value", dollars(item.value))
            } else if asset.symbol == nil && (snapshot.allocation?.cash ?? 0) <= 0 {
                metric("Cash balance", dollars(snapshot.allocation?.cash))
            }
        }.frame(maxWidth: .infinity, alignment: .leading)
    }

    private func metric(_ label: LocalizedStringKey, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 1) {
            Text(label).font(.caption2).foregroundStyle(.secondary)
            Text(verbatim: value).monospacedDigit()
        }
    }
}
