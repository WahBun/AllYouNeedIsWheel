import SwiftUI

struct IndicatorTimeframeVisibility: Codable, Equatable {
    struct Band: Codable, Equatable {
        var enabled = true
        var min = 1
        var max: Int
        init(enabled: Bool = true, min: Int = 1, max: Int) {
            self.enabled = enabled; self.min = min; self.max = max
        }
        private enum CodingKeys: String, CodingKey { case enabled, min, max }
        init(from decoder: Decoder) throws {
            let container = try decoder.container(keyedBy: CodingKeys.self)
            enabled = (try? container.decode(Bool.self, forKey: .enabled)) ?? true
            min = (try? container.decode(Int.self, forKey: .min)) ?? 1
            max = (try? container.decode(Int.self, forKey: .max)) ?? Int.max
        }
    }
    enum Unit: String, CaseIterable, Identifiable {
        case minutes, hours, days, weeks, months
        var id: String { rawValue }
        var title: String { rawValue.capitalized }
        var limit: Int {
            switch self { case .minutes: 59; case .hours: 24; case .days: 366; case .weeks: 52; case .months: 12 }
        }
        var key: WritableKeyPath<IndicatorTimeframeVisibility, Band> {
            switch self { case .minutes: \.minutes; case .hours: \.hours; case .days: \.days; case .weeks: \.weeks; case .months: \.months }
        }
    }
    var minutes = Band(max: 59)
    var hours = Band(max: 24)
    var days = Band(max: 366)
    var weeks = Band(max: 52)
    var months = Band(max: 12)
    init() {}
    init(json: String) { self = (try? JSONDecoder().decode(Self.self, from: Data(json.utf8))) ?? Self() }
    private enum CodingKeys: String, CodingKey { case minutes, hours, days, weeks, months }
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        for unit in Unit.allCases {
            let key = CodingKeys(rawValue: unit.rawValue)!
            if let band = try? container.decode(Band.self, forKey: key) { set(band, for: unit) }
        }
    }
    mutating func set(_ band: Band, for unit: Unit) {
        let low = Swift.min(unit.limit, Swift.max(1, band.min))
        let high = Swift.min(unit.limit, Swift.max(1, band.max))
        self[keyPath: unit.key] = Band(enabled: band.enabled, min: Swift.min(low, high), max: Swift.max(low, high))
    }
    var json: String { String(decoding: (try? JSONEncoder().encode(self)) ?? Data(), as: UTF8.self) }
    func allows(_ interval: Int) -> Bool {
        let unit: Unit, count: Int
        switch interval {
        case 1..<60: unit = .minutes; count = interval
        case 60..<1440: unit = .hours; count = interval / 60
        case 1440..<10080: unit = .days; count = interval / 1440
        case 10080..<43200: unit = .weeks; count = interval / 10080
        case 43200...: unit = .months; count = interval / 43200
        default: return true
        }
        let band = self[keyPath: unit.key]
        return band.enabled && (band.min...band.max).contains(count)
    }
}

struct IndicatorTimeframeVisibilitySection: View {
    @Binding var settings: IndicatorTimeframeVisibility
    private func band(_ unit: IndicatorTimeframeVisibility.Unit) -> Binding<IndicatorTimeframeVisibility.Band> {
        Binding(get: { settings[keyPath: unit.key] }, set: { settings.set($0, for: unit) })
    }
    var body: some View {
        Section {
            ForEach(IndicatorTimeframeVisibility.Unit.allCases) { unit in
                let value = settings[keyPath: unit.key]
                VStack(spacing: 12) {
                    Toggle(unit.title, isOn: band(unit).enabled)
                    HStack(spacing: 12) {
                        Text("From").foregroundStyle(.secondary)
                        IndicatorTimeframeBound(value: band(unit).min, bounds: 1...value.max, label: "\(unit.title) from")
                        Text("to").foregroundStyle(.secondary)
                        IndicatorTimeframeBound(value: band(unit).max, bounds: value.min...unit.limit, label: "\(unit.title) to")
                    }.disabled(!value.enabled)
                }.padding(.vertical, 6)
            }
        } header: { Text("Show on timeframes") } footer: {
            Text("Applies to all indicators in this chart. Hidden indicators return when you switch to an allowed timeframe. Changes apply immediately and are saved.")
        }
    }
}

private struct IndicatorTimeframeBound: View {
    @Binding var value: Int
    let bounds: ClosedRange<Int>
    let label: String
    @State private var draft = ""
    @FocusState private var focused: Bool
    private func finish() {
        value = Int(draft).map { min(bounds.upperBound, max(bounds.lowerBound, $0)) } ?? value
        draft = String(value)
    }
    var body: some View {
        TextField("", text: $draft)
            .keyboardType(.numberPad).textFieldStyle(.roundedBorder)
            .multilineTextAlignment(.center).focused($focused)
            .accessibilityLabel(label)
            .onAppear { draft = String(value) }
            .onChange(of: draft) { _, text in
                let digits = String(text.filter { $0.isASCII && $0.isNumber }.prefix(3))
                if digits != text { draft = digits }
                if let number = Int(digits), bounds.contains(number) { value = number }
            }
            .onChange(of: value) { _, number in if !focused { draft = String(number) } }
            .onChange(of: focused) { _, editing in if !editing { finish() } }
            .onDisappear { finish() }
            .toolbar {
                ToolbarItemGroup(placement: .keyboard) {
                    if focused { Spacer(); Button("Done") { finish(); focused = false } }
                }
            }
    }
}
