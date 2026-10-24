import SwiftUI
import Observation

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
    var distance: Bool = false
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
    var position: String = "Bottom Center"
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
    var tab: String = "Inputs"
    var sharedRulesEditable: Bool = true
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
            if tab == "Inputs" {
                Toggle("RTH only (New York)", isOn: $settings.rthOnly)
                Stepper("1st multiplier: \(settings.inner, specifier: "%.1f")", value: $settings.inner, in: 0...10, step: 0.1).disabled(!sharedRulesEditable)
                Stepper("2nd multiplier: \(settings.outer, specifier: "%.1f")", value: $settings.outer, in: 0...10, step: 0.1).disabled(!sharedRulesEditable)
            } else {
                Toggle("Enable channels", isOn: $settings.channels)
                Toggle("Show 1st TP", isOn: $settings.showInner)
                Toggle("Show 2nd TP", isOn: $settings.showOuter)
                Toggle("Distance table", isOn: $settings.distance)
                Toggle("Price scale labels", isOn: $settings.priceScale)
                Toggle("Mark first hits", isOn: $settings.markHits)
                Toggle("On-chart hit alerts", isOn: $settings.alerts)
                Stepper("Line width: \(settings.width, specifier: "%.1f")", value: $settings.width, in: 1...4, step: 1)
                Stepper("Label offset: \(settings.labelOffset, specifier: "%.1f")", value: $settings.labelOffset, in: 1...50, step: 1)
                ColorPicker("1st Bulls", selection: color(\.up1), supportsOpacity: false)
                ColorPicker("1st Bears", selection: color(\.down1), supportsOpacity: false)
                ColorPicker("2nd Bulls", selection: color(\.up2), supportsOpacity: false)
                ColorPicker("2nd Bears", selection: color(\.down2), supportsOpacity: false)
            }
        }
        if tab == "Inputs" {
        Section("Volatility Symbols") {
            Picker("ES / SPY", selection: $settings.spx) { ForEach(indices, id: \.self) { Text($0).tag($0) } }.disabled(!sharedRulesEditable)
            Picker("NQ / QQQ / TQQQ", selection: $settings.ndx) { ForEach(indices, id: \.self) { Text($0).tag($0) } }.disabled(!sharedRulesEditable)
            Picker("YM / DIA", selection: $settings.dow) { ForEach(indices, id: \.self) { Text($0).tag($0) } }
            Picker("RTY / IWM", selection: $settings.r2k) { ForEach(indices, id: \.self) { Text($0).tag($0) } }
            Picker("GC / GLD", selection: $settings.gold) { ForEach(indices, id: \.self) { Text($0).tag($0) } }
            Picker("CL / USO", selection: $settings.oil) { ForEach(indices, id: \.self) { Text($0).tag($0) } }
        }
        }
        Section("Intraday Extreme Gauge") {
            if tab == "Inputs" {
                Picker("Curve", selection: $settings.curve) { ForEach(["Auto", "ES", "NQ"], id: \.self) { Text($0).tag($0) } }
            } else {
                Toggle("Enable gauge", isOn: $settings.gauge)
                Picker("Position", selection: $settings.position) { ForEach(["Top Left", "Top Right", "Bottom Left", "Bottom Center", "Bottom Right"], id: \.self) { Text($0).tag($0) } }
            }
        }
        if tab == "Style" {
        Section("Gauge Colors") {
            ColorPicker("Background", selection: color(\.background), supportsOpacity: false)
            ColorPicker("Track", selection: color(\.track), supportsOpacity: false)
            ColorPicker("Low", selection: color(\.lowColor), supportsOpacity: false)
            ColorPicker("Medium", selection: color(\.midColor), supportsOpacity: false)
            ColorPicker("High", selection: color(\.highColor), supportsOpacity: false)
            ColorPicker("Text", selection: color(\.textColor), supportsOpacity: false)
            Stepper("Background transparency: \(Int(settings.backgroundTransparency))%", value: $settings.backgroundTransparency, in: 0...100, step: 5)
            Stepper("Track transparency: \(Int(settings.trackTransparency))%", value: $settings.trackTransparency, in: 0...100, step: 5)
            Stepper("Fill transparency: \(Int(settings.fillTransparency))%", value: $settings.fillTransparency, in: 0...100, step: 5)
        }
        }
    }
}
private extension UIColor {
    convenience init(hexRGB: String) {
        let n = UInt32(hexRGB.trimmingCharacters(in: CharacterSet(charactersIn: "#")), radix: 16) ?? 0
        self.init(red: CGFloat((n >> 16) & 255)/255, green: CGFloat((n >> 8) & 255)/255, blue: CGFloat(n & 255)/255, alpha: 1)
    }
}

