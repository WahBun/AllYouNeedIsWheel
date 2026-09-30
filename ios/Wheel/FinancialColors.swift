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
    static func color(_ progress: Double, scheme: ColorScheme) -> Color {
        let stops: [(Double, Double, Double)] = scheme == .dark
            ? [(0.44, 0.73, 1), (1, 0.84, 0.32), (0.77, 0.57, 1)]
            : [(0.12, 0.36, 0.67), (0.53, 0.37, 0.02), (0.48, 0.23, 0.72)]
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
    var body: some View {
        List {
            Section("P&L") {
                Text("+$128.00  +12.8%").foregroundStyle(FinancialColors.gain)
                Text("−$64.00  −6.4%").foregroundStyle(FinancialColors.loss)
            }
            Section("Delta / Spread / IV") {
                HStack { Text("Low"); Spacer(); OpportunityMetrics(quote: ContractQuote(strike: 10, expiration: "", bid: 0.99, ask: 1.01, delta: 0.15, implied_volatility: 20)) }
                HStack { Text("Medium"); Spacer(); OpportunityMetrics(quote: ContractQuote(strike: 10, expiration: "", bid: 0.9, ask: 1.1, delta: 0.5, implied_volatility: 70)) }
                HStack { Text("High"); Spacer(); OpportunityMetrics(quote: ContractQuote(strike: 10, expiration: "", bid: 0.8, ask: 1.2, delta: 1, implied_volatility: 140)) }
            }
        }.environment(\.demoMetricPalette, true)
            .navigationTitle("Demo colors")
    }
}
