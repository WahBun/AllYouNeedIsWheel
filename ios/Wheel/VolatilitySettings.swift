import SwiftUI

struct VolatilitySettings: Codable, Equatable {
    var channels: Bool = true
    var rthOnly: Bool = true
    var showInner: Bool = true
    var showOuter: Bool = true
    var inner: Double = 0.5
    var outer: Double = 0.8
    var width: Double = 1
    var labelOffset: Double = 2
    var alerts: Bool = true
    var distance: Bool = true
    var priceScale: Bool = true
    var markHits: Bool = false
    var up1: String = "#c8e6c9"
    var down1: String = "#FF1493"
    var up2: String = "#008000"
    var down2: String = "#ff0000"
    var spx: String = "VIX"
    var ndx: String = "VXN"
    var dow: String = "VXD"
    var r2k: String = "RVX"
    var gold: String = "GVZ"
    var oil: String = "OVX"
    var gauge: Bool = true
    var curve: String = "Auto"
    var position: String = "Bottom Left"
    var background: String = "#ECF1EC"
    var track: String = "#C5CFC5"
    var lowColor: String = "#22c55e"
    var midColor: String = "#eab308"
    var highColor: String = "#ef4444"
    var textColor: String = "#1f2937"
    var backgroundTransparency: Double = 50
    var trackTransparency: Double = 60
    var fillTransparency: Double = 35
    var dictionary: [String: Any] {
        guard let data = try? JSONEncoder().encode(self), let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return [:] }
        return object
    }
    static func family(symbol: String, type: String) -> String? {
        guard ["STK", "FUT", "IND"].contains(type) else { return nil }
        let groups = ["spx": ["SPY","SPX","XSP","SP500","US500","ES","MES"], "ndx": ["QQQ","TQQQ","NQ","MNQ","NDX","US100","UST100"], "dow": ["DIA","YM","MYM","US30"], "r2k": ["IWM","RUT","RTY","M2K","US2000"], "gold": ["GLD","IAU","GC","MGC","GOLD","XAUUSD"], "oil": ["USO","CL","MCL","USOIL"]]
        return groups.first { $0.value.contains(symbol.uppercased()) }?.key
    }
}
struct VolatilitySettingsSections: View {
    @Binding var settings: VolatilitySettings
    private let indices = ["VIX", "VXN", "VXD", "RVX", "GVZ", "OVX"]
    private func color(_ path: WritableKeyPath<VolatilitySettings, String>) -> Binding<Color> {
        Binding(get: { Color(uiColor: UIColor(hexRGB: settings[keyPath: path])) }, set: { value in
            var r: CGFloat = 0, g: CGFloat = 0, b: CGFloat = 0, a: CGFloat = 0
            UIColor(value).getRed(&r, green: &g, blue: &b, alpha: &a)
            settings[keyPath: path] = String(format: "#%02x%02x%02x", Int(r*255), Int(g*255), Int(b*255))
        })
    }
    var body: some View {
        Section("Volatility Channels") {
            Toggle("Enable channels", isOn: $settings.channels)
            Toggle("RTH only (New York)", isOn: $settings.rthOnly)
            Toggle("Show 1st TP", isOn: $settings.showInner)
            Toggle("Show 2nd TP", isOn: $settings.showOuter)
            Toggle("Distance table", isOn: $settings.distance)
            Toggle("Price scale labels", isOn: $settings.priceScale)
            Toggle("Mark first hits", isOn: $settings.markHits)
            Toggle("On-chart hit alerts", isOn: $settings.alerts)
            Stepper("1st multiplier: \(settings.inner, specifier: "%.1f")", value: $settings.inner, in: 0...10, step: 0.1)
            Stepper("2nd multiplier: \(settings.outer, specifier: "%.1f")", value: $settings.outer, in: 0...10, step: 0.1)
            Stepper("Line width: \(settings.width, specifier: "%.1f")", value: $settings.width, in: 1...4, step: 1)
            Stepper("Label offset: \(settings.labelOffset, specifier: "%.1f")", value: $settings.labelOffset, in: 1...50, step: 1)
            ColorPicker("1st Bulls", selection: color(\.up1), supportsOpacity: false)
            ColorPicker("1st Bears", selection: color(\.down1), supportsOpacity: false)
            ColorPicker("2nd Bulls", selection: color(\.up2), supportsOpacity: false)
            ColorPicker("2nd Bears", selection: color(\.down2), supportsOpacity: false)
        }
        Section("Volatility Symbols") {
            Picker("ES / SPY", selection: $settings.spx) { ForEach(indices, id: \.self) { Text($0).tag($0) } }
            Picker("NQ / QQQ / TQQQ", selection: $settings.ndx) { ForEach(indices, id: \.self) { Text($0).tag($0) } }
            Picker("YM / DIA", selection: $settings.dow) { ForEach(indices, id: \.self) { Text($0).tag($0) } }
            Picker("RTY / IWM", selection: $settings.r2k) { ForEach(indices, id: \.self) { Text($0).tag($0) } }
            Picker("GC / GLD", selection: $settings.gold) { ForEach(indices, id: \.self) { Text($0).tag($0) } }
            Picker("CL / USO", selection: $settings.oil) { ForEach(indices, id: \.self) { Text($0).tag($0) } }
        }
        Section("Intraday Extreme Gauge") {
            Toggle("Enable gauge", isOn: $settings.gauge)
            Picker("Curve", selection: $settings.curve) { ForEach(["Auto", "ES", "NQ"], id: \.self) { Text($0).tag($0) } }
            Picker("Position", selection: $settings.position) { ForEach(["Top Left", "Top Right", "Bottom Left", "Bottom Right"], id: \.self) { Text($0).tag($0) } }
        }
        Section("Gauge Colors") {
            ColorPicker("Background", selection: color(\.background), supportsOpacity: false)
            ColorPicker("Track", selection: color(\.track), supportsOpacity: false)
            ColorPicker("Low", selection: color(\.lowColor), supportsOpacity: false)
            ColorPicker("Medium", selection: color(\.midColor), supportsOpacity: false)
            ColorPicker("High", selection: color(\.highColor), supportsOpacity: false)
            ColorPicker("Text", selection: color(\.textColor), supportsOpacity: false)
            Stepper("backgroundTransparency: \(Int(settings.backgroundTransparency))%", value: $settings.backgroundTransparency, in: 0...100, step: 5)
            Stepper("trackTransparency: \(Int(settings.trackTransparency))%", value: $settings.trackTransparency, in: 0...100, step: 5)
            Stepper("fillTransparency: \(Int(settings.fillTransparency))%", value: $settings.fillTransparency, in: 0...100, step: 5)
        }
    }
}
private extension UIColor {
    convenience init(hexRGB: String) {
        let n = UInt32(hexRGB.trimmingCharacters(in: CharacterSet(charactersIn: "#")), radix: 16) ?? 0
        self.init(red: CGFloat((n >> 16) & 255)/255, green: CGFloat((n >> 8) & 255)/255, blue: CGFloat(n & 255)/255, alpha: 1)
    }
}
