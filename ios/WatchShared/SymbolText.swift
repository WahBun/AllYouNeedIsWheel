import SwiftUI
import UIKit

enum CoreAssetStyle {
    private static let letteringBySymbol = [
        "SGOV": "𝕊𝔾𝕆𝕍", "VTI": "𝕍𝕋𝕀", "QQQ": "ℚℚℚ",
        "QQQM": "ℚℚℚ𝕄", "SPY": "𝕊ℙ𝕐", "VOO": "𝕍𝕆𝕆", "NVDA": "ℕ𝕍𝔻𝔸"
    ]
    static func contains(_ symbol: String) -> Bool { letteringBySymbol[symbol.uppercased()] != nil }
    static func lettering(_ symbol: String) -> String {
        letteringBySymbol[symbol.uppercased()] ?? symbol
    }
    static func usesTealApricot(_ symbol: String) -> Bool {
        ["NVDA", "QQQ", "QQQM"].contains(symbol.uppercased())
    }
    static func teal(_ scheme: ColorScheme) -> Color {
        scheme == .dark ? Color(red: 40/255, green: 164/255, blue: 153/255)
                        : Color(red: 18/255, green: 105/255, blue: 95/255)
    }
    static func apricot(_ scheme: ColorScheme) -> Color {
        scheme == .dark ? Color(red: 250/255, green: 188/255, blue: 132/255)
                        : Color(red: 149/255, green: 83/255, blue: 33/255)
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

struct TealApricotFlow: View {
    var active = true
    @Environment(\.colorScheme) private var scheme
    @Environment(\.scenePhase) private var phase
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.isLuminanceReduced) private var dimmed
    @State private var visible = false

    var body: some View {
        let animate = active && visible && phase == .active && !reduceMotion && !dimmed
        TimelineView(.animation(minimumInterval: 1.0 / 30, paused: !animate)) { context in
            let offset = animate ? context.date.timeIntervalSinceReferenceDate.truncatingRemainder(dividingBy: 5) * 2 / 5 : 0
            let teal = CoreAssetStyle.teal(scheme), apricot = CoreAssetStyle.apricot(scheme)
            LinearGradient(colors: [teal, apricot, teal, apricot],
                           startPoint: UnitPoint(x: -offset, y: 0.5), endPoint: UnitPoint(x: 3 - offset, y: 0.5))
        }
        .onAppear { visible = true }.onDisappear { visible = false }
        .allowsHitTesting(false).accessibilityHidden(true)
    }
}

struct SymbolText: View {
    let symbol: String
    var textStyle: UIFont.TextStyle = .body
    @Environment(\.colorScheme) private var scheme
    @Environment(\.scenePhase) private var phase
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var visible = false

    private var letteringStyle: AnyShapeStyle {
        #if os(watchOS)
        // The watch may pause its animation timeline while the lettering stays visible.
        if symbol.uppercased() != "SGOV" {
            return AnyShapeStyle(LinearGradient(colors: [CoreAssetStyle.red, CoreAssetStyle.brightGold, CoreAssetStyle.darkGold],
                                                startPoint: .leading, endPoint: .trailing))
        }
        #endif
        return AnyShapeStyle(TradingColors.symbol(symbol, scheme: scheme))
    }

    var body: some View {
        if CoreAssetStyle.contains(symbol) {
            let text = Text(verbatim: CoreAssetStyle.lettering(symbol))
            // The default fallback splits ℕ from the other three double-struck capitals.
            let lettering = symbol.uppercased() == "NVDA"
                ? text.font(.custom("STIXTwoMath-Regular", fixedSize: UIFont.preferredFont(forTextStyle: textStyle).pointSize))
                : text
            Group {
                if CoreAssetStyle.usesTealApricot(symbol) {
                    lettering.foregroundStyle(.clear).overlay { TealApricotFlow().mask(lettering) }
                } else {
                    TimelineView(.animation(minimumInterval: 1.0 / 30, paused: !visible || phase != .active || reduceMotion)) { context in
                        let progress = reduceMotion ? 0.5 : context.date.timeIntervalSinceReferenceDate.truncatingRemainder(dividingBy: 5) / 5
                        lettering.foregroundStyle(letteringStyle)
                            .overlay {
                                if !reduceMotion {
                                    GeometryReader { geometry in
                                        LinearGradient(colors: symbol.uppercased() == "SGOV" ? [.clear, scheme == .dark ? Color.white : Color(red: 0.48, green: 0.23, blue: 0.02), .clear] : CoreAssetStyle.signatureFlow, startPoint: .leading, endPoint: .trailing)
                                            .frame(width: geometry.size.width * 0.65)
                                            .offset(x: geometry.size.width * (progress * 1.65 - 0.65))
                                    }.mask(lettering).allowsHitTesting(false)
                                }
                            }
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
        if CoreAssetStyle.usesTealApricot(symbol) { return CoreAssetStyle.teal(scheme) }
        if symbol.uppercased() != "SGOV" { return scheme == .dark ? CoreAssetStyle.brightGold : CoreAssetStyle.darkGold }
        return scheme == .dark ? Color(red: 1.00, green: 0.88, blue: 0.58) : Color(red: 0.78, green: 0.60, blue: 0.16)
    }
}
