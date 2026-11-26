import SwiftUI

struct AllocationPosition: Codable {
    let symbol: String
    let value: Double?
}

struct AllocationSnapshot: Codable {
    let positions: [AllocationPosition]
    let cash: Double?
    let net: Double?
}

struct AllocationItem: Identifiable {
    let id: String
    let name: String
    let value: Double
}

struct AllocationData {
    let assets: [AllocationItem]
    let liabilities: [AllocationItem]
    let missingCount: Int
    let net: Double?
    private let ordinaryColorIndex: [String: Int]
    var total: Double { assets.reduce(0) { $0 + $1.value } }
    var accountedNet: Double { total + liabilities.reduce(0) { $0 + $1.value } }
    var difference: Double? { net.map { $0 - accountedNet } }

    init(snapshot: AllocationSnapshot?) {
        var positive: [String: Double] = [:]
        var negative: [String: Double] = [:]
        var missing = 0
        for position in snapshot?.positions ?? [] {
            guard let value = position.value, value.isFinite else { missing += 1; continue }
            let symbol = position.symbol.uppercased()
            if value > 0 { positive[symbol, default: 0] += value }
            if value < 0 { negative[symbol, default: 0] += value }
        }
        var assets = positive.map { AllocationItem(id: "asset:\($0.key)", name: $0.key, value: $0.value) }
        var liabilities = negative.map { AllocationItem(id: "liability:\($0.key)", name: $0.key, value: $0.value) }
        if let cash = snapshot?.cash, cash.isFinite {
            if cash > 0 { assets.append(AllocationItem(id: "cash", name: "Cash", value: cash)) }
            if cash < 0 { liabilities.append(AllocationItem(id: "cash", name: "Cash", value: cash)) }
        } else if snapshot != nil { missing += 1 }
        let ordinary = Set((snapshot?.positions ?? []).map { $0.symbol.uppercased() }.filter { !CoreAssetStyle.contains($0) })
        let positiveSymbols = ordinary.intersection(positive.keys).sorted()
        let symbols = positiveSymbols + ordinary.subtracting(positiveSymbols).sorted()
        ordinaryColorIndex = Dictionary(uniqueKeysWithValues: symbols.enumerated().map { ($0.element, $0.offset) })
        self.assets = assets.sorted { $0.value == $1.value ? $0.id < $1.id : $0.value > $1.value }
        self.liabilities = liabilities.sorted { $0.value == $1.value ? $0.id < $1.id : $0.value < $1.value }
        missingCount = missing
        net = snapshot?.net.flatMap { $0.isFinite ? $0 : nil }
    }

    func color(_ item: AllocationItem, scheme: ColorScheme) -> Color {
        item.id == "cash" ? .gray : symbolColor(item.name, scheme: scheme)
    }

    func symbolColor(_ name: String, scheme: ColorScheme) -> Color {
        if CoreAssetStyle.contains(name) { return TradingColors.symbol(name, scheme: scheme) }
        guard let index = ordinaryColorIndex[name] else { return .secondary }
        // Spread neighboring sectors around the hue wheel. Keep the first slots
        // clear of the teal, apricot and gold used by the special symbols.
        let hues: [Double] = [215, 317, 94, 262, 8, 184, 337, 68]
        let hue = index < hues.count ? hues[index] / 360
            : (0.37 + Double(index - hues.count) * 0.61803398875).truncatingRemainder(dividingBy: 1)
        return Color(hue: hue, saturation: scheme == .dark ? 0.62 : 0.80, brightness: scheme == .dark ? 0.96 : 0.70)
    }
}

struct AllocationSlice: Identifiable {
    let item: AllocationItem
    let start: Double
    let end: Double
    var id: String { item.id }

    static func at(clockwiseDegrees angle: Double, in slices: [Self]) -> Self? {
        let normalized = (angle.truncatingRemainder(dividingBy: 360) + 360).truncatingRemainder(dividingBy: 360)
        return slices.first { normalized >= $0.start && normalized < $0.end }
    }
}

extension AllocationData {
    var slices: [AllocationSlice] {
        let sum = total
        guard sum.isFinite, sum > 0 else { return [] }
        var start = 0.0
        return assets.sorted { $0.id < $1.id }.map { item in
            let end = start + item.value / sum * 360
            defer { start = end }
            return AllocationSlice(item: item, start: start, end: end)
        }
    }
}
