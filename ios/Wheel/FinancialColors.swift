import SwiftUI
import UIKit

enum FinancialColors {
    // Match the Trade summary premium; use a darker green on light surfaces.
    static let gain = Color(uiColor: UIColor { traits in
        traits.userInterfaceStyle == .dark
            ? UIColor(red: 0.70, green: 1, blue: 0.30, alpha: 1)
            : UIColor(red: 0.28, green: 0.46, blue: 0.02, alpha: 1)
    })
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
private struct PaletteEditTarget: Identifiable {
    let id: String
    let title: String
    let fallback: Color
}
struct MetricPalettePreview: View {
    @State private var editing: PaletteEditTarget?
    @AppStorage("demoCustomColors") private var json = "{}"
    @Environment(\.colorScheme) private var scheme
    private var palette: CustomPalette { CustomPalette(json: json) }
    var body: some View {
        List {
            Section("P&L") {
                Button { editing = PaletteEditTarget(id: "gain", title: "Profit", fallback: FinancialColors.gain) } label: {
                    Text("+$128.00  +12.8%").foregroundStyle(palette.color("gain", scheme: scheme, fallback: FinancialColors.gain)).frame(maxWidth: .infinity, alignment: .leading).contentShape(Rectangle())
                }.buttonStyle(.plain)
                Button { editing = PaletteEditTarget(id: "loss", title: "Loss", fallback: FinancialColors.loss) } label: {
                    Text("−$64.00  −6.4%").foregroundStyle(palette.color("loss", scheme: scheme, fallback: FinancialColors.loss)).frame(maxWidth: .infinity, alignment: .leading).contentShape(Rectangle())
                }.buttonStyle(.plain)
            }
            Section("Delta / Spread / IV") {
                metricRow("Low", band: "low", progress: 0, values: ["0.15", "10.0%", "20.0%"])
                metricRow("Medium", band: "medium", progress: 0.5, values: ["0.50", "15.0%", "70.0%"])
                metricRow("High", band: "high", progress: 1, values: ["1.00", "20.0%", "140.0%"])

            }
            Section {
                Button {
                    editing = PaletteEditTarget(id: "accent", title: "System color", fallback: scheme == .dark ? Color(red: 0.93, green: 0.92, blue: 0.89) : Color(red: 0.27, green: 0.28, blue: 0.30))
                } label: {
                    HStack {
                        Text("System color").foregroundStyle(.primary)
                        Spacer()
                        Circle().fill(palette.color("accent", scheme: scheme, fallback: scheme == .dark ? Color(red: 0.93, green: 0.92, blue: 0.89) : Color(red: 0.27, green: 0.28, blue: 0.30)))
                            .frame(width: 24, height: 24)
                            .overlay(Circle().stroke(.secondary.opacity(0.4), lineWidth: 1))
                    }.frame(minHeight: 44).contentShape(Rectangle())
                }.buttonStyle(.plain)
            }
            Section {
                Button("Restore default colors") { json = "{}" }
            }
        }.environment(\.customPalette, palette)
        .environment(\.demoMetricPalette, true)
            .navigationTitle("Custom colors")
            .sheet(item: $editing) { target in
                NavigationStack {
                    Form {
                        PaletteColorEditor(title: target.title, colorKey: target.id, fallback: target.fallback)
                    }.navigationTitle(LocalizedStringKey(target.title))
                        .navigationBarTitleDisplayMode(.inline)
                        .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { editing = nil } } }
                }.presentationDetents([.medium, .large])
            }
    }
    private func metricRow(_ title: String, band: String, progress: Double, values: [String]) -> some View {
        HStack {
            Text(LocalizedStringKey(title))
            Spacer()
            ForEach(Array(["Delta", "Spread", "IV"].enumerated()), id: \.offset) { index, name in
                let key = name.lowercased() + "." + band
                let fallback = CustomPalette.metricFallback(name.lowercased(), band: progress, scheme: scheme)
                Button { editing = PaletteEditTarget(id: key, title: name + " · " + title, fallback: fallback) } label: {
                    Text(values[index]).font(.caption).monospacedDigit()
                        .foregroundStyle(palette.color(key, scheme: scheme, fallback: fallback))
                        .modifier(MetricHighFinish(active: band == "high", color: palette.color(key, scheme: scheme, fallback: fallback)))
                        .frame(minWidth: 44, minHeight: 44).contentShape(Rectangle())
                }.buttonStyle(.plain).accessibilityLabel(name + " " + title)
            }
        }
    }

}
