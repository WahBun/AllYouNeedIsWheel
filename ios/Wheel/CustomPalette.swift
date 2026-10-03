import SwiftUI
import UIKit

struct CustomPalette {
    var values: [String: String] = [:]
    init(json: String = "{}") { values = (try? JSONDecoder().decode([String: String].self, from: Data(json.utf8))) ?? [:] }
    static func normalized(_ text: String) -> String? {
        let value = text.trimmingCharacters(in: .whitespacesAndNewlines).replacingOccurrences(of: "#", with: "").uppercased()
        guard value.count == 6, value.allSatisfy({ $0.isHexDigit }), UInt32(value, radix: 16) != nil else { return nil }
        return "#" + value
    }
    static func color(_ hex: String) -> Color? {
        guard let hex = normalized(hex), let number = UInt32(hex.dropFirst(), radix: 16) else { return nil }
        return Color(red: Double((number >> 16) & 255) / 255, green: Double((number >> 8) & 255) / 255, blue: Double(number & 255) / 255)
    }
    func color(_ key: String, scheme: ColorScheme, fallback: Color) -> Color {
        values[key + (scheme == .dark ? ".dark" : ".light")].flatMap(Self.color) ?? fallback
    }
    static func metricFallback(_ name: String, band: Double, scheme: ColorScheme) -> Color {
        if ["spread", "delta", "iv"].contains(name) && band == 1 { return Self.color(scheme == .dark ? "#AD6417" : "#854A0F")! }
        return DemoMetricColors.color(band, scheme: scheme)
    }
    func metric(_ name: String, value: Double, scheme: ColorScheme) -> Color {
        let band: Double
        if name == "spread" {
            switch SpreadBand.classify(value) {
            case .tight: band = 0
            case .medium: band = 0.5
            case .wide: band = 1
            case .unavailable: return .secondary
            }
        } else { band = DemoMetricColors.band(value) }
        let key = name + (band == 0 ? ".low" : band == 0.5 ? ".medium" : ".high")
        return color(key, scheme: scheme, fallback: Self.metricFallback(name, band: band, scheme: scheme))
    }
}
private struct CustomPaletteKey: EnvironmentKey { static let defaultValue = CustomPalette() }
extension EnvironmentValues {
    var customPalette: CustomPalette {
        get { self[CustomPaletteKey.self] }
        set { self[CustomPaletteKey.self] = newValue }
    }
}

struct PaletteColorEditor: View {
    let title: String
    let colorKey: String
    let fallback: Color
    @Environment(\.colorScheme) private var scheme
    @AppStorage("demoCustomColors") private var json = "{}"
    @State private var draft = ""
    private var palette: CustomPalette { CustomPalette(json: json) }
    private var color: Color { palette.color(colorKey, scheme: scheme, fallback: fallback) }
    private var hex: String {
        var r: CGFloat = 0, g: CGFloat = 0, b: CGFloat = 0, a: CGFloat = 0
        UIColor(color).getRed(&r, green: &g, blue: &b, alpha: &a)
        return String(format: "#%02X%02X%02X", Int((r * 255).rounded()), Int((g * 255).rounded()), Int((b * 255).rounded()))
    }
    private func save(_ value: String) {
        guard let value = CustomPalette.normalized(value) else { return }
        var values = palette.values
        values[colorKey + (scheme == .dark ? ".dark" : ".light")] = value
        if let data = try? JSONEncoder().encode(values), let text = String(data: data, encoding: .utf8) { json = text }
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            ColorPicker(LocalizedStringKey(title), selection: Binding(get: { color }, set: { next in
                var r: CGFloat = 0, g: CGFloat = 0, b: CGFloat = 0, a: CGFloat = 0
                guard UIColor(next).getRed(&r, green: &g, blue: &b, alpha: &a) else { return }
                save(String(format: "#%02X%02X%02X", Int((r * 255).rounded()), Int((g * 255).rounded()), Int((b * 255).rounded())))
            }), supportsOpacity: false)
            HStack {
                TextField("#RRGGBB", text: $draft).textInputAutocapitalization(.characters).autocorrectionDisabled().font(.caption.monospaced())
                    .onSubmit { save(draft) }
                Button("Apply") { save(draft) }.disabled(CustomPalette.normalized(draft) == nil)
            }
        }.onAppear { draft = hex }.onChange(of: hex) { draft = hex }
    }
}

struct MetricHighFinish: ViewModifier {
    var active: Bool
    var color: Color
    @Environment(\.scenePhase) private var phase
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var visible = false
    func body(content: Content) -> some View {
        if active {
            TimelineView(.animation(minimumInterval: 1.0 / 30, paused: !visible || phase != .active || reduceMotion)) { context in
                let progress = context.date.timeIntervalSinceReferenceDate.truncatingRemainder(dividingBy: 5) / 5
                content.overlay {
                    if !reduceMotion {
                        GeometryReader { geometry in
                            LinearGradient(colors: CoreAssetStyle.signatureFlow, startPoint: .leading, endPoint: .trailing)
                                .frame(width: geometry.size.width * 0.8)
                                .offset(x: geometry.size.width * (progress * 1.8 - 0.8))
                        }.mask(content).allowsHitTesting(false).accessibilityHidden(true)
                    }
                }
            }.onAppear { visible = true }.onDisappear { visible = false }
        } else { content }
    }
}