struct MoonshineRules: Codable, Equatable {
    var version: Int
    var inner: Double
    var outer: Double
    var spx: String
    var ndx: String

    func applying(to local: VolatilitySettings) -> VolatilitySettings {
        var value = local
        value.inner = inner; value.outer = outer; value.spx = spx; value.ndx = ndx
        return value
    }
}

@MainActor @Observable
final class MoonshineRulesModel {
    private(set) var account: NotificationAccount?
    private(set) var rules: MoonshineRules?
    private(set) var busy = false
    private(set) var message = "Connect to sync MoonShine rules."
    @ObservationIgnored private var revision = UUID()
    @ObservationIgnored private let session: URLSession

    init(session: URLSession = URLSession(configuration: .ephemeral, delegate: NoRedirect(), delegateQueue: nil)) {
        self.session = session
    }
    func select(_ account: NotificationAccount?) {
        guard self.account != account else { return }
        revision = UUID(); self.account = account; rules = nil; busy = false
        message = account == nil ? "Connect to sync MoonShine rules." : "Loading shared MoonShine rules…"
    }
    private func request(_ account: NotificationAccount, body: [String: Any]? = nil) async throws -> MoonshineRules {
        guard let base = URL(string: account.address), base.scheme == "https", base.host != nil else {
            throw AppError.message("Connect to your private HTTPS backend first.")
        }
        var request = URLRequest(url: base.appendingPathComponent("api/notifications/moonshine-rules"), cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 12)
        request.httpMethod = body == nil ? "GET" : "POST"
        request.setValue("1", forHTTPHeaderField: "X-All-You-Need-Is-Wheel")
        request.setValue(account.epoch, forHTTPHeaderField: "X-Wheel-Account-Epoch")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let body { request.httpBody = try JSONSerialization.data(withJSONObject: body) }
        let (data, response) = try await session.data(for: request)
        guard (response as? HTTPURLResponse)?.statusCode == 200 else {
            let reply = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
            throw AppError.message(reply?["error"] as? String ?? "MoonShine rules are unavailable. Refresh before saving.")
        }
        struct Reply: Decodable { let rules: MoonshineRules; let epoch: String }
        let reply = try JSONDecoder().decode(Reply.self, from: data)
        guard reply.epoch == account.epoch else { throw AppError.message("Account changed. Refresh MoonShine settings.") }
        return reply.rules
    }
    func refresh() async {
        guard !busy, let account else { return }
        let token = revision; busy = true
        defer { if token == revision { busy = false } }
        do {
            let value = try await request(account)
            guard token == revision else { return }
            rules = value; message = "Shared across charts and QQQ / ES alerts for this account."
        } catch {
            guard token == revision else { return }
            message = (error as? AppError)?.localizedDescription ?? "MoonShine sync failed. Refresh before saving."
        }
    }
    func save(_ value: VolatilitySettings, account expectedAccount: NotificationAccount?, version expectedVersion: Int?) async {
        guard !busy, let account, let rules, account == expectedAccount, rules.version == expectedVersion else { return }
        let old = rules.applying(to: value)
        var patch: [String: Any] = ["version": rules.version]
        if value.inner != old.inner { patch["inner"] = value.inner }
        if value.outer != old.outer { patch["outer"] = value.outer }
        if value.spx != old.spx { patch["spx"] = value.spx }
        if value.ndx != old.ndx { patch["ndx"] = value.ndx }
        guard patch.count > 1 else { return }
        let token = revision; busy = true; message = "Saving shared MoonShine rules…"
        defer { if token == revision { busy = false } }
        do {
            let updated = try await request(account, body: patch)
            guard token == revision else { return }
            self.rules = updated; message = "MoonShine rules saved for this account."
        } catch {
            guard token == revision else { return }
            message = (error as? AppError)?.localizedDescription ?? "Save could not be confirmed. Refresh before trying again."
            // Reconcile an uncertain response without replaying the write.
            if let updated = try? await request(account), token == revision { self.rules = updated }
        }
    }
}
