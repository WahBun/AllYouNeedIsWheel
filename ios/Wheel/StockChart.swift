import SwiftUI
import WebKit

@MainActor enum RecentStockCharts {
    static var packets: [String: (Date, [String: Any])] = [:]
    static var lastSaved: [String: Date] = [:]
    static let diskKey = "recentStockChartHistoryV1"
    static func load(_ key: String) -> (Date, [String: Any])? {
        if let cached = packets[key], Date().timeIntervalSince(cached.0) < 86400 { return cached }
        guard let data = UserDefaults.standard.data(forKey: diskKey),
              let all = try? JSONSerialization.jsonObject(with: data) as? [String: [String: Any]],
              let record = all[key], let stamp = record["saved"] as? Double,
              Date().timeIntervalSince1970 - stamp < 86400,
              let packet = record["packet"] as? [String: Any] else { return nil }
        let cached = (Date(timeIntervalSince1970: stamp), packet)
        packets[key] = cached
        return cached
    }
    static func save(_ packet: [String: Any], key: String) {
        guard let bars = packet["bars"] as? [[String: Any]], !bars.isEmpty else { return }
        packets = packets.filter { Date().timeIntervalSince($0.value.0) < 86400 }
        if packets.count >= 12 && packets[key] == nil, let oldest = packets.min(by: { $0.value.0 < $1.value.0 }) { packets.removeValue(forKey: oldest.key) }
        // Keep the known bar deadline and clock anchor, never quote eligibility or stream state.
        var history = packet
        for field in ["bid", "ask", "quote_time", "quote_expires_at", "sequence", "mode", "changed_bars", "stream_id"] { history.removeValue(forKey: field) }
        history["chart_received_at"] = packet["chart_received_at"] ?? Date().timeIntervalSince1970
        history["status"] = "waiting"
        history["bars"] = Array(bars.suffix(2500))
        packets[key] = (.now, history)
        guard lastSaved[key].map({ Date().timeIntervalSince($0) >= 15 }) ?? true else { return }
        lastSaved[key] = .now
        let records = packets.mapValues { ["saved": $0.0.timeIntervalSince1970, "packet": $0.1] as [String: Any] }
        if let data = try? JSONSerialization.data(withJSONObject: records) { UserDefaults.standard.set(data, forKey: diskKey) }
    }
}

