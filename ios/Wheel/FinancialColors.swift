import SwiftUI

enum FinancialColors {
    static let gain = Color(red: 57.0 / 255, green: 1, blue: 20.0 / 255)
    static let loss = Color(red: 1, green: 94.0 / 255, blue: 94.0 / 255)
}
private struct DemoMetricPaletteKey: EnvironmentKey { static let defaultValue = false }
extension EnvironmentValues {
    var demoMetricPalette: Bool {
        get { self[DemoMetricPaletteKey.self] }
        set { self[DemoMetricPaletteKey.self] = newValue }
    }
}
enum DemoMetricColors {
    static func band(_ value: Double) -> Double {
        value <= 30 ? 0 : value <= 70 ? 0.5 : 1
    }
    static func color(_ progress: Double, scheme: ColorScheme) -> Color {
        let high: (Double, Double, Double) = (209.0 / 255.0, 196.0 / 255.0, 233.0 / 255.0)
        let stops: [(Double, Double, Double)] = scheme == .dark
            ? [(0.44, 0.73, 1), (1, 0.72, 0.48), high]
            : [(0.12, 0.36, 0.67), (1, 0.72, 0.48), high]
        let value = min(1, max(0, progress)) * 2
        let index = min(1, Int(value))
        let fraction = value - Double(index)
        let a = stops[index], b = stops[index + 1]
        return Color(red: a.0 + (b.0 - a.0) * fraction,
                     green: a.1 + (b.1 - a.1) * fraction,
                     blue: a.2 + (b.2 - a.2) * fraction)
    }
}
struct MetricPalettePreview: View {
    @AppStorage("demoCustomColors") private var json = "{}"
    @Environment(\.colorScheme) private var scheme
    private var palette: CustomPalette { CustomPalette(json: json) }
    var body: some View {
        List {
            Section("P&L") {
                Text("+$128.00  +12.8%").foregroundStyle(palette.color("gain", scheme: scheme, fallback: FinancialColors.gain))
                Text("−$64.00  −6.4%").foregroundStyle(palette.color("loss", scheme: scheme, fallback: FinancialColors.loss))
            }
            Section("Delta / Spread / IV") {
                HStack { Text("Low"); Spacer(); OpportunityMetrics(quote: ContractQuote(strike: 10, expiration: "", bid: 0.99, ask: 1.01, delta: 0.15, implied_volatility: 20)) }
                HStack { Text("Medium"); Spacer(); OpportunityMetrics(quote: ContractQuote(strike: 10, expiration: "", bid: 0.75, ask: 1.25, delta: 0.5, implied_volatility: 70)) }
                HStack { Text("High"); Spacer(); OpportunityMetrics(quote: ContractQuote(strike: 10, expiration: "", bid: 0.6, ask: 1.4, delta: 1, implied_volatility: 140)) }
            }
            Section("System color") {
                PaletteColorEditor(title: "System color", colorKey: "accent", fallback: scheme == .dark ? Color(red: 0.93, green: 0.92, blue: 0.89) : Color(red: 0.27, green: 0.28, blue: 0.30))
            }
            Section("P&L colors") {
                PaletteColorEditor(title: "Profit", colorKey: "gain", fallback: FinancialColors.gain)
                PaletteColorEditor(title: "Loss", colorKey: "loss", fallback: FinancialColors.loss)
            }
            ForEach(["Delta", "Spread", "IV"], id: \.self) { name in
                Section(name) {
                    PaletteColorEditor(title: "Low", colorKey: name.lowercased() + ".low", fallback: DemoMetricColors.color(0, scheme: scheme))
                    PaletteColorEditor(title: "Medium", colorKey: name.lowercased() + ".medium", fallback: DemoMetricColors.color(0.5, scheme: scheme))
                    PaletteColorEditor(title: "High", colorKey: name.lowercased() + ".high", fallback: DemoMetricColors.color(1, scheme: scheme))
                }
            }
            Section {
                Text("Colors apply to Demo and Live. Light and Dark are saved separately. Thresholds remain 30 / 70.").font(.footnote).foregroundStyle(.secondary)
                Button("Restore default colors") { json = "{}" }
            }
        }.environment(\.customPalette, palette)
        .environment(\.demoMetricPalette, true)
            .navigationTitle("Custom colors")
    }
}
