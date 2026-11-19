import SwiftUI

enum CoreAssetStyle {
    static let symbols = ["SGOV", "VTI", "QQQ", "SPY", "VOO"]
    static func contains(_ symbol: String) -> Bool { symbols.contains(symbol.uppercased()) }
    static func lettering(_ symbol: String) -> String {
        ["SGOV": "𝕊𝔾𝕆𝕍", "VTI": "𝕍𝕋𝕀", "QQQ": "ℚℚℚ", "SPY": "𝕊ℙ𝕐", "VOO": "𝕍𝕆𝕆"][symbol.uppercased()] ?? symbol
    }
    static let red = Color(red: 0.84, green: 0.13, blue: 0.09)
    static let brightGold = Color(red: 1, green: 0.84, blue: 0.32)
    static let darkGold = Color(red: 0.58, green: 0.30, blue: 0.05)
    static let signatureFlow: [Color] = [.clear, red, brightGold, darkGold, .clear]
    static func sectorColor(_ fraction: Double) -> Color {
        let stops: [(Double, Double, Double)] = [(0.84, 0.13, 0.09), (1, 0.84, 0.32), (0.58, 0.30, 0.05)]
        let t = min(1, max(0, fraction)) * 2
        let index = min(1, Int(t)), mix = t - Double(min(1, Int(t)))
        let a = stops[index], b = stops[index + 1]
        return Color(red: a.0 + (b.0 - a.0) * mix, green: a.1 + (b.1 - a.1) * mix, blue: a.2 + (b.2 - a.2) * mix)
    }
}

struct SymbolText: View {
    let symbol: String
    @Environment(\.colorScheme) private var scheme
    @Environment(\.scenePhase) private var phase
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var visible = false
    var body: some View {
        if CoreAssetStyle.contains(symbol) {
            TimelineView(.animation(minimumInterval: 1.0 / 30, paused: !visible || phase != .active || reduceMotion)) { context in
                let progress = reduceMotion ? 0.5 : context.date.timeIntervalSinceReferenceDate.truncatingRemainder(dividingBy: 5) / 5
                Text(verbatim: CoreAssetStyle.lettering(symbol)).foregroundStyle(TradingColors.symbol(symbol, scheme: scheme))
                    .overlay {
                        if !reduceMotion {
                            GeometryReader { geometry in
                                LinearGradient(colors: symbol.uppercased() == "SGOV" ? [.clear, scheme == .dark ? Color.white : Color(red: 0.48, green: 0.23, blue: 0.02), .clear] : CoreAssetStyle.signatureFlow, startPoint: .leading, endPoint: .trailing)
                                    .frame(width: geometry.size.width * 0.65)
                                    .offset(x: geometry.size.width * (progress * 1.65 - 0.65))
                            }.mask(Text(verbatim: CoreAssetStyle.lettering(symbol))).allowsHitTesting(false)
                        }
                    }
            }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(Text(verbatim: symbol))
            .onAppear { visible = true }.onDisappear { visible = false }
        } else {
            Text(symbol)
        }
    }
}

enum TradingColors {
    static func symbol(_ symbol: String, scheme: ColorScheme) -> Color {
        guard CoreAssetStyle.contains(symbol) else { return .primary }
        if symbol.uppercased() != "SGOV" { return scheme == .dark ? CoreAssetStyle.brightGold : CoreAssetStyle.darkGold }
        return scheme == .dark ? Color(red: 1.00, green: 0.88, blue: 0.58) : Color(red: 0.78, green: 0.60, blue: 0.16)
    }
}