struct StockChartView: View {
    let position: Position
    var resumeLast = false
    @State private var initialized = false
    private var recentChartKey: String { "lastViewedChartV1-\(store.demo)-\(store.address)" }
    private func rememberChart() {
        guard initialized, let id = chartID, id > 0 else { return }
        var contract = selectedContract
        contract["con_id"] = id
        contract["local_symbol"] = chartSymbol
        contract["security_type"] = chartType
        let record: [String: Any] = ["contract": contract, "interval": interval, "session": session]
        if let data = try? JSONSerialization.data(withJSONObject: record) {
            UserDefaults.standard.set(data, forKey: recentChartKey)
        }
    }
    @State private var paperState: [String: Any] = [:]
    @State private var completedPaperOrders: Set<String> = []
    @State private var showQuantityEditor = false
    @State private var quantityDraft = "1"
    private var quantityLimit: Int { chartType == "FUT" ? 10 : 1000 }
    private var validQuantityDraft: Int? {
        guard let value = Int(quantityDraft), (1...quantityLimit).contains(value) else { return nil }
        return value
    }
    @State private var paperBusy = false
    @State private var paperMessage: String?
    private var paperEnabled: Bool { chartType != "OPT" && paperState["enabled"] as? Bool == true }
    private var paperActive: Bool { paperState["active"] as? Bool == true }
    private func applyPaperState(_ state: [String: Any]) {
        paperState = state
        if state["active"] as? Bool == true, let price = state["entry"] as? Double, price > 0 { entry = String(price) }
        let rows = state["orders"] as? [[String: Any]] ?? []
        if state["status"] as? String == "done",
           let id = rows.first(where: { $0["role"] as? String == "entry" })?["order_id"] as? Int,
           completedPaperOrders.insert("\(store.address)-\(chartID ?? 0)-\(id)").inserted { entry = "0"; beApplied = false }
    }
    private func paperAction(_ body: [String: Any]) {
        if body["action"] as? String == "indicatorSettings" { showIndicatorSettings = true; return }
        if body["action"] as? String == "indicatorToggle" { indicatorVisible.toggle(); return }
        if body["action"] as? String == "indicatorCollapse", let collapsed = body["collapsed"] as? Bool { indicatorCollapsed = collapsed; return }
        if body["action"] as? String == "editQuantity" {
            guard !paperActive, !paperBusy, body["con_id"] as? Int == chartID else { return }
            quantityDraft = quantity; showQuantityEditor = true; return
        }
        guard !paperBusy, paperEnabled, let cid = chartID else { return }
        if let source = body["con_id"] as? Int, source != cid { return }
        if body["action"] as? String == "submit" {
            if let type = body["entry_type"] as? String, ["LMT", "STP"].contains(type) { entryType = type }
            if let price = body["entry"] as? Double { entry = String(price) }
        }
        paperBusy = true
        Task {
            defer { paperBusy = false }
            do {
                let result = try await store.trading.paperChartWrite(base: store.address, conID: cid, body: body)
                guard chartID == cid else { return }
                paperMessage = result["message"] as? String
                if let state = result["state"] as? [String: Any] { applyPaperState(state) }
            } catch { paperMessage = connectionMessage(error) + " · Check Gateway before retrying" }
        }
    }
    @State private var selectedContract: [String: Any] = [:]
    @State private var showSymbols = false
    @State private var symbolQuery = "TSLA"
    @State private var symbolResults: [[String: Any]] = []
    @State private var symbolError: String?
    @State private var searching = false
    private var chartID: Int? { selectedContract["con_id"] as? Int ?? position.con_id }
    private var chartSymbol: String { selectedContract["local_symbol"] as? String ?? position.chartLabel }
    private var chartType: String { selectedContract["security_type"] as? String ?? position.security_type }
    private func searchSymbols() async {
        guard !searching else { return }; searching = true; symbolError = nil
        defer { searching = false }
        do {
            let result = try await store.trading.get("api/portfolio/chart-contracts", base: store.address, query: [URLQueryItem(name: "q", value: symbolQuery)])
            symbolResults = result["contracts"] as? [[String: Any]] ?? []
            if symbolResults.isEmpty { symbolError = "No matching contract" }
        } catch { symbolError = connectionMessage(error) }
    }
    @Environment(WheelStore.self) private var store
    @Environment(\.scenePhase) private var phase
    @Environment(\.colorScheme) private var colors
    @State private var interval = 5
    @State private var fullScreen = false
    @AppStorage("chartFavoriteIntervals") private var favoriteIntervals = "1,3,5,10,15,60,480,1440,10080,43200"
    @State private var showIntervals = false
    private let intervals = [1, 3, 5, 10, 15, 60, 480, 1440, 10080, 43200]
    private var favorites: Set<Int> { Set(favoriteIntervals.split(separator: ",").compactMap { Int($0) }) }
    private func intervalLabel(_ value: Int) -> String {
        switch value { case 1440: return "D"; case 10080: return "W"; case 43200: return "M"; default: return value < 60 ? "\(value)m" : "\(value / 60)h" }
    }
    @AppStorage("stockChartSession") private var session = "rth"
    @State private var quantity = "1"
    @State private var entry = ""
    @State private var entryType = "LMT"
    @State private var joinSide = 0
    @State private var joinRevision = 0
    @State private var showInfo = false
    @State private var showClosePreview = false
    @State private var beRevision = 0
    @State private var beApplied = false
    // Existing distances remain the stock profile; other asset classes are independent.
    @AppStorage("chartTPDistance") private var stockTPDistance = "0.20"
    @AppStorage("chartSLDistance") private var stockSLDistance = "0.10"
    @AppStorage("optionChartTPDistance") private var optionTPDistance = "0.20"
    @AppStorage("optionChartSLDistance") private var optionSLDistance = "0.10"
    @AppStorage("futureChartTPDistance") private var futureTPDistance = "2.00"
    @AppStorage("futureChartSLDistance") private var futureSLDistance = "1.00"
    @AppStorage("chartShowProfit") private var showProfit = true
    @AppStorage("chartShowPositionProfit") private var showPositionProfit = false
    @AppStorage("chartShowBracketProfit") private var showBracketProfit = true
    @AppStorage("chartShowExecutions") private var showExecutions = true
    @AppStorage("chartShowExecutionLabels") private var showExecutionLabels = true
    @AppStorage("chartPositionProfitUnit") private var positionProfitUnit = "money"
    @AppStorage("chartBracketProfitUnit") private var bracketProfitUnit = "money"
    @AppStorage("chartShowATR") private var showATR = true
    @AppStorage("chartATRLength") private var atrLength = 4
    @AppStorage("chartIndicatorCollapsed") private var indicatorCollapsed = false
    @AppStorage("chartIndicatorVisible") private var indicatorVisible = true
    @AppStorage("chartShowEMA") private var showEMA = true
    @AppStorage("chartEMALength") private var emaLength = 20
    @AppStorage("chartEMASource") private var emaSource = "close"
    @AppStorage("chartEMAOffset") private var emaOffset = 0
    @AppStorage("chartEMADynamic") private var emaDynamic = true
    @AppStorage("chartEMAColor") private var emaColor = "#f9f1db"
    @AppStorage("chartEMAWidth") private var emaWidth = 1
    @AppStorage("chartEMAStyle") private var emaStyle = 0
    @State private var showIndicatorSettings = false
    @State private var indicatorTab = "Inputs"
    private var emaColorBinding: Binding<Color> {
        Binding(get: {
            let rgb = Int(emaColor.dropFirst(), radix: 16) ?? 0xf9f1db
            return Color(red: Double((rgb >> 16) & 255) / 255, green: Double((rgb >> 8) & 255) / 255, blue: Double(rgb & 255) / 255)
        }, set: { color in
            var r: CGFloat = 0, g: CGFloat = 0, b: CGFloat = 0, a: CGFloat = 0
            UIColor(color).getRed(&r, green: &g, blue: &b, alpha: &a)
            emaColor = String(format: "#%02X%02X%02X", Int(r * 255), Int(g * 255), Int(b * 255))
        })
    }
    private var indicatorSettings: some View {
        NavigationStack {
            Form {
                Picker("Settings", selection: $indicatorTab) {
                    Text("Inputs").tag("Inputs"); Text("Style").tag("Style"); Text("Visibility").tag("Visibility")
                }.pickerStyle(.segmented)
                if indicatorTab == "Inputs" {
                    Section("EMA") {
                        Stepper("Length: \(emaLength)", value: $emaLength, in: 1...500)
                        Picker("Source", selection: $emaSource) {
                            ForEach(["close", "open", "high", "low", "hl2", "hlc3", "ohlc4"], id: \.self) { Text($0.uppercased()).tag($0) }
                        }
                        Stepper("Offset: \(emaOffset)", value: $emaOffset, in: -100...100)
                        Text("Timeframe follows the chart").font(.caption).foregroundStyle(.secondary)
                    }
                    Section("ATR") { Stepper("Length: \(atrLength)", value: $atrLength, in: 1...200) }
                } else if indicatorTab == "Style" {
                    Section("EMA") {
                        Toggle("Dynamic colors", isOn: $emaDynamic)
                        ColorPicker("Line color", selection: emaColorBinding, supportsOpacity: false).disabled(emaDynamic)
                        Stepper("Line width: \(emaWidth)", value: $emaWidth, in: 1...4)
                        Picker("Line style", selection: $emaStyle) {
                            Text("Solid").tag(0); Text("Dotted").tag(1); Text("Dashed").tag(2)
                        }
                    }
                } else {
                    Section("Indicators") {
                        Toggle("EMA", isOn: $showEMA)
                        Toggle("ATR", isOn: $showATR)
                    }
                }
                Section {
                    Text("Changes apply immediately and are saved.").font(.caption).foregroundStyle(.secondary)
                    Button("Restore defaults") {
                        indicatorVisible = true; showEMA = true; emaLength = 20; emaSource = "close"; emaOffset = 0
                        emaDynamic = true; emaColor = "#f9f1db"; emaWidth = 1; emaStyle = 0
                        showATR = true; atrLength = 4
                    }
                }
            }.navigationTitle("𝔹𝕖𝕟").navigationBarTitleDisplayMode(.inline)
                .toolbar { Button("Done") { showIndicatorSettings = false } }
        }
    }
    @State private var adjustmentAction = ""
    @State private var adjustmentQuantity = 1
    @State private var showAdjustment = false
    private var positionSize: Int { Int(abs(paperState["position"] as? Double ?? 0)) }
    private var adjustmentLimit: Int { adjustmentAction == "trim" ? max(0, positionSize - 1) : max(0, quantityLimit - positionSize) }
    @State private var showDisplaySettings = false
    private var chartDisplay: [String: Any] {
        ["indicatorCollapsed": indicatorCollapsed, "indicatorVisible": indicatorVisible, "ema": showEMA && indicatorVisible, "emaLength": emaLength, "emaSource": emaSource, "emaOffset": emaOffset,
         "emaDynamic": emaDynamic, "emaColor": emaColor + "ab", "emaWidth": emaWidth, "emaStyle": emaStyle,
         "atr": showATR && indicatorVisible, "atrLength": atrLength, "profit": showProfit, "positions": showPositionProfit, "brackets": showBracketProfit,
         "executions": showExecutions, "executionLabels": showExecutionLabels,
         "positionUnit": positionProfitUnit, "bracketUnit": bracketProfitUnit]
    }
    private var paperStatusText: String {
        let rows = paperState["orders"] as? [[String: Any]] ?? []
        if paperState["sync_error"] as? Bool == true { return "Order updates paused · verify Gateway" }
        if paperState["known"] as? Bool == false { return "Order status unknown · verify Gateway" }
        if paperState["rejected"] as? Bool == true { return "Order rejected · verify Gateway" }
        if let size = paperState["position"] as? Double, size != 0 { return "IB Paper · \(size > 0 ? "Long" : "Short") \(abs(size).formatted()) filled" }
        if paperState["status"] as? String == "done" {
            let exit = rows.first { ["tp", "sl", "close"].contains($0["role"] as? String ?? "") && ($0["filled"] as? Double ?? 0) > 0 }
            return exit.map { "IB Paper · \(($0["role"] as? String ?? "").uppercased()) filled · Flat" } ?? "IB Paper · Orders finished · Flat"
        }
        if let row = rows.first(where: { $0["role"] as? String == "entry" }) { return "IB Paper · \(row["status"] as? String ?? "Unknown") · Filled \((row["filled"] as? Double ?? 0).formatted())" }
        return ""
    }
    @State private var templateType = "STK"
    @State private var showTemplate = false
    @State private var templateRevision = 1
    private func distanceBinding(_ type: String, tp: Bool) -> Binding<String> {
        switch type {
        case "FUT": return tp ? $futureTPDistance : $futureSLDistance
        case "OPT": return tp ? $optionTPDistance : $optionSLDistance
        default: return tp ? $stockTPDistance : $stockSLDistance
        }
    }
    private var tpDistance: String { distanceBinding(chartType, tp: true).wrappedValue }
    private var slDistance: String { distanceBinding(chartType, tp: false).wrappedValue }
    private var validTemplate: Bool {
        [true, false].allSatisfy { tp in
            Double(distanceBinding(templateType, tp: tp).wrappedValue).map { $0.isFinite && $0 > 0 } ?? false
        }
    }
    @State private var packet: [String: Any] = [:]
    @State private var notice = "Loading chart…"
    @State private var visible = false
    @State private var received: Date?
    @State private var loadedChartKey = ""
    private var cacheKey: String { "\(store.address)-\(chartID ?? 0)-\(interval)-\(session)" }
    private var context: String { "\(store.demo)-\(store.address)-\(chartID ?? 0)-\(interval)-\(session)-\(phase == .active)-\(visible)" }
    private var validEntry: Double { Double(entry).flatMap { $0.isFinite && $0 > 0 ? $0 : nil } ?? 0 }
    private var validQuantity: Double { Double(quantity).flatMap { $0.isFinite && $0 > 0 && $0 <= 1_000_000 ? $0 : nil } ?? 0 }
    private func joinPrice(_ side: String) -> Double? {
        guard visible, phase == .active, let received, Date().timeIntervalSince(received) < 3,
              let expires = packet["quote_expires_at"] as? Double,
              let serverTime = packet["server_time"] as? Double,
              serverTime + Date().timeIntervalSince(received) < expires,
              let price = packet[side] as? Double, price.isFinite, price > 0 else { return nil }
        return price
    }
    private func join(_ side: String) {
        guard let price = joinPrice(side) else { return }
        entryType = "LMT"; entry = String(price)
        joinSide = side == "bid" ? 1 : -1; joinRevision += 1
    }
    private func distanceRow(_ title: String, value: Binding<String>) -> some View {
        HStack {
            Text(title)
            Spacer()
            TextField(title, text: value).keyboardType(.decimalPad)
                .multilineTextAlignment(.trailing).frame(width: 80)
            Menu {
                ForEach(["0.01", "0.05", "0.10", "0.15", "0.20", "0.25", "0.50", "1.00", "2.00", "5.00", "10.00"], id: \.self) { distance in
                    Button {
                        UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder), to: nil, from: nil, for: nil)
                        value.wrappedValue = distance
                    } label: {
                        if Double(value.wrappedValue) == Double(distance) {
                            Label(distance, systemImage: "checkmark")
                        } else { Text(distance) }
                    }
                }
            } label: { Image(systemName: "chevron.up.chevron.down").frame(width: 36, height: 44) }
                .accessibilityLabel(title + " price distance")
        }
    }
    var body: some View {
        VStack(spacing: 8) {
            HStack {
                Button { showSymbols = true } label: { Image(systemName: "magnifyingglass").frame(width: 30, height: 40) }.buttonStyle(.plain).accessibilityLabel("Search chart symbol")
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 2) {
                        ForEach(intervals.filter { favorites.contains($0) }, id: \.self) { value in
                            Button { interval = value } label: {
                                Text(intervalLabel(value))
                                    .font(.system(size: 13, weight: interval == value ? .semibold : .regular))
                                    .fixedSize().padding(.horizontal, 9).frame(height: 40)
                                    .background(interval == value ? Color.secondary.opacity(0.25) : .clear, in: RoundedRectangle(cornerRadius: 6))
                            }.buttonStyle(.plain)
                                .accessibilityAddTraits(interval == value ? .isSelected : [])
                        }
                    }
                }
                Button { showIntervals = true } label: {
                    HStack(spacing: 3) { Text(intervalLabel(interval)); Image(systemName: "chevron.down") }.font(.caption)
                }.buttonStyle(.plain).frame(minHeight: 40)
                Picker("Session", selection: $session) {
                    Text("RTH").tag("rth"); Text("ETH").tag("all")
                }.fixedSize()
                Button { fullScreen.toggle() } label: {
                    Image(systemName: fullScreen ? "arrow.down.right.and.arrow.up.left" : "arrow.up.left.and.arrow.down.right")
                        .frame(width: 36, height: 44)
                }.buttonStyle(.plain).accessibilityLabel(fullScreen ? "Exit full screen" : "Full screen")
            }
            if !fullScreen {
            TimelineView(.periodic(from: .now, by: 1)) { time in
                Text(received.map { time.date.timeIntervalSince($0) > 3 } == true ? "Chart updates paused · verify connection" : LocalizedStringKey(notice))
                    .font(.caption).foregroundStyle(.secondary).frame(maxWidth: .infinity, alignment: .leading)
            }
            }
            StockChartWeb(display: chartDisplay, drawingKey: "\(store.address)-\(chartID ?? 0)", packet: packet, entry: chartType == "OPT" ? 0 : validEntry, quantity: validQuantity, dark: colors == .dark, entryType: entryType, joinSide: joinSide, joinRevision: joinRevision, beRevision: beRevision, tpDistance: Double(tpDistance) ?? 0, slDistance: Double(slDistance) ?? 0, templateRevision: templateRevision, onBE: { beApplied = $0 }, onEntry: { entry = String($0) }, paperState: paperState.merging(["busy": paperBusy, "chart_only": chartType == "OPT"]) { _, new in new }, conID: chartID ?? 0, onPaper: paperAction)
                .clipShape(RoundedRectangle(cornerRadius: 12))
            HStack(spacing: 8) {
                Color.clear.frame(width: 36, height: 32).accessibilityHidden(true)
                Text(chartType == "OPT" ? "Option chart · View only" : paperStatusText.isEmpty ? (paperEnabled ? "IB Paper trading" : "Preview only") : paperStatusText)
                    .font(.caption).foregroundStyle(paperEnabled ? .orange : .secondary)
                    .multilineTextAlignment(.center).lineLimit(2).frame(maxWidth: .infinity)
                Button { showDisplaySettings = true } label: {
                    Image(systemName: "gearshape").frame(width: 36, height: 32)
                }.buttonStyle(.plain).accessibilityLabel("Chart display")
            }
            if !fullScreen && chartType != "OPT" {
            if let paperMessage { Text(paperMessage).font(.caption).foregroundStyle(.secondary) }
            HStack(spacing: 8) {
                TextField("Shares", text: $quantity).keyboardType(.decimalPad)
                    .multilineTextAlignment(.center).textFieldStyle(.roundedBorder).frame(width: 48)
                Stepper("Shares", value: Binding(get: { max(1, Int(validQuantity)) }, set: { quantity = String($0) }), in: 1...1_000_000).labelsHidden()
                Spacer(minLength: 0)
                if validEntry == 0 {
                    Button { entry = String(((packet["bars"] as? [[String: Any]])?.last?["close"] as? Double) ?? position.market_price ?? 0) } label: { Image(systemName: "plus.circle").frame(minWidth: 32, minHeight: 44) }.accessibilityLabel("Entry reference")
                }
                Picker("Entry type", selection: $entryType) {
                    Text("LMT").tag("LMT"); Text("STP").tag("STP")
                }.pickerStyle(.segmented).frame(maxWidth: 140)
            }
            HStack(spacing: 10) {
                VStack(spacing: 6) {
                    Button { showInfo = true } label: { Image(systemName: "info.circle").frame(width: 28, height: 30) }.accessibilityLabel("Chart details")
                    Button { templateType = chartType; showTemplate = true } label: { Image(systemName: "slider.horizontal.3").frame(width: 28, height: 30) }.accessibilityLabel("TP / SL template")
                }
                VStack(spacing: 6) {
                    HStack(spacing: 8) {
                        Button { join("bid") } label: { Text("Join Bid").frame(maxWidth: .infinity, minHeight: 30) }.tint(.green).disabled(joinPrice("bid") == nil || paperBusy || paperActive)
                        Button { join("ask") } label: { Text("Join Ask").frame(maxWidth: .infinity, minHeight: 30) }.tint(.red).disabled(joinPrice("ask") == nil || paperBusy || paperActive)
                    }
                    HStack(spacing: 8) {
                        Menu {
                            Button("Add contracts") { adjustmentAction = "add"; adjustmentQuantity = 1; showAdjustment = true }.disabled(positionSize >= quantityLimit)
                            Button("Trim contracts") { adjustmentAction = "trim"; adjustmentQuantity = 1; showAdjustment = true }.disabled(positionSize < 2)
                        } label: { Image(systemName: "plus.forwardslash.minus").frame(minWidth: 0, maxWidth: .infinity, minHeight: 30) }.accessibilityLabel("Add or trim contracts").disabled(!paperEnabled || paperBusy || positionSize == 0 || paperState["known"] as? Bool != true || paperState["scalable"] as? Bool != true)
                        Button { if paperEnabled { paperAction(["action": "close"]) } else if validEntry > 0 { entry = "0" } else { showClosePreview = true } } label: { Text("Close Position").lineLimit(1).minimumScaleFactor(0.65).frame(minWidth: 0, maxWidth: .infinity, minHeight: 30) }.tint(.orange).disabled(paperBusy || (paperEnabled ? !paperActive : validEntry <= 0))
                        Button { if paperEnabled { paperAction(["action": "be"]) } else { beRevision += 1 } } label: { Text("BE").frame(minWidth: 0, maxWidth: .infinity, minHeight: 30) }.tint(.purple).disabled(paperBusy || (paperEnabled && (paperState["position"] as? Double ?? 0) == 0) || beApplied || validEntry <= 0 || (packet["price_rules"] as? [[String: Any]])?.isEmpty != false)
                    }
                }.font(.system(size: 13, weight: .semibold))
            }.buttonStyle(.bordered)
            }
        }.padding(.horizontal, 12).padding(.bottom, 8)
        .navigationTitle(chartSymbol).navigationBarTitleDisplayMode(.inline)
        .toolbar(fullScreen ? .hidden : .visible, for: .navigationBar, .tabBar)
        .modifier(KeyboardDismissal())
        .sheet(isPresented: $showSymbols) {
            NavigationStack {
                List {
                    HStack {
                        TextField("Symbol", text: $symbolQuery).textInputAutocapitalization(.characters).autocorrectionDisabled()
                            .onSubmit { Task { await searchSymbols() } }
                        Button("Search") { Task { await searchSymbols() } }.disabled(searching)
                    }
                    LazyVGrid(columns: Array(repeating: GridItem(.flexible()), count: 3)) { ForEach(["TSLA", "ES", "NQ", "TSLL", "MES", "MNQ"], id: \.self) { symbol in Button(symbol) { symbolQuery = symbol; Task { await searchSymbols() } }.buttonStyle(.bordered) } }
                    if searching { ProgressView() }
                    if let symbolError { Text(symbolError).foregroundStyle(.red) }
                    ForEach(symbolResults.indices, id: \.self) { index in
                        let result = symbolResults[index]
                        Button {
                            selectedContract = result; entry = "0"; beApplied = false; paperState = [:]; paperMessage = nil
                            if chartType == "FUT" { session = "all" }
                            showSymbols = false
                        } label: {
                            VStack(alignment: .leading) {
                                Text(result["local_symbol"] as? String ?? "")
                                Text("\(result["exchange"] as? String ?? "") · \(result["expiration"] as? String ?? "")").font(.caption).foregroundStyle(.secondary)
                            }
                        }
                    }
                }.navigationTitle("Chart symbol").toolbar { Button("Done") { showSymbols = false } }
            }
        }
        .alert("Close Position · Preview", isPresented: $showClosePreview) {
            Button("Done", role: .cancel) { }
        } message: {
            Text("This will close the current symbol when live chart trading is enabled. No order has been sent; your position is unchanged.")
        }
        .sheet(isPresented: $showQuantityEditor) {
            NavigationStack {
                Form {
                    Section("Quantity") {
                        TextField("Quantity", text: $quantityDraft).keyboardType(.numberPad)
                            .font(.title2).multilineTextAlignment(.center)
                        HStack {
                            Button { quantityDraft = String(max(1, (Int(quantityDraft) ?? 1) - 1)) } label: { Image(systemName: "minus").frame(maxWidth: .infinity) }
                            Button { quantityDraft = String(min(quantityLimit, (Int(quantityDraft) ?? 0) + 1)) } label: { Image(systemName: "plus").frame(maxWidth: .infinity) }
                        }.buttonStyle(.bordered)
                        LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())]) {
                            ForEach([1, 2, 3, 5, 10, 25], id: \.self) { value in
                                Button { quantityDraft = String(value) } label: { Text(value.formatted()).frame(maxWidth: .infinity) }.buttonStyle(.bordered).disabled(value > quantityLimit)
                            }
                        }
                        HStack {
                            Button("Clear") { quantityDraft = "" }
                            Spacer()
                            Button("Reset") { quantityDraft = quantity }
                        }
                        Text("1–\(quantityLimit)").font(.caption).foregroundStyle(.secondary)
                    }
                }.navigationTitle("Order quantity").navigationBarTitleDisplayMode(.inline)
                    .toolbar {
                        ToolbarItem(placement: .cancellationAction) { Button("Cancel") { showQuantityEditor = false } }
                        ToolbarItem(placement: .confirmationAction) { Button("Apply") {
                            if let value = validQuantityDraft, !paperActive, !paperBusy { quantity = String(value); showQuantityEditor = false }
                        }.disabled(validQuantityDraft == nil || paperActive || paperBusy) }
                    }
            }.presentationDetents([.medium, .large])
        }
        .sheet(isPresented: $showAdjustment) {
            NavigationStack {
                Form {
                    Text("Current position: \(positionSize)")
                    Stepper("Quantity: \(adjustmentQuantity)", value: $adjustmentQuantity, in: 1...max(1, adjustmentLimit))
                    Text("Futures use one protected bracket per contract. Add creates new brackets. Trim exits selected contracts at bid/ask while keeping every other bracket unchanged.").font(.caption)
                    Button(adjustmentAction == "trim" ? "Trim position" : "Add to position") {
                        showAdjustment = false
                        paperAction(["action": adjustmentAction, "quantity": adjustmentQuantity])
                    }.disabled(paperBusy || adjustmentLimit < adjustmentQuantity)
                }.navigationTitle(adjustmentAction == "trim" ? "Trim" : "Add")
                    .toolbar { Button("Cancel") { showAdjustment = false } }
            }.presentationDetents([.medium])
        }
        .sheet(isPresented: $showIndicatorSettings) { indicatorSettings }
        .sheet(isPresented: $showDisplaySettings) {
            NavigationStack {
                Form {
                    Section("Profit and loss value") {
                        Toggle("Show P&L", isOn: $showProfit)
                        Toggle("Positions", isOn: $showPositionProfit).disabled(!showProfit)
                        Picker("Position P&L unit", selection: $positionProfitUnit) {
                            Text("Money").tag("money"); Text("Ticks").tag("ticks")
                        }.disabled(!showProfit || !showPositionProfit)
                        Toggle("Brackets", isOn: $showBracketProfit).disabled(!showProfit)
                        Picker("Bracket P&L unit", selection: $bracketProfitUnit) {
                            Text("Money").tag("money"); Text("Ticks").tag("ticks")
                        }.disabled(!showProfit || !showBracketProfit)
                    }
                    Section("ATR") {
                        Toggle("Show ATR", isOn: $showATR)
                        Stepper("ATR Length: \(atrLength)", value: $atrLength, in: 1...200).disabled(!showATR)
                    }
                    Section("Executions") {
                        Toggle("Execution marks", isOn: $showExecutions)
                        Toggle("Execution labels", isOn: $showExecutionLabels).disabled(!showExecutions)
                    }
                }.navigationTitle("Chart display").toolbar { Button("Done") { showDisplaySettings = false } }
            }.presentationDetents([.medium, .large])
        }
        .sheet(isPresented: $showTemplate) {
            NavigationStack {
                Form {
                    Picker("Asset class", selection: $templateType) {
                        Text("Stocks").tag("STK")
                        Text("Options").tag("OPT")
                        Text("Futures").tag("FUT")
                    }.pickerStyle(.segmented)
                    Section("Price distance") {
                        distanceRow("TP", value: distanceBinding(templateType, tp: true))
                        distanceRow("SL", value: distanceBinding(templateType, tp: false))
                    }
                    if validEntry > 0 && templateType == chartType && !paperActive {
                        Text("Apply updates the current preview and saves these distances for new orders.")
                        Button("Apply to preview") { templateRevision += 1; showTemplate = false }.disabled(!validTemplate)
                    } else {
                        Text(paperActive ? "These distances apply to your next order. Existing orders stay unchanged." : "These distances will be used for new orders in this asset class.")
                        Button("Save template") { showTemplate = false }.disabled(!validTemplate)
                    }
                    if !validTemplate { Text("Enter a positive TP and SL distance.").font(.caption).foregroundStyle(.orange) }
                }.navigationTitle("TP / SL template").toolbar { Button("Done") { showTemplate = false } }
            }.presentationDetents([.medium, .large])
        }
        .sheet(isPresented: $showIntervals) {
            NavigationStack {
                List(intervals, id: \.self) { value in
                    HStack {
                        Button { interval = value; showIntervals = false } label: {
                            HStack { Text(intervalLabel(value)); Spacer(); if interval == value { Image(systemName: "checkmark") } }.contentShape(Rectangle())
                        }.buttonStyle(.plain)
                        Button {
                            var selected = favorites
                            if selected.contains(value) { selected.remove(value) } else { selected.insert(value) }
                            favoriteIntervals = intervals.filter { selected.contains($0) }.map(String.init).joined(separator: ",")
                        } label: { Image(systemName: favorites.contains(value) ? "star.fill" : "star").foregroundStyle(favorites.contains(value) ? Color.yellow : Color.secondary).frame(width: 44, height: 44) }.buttonStyle(.plain).accessibilityLabel("Favorite " + intervalLabel(value))
                    }
                }.navigationTitle("Interval").toolbar { Button("Done") { showIntervals = false } }
            }.presentationDetents([.medium, .large])
        }
        .sheet(isPresented: $showInfo) {
            NavigationStack {
                Form {
                    Section("Entry reference") { TextField("Price", text: $entry).keyboardType(.decimalPad) }
                    Text(paperEnabled ? "IB Paper: Join Bid / Ask submits Entry, TP and SL. Dragging TP / SL sends an amendment on release. New futures brackets keep protection while Trim / Close sends a limit exit at bid / ask; a moving market may leave the exit working." : "TP / SL preview only · drag the labels. No orders are sent.")
                    Text("Prices and market-data permissions come from the connected IB account.")
                    Text("ETH includes available extended-hours data. Time: New York.")
                    Text("TradingView Lightweight Charts™ · Copyright © 2025 TradingView, Inc.")
                    Link("TradingView", destination: URL(string: "https://www.tradingview.com/")!)
                }.navigationTitle("Chart details")
                    .toolbar { Button("Done") { showInfo = false } }
            }.presentationDetents([.medium, .large])
        }
        .onAppear {
            if !initialized {
                if resumeLast {
                    if let data = UserDefaults.standard.data(forKey: recentChartKey),
                       let record = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                       let contract = record["contract"] as? [String: Any],
                       let id = contract["con_id"] as? Int, id > 0 {
                        selectedContract = contract
                        if let saved = record["interval"] as? Int, intervals.contains(saved) { interval = saved }
                        if let saved = record["session"] as? String, ["rth", "all"].contains(saved) { session = saved }
                    } else if position.con_id == nil { showSymbols = true }
                }
                if chartType == "FUT" && !resumeLast { session = "all" }
                initialized = true
                rememberChart()
            }
            visible = true
            if entry.isEmpty { entry = selectedContract.isEmpty ? String(position.market_price ?? 0) : "0" }
        }
        .onChange(of: cacheKey) { rememberChart() }
        .onDisappear { rememberChart(); visible = false }
        .task(id: "paper-" + context) {
            paperState = [:]
            guard visible, phase == .active, !store.demo, chartType != "OPT", let cid = chartID else { return }
            while !Task.isCancelled {
                do {
                    let state = try await store.trading.get("api/portfolio/paper-chart/\(cid)", base: store.address)
                    try Task.checkCancellation()
                    guard chartID == cid else { return }
                    if !paperBusy { applyPaperState(state) }
                } catch {
                    if Task.isCancelled { return }
                    paperState["sync_error"] = true
                }
                do { try await Task.sleep(for: .seconds(1)) } catch { return }
            }
        }
        .task(id: context) {
            // Scene transitions cancel transport, not the chart or its viewport.
            // A fresh stream must validate quotes again before Join is enabled.
            received = nil
            guard visible, phase == .active else { return }
            if loadedChartKey != cacheKey {
                packet = [:]
                loadedChartKey = cacheKey
            }
            notice = "Reconnecting chart…"
            guard !store.demo else { notice = "Chart requires a connected brokerage account"; return }
            guard let conID = chartID, conID > 0 else { return }
            let requestContext = context
            let requestCacheKey = cacheKey
            if packet.isEmpty, let cached = RecentStockCharts.load(requestCacheKey) {
                packet = cached.1
                packet["bid"] = NSNull(); packet["ask"] = NSNull()
                // Legacy caches lack a local clock anchor; never restart an old timer.
                if packet["chart_received_at"] == nil { packet["bar_closes_at"] = NSNull() }
                notice = "Saved chart · connecting to live data"
            }
            var failures = 0
            while !Task.isCancelled {
                do {
                    if interval < 1440 && !(interval == 480 && session == "rth") {
                        try await store.trading.chartStream(base: store.address, conID: conID, interval: interval, marketSession: session) { result in
                            guard !Task.isCancelled, context == requestContext, result["con_id"] as? Int == conID else { return }
                            packet = result; received = .now; packet["chart_received_at"] = Date().timeIntervalSince1970; failures = 0
                            RecentStockCharts.save(packet, key: requestCacheKey)
                            notice = chartType == "OPT" ? (result["status"] as? String == "live" ? "IB option bars · live updates" : "Historical option bars · waiting for updates") : (result["status"] as? String == "live" ? "IB Last ticks · live push" : "Historical bars · waiting for IB Last ticks")
                        }
                    }
                    let result = try await store.trading.get("api/portfolio/stock-chart/\(conID)", base: store.address,
                        query: [URLQueryItem(name: "interval", value: String(interval)), URLQueryItem(name: "session", value: session)])
                    try Task.checkCancellation()
                    guard context == requestContext else { return }
                    guard result["con_id"] as? Int == conID, result["bars"] is [[String: Any]] else { throw AppError.message("Invalid chart response") }
                    packet = result; received = .now; packet["chart_received_at"] = Date().timeIntervalSince1970; failures = 0
                    RecentStockCharts.save(packet, key: requestCacheKey)
                    notice = chartType == "OPT" ? (result["status"] as? String == "live" ? "IB option bars · live updates" : "Historical option bars · waiting for updates") : (interval >= 1440 || (interval == 480 && session == "rth")) ? "IB historical bars · chart updates" : result["status"] as? String == "live" ? "IB Last ticks · display batches ≈250ms" : "Historical bars · waiting for IB Last ticks"
                } catch {
                    guard !Task.isCancelled else { return }
                    failures = min(failures + 1, 5)
                    notice = connectionMessage(error)
                }
                do { try await Task.sleep(for: .seconds(failures == 0 ? (packet["status"] as? String == "live" ? 0.25 : 1) : min(10, pow(2, Double(failures - 1))))) } catch { return }
            }
        }
    }
}

// WebKit's CSS viewport can lag SwiftUI's first layout/full-screen transition.
// Forward actual native bounds, independently of market-data updates.
final class ChartViewportWebView: WKWebView {
    var viewportReady = false
    private var sentSize: CGSize = .zero
    override func layoutSubviews() {
        super.layoutSubviews()
        synchronizeViewport()
    }
    func synchronizeViewport(force: Bool = false) {
        let size = bounds.size
        guard viewportReady, size.width > 0, size.height > 0,
              force || size != sentSize else { return }
        sentSize = size
        evaluateJavaScript("window.setNativeViewport?.(\(size.width),\(size.height))", completionHandler: nil)
    }
}

private struct StockChartWeb: UIViewRepresentable {
    var display: [String: Any]
    var drawingKey: String
    var packet: [String: Any]
    var entry: Double
    var quantity: Double
    var dark: Bool
    var entryType: String
    var joinSide: Int
    var joinRevision: Int
    var beRevision: Int
    var tpDistance: Double
    var slDistance: Double
    var templateRevision: Int
    var onBE: (Bool) -> Void
    var onEntry: (Double) -> Void
    var paperState: [String: Any]
    var conID: Int
    var onPaper: ([String: Any]) -> Void
    func makeCoordinator() -> Coordinator { Coordinator() }
    func makeUIView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        config.websiteDataStore = .nonPersistent()
        config.userContentController.add(context.coordinator, name: "drawingsChanged")
        config.userContentController.add(context.coordinator, name: "chartReady")
        config.userContentController.add(context.coordinator, name: "entryChanged")
        config.userContentController.add(context.coordinator, name: "beState")
        config.userContentController.add(context.coordinator, name: "paperAction")
        let web = ChartViewportWebView(frame: .zero, configuration: config)
        web.scrollView.isScrollEnabled = false
        web.scrollView.contentInsetAdjustmentBehavior = .never
        web.isOpaque = false
        context.coordinator.web = web
        func resource(_ name: String, _ ext: String) -> URL? {
            Bundle.main.url(forResource: name, withExtension: ext) ?? Bundle.main.url(forResource: name, withExtension: ext, subdirectory: "ChartAssets")
        }
        if let html = resource("stock-chart", "html"), let library = resource("lightweight-charts.standalone.production", "js"),
           let template = try? String(contentsOf: html, encoding: .utf8), let js = try? String(contentsOf: library, encoding: .utf8) {
            let drawingJS = resource("chart-drawings", "js").flatMap { try? String(contentsOf: $0, encoding: .utf8) } ?? ""
            let html = template.replacingOccurrences(of: "/*LIBRARY*/", with: js)
                .replacingOccurrences(of: "</body>", with: "<script>" + drawingJS + "</script></body>")
            web.loadHTMLString(html, baseURL: nil)
        } else { web.loadHTMLString("<p>Chart resources unavailable</p>", baseURL: nil) }
        return web
    }
    func updateUIView(_ web: WKWebView, context: Context) {
        context.coordinator.packet = packet.isEmpty ? ["bars": [], "generation": "clear", "interval": 0, "session": ""] : packet
        context.coordinator.drawingKey = drawingKey
        context.coordinator.onEntry = onEntry
        context.coordinator.onBE = onBE
        context.coordinator.onPaper = onPaper
        context.coordinator.config = ["display": display, "entry": entry, "quantity": quantity, "dark": dark, "entryType": entryType, "joinSide": joinSide, "joinRevision": joinRevision, "beRevision": beRevision, "tpDistance": tpDistance.isFinite ? tpDistance : 0, "slDistance": slDistance.isFinite ? slDistance : 0, "templateRevision": templateRevision, "priceRules": packet["price_rules"] ?? [], "paper": paperState, "con_id": conID, "multiplier": packet["multiplier"] ?? 1]
        context.coordinator.update()
    }
    static func dismantleUIView(_ web: WKWebView, coordinator: Coordinator) {
        web.configuration.userContentController.removeScriptMessageHandler(forName: "drawingsChanged")
        web.configuration.userContentController.removeScriptMessageHandler(forName: "chartReady")
        web.configuration.userContentController.removeScriptMessageHandler(forName: "entryChanged")
        web.configuration.userContentController.removeScriptMessageHandler(forName: "beState")
        web.configuration.userContentController.removeScriptMessageHandler(forName: "paperAction")
        web.stopLoading(); web.loadHTMLString("", baseURL: nil)
    }
    class Coordinator: NSObject, WKScriptMessageHandler {
        weak var web: WKWebView?
        var ready = false
        var drawingKey = ""
        var loadedDrawingKey = ""
        var bridgeBusy = false
        var bridgePending = false
        var lastStreamSequence = 0
        var lastStreamKey = ""
        var packet: [String: Any] = [:]
        var config: [String: Any] = [:]
        var onEntry: ((Double) -> Void)?
        var onBE: ((Bool) -> Void)?
        var onPaper: (([String: Any]) -> Void)?
        func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
            if message.name == "drawingsChanged", let value = message.body as? [String: Any],
               let data = try? JSONSerialization.data(withJSONObject: value), data.count < 2_000_000 {
                UserDefaults.standard.set(data, forKey: "chartDrawings-" + drawingKey)
                if let styles = value["toolStyles"] as? [String: Any], let stylesData = try? JSONSerialization.data(withJSONObject: styles) { UserDefaults.standard.set(stylesData, forKey: "chartToolStylesV1") }
                if let favorites = value["favorites"] as? [String] { UserDefaults.standard.set(favorites, forKey: "chartDrawingFavorites") }
                if let order = value["order"] as? [String] { UserDefaults.standard.set(order, forKey: "chartDrawingOrder") }
                if let magnet = value["magnet"] as? String { UserDefaults.standard.set(magnet, forKey: "chartDrawingMagnet") }
                if let collapsed = value["collapsed"] as? Bool { UserDefaults.standard.set(collapsed, forKey: "chartDrawingCollapsed") }
            } else if message.name == "paperAction", let body = message.body as? [String: Any] { onPaper?(body)
            } else if message.name == "beState", let applied = message.body as? Bool { onBE?(applied)
            } else if message.name == "entryChanged", let price = message.body as? Double, price.isFinite, price >= 0 {
                onEntry?(price)
            } else if message.name == "chartReady" {
                ready = true
                (web as? ChartViewportWebView)?.viewportReady = true
                update()
            }
        }
        func update() {
            guard ready else { return }
            if bridgeBusy { bridgePending = true; return }
            if drawingKey != loadedDrawingKey {
                var value: [String: Any] = [:]
                if let data = UserDefaults.standard.data(forKey: "chartDrawings-" + drawingKey),
                   let saved = try? JSONSerialization.jsonObject(with: data) as? [String: Any] { value = saved }
                if let stylesData = UserDefaults.standard.data(forKey: "chartToolStylesV1"), let styles = try? JSONSerialization.jsonObject(with: stylesData) as? [String: Any] { value["toolStyles"] = styles }
                if let favorites = UserDefaults.standard.stringArray(forKey: "chartDrawingFavorites") { value["favorites"] = favorites }
                if let order = UserDefaults.standard.stringArray(forKey: "chartDrawingOrder") { value["order"] = order }
                if let magnet = UserDefaults.standard.string(forKey: "chartDrawingMagnet") { value["magnet"] = magnet }
                if let collapsed = UserDefaults.standard.object(forKey: "chartDrawingCollapsed") as? Bool { value["collapsed"] = collapsed }
                if let data = try? JSONSerialization.data(withJSONObject: ["key": drawingKey, "value": value]), let json = String(data: data, encoding: .utf8) {
                    web?.evaluateJavaScript("window.configureDrawings?.(\(json))", completionHandler: nil)
                    loadedDrawingKey = drawingKey
                }
            }
            var outgoing = packet
            if let sequence = packet["sequence"] as? Int {
                let key = "\(packet["stream_id"] ?? "")-\(packet["con_id"] ?? "")-\(packet["generation"] ?? "")-\(packet["interval"] ?? "")-\(packet["session"] ?? "")"
                if sequence == lastStreamSequence && key == lastStreamKey { outgoing = [:] }
                else {
                    if lastStreamKey == key && sequence == lastStreamSequence + 1 && packet["mode"] as? String == "delta" {
                        outgoing["bars"] = packet["changed_bars"] ?? []
                    } else { outgoing["mode"] = "snapshot" }
                    lastStreamKey = key; lastStreamSequence = sequence
                }
                outgoing.removeValue(forKey: "changed_bars")
            } else { lastStreamSequence = 0; lastStreamKey = "" }
            guard let web else { return }
            // Initial settings, cached bars and native dimensions enter JS together.
            // Do not display bars using a previous frame's formatter or canvas size.
            let state: [String: Any] = ["config": config, "packet": outgoing,
                                        "width": web.bounds.width, "height": web.bounds.height]
            guard let data = try? JSONSerialization.data(withJSONObject: state),
                  let json = String(data: data, encoding: .utf8) else { return }
            bridgeBusy = true
            web.evaluateJavaScript("window.applyChartState(\(json))") { [weak self] _, error in
                guard let self else { return }
                self.bridgeBusy = false
                if error != nil { self.lastStreamSequence = 0; self.lastStreamKey = "" }
                if self.bridgePending { self.bridgePending = false; self.update() }
            }
        }
    }
}
