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
        let bars = packet["bars"] as? [[String: Any]] ?? []
        guard !bars.isEmpty || !(packet["frames"] as? [String: Any] ?? [:]).isEmpty else { return }
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

private struct ChartPositionActionsLayout: Layout {
    private let spacing: CGFloat = 8

    private func widths(_ width: CGFloat) -> [CGFloat] {
        let available = max(0, width - 2 * spacing)
        let be = available / 3
        let adjustment = min(be, max(44, min(56, be * 0.6)))
        return [adjustment, available - be - adjustment, be]
    }

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let width = proposal.width.flatMap { $0.isFinite ? $0 : nil } ?? 300
        let sizes = zip(subviews, widths(width)).map { view, width in
            view.sizeThatFits(ProposedViewSize(width: width, height: nil)).height
        }
        return CGSize(width: width, height: sizes.max() ?? 44)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var x = bounds.minX
        for (view, width) in zip(subviews, widths(bounds.width)) {
            view.place(at: CGPoint(x: x, y: bounds.minY), anchor: .topLeading,
                       proposal: ProposedViewSize(width: width, height: bounds.height))
            x += width + spacing
        }
    }
}

struct ChartOrderProgressView: View {
    var state: [String: Any]
    @Environment(\.locale) private var locale
    private func label(_ key: String) -> String { localizedLabel(key, locale: locale) }
    private func number(_ data: [String: Any], _ key: String) -> String { (data[key] as? Double)?.formatted() ?? "—" }
    var body: some View {
        VStack(spacing: 3) {
            if let progress = state["close_progress"] as? [String: Any] {
                Text(verbatim: "Close · \(label("Filled")) \(number(progress, "filled"))/\(number(progress, "requested")) · \(label("Position")) \(number(progress, "remaining")) · \(progress["status"] as? String ?? "unknown")")
            } else if let progress = state["adjustment"] as? [String: Any] {
                Text(verbatim: "\(label("Filled")) \(number(progress, "filled"))/\(number(progress, "requested")) · \(label("Awaiting fill")) \(number(progress, "pending")) · \(label("Remaining")) \(number(progress, "remaining"))")
            }
            if let protection = state["protection"] as? [String: Any], state["active"] as? Bool == true {
                Text(verbatim: "\(label("Position")) \(number(protection, "remaining_position")) · TP \(number(protection, "tp")) · SL \(number(protection, "sl"))")
                Text(verbatim: label(state["sync_error"] as? Bool == true ? "unknown" : protection["status"] as? String ?? "unknown"))
            }
        }.font(.caption).foregroundStyle(.secondary).multilineTextAlignment(.center)
            .fixedSize(horizontal: false, vertical: true).frame(maxWidth: .infinity)
    }
}

struct ChartBarCountInput: View {
    @Binding var value: Int
    @State private var draft = ""
    @FocusState private var focused: Bool
    private func finishEditing() {
        value = Int(draft).map { min(2000, max(50, $0)) } ?? value
        draft = String(value)
    }
    var body: some View {
        HStack {
            Text("Bars to render")
            Spacer()
            TextField("50–2000", text: $draft)
                .keyboardType(.numberPad).multilineTextAlignment(.trailing)
                .frame(width: 100).focused($focused)
                .accessibilityLabel("Bars to render")
        }
        .onAppear { draft = String(value) }
        .onChange(of: draft) { _, text in
            let digits = String(text.filter { $0.isASCII && $0.isNumber }.prefix(5))
            if digits != text { draft = digits }
            if let number = Int(digits), (50...2000).contains(number) { value = number }
        }
        .onChange(of: value) { _, number in if !focused { draft = String(number) } }
        .onChange(of: focused) { _, editing in if !editing { finishEditing() } }
        .onDisappear { finishEditing() }
        .toolbar {
            ToolbarItemGroup(placement: .keyboard) {
                Spacer()
                Button("Done") { finishEditing(); focused = false }
            }
        }
    }
}

struct PreviousValueRow: Codable, Equatable {
    var enabled = true
    var frame = 1440
    var source: String
    var color: String
    var style = "dotted"
    var width = 1
}
struct PreviousValuesSettings: Codable, Equatable {
    var enabled = true
    var display = "Today"
    var baseChart = true
    var lineDraw = true
    var rows = [PreviousValueRow(source: "close", color: "#434651"), PreviousValueRow(source: "high", color: "#F23645"), PreviousValueRow(source: "low", color: "#089981")]
}

struct FVGSettings: Codable, Equatable {
    var enabled = true
    var confirmed = true
    var shrink = true
    var maxCount = 8
    var minTicks = 2
    var atrFactor = 0.05
    var bullColor = "#f5a623"
    var bearColor = "#4b8cff"
    var bullOpacity = 22.0
    var bearOpacity = 20.0
}

struct IndicatorTemplate: Codable, Identifiable {
    var id = UUID()
    var name: String
    var settings: IndicatorSettingsSnapshot
}

struct IndicatorSettingsSnapshot: Codable, Equatable {
    var fvg: FVGSettings? = nil
    var previousValues: PreviousValuesSettings? = nil
    var showEMA: Bool
    var emaLength: Int
    var emaSource: String
    var emaOffset: Int
    var emaFrame: Int
    var emaDynamic: Bool
    var emaColor: String
    var emaWidth: Int
    var emaStyle: Int
    var extraEMAJSON: String
    var showATR: Bool
    var atrLength: Int
    var showBarCount: Bool
    var barCountFrame: Int
    var barCountSize: String
    var barCountColor: String
    var barCountOpacity: Double
    var barCountLimit: Bool
    var barCountBars: Int
    var indicatorVisible: Bool
}

struct ExtraEMA: Codable {
    var enabled = true
    var timeframe: Int
    var length = 20
    var source = "close"
    var offset = 0
    var color: String
    var width = 1
    var style = 0
    var stepped = false
    static let defaults = [ExtraEMA(timeframe: 15, color: "#d1c4e9"), ExtraEMA(timeframe: 60, color: "#8d8da0", stepped: true)]
}

enum ChartHoldingOverlay {
    static func rows(positions: [Position], conID: Int?, symbol: String, type: String, chinese: Bool) -> [[String: Any]] {
        guard let conID, conID > 0 else { return [] }
        let underlyingSymbol = positions.first { $0.con_id == conID && $0.security_type == type }?.symbol ?? symbol
        return positions.compactMap { holding in
            guard holding.position.isFinite, holding.position != 0, let id = holding.con_id, id > 0 else { return nil }
            let exact = id == conID && holding.security_type == type
            let strike = type == "STK" && holding.security_type == "OPT" && holding.symbol.uppercased() == underlyingSymbol.uppercased()
            guard exact || strike else { return nil }
            let size = holding.position.formatted(.number.grouping(.never).precision(.fractionLength(0...8)))
            var price: Double?
            var caption: String
            if strike {
                price = holding.strike
                let option = ["CALL", "C"].contains(holding.option_type?.uppercased() ?? "") ? "C" : "P"
                let strikeText = holding.strike?.formatted(.number.grouping(.never).precision(.fractionLength(0...4))) ?? "—"
                let fill = holding.entry_fill_price.flatMap { $0.isFinite && $0 > 0 ? String(format: "%.2f", $0) : nil } ?? "—"
                caption = "\(size) \(strikeText)\(option)@\(fill)"

            } else {
                // Fill prices are already in quoted units and exclude commission.
                if holding.security_type == "STK", let report = holding.reported_cost,
                   report.quantity.isFinite, abs(report.quantity - holding.position) < 0.000001 {
                    price = report.average
                } else { price = holding.entry_fill_price }
                caption = "\(size) · " + (chinese ? "成交均价" : "Avg")
            }
            if let value = price, !value.isFinite || value <= 0 { price = nil }
            if strike && price == nil { return nil }
            if price == nil { caption += " —" }
            return ["id": "\(strike ? "strike" : "holding")-\(id)", "price": price as Any? ?? NSNull(), "title": caption,
                    "kind": strike ? "strike" : "holding", "side": holding.position > 0 ? 1 : -1,
                    "pnl": holding.unrealized_pnl.flatMap { $0.isFinite ? $0 : nil } as Any? ?? NSNull(),
                    "basis": holding.avg_cost.flatMap { cost -> Double? in
                        let basis = abs(cost * holding.position)
                        return basis.isFinite && basis > 0 ? basis : nil
                    } as Any? ?? NSNull(),
                    "marketPrice": holding.market_price.flatMap { $0.isFinite ? $0 : nil } as Any? ?? NSNull()]
        }
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
    @State private var accountExecutions: [[String: Any]] = []
    @State private var executionCID: Int?
    @State private var paperState: [String: Any] = [:]
    @State private var completedPaperOrders: Set<String> = []
    @State private var showQuantityEditor = false
    @State private var quantityDraft = "1"
    @State private var editSnapshot: [[String: Any]] = []
    @State private var editOrderRef = ""
    @State private var editTIF = "DAY"
    @State private var previewTIF = "DAY"
    @State private var editingExistingOrder = false
    @State private var editAllowedTIFs = ["DAY", "GTC"]
    @State private var confirmRemoveProtection = false
    private var removingProtection: Bool { editTIF == "OVERNIGHT" && (!editingExistingOrder || paperState["mode"] as? String != "overnight_entry") }
    @State private var editPrice = ""
    private var entryEditable: Bool { paperState["entry_editable"] as? Bool == true && paperEnabled }
    private func beginOrderEdit() {
        quantityDraft = String(Int(paperState["quantity"] as? Double ?? (paperState["orders"] as? [[String: Any]])?.first(where: { $0["role"] as? String == "entry" })?["quantity"] as? Double ?? validQuantity))
        editSnapshot = paperState["edit_snapshot"] as? [[String: Any]] ?? []
        editOrderRef = paperState["order_ref"] as? String ?? ""
        editTIF = paperState["tif"] as? String ?? "DAY"
        confirmRemoveProtection = false
        editPrice = String(paperState["entry"] as? Double ?? validEntry)
    }
    private var quantityLimit: Int { chartType == "STK" ? 1000 : 10 }
    private var validQuantityDraft: Int? {
        guard let value = Int(quantityDraft), (1...quantityLimit).contains(value) else { return nil }
        return value
    }
    @State private var paperReceived: Date?
    @State private var paperBusy = false
    @State private var submitRevision = 0
    @State private var joinSubmissionGate = ChartJoinGate()
    @State private var paperMessage: String?
    @State private var pendingActionLabel = ""
    @State private var protectionCancelRef: String?
    @State private var protectionCancelCID: Int?
    @State private var protectionCancelRole: String?
    @State private var showPositionProtection = false
    @State private var positionProtectionState: [String: Any] = [:]
    @State private var positionProtectionCID: Int?
    @AppStorage("chartProtectionOptionsV14") private var protectionOptions = "{}"
    private func protectionOption(_ type: String, _ key: String) -> String? {
        guard let data = protectionOptions.data(using: .utf8), let values = try? JSONDecoder().decode([String: String].self, from: data) else { return nil }
        return values[type + key]
    }
    private func saveProtectionOption(_ type: String, _ key: String, _ value: String) {
        var values = (try? JSONDecoder().decode([String: String].self, from: Data(protectionOptions.utf8))) ?? [:]
        values[type + key] = value
        if let data = try? JSONEncoder().encode(values), let text = String(data: data, encoding: .utf8) { protectionOptions = text }
    }
    private func protectionToggle(_ type: String, _ role: String) -> Binding<Bool> {
        Binding(get: { protectionOption(type, role) != "off" }, set: { saveProtectionOption(type, role, $0 ? "on" : "off"); templateRevision += 1 })
    }
    private func protectionMode(_ type: String) -> Binding<String> {
        Binding(get: { protectionOption(type, "mode") ?? "distance" }, set: { value in
            saveProtectionOption(type, "mode", value)
            distanceBinding(type, tp: true).wrappedValue = value == "percent" ? "75" : value == "price" ? String(max(validEntry, 0.01)) : "0.20"
            templateRevision += 1
        })
    }
    private var hasOrderPreview: Bool { !paperActive && validEntry > 0 && validQuantity > 0 }
    private var paperEnabled: Bool { !store.trading.paperPending(base: store.address, conID: chartID ?? 0) && !store.trading.busy && Date().timeIntervalSince(paperReceived ?? .distantPast) < 3 && store.chartTradingAvailable && paperState["sync_error"] as? Bool != true && paperState["known"] as? Bool != false && paperState["enabled"] as? Bool == true }
    private var paperActive: Bool { paperState["active"] as? Bool == true }
    private func applyPaperState(_ state: [String: Any]) {
        paperState = state
        paperReceived = .now
        if state["active"] as? Bool == true, let price = state["entry"] as? Double, price > 0 { entry = String(price) }
        let rows = state["orders"] as? [[String: Any]] ?? []
        if state["status"] as? String == "done",
           let id = rows.first(where: { $0["role"] as? String == "entry" })?["order_id"] as? Int,
           completedPaperOrders.insert("\(store.address)-\(chartID ?? 0)-\(id)").inserted { entry = "0"; beApplied = false }
    }
    private func paperAction(_ incoming: [String: Any]) {
        var body = incoming
        if body["action"] as? String == "cancelProtectionPreview" {
            protectionCancelRef = body["expected_ref"] as? String
            protectionCancelCID = chartID
            protectionCancelRole = body["role"] as? String
            return
        }
        if body["action"] as? String == "close", paperState["closing"] as? Bool == true { return }
        if body["action"] as? String == "close" { body = TradeRules.chartCloseRequest(paperState); body["con_id"] = chartID }
        if body["action"] as? String == "indicatorSettings" { showIndicatorSettings = true; return }
        if body["action"] as? String == "indicatorToggle" { indicatorVisible.toggle(); return }
        if body["action"] as? String == "indicatorCollapse", let collapsed = body["collapsed"] as? Bool { indicatorCollapsed = collapsed; return }
        if body["action"] as? String == "previewOrder" {
            guard !paperActive, !paperBusy, body["con_id"] as? Int == chartID,
                  let price = body["entry"] as? Double, price > 0,
                  let type = body["entry_type"] as? String, ["LMT", "STP"].contains(type) else { return }
            guard previewTIF != "OVERNIGHT" || type == "LMT" else { paperMessage = "OVT supports limit orders only; STP is unavailable"; return }
            entry = String(price); entryType = type
            return
        }
        if body["action"] as? String == "setQuantity" {
            guard !paperActive, !paperBusy, body["con_id"] as? Int == chartID,
                  let value = body["quantity"] as? Int, (1...quantityLimit).contains(value) else { return }
            quantity = String(value); return
        }
        if ["editQuantity", "editOrderSettings"].contains(body["action"] as? String ?? "") {
            guard !paperBusy, !paperActive || entryEditable, body["con_id"] as? Int == chartID else { return }
            editingExistingOrder = paperActive
            editAllowedTIFs = paperActive ? (paperState["allowed_tifs"] as? [String] ?? ["DAY", "GTC"]) : TradeRules.chartTIFs(securityType: chartType, currency: packet["currency"] as? String ?? "", side: body["side"] as? Int ?? 0, entryType: entryType)
            if editingExistingOrder { beginOrderEdit() } else { quantityDraft = quantity; editPrice = entry; editTIF = editAllowedTIFs.contains(previewTIF) ? previewTIF : "DAY"; confirmRemoveProtection = false }
            showQuantityEditor = true; return
        }
        guard !paperBusy, paperEnabled, let cid = chartID else { return }
        if let source = body["con_id"] as? Int, source != cid { return }
        if body["action"] as? String == "submit" {
            guard !paperActive else { return }
            if body["source"] as? String == "join" {
                guard let revision = body["join_revision"] as? Int, revision == joinRevision, joinSubmissionGate.accept(revision) else { return }
            }
            if let type = body["entry_type"] as? String, ["LMT", "STP"].contains(type) { entryType = type }
            if let price = body["entry"] as? Double { entry = String(price) }
        }
        pendingActionLabel = body["cancel"] as? Bool == true ? "Canceling order…" : body["action"] as? String == "submit" ? "Submitting order…" : body["action"] as? String == "close" ? "Closing position…" : "Updating order…"
        paperMessage = nil
        paperBusy = true
        Task {
            defer { paperBusy = false; submitRevision += 1 }
            do {
                var request = body
                if body["action"] as? String == "submit" {
                    request["tif"] = previewTIF
                    if previewTIF == "OVERNIGHT" {
                        guard TradeRules.chartTIFs(securityType: chartType, currency: packet["currency"] as? String ?? "", side: body["side"] as? Int ?? 0, entryType: body["entry_type"] as? String ?? "").contains("OVERNIGHT") else { paperMessage = "OVT requires a USD stock limit entry"; return }
                        request["mode"] = "overnight_entry"; request.removeValue(forKey: "tp"); request.removeValue(forKey: "sl")
                    }
                }
                let result = try await store.trading.paperChartWrite(base: store.address, conID: cid, body: request)
                guard chartID == cid else { return }
                paperMessage = result["message"] as? String
                if let state = result["state"] as? [String: Any] { applyPaperState(state) }
                Task { await store.refreshOrders() }
            } catch {
                paperMessage = connectionMessage(error) + ((error as? BackendHTTPError)?.confirmedRejection == true ? "" : " · Confirming order outcome; do not resubmit")
            }
        }
    }
    @State private var selectedContract: [String: Any] = [:]
    @State private var showSymbols = false
    @State private var symbolQuery = "QQQ"
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
    @Environment(\.locale) private var locale
    @State private var interval = 5
    @State private var fullScreen = false
    @State private var tradingPanelCollapsed = true
    @AppStorage("chartOneMinuteShortcutAdded") private var oneMinuteShortcutAdded = false
    @AppStorage("chartFavoriteIntervals") private var favoriteIntervals = "1,3,5,10,15,60,480,1440,10080,43200"
    @State private var showIntervals = false
    private let intervals = [1, 3, 5, 10, 15, 60, 480, 1440, 10080, 43200]
    private var favorites: Set<Int> { Set(favoriteIntervals.split(separator: ",").compactMap { Int($0) }) }
    private func intervalLabel(_ value: Int) -> String {
        switch value { case 1440: return "D"; case 10080: return "W"; case 43200: return "M"; default: return value < 60 ? "\(value)m" : "\(value / 60)h" }
    }
    @AppStorage("stockChartSession") private var session = "rth"
    @State private var quantity = "1"
    @State private var entry = "0"
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
    @AppStorage("chartShowHoldings") private var showHoldings = true
    @AppStorage("chartOrderExtensionLines") private var showOrderExtensionLines = true
    @AppStorage("chartBarCount") private var rthBarCount = true
    @AppStorage("chartBarCountETH") private var ethBarCount = false
    private var showBarCount: Bool {
        get { session == "rth" ? rthBarCount : ethBarCount }
        nonmutating set { if session == "rth" { rthBarCount = newValue } else { ethBarCount = newValue } }
    }
    @AppStorage("chartBarCountFrame") private var barCountFrame = 1440
    @AppStorage("chartBarCountSize") private var barCountSize = "tiny"
    @AppStorage("chartBarCountColor") private var barCountColor = "#521c6e"
    @AppStorage("chartBarCountOpacityV1") private var barCountOpacity = 66.0
    @AppStorage("chartBarCountOpacityMigrationV1") private var barCountOpacityMigrated = false
    @AppStorage("chartBarCountLimit") private var barCountLimit = true
    @AppStorage("chartBarCountBars") private var barCountBars = 162
    private var barCountColorBinding: Binding<Color> {
        Binding(get: { CustomPalette.color(barCountColor) ?? .purple }, set: { color in
            var r: CGFloat = 0, g: CGFloat = 0, b: CGFloat = 0, a: CGFloat = 0
            UIColor(color).getRed(&r, green: &g, blue: &b, alpha: &a)
            barCountColor = String(format: "#%02X%02X%02X", Int(r*255), Int(g*255), Int(b*255))
        })
    }
    @AppStorage("chartShowPositionProfit") private var showPositionProfit = false
    @AppStorage("chartShowBracketProfit") private var showBracketProfit = true
    @AppStorage("chartShowExecutions") private var showExecutions = true
    @AppStorage("chartShowExecutionLabels") private var showExecutionLabels = true
    @AppStorage("chartPositionProfitUnit") private var positionProfitUnit = "money"
    @AppStorage("chartBracketProfitUnit") private var bracketProfitUnit = "money"
    @AppStorage("chartShowATR") private var showATR = true
    @AppStorage("chartATRLength") private var atrLength = 4
    @AppStorage("chartIndicatorCollapsedV2") private var indicatorCollapsed = true
    @AppStorage("chartIndicatorVisible") private var indicatorVisible = true
    @AppStorage("chartEMAFrame") private var emaFrame = 0
    @AppStorage("chartExtraEMAsV1") private var extraEMAJSON = ""
    @State private var emaFrames: [String: Any] = [:]
    @State private var emaFrameContext = ""
    @State private var emaHistoryNotice: String?
    private let emaIntervals = [0, 1, 3, 5, 10, 15, 30, 60, 240, 1440, 10080, 43200]
    private var extraEMAs: [ExtraEMA] {
        guard let data = extraEMAJSON.data(using: .utf8), let values = try? JSONDecoder().decode([ExtraEMA].self, from: data), values.count == 2 else { return ExtraEMA.defaults }
        return values
    }
    private func extraBinding<T>(_ index: Int, _ path: WritableKeyPath<ExtraEMA, T>) -> Binding<T> {
        Binding(get: { extraEMAs[index][keyPath: path] }, set: { value in
            var all = extraEMAs; all[index][keyPath: path] = value
            if let data = try? JSONEncoder().encode(all), let text = String(data: data, encoding: .utf8) { extraEMAJSON = text }
        })
    }
    private func extraColor(_ index: Int) -> Binding<Color> {
        Binding(get: { CustomPalette.color(extraEMAs[index].color) ?? .gray }, set: { color in
            var r: CGFloat = 0, g: CGFloat = 0, b: CGFloat = 0, a: CGFloat = 0
            UIColor(color).getRed(&r, green: &g, blue: &b, alpha: &a)
            extraBinding(index, \.color).wrappedValue = String(format: "#%02X%02X%02X", Int(r*255), Int(g*255), Int(b*255))
        })
    }
    @ViewBuilder private func frameChoices() -> some View {
        ForEach(emaIntervals, id: \.self) { value in Text(value == 0 ? "Chart" : intervalLabel(value)).tag(value) }
    }
    @ViewBuilder private func extraEMASection(_ index: Int) -> some View {
        Section("EMA \(index + 2)") {
            if indicatorTab == "Inputs" {
                Picker("Timeframe", selection: extraBinding(index, \.timeframe)) { frameChoices() }
                Stepper("Length: \(extraEMAs[index].length)", value: extraBinding(index, \.length), in: 1...500)
                Picker("Source", selection: extraBinding(index, \.source)) {
                    ForEach(["close", "open", "high", "low", "hl2", "hlc3", "ohlc4"], id: \.self) { Text($0.uppercased()).tag($0) }
                }
                Stepper("Offset: \(extraEMAs[index].offset)", value: extraBinding(index, \.offset), in: -100...100)
            } else if indicatorTab == "Style" {
                ColorPicker("Line color", selection: extraColor(index), supportsOpacity: false)
                Stepper("Line width: \(extraEMAs[index].width)", value: extraBinding(index, \.width), in: 1...4)
                Picker("Line style", selection: extraBinding(index, \.style)) { Text("Solid").tag(0); Text("Dotted").tag(1); Text("Dashed").tag(2) }
                Toggle("Stepped line", isOn: extraBinding(index, \.stepped))
            } else { Toggle("Show EMA \(index + 2)", isOn: extraBinding(index, \.enabled)) }
        }
    }
    private var requestedEMAFrames: [Int] {
        guard indicatorVisible else { return [] }
        var frames = extraEMAs.filter { $0.enabled }.map { $0.timeframe }
        if showEMA { frames.append(emaFrame) }
        if session == "rth" && pvSettings.enabled && !pvSettings.baseChart { frames += pvSettings.rows.filter { $0.enabled }.map { $0.frame } }
        return Array(Set(frames.filter { $0 > 0 && $0 != interval })).sorted()
    }
    private var emaCacheKey: String { "ema-history-\(cacheKey)-" + requestedEMAFrames.map(String.init).joined(separator: ",") }
    private var emaRequestKey: String { context + requestedEMAFrames.map(String.init).joined(separator: ",") }
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
    @AppStorage("chartIndicatorTemplatesV1") private var indicatorTemplatesJSON = "[]"
    @State private var templateName = ""
    @State private var namingTemplate = false
    @State private var replacingTemplate = false
    private var indicatorTemplates: [IndicatorTemplate] {
        guard let data = indicatorTemplatesJSON.data(using: .utf8),
              let rows = try? JSONDecoder().decode([IndicatorTemplate].self, from: data) else { return [] }
        return rows
    }
    private var indicatorSnapshot: IndicatorSettingsSnapshot {
        IndicatorSettingsSnapshot(fvg: fvgSettings, previousValues: pvSettings, showEMA: showEMA, emaLength: emaLength, emaSource: emaSource, emaOffset: emaOffset, emaFrame: emaFrame, emaDynamic: emaDynamic, emaColor: emaColor, emaWidth: emaWidth, emaStyle: emaStyle, extraEMAJSON: extraEMAJSON, showATR: showATR, atrLength: atrLength, showBarCount: showBarCount, barCountFrame: barCountFrame, barCountSize: barCountSize, barCountColor: barCountColor, barCountOpacity: barCountOpacity, barCountLimit: barCountLimit, barCountBars: barCountBars, indicatorVisible: indicatorVisible)
    }
    private func saveIndicatorTemplates(_ rows: [IndicatorTemplate]) {
        if let data = try? JSONEncoder().encode(rows), let text = String(data: data, encoding: .utf8) {
            indicatorTemplatesJSON = text
        }
    }
    private func applyIndicatorTemplate(_ settings: IndicatorSettingsSnapshot) {
        saveFVG(settings.fvg ?? FVGSettings())
        savePV(settings.previousValues ?? PreviousValuesSettings())
        showEMA = settings.showEMA
        emaLength = settings.emaLength
        emaSource = settings.emaSource
        emaOffset = settings.emaOffset
        emaFrame = settings.emaFrame
        emaDynamic = settings.emaDynamic
        emaColor = settings.emaColor
        emaWidth = settings.emaWidth
        emaStyle = settings.emaStyle
        extraEMAJSON = settings.extraEMAJSON
        showATR = settings.showATR
        atrLength = settings.atrLength
        showBarCount = settings.showBarCount
        barCountFrame = settings.barCountFrame
        barCountSize = settings.barCountSize
        barCountColor = settings.barCountColor
        barCountOpacity = settings.barCountOpacity
        barCountLimit = settings.barCountLimit
        barCountBars = settings.barCountBars
        indicatorVisible = settings.indicatorVisible
    }
    private var cleanTemplateName: String { templateName.trimmingCharacters(in: .whitespacesAndNewlines) }
    private var canSaveIndicatorTemplate: Bool {
        !cleanTemplateName.isEmpty && cleanTemplateName.count <= 40
    }
    private func storeNamedIndicatorTemplate() {
        guard canSaveIndicatorTemplate else { return }
        var rows = indicatorTemplates
        if let index = rows.firstIndex(where: { $0.name.caseInsensitiveCompare(cleanTemplateName) == .orderedSame }) {
            rows[index].settings = indicatorSnapshot
        } else {
            rows.append(IndicatorTemplate(name: cleanTemplateName, settings: indicatorSnapshot))
        }
        saveIndicatorTemplates(rows)
        namingTemplate = false
    }
    private var saveIndicatorTemplateSheet: some View {
        NavigationStack {
            Form {
                Section("Template name") {
                    HStack {
                        TextField("New template name", text: $templateName)
                            .autocorrectionDisabled().submitLabel(.done)
                        if !indicatorTemplates.isEmpty {
                            Menu {
                                ForEach(indicatorTemplates) { item in
                                    Button(item.name) { templateName = item.name }
                                }
                            } label: { Image(systemName: "chevron.down") }
                            .accessibilityLabel("Choose existing template")
                        }
                    }
                }
            }
            .navigationTitle("Save indicator template")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { namingTemplate = false } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        if indicatorTemplates.contains(where: { $0.name.caseInsensitiveCompare(cleanTemplateName) == .orderedSame }) {
                            replacingTemplate = true
                        } else { storeNamedIndicatorTemplate() }
                    }.disabled(!canSaveIndicatorTemplate)
                }
            }
            .alert("Replace template?", isPresented: $replacingTemplate) {
                Button("Cancel", role: .cancel) {}
                Button("Replace") { storeNamedIndicatorTemplate() }
            } message: { Text("Replace the saved settings for \(cleanTemplateName)?") }
        }.presentationDetents([.medium, .large])
    }
    private func applyDefaultIndicatorTemplate() {
        saveFVG(FVGSettings())
        savePV(PreviousValuesSettings())
                        emaFrame = 0; extraEMAJSON = ""
                        showBarCount = session == "rth"; barCountFrame = 1440; barCountSize = "tiny"; barCountColor = "#521c6e"; barCountOpacity = 66; barCountLimit = true; barCountBars = 162
                        indicatorVisible = true; showEMA = true; emaLength = 20; emaSource = "close"; emaOffset = 0
                        emaDynamic = true; emaColor = "#f9f1db"; emaWidth = 1; emaStyle = 0
                        showATR = true; atrLength = 4

    }
    private var indicatorTemplateSection: some View {
        Section("Indicator templates") {
            Button("Save Indicator Template As…") { templateName = ""; namingTemplate = true }
            Button("Apply Default Indicator Template") { applyDefaultIndicatorTemplate() }
            ForEach(indicatorTemplates) { item in
                HStack {
                    Button { applyIndicatorTemplate(item.settings) } label: {
                        HStack {
                            Text(verbatim: item.name)
                            Spacer()
                            if item.settings == indicatorSnapshot { Image(systemName: "checkmark") }
                        }.contentShape(Rectangle())
                    }.buttonStyle(.plain)
                    Menu {
                        Button("Update with current settings") {
                            templateName = item.name
                            namingTemplate = true
                        }
                        Button("Delete", role: .destructive) {
                            saveIndicatorTemplates(indicatorTemplates.filter { $0.id != item.id })
                        }
                    } label: { Image(systemName: "ellipsis.circle").padding(.leading, 8) }
                    .accessibilityLabel(Text("Template actions: \(item.name)"))
                }
            }
        }
    }
    @AppStorage("chartFVGSettingsV1") private var fvgJSON = ""
    private var fvgSettings: FVGSettings {
        (try? JSONDecoder().decode(FVGSettings.self, from: Data(fvgJSON.utf8))) ?? FVGSettings()
    }
    private func saveFVG(_ value: FVGSettings) {
        var checked = value
        checked.atrFactor = value.atrFactor.isFinite ? max(0, value.atrFactor) : 0.05
        if let data = try? JSONEncoder().encode(checked) { fvgJSON = String(decoding: data, as: UTF8.self) }
    }
    private func fvgBinding<T>(_ path: WritableKeyPath<FVGSettings, T>) -> Binding<T> {
        Binding(get: { fvgSettings[keyPath: path] }, set: { value in
            var settings = fvgSettings; settings[keyPath: path] = value; saveFVG(settings)
        })
    }
    private func fvgColor(_ path: WritableKeyPath<FVGSettings, String>) -> Binding<Color> {
        Binding(get: { CustomPalette.color(fvgSettings[keyPath: path]) ?? .orange }, set: { color in
            var r: CGFloat = 0, g: CGFloat = 0, b: CGFloat = 0, a: CGFloat = 0
            UIColor(color).getRed(&r, green: &g, blue: &b, alpha: &a)
            fvgBinding(path).wrappedValue = String(format: "#%02X%02X%02X", Int(r*255), Int(g*255), Int(b*255))
        })
    }
    private var fvgDisplay: [String: Any] {
        var result = (try? JSONSerialization.jsonObject(with: JSONEncoder().encode(fvgSettings))) as? [String: Any] ?? [:]
        result["enabled"] = fvgSettings.enabled && indicatorVisible
        return result
    }
    @ViewBuilder private var fvgSection: some View {
        Section("FVG") {
            if indicatorTab == "Inputs" {
                Toggle("Confirmed Close Only", isOn: fvgBinding(\.confirmed))
                Toggle("Show Open Portion Only", isOn: fvgBinding(\.shrink))
                Stepper("Max FVGs: \(fvgSettings.maxCount)", value: fvgBinding(\.maxCount), in: 1...50)
                Stepper("Min Gap Ticks: \(fvgSettings.minTicks)", value: fvgBinding(\.minTicks), in: 0...100)
                HStack { Text("Min Gap ATR Factor"); TextField("0.05", value: fvgBinding(\.atrFactor), format: .number).keyboardType(.decimalPad).multilineTextAlignment(.trailing) }
            } else if indicatorTab == "Style" {
                ColorPicker("Bullish FVG", selection: fvgColor(\.bullColor), supportsOpacity: false)
                Slider(value: fvgBinding(\.bullOpacity), in: 0...100, step: 1) { Text("Bullish opacity") }
                ColorPicker("Bearish FVG", selection: fvgColor(\.bearColor), supportsOpacity: false)
                Slider(value: fvgBinding(\.bearOpacity), in: 0...100, step: 1) { Text("Bearish opacity") }
            } else { Toggle("Show Unfilled FVG", isOn: fvgBinding(\.enabled)) }
        }
    }
    @AppStorage("chartPreviousValuesV1") private var pvJSON = ""
    private var pvSettings: PreviousValuesSettings {
        guard let value = try? JSONDecoder().decode(PreviousValuesSettings.self, from: Data(pvJSON.utf8)), value.rows.count == 3 else { return PreviousValuesSettings() }
        return value
    }
    private func savePV(_ settings: PreviousValuesSettings) {
        if let data = try? JSONEncoder().encode(settings) { pvJSON = String(decoding: data, as: UTF8.self) }
    }
    private func pvBinding<T>(_ path: WritableKeyPath<PreviousValuesSettings,T>) -> Binding<T> {
        Binding(get: { pvSettings[keyPath: path] }, set: { v in var s = pvSettings; s[keyPath: path] = v; savePV(s) })
    }
    private func pvRowBinding<T>(_ i: Int, _ path: WritableKeyPath<PreviousValueRow,T>) -> Binding<T> {
        Binding(get: { pvSettings.rows[i][keyPath: path] }, set: { v in var s = pvSettings; s.rows[i][keyPath: path] = v; savePV(s) })
    }
    private func pvColor(_ i: Int) -> Binding<Color> {
        Binding(get: { CustomPalette.color(pvSettings.rows[i].color) ?? .gray }, set: { c in
            var r: CGFloat = 0, g: CGFloat = 0, b: CGFloat = 0, a: CGFloat = 0
            UIColor(c).getRed(&r, green: &g, blue: &b, alpha: &a)
            pvRowBinding(i, \.color).wrappedValue = String(format: "#%02X%02X%02X", Int(r*255), Int(g*255), Int(b*255))
        })
    }
    private var pvDisplay: [String: Any] {
        var value = (try? JSONSerialization.jsonObject(with: JSONEncoder().encode(pvSettings))) as? [String: Any] ?? [:]
        value["enabled"] = session == "rth" && pvSettings.enabled && indicatorVisible
        return value
    }
    private var pvSection: some View {
        Section("Previous Values") {
            if indicatorTab == "Inputs" {
                Picker("Display", selection: pvBinding(\.display)) { ForEach(["Today","TimeFrame","All"], id: \.self) { Text($0).tag($0) } }
                Toggle("Base On Chart", isOn: pvBinding(\.baseChart))
                Toggle("Draw By Line", isOn: pvBinding(\.lineDraw))
            } else if indicatorTab == "Visibility" { Toggle("Previous Values", isOn: pvBinding(\.enabled)) }
            ForEach(0..<3, id: \.self) { i in
                if indicatorTab == "Inputs" {
                    Picker("Timeframe \(i+1)", selection: pvRowBinding(i, \.frame)) {
                        ForEach(emaIntervals.filter { $0 > 0 }, id: \.self) { Text(intervalLabel($0)).tag($0) }
                    }
                    Picker("Source \(i+1)", selection: pvRowBinding(i, \.source)) {
                        ForEach(["close","high","low","open","hl/2","hlc3","ohlc/4","hlcc/4","CurrentOpen"], id: \.self) { Text($0).tag($0) }
                    }
                } else if indicatorTab == "Style" {
                    ColorPicker("Color \(i+1)", selection: pvColor(i), supportsOpacity: false)
                    Picker("Line style \(i+1)", selection: pvRowBinding(i, \.style)) {
                        ForEach(["solid","dotted","dashed","arrow_left","arrow_right","arrow_both"], id: \.self) { Text($0).tag($0) }
                    }
                    Stepper("Width \(i+1): \(pvSettings.rows[i].width)", value: pvRowBinding(i, \.width), in: 1...4)
                } else { Toggle("Level \(i+1)", isOn: pvRowBinding(i, \.enabled)) }
            }
        }
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
                        Picker("Timeframe", selection: $emaFrame) { frameChoices() }
                    }
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
                Section("Bar Count") {
                    if indicatorTab == "Inputs" {
                        Picker("Reset timeframe", selection: $barCountFrame) {
                            Text("1 hour").tag(60); Text("1 day").tag(1440); Text("1 week").tag(10080); Text("1 month").tag(43200)
                        }
                        Toggle("Limit rendering range", isOn: $barCountLimit)
                        ChartBarCountInput(value: $barCountBars).disabled(!barCountLimit)
                        Text("Every third bar, plus the reference indicator’s highlighted counts.").font(.caption).foregroundStyle(.secondary)
                    } else if indicatorTab == "Style" {
                        Picker("Label size", selection: $barCountSize) {
                            ForEach(["auto", "tiny", "small", "normal", "large", "huge"], id: \.self) { Text($0.capitalized).tag($0) }
                        }
                        ColorPicker("Label color", selection: barCountColorBinding, supportsOpacity: false)
                        HStack { Text("Opacity"); Spacer(); Text((barCountOpacity / 100).formatted(.percent.precision(.fractionLength(0)))).monospacedDigit() }
                        Slider(value: $barCountOpacity, in: 0...100, step: 1)
                    } else { Toggle("Bar Count", isOn: Binding(get: { showBarCount }, set: { showBarCount = $0 })) }
                }
                extraEMASection(0)
                extraEMASection(1)
                pvSection
                fvgSection
                indicatorTemplateSection
                Section {
                    Text("Changes apply immediately and are saved.").font(.caption).foregroundStyle(.secondary)

                }
                // Keep ATR last; add future indicator sections above this trailing section.
                if indicatorTab == "Inputs" {
                    Section("ATR") { Stepper("Length: \(atrLength)", value: $atrLength, in: 1...200) }
                }
            }.navigationTitle("𝔹𝕖𝕟").navigationBarTitleDisplayMode(.inline)
                .toolbar { Button("Done") { showIndicatorSettings = false } }
                .sheet(isPresented: $namingTemplate) { saveIndicatorTemplateSheet }

        }
    }
    @State private var adjustmentAction = ""
    @State private var adjustmentQuantity = 1
    @State private var showAdjustment = false
    private var positionSize: Int { Int(abs(paperState["position"] as? Double ?? 0)) }
    private var adjustmentLimit: Int { adjustmentAction == "trim" ? min(max(0, positionSize - 1), (paperState["trim_available"] as? NSNumber)?.intValue ?? positionSize) : Int.max }
    @State private var showDisplaySettings = false
    private var chartDisplay: [String: Any] {
        ["previousValues": pvDisplay, "fvg": fvgDisplay, "holdingsVisible": showHoldings, "orderExtensionLines": showOrderExtensionLines, "barCount": showBarCount && indicatorVisible, "barCountFrame": barCountFrame, "barCountSize": barCountSize, "barCountColor": barCountColor, "barCountOpacity": barCountOpacity, "barCountLimit": barCountLimit, "barCountBars": barCountBars, "emaFrame": emaFrame, "extraEMAs": extraEMAs.map { ["enabled": $0.enabled && indicatorVisible, "timeframe": $0.timeframe, "length": $0.length, "source": $0.source, "offset": $0.offset, "color": $0.color + "ab", "width": $0.width, "style": $0.style, "stepped": $0.stepped] as [String: Any] }, "emaFrames": emaFrameContext == emaRequestKey ? emaFrames : [:], "indicatorCollapsed": indicatorCollapsed, "indicatorVisible": indicatorVisible, "ema": showEMA && indicatorVisible, "emaLength": emaLength, "emaSource": emaSource, "emaOffset": emaOffset,
         "emaDynamic": emaDynamic, "emaColor": emaColor + "ab", "emaWidth": emaWidth, "emaStyle": emaStyle,
         "atr": showATR && indicatorVisible, "atrLength": atrLength, "profit": showHoldings && showProfit, "positions": showHoldings && showPositionProfit, "brackets": showHoldings && showBracketProfit,
         "executions": showExecutions, "executionLabels": showExecutionLabels,
         "positionUnit": positionProfitUnit, "bracketUnit": bracketProfitUnit]
    }
    private var chartStatusText: String {
        let chinese = locale.language.languageCode?.identifier == "zh"
        let chartName: String
        switch chartType {
        case "OPT": chartName = chinese ? "期权图表" : "Option chart"
        case "FUT": chartName = chinese ? "期货图表" : "Futures chart"
        default: chartName = chinese ? "股票图表" : "Stock chart"
        }
        if !paperStatusText.isEmpty {
            return chartName + " · " + localizedNotice(paperStatusText, locale: locale)
        }
        let state = paperEnabled ? (chinese ? "交易" : "Trading") : (chinese ? "查看" : "View")
        return localizedLabel(store.accountModeLabel, locale: locale) + " · " + chartName + " · " + state
    }
    private var paperStatusText: String {
        let rows = paperState["orders"] as? [[String: Any]] ?? []
        if paperBusy { return pendingActionLabel }
        if store.trading.paperPending(base: store.address, conID: chartID ?? 0) { return "Confirming this order with IB…" }
        if paperState["sync_error"] as? Bool == true { return "Order updates paused · verify Gateway" }
        if paperState["known"] as? Bool == false { return "Order status unknown · verify Gateway" }
        if hasOrderPreview { return "\(store.accountModeLabel) · Preview · \(previewTIF == "OVERNIGHT" ? "OVT" : previewTIF)" }
        if paperState["rejected"] as? Bool == true { return "Order rejected · verify Gateway" }
        if let progress = paperState["adjustment"] as? [String: Any] {
            return "\(localizedLabel("Paper", locale: locale)) · \(localizedLabel(progress["action"] as? String ?? "close", locale: locale)) · \(localizedLabel(progress["status"] as? String ?? "unknown", locale: locale))"
        }
        if paperState["closing"] as? Bool == true { return "Paper · Closing position · \(paperState["close_status"] as? String ?? "Pending")" }
        if let size = paperState["position"] as? Double, size != 0 { return "Paper · \(size > 0 ? "Long" : "Short") \(abs(size).formatted()) filled" }
        if paperState["status"] as? String == "done" {
            let exit = rows.first { ["tp", "sl", "close"].contains($0["role"] as? String ?? "") && ($0["filled"] as? Double ?? 0) > 0 }
            return exit.map { "Paper · \(($0["role"] as? String ?? "").uppercased()) filled · Flat" } ?? "Paper · Orders finished · Flat"
        }
        if let row = rows.first(where: { $0["role"] as? String == "entry" }) { return "Paper · \(row["status"] as? String ?? "Unknown") · Filled \((row["filled"] as? Double ?? 0).formatted())" }
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
            (protectionOption(templateType, tp ? "tp" : "sl") == "off") || Double(distanceBinding(templateType, tp: tp).wrappedValue).map { $0.isFinite && $0 > 0 } ?? false
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
    private var validQuantity: Double { Double(quantity).flatMap { $0.isFinite && $0 > 0 && $0 <= 1_000_000 && (chartType == "STK" || $0.rounded(.towardZero) == $0) ? $0 : nil } ?? 0 }
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
    private var distancePresets: [String] {
        switch templateType {
        case "OPT": return ["0.05", "0.1", "0.2", "0.3", "0.5", "1", "2", "3", "5", "10"]
        case "FUT": return ["5", "10", "20", "30", "50", "75", "100", "150", "200", "300", "500"]
        default: return ["1", "2", "3", "5", "10", "15", "20", "30", "50", "75", "100"]
        }
    }
    private func distanceRow(_ title: String, value: Binding<String>) -> some View {
        HStack {
            Text(title)
            Spacer()
            TextField(title, text: value).keyboardType(.decimalPad)
                .multilineTextAlignment(.trailing).frame(width: 80)
            Menu {
                ForEach(distancePresets, id: \.self) { distance in
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
            HStack(spacing: 4) {
                Button { showSymbols = true } label: { Image(systemName: "magnifyingglass").frame(width: 30, height: 40) }.buttonStyle(.plain).accessibilityLabel("Search chart symbol")
                GeometryReader { geometry in
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 2) {
                        ForEach(intervals.filter { favorites.contains($0) }, id: \.self) { value in
                            Button { interval = value } label: {
                                Text(intervalLabel(value))
                                    .font(.system(size: 13, weight: interval == value ? .semibold : .regular))
                                    .fixedSize().padding(.horizontal, 9)
                                    .frame(minWidth: max(0, (geometry.size.width - 8) / CGFloat(max(1, min(5, favorites.count)))), minHeight: 40)
                                    .background(interval == value ? Color.secondary.opacity(0.25) : .clear, in: RoundedRectangle(cornerRadius: 6))
                            }.buttonStyle(.plain)
                                .accessibilityAddTraits(interval == value ? .isSelected : [])
                        }
                    }
                }
                }.frame(height: 44)
                Button { showIntervals = true } label: {
                    Image(systemName: "chevron.down").font(.caption).frame(width: 24, height: 44)
                }.buttonStyle(.plain).accessibilityLabel("Timeframe").accessibilityValue(intervalLabel(interval))
                Picker("Session", selection: $session) {
                    Text("RTH").tag("rth"); Text("ETH").tag("all")
                }.fixedSize()
                Button { fullScreen.toggle() } label: {
                    Image(systemName: fullScreen ? "arrow.down.right.and.arrow.up.left" : "viewfinder")
                        .frame(width: 36, height: 44)
                }.buttonStyle(.plain).accessibilityLabel(fullScreen ? "Exit full screen" : "Full screen")
            }
            if !fullScreen {
            TimelineView(.periodic(from: .now, by: 1)) { time in
                Text(verbatim: localizedNotice(received.map { time.date.timeIntervalSince($0) > 3 } == true ? "Chart updates paused · verify connection" : notice, locale: locale))
                    .font(.caption).foregroundStyle(.secondary).frame(maxWidth: .infinity, alignment: .leading)
            }
            }
            if let emaHistoryNotice { Text(verbatim: emaHistoryNotice).font(.caption2).foregroundStyle(.secondary) }
            StockChartWeb(executions: executionCID == chartID ? accountExecutions : [], holdings: ChartHoldingOverlay.rows(positions: store.portfolio?.positions ?? [], conID: chartID, symbol: selectedContract["symbol"] as? String ?? position.symbol, type: chartType, chinese: locale.language.languageCode?.identifier == "zh"), display: chartDisplay, drawingKey: "\(store.address)-\(chartID ?? 0)", packet: packet, entry: validEntry, quantity: validQuantity, dark: colors == .dark, entryType: entryType, joinSide: joinSide, joinRevision: joinRevision, beRevision: beRevision, tpDistance: Double(tpDistance) ?? 0, slDistance: Double(slDistance) ?? 0, tpEnabled: protectionOption(chartType, "tp") != "off", slEnabled: protectionOption(chartType, "sl") != "off", tpMode: protectionOption(chartType, "mode") ?? "distance", templateRevision: templateRevision, onBE: { beApplied = $0 }, onEntry: { entry = String($0) }, paperState: paperState.merging(["enabled": paperEnabled, "busy": paperBusy, "chart_only": false, "submit_revision": submitRevision, "preview_tif": previewTIF]) { _, new in new }, conID: chartID ?? 0, onPaper: paperAction)
                .clipShape(RoundedRectangle(cornerRadius: 12))
            HStack(spacing: 8) {
                Button { showDisplaySettings = true } label: {
                    Image(systemName: "gearshape").frame(width: 36, height: 32)
                }.buttonStyle(.plain).accessibilityLabel("Chart display")
                Text(verbatim: chartStatusText)
                    .font(.caption).foregroundStyle(paperEnabled ? .orange : .secondary)
                    .multilineTextAlignment(.center).fixedSize(horizontal: false, vertical: true).frame(maxWidth: .infinity)
                if !fullScreen {
                    Button { tradingPanelCollapsed.toggle() } label: {
                        Image(systemName: tradingPanelCollapsed ? "chevron.up" : "chevron.down")
                            .font(.system(size: 12, weight: .medium))
                            .frame(width: 24, height: 18)
                            .overlay(RoundedRectangle(cornerRadius: 3).stroke(.secondary.opacity(0.5), lineWidth: 1))
                            .frame(width: 36, height: 32).contentShape(Rectangle())
                    }.buttonStyle(.plain)
                        .accessibilityLabel(tradingPanelCollapsed ? "Show trading controls" : "Hide trading controls")
                } else {
                    Color.clear.frame(width: 36, height: 32).accessibilityHidden(true)
                }
            }
            if !hasOrderPreview { ChartOrderProgressView(state: paperState) }
            if positionSize > 0 {
                Button("Manage TP / SL") {
                    positionProtectionState = paperState; positionProtectionCID = chartID; showPositionProtection = true
                }.disabled(!paperEnabled || paperBusy || paperState["protection_manageable"] as? Bool != true)
                if let reason = paperState["protection_block_reason"] as? String, !reason.isEmpty { Text(reason).font(.caption).foregroundStyle(.secondary) }
            }
            if let paperMessage, !paperMessage.isEmpty { NoticeText(paperMessage).font(.caption).foregroundStyle(.secondary) }
            if !fullScreen && !tradingPanelCollapsed {
            HStack(spacing: 8) {
                TextField(chartType == "STK" ? "Shares" : "Contracts", text: $quantity).keyboardType(chartType == "STK" ? .decimalPad : .numberPad)
                    .multilineTextAlignment(.center).textFieldStyle(.roundedBorder).frame(width: 48)
                Stepper(chartType == "STK" ? "Shares" : "Contracts", value: Binding(get: { max(1, Int(validQuantity)) }, set: { quantity = String($0) }), in: 1...1_000_000).labelsHidden()
                Spacer(minLength: 0)
                if validEntry == 0 {
                    Button { entry = String(((packet["bars"] as? [[String: Any]])?.last?["close"] as? Double) ?? position.market_price ?? 0) } label: { Image(systemName: "plus.circle").frame(minWidth: 32, minHeight: 44) }.accessibilityLabel("Entry reference")
                }
                Picker("Entry type", selection: $entryType) {
                    Text("LMT").tag("LMT"); Text("STP").tag("STP").disabled(previewTIF == "OVERNIGHT" || paperState["tif"] as? String == "OVERNIGHT")
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
                    ChartPositionActionsLayout {
                        Menu {
                            Button("Add contracts") { adjustmentAction = "add"; adjustmentQuantity = 1; showAdjustment = true }
                            Button("Trim contracts") { adjustmentAction = "trim"; adjustmentQuantity = 1; showAdjustment = true }.disabled(positionSize < 2 || ((paperState["trim_available"] as? NSNumber)?.intValue ?? positionSize) < 1)
                        } label: { Image(systemName: "plus.forwardslash.minus").frame(minWidth: 0, maxWidth: .infinity, minHeight: 30) }.accessibilityLabel("Add or trim contracts").disabled(!paperEnabled || paperBusy || positionSize == 0 || paperState["known"] as? Bool != true || paperState["scalable"] as? Bool != true)
                        Button { if paperEnabled { paperAction(["action": "close"]) } else if validEntry > 0 { entry = "0" } else { showClosePreview = true } } label: { Text("Close Position").font(.system(size: 14, weight: .semibold)).lineLimit(1).minimumScaleFactor(0.65).frame(minWidth: 0, maxWidth: .infinity, minHeight: 30) }.tint(.orange).disabled(paperBusy || paperState["position_only"] as? Bool == true || paperState["closing"] as? Bool == true || (paperEnabled ? !paperActive : validEntry <= 0))
                        Button { if paperEnabled { paperAction(["action": "be"]) } else { beRevision += 1 } } label: { Text("BE").frame(minWidth: 0, maxWidth: .infinity, minHeight: 30) }.tint(.purple).disabled(paperBusy || (paperEnabled && ((paperState["position"] as? Double ?? 0) == 0 || (paperState["sl"] as? Double ?? 0) <= 0)) || (!paperEnabled && protectionOption(chartType, "sl") == "off") || beApplied || validEntry <= 0 || (packet["price_rules"] as? [[String: Any]])?.isEmpty != false)
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
                    LazyVGrid(columns: Array(repeating: GridItem(.flexible()), count: 3)) { ForEach(["TSLA", "ES", "NQ", "NVDA", "MES", "MNQ"], id: \.self) { symbol in Button(symbol) { symbolQuery = symbol; Task { await searchSymbols() } }.buttonStyle(.bordered) } }
                    if searching { ProgressView() }
                    if let symbolError { Text(symbolError).foregroundStyle(.red) }
                    ForEach(symbolResults.indices, id: \.self) { index in
                        let result = symbolResults[index]
                        Button {
                            selectedContract = result; previewTIF = "DAY"; showQuantityEditor = false; entry = "0"; beApplied = false; paperState = [:]; paperMessage = nil
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
                    Group {
                        Section("Order settings") {
                            TextField("Price", text: $editPrice).keyboardType(.decimalPad)
                            Picker("Time in force", selection: $editTIF) {
                                Text("DAY").tag("DAY")
                                Text("GTC").tag("GTC")
                                if editAllowedTIFs.contains("OVERNIGHT") { Text("OVT").tag("OVERNIGHT") }
                            }
                            if removingProtection {
                                Text("OVT uses an overnight limit order without TP/SL. No TP/SL protection is attached to an OVT entry.").font(.caption).foregroundStyle(.orange)
                                Toggle("Confirm OVT without TP/SL", isOn: $confirmRemoveProtection)
                            } else if editingExistingOrder {
                                Text("Quantity or time-in-force changes cancel and replace the unfilled order. Queue priority resets.").font(.caption).foregroundStyle(.secondary)
                            }
                        }
                    }
                    Section("Quantity") {
                        TextField("Quantity", text: $quantityDraft).keyboardType(.numberPad)
                            .font(.title2).multilineTextAlignment(.center)
                        HStack {
                            Button { quantityDraft = String(max(1, (Int(quantityDraft) ?? 1) - 1)) } label: { Image(systemName: "minus").font(.system(size: 18, weight: .medium)).frame(width: 22, height: 22).frame(maxWidth: .infinity, minHeight: 36) }
                            Button { quantityDraft = String(min(quantityLimit, (Int(quantityDraft) ?? 0) + 1)) } label: { Image(systemName: "plus").font(.system(size: 18, weight: .medium)).frame(width: 22, height: 22).frame(maxWidth: .infinity, minHeight: 36) }
                        }.buttonStyle(.bordered)
                        LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())]) {
                            ForEach(chartType == "STK" ? [1, 5, 25, 100, 500, 1000] : [1, 2, 3, 5, 8, 10], id: \.self) { value in
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


                }.navigationTitle(editingExistingOrder ? "Edit order" : "Order settings").navigationBarTitleDisplayMode(.inline)
                    .toolbar {
                        ToolbarItem(placement: .cancellationAction) { Button("Cancel") { showQuantityEditor = false } }
                        ToolbarItem(placement: .confirmationAction) { Button("Apply") {
                            if let value = validQuantityDraft, !paperBusy {
                                if editingExistingOrder {
                                    guard entryEditable, !removingProtection || confirmRemoveProtection, let price = Double(editPrice), price.isFinite, price > 0 else { return }
                                    paperAction(["action": "edit_entry", "quantity": value, "price": price, "tif": editTIF, "expected_ref": editOrderRef, "expected_snapshot": editSnapshot, "confirm_remove_protection": confirmRemoveProtection])
                                } else {
                                    guard !paperActive, !removingProtection || confirmRemoveProtection else { return }
                                    quantity = String(value); previewTIF = editTIF
                                    if let price = Double(editPrice), price.isFinite, price > 0 { entry = String(price) }
                                }
                                showQuantityEditor = false
                            }
                        }.disabled(validQuantityDraft == nil || (Double(editPrice).map { !$0.isFinite || $0 <= 0 } ?? true) || (editingExistingOrder && (!entryEditable || paperState["order_ref"] as? String != editOrderRef)) || (!editingExistingOrder && paperActive) || (removingProtection && !confirmRemoveProtection) || paperBusy) }
                    }
            }.presentationDetents([.large])
        }
        .confirmationDialog(localizedLabel(protectionCancelRole.map { "Cancel " + $0.uppercased() + "?" } ?? "Cancel both TP and SL?", locale: locale), isPresented: Binding(get: { protectionCancelRef != nil }, set: { if !$0 { protectionCancelRef = nil } }), titleVisibility: .visible) {
            Button(localizedLabel(protectionCancelRole.map { "Remove " + $0.uppercased() + "; keep position" } ?? "Remove TP/SL; keep position", locale: locale), role: .destructive) {
                guard let ref = protectionCancelRef, protectionCancelCID == chartID, paperState["order_ref"] as? String == ref else { return }
                var request: [String: Any] = ["action": "cancel_protection", "expected_ref": ref, "confirm_remove_protection": true]
                if let role = protectionCancelRole { request["role"] = role }
                paperAction(request)
                protectionCancelRef = nil
            }
        } message: { Text(protectionCancelRole == "tp" ? "Only ordinary TP exits will be canceled. Trim / Close plans and SL remain." : "The selected exits will be canceled. Your position remains open. Check remaining orders after cancellation.") }
        .sheet(isPresented: $showAdjustment) {
            NavigationStack {
                Form {
                    Text("Current position: \(positionSize)")
                    TextField("Quantity", value: $adjustmentQuantity, format: .number.grouping(.never)).keyboardType(.numberPad)
                    Text("Futures use one protected bracket per contract. Add creates new brackets. Trim exits selected contracts at bid/ask while keeping every other bracket unchanged.").font(.caption)
                    Button(adjustmentAction == "trim" ? "Trim position" : "Add to position") {
                        showAdjustment = false
                        paperAction(["action": adjustmentAction, "quantity": adjustmentQuantity, "expected_ref": paperState["order_ref"] ?? ""])
                    }.disabled(paperBusy || adjustmentQuantity < 1 || adjustmentLimit < adjustmentQuantity)
                }.navigationTitle(adjustmentAction == "trim" ? "Trim" : "Add")
                    .toolbar { Button("Cancel") { showAdjustment = false } }
            }.presentationDetents([.medium])
        }
        .sheet(isPresented: $showIndicatorSettings) { indicatorSettings }
        .sheet(isPresented: $showDisplaySettings) {
            NavigationStack {
                Form {
                    Section("Positions") {
                        Toggle("Positions", isOn: $showHoldings)
                        Toggle("Order and TP/SL extension lines", isOn: $showOrderExtensionLines)
                    }
                    Section("Profit and loss value") {
                        Toggle("Show P&L", isOn: Binding(get: { showHoldings && showProfit }, set: { showProfit = $0 }))
                        Toggle("Position P&L", isOn: Binding(get: { showHoldings && showProfit && showPositionProfit }, set: { showPositionProfit = $0 })).disabled(!showProfit || !showHoldings)
                        Picker("Position P&L unit", selection: $positionProfitUnit) {
                            Text("Money").tag("money"); Text("Percent").tag("percent"); Text("Ticks").tag("ticks")
                        }.disabled(!showProfit || !showHoldings || !showPositionProfit)
                        Toggle("Brackets", isOn: Binding(get: { showHoldings && showProfit && showBracketProfit }, set: { showBracketProfit = $0 })).disabled(!showProfit)
                        Picker("Bracket P&L unit", selection: $bracketProfitUnit) {
                            Text("Money").tag("money"); Text("Ticks").tag("ticks")
                        }.disabled(!showProfit || !showBracketProfit)
                    }
                    .disabled(!showHoldings)
                    Section("Executions") {
                        Toggle("Execution marks", isOn: $showExecutions)
                        Toggle("Execution labels", isOn: $showExecutionLabels).disabled(!showExecutions)
                    }
                }.navigationTitle("Chart display").toolbar { Button("Done") { showDisplaySettings = false } }
            }.presentationDetents([.medium, .large])
        }
        .sheet(isPresented: $showPositionProtection) {
            PositionProtectionEditor(state: positionProtectionState, rules: packet["price_rules"] as? [[String: Any]] ?? []) { request in
                guard positionProtectionCID == chartID, positionProtectionState["order_ref"] as? String == paperState["order_ref"] as? String else { paperMessage = "Order changed; reopen TP / SL"; return }
                showPositionProtection = false; paperAction(request)
            }
        }
        .sheet(isPresented: $showTemplate) {
            NavigationStack {
                Form {
                    Picker("Asset class", selection: $templateType) {
                        Text("Stocks").tag("STK")
                        Text("Options").tag("OPT")
                        Text("Futures").tag("FUT")
                    }.pickerStyle(.segmented)
                    Section("Optional TP / SL · GTC") {
                        Text(verbatim: locale.language.languageCode?.identifier == "zh" ? "新订单默认设置，不会修改当前持仓。当前保护请用管理 TP / SL。" : "Defaults for new orders. Existing positions are unchanged; use Manage TP / SL for current protection.").font(.caption).foregroundStyle(.secondary)
                        Toggle("Enable TP", isOn: protectionToggle(templateType, "tp"))
                        if protectionToggle(templateType, "tp").wrappedValue {
                            Picker("TP input", selection: protectionMode(templateType)) {
                                Text("Distance").tag("distance"); Text("Target price").tag("price"); Text("Profit %").tag("percent")
                            }
                            distanceRow("TP", value: distanceBinding(templateType, tp: true))
                        }
                        Toggle("Enable SL", isOn: protectionToggle(templateType, "sl"))
                        if protectionToggle(templateType, "sl").wrappedValue { distanceRow("SL distance", value: distanceBinding(templateType, tp: false)) }
                        Text("Profit % uses the entry premium before fees. A short option sold at 2.12 with 75% profit targets 0.53, rounded to the contract tick.").font(.caption)
                    }
                    if validEntry > 0 && templateType == chartType && !paperActive {
                        Text("Apply updates the current preview and saves these distances for new orders.")
                        Button("Apply to preview") { templateRevision += 1; showTemplate = false }.disabled(!validTemplate)
                    } else {
                        Text(paperActive ? "These distances apply to your next order. Existing orders stay unchanged." : "These distances will be used for new orders in this asset class.")
                        Button("Save template") { showTemplate = false }.disabled(!validTemplate)
                    }
                    if !validTemplate { Text("Enter a positive value for each enabled exit.").font(.caption).foregroundStyle(.orange) }
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
                    Text(paperEnabled ? "IB Paper: Join Bid / Ask submits Entry and the enabled TP / SL exits. Dragging TP / SL sends an amendment on release. New futures brackets keep protection while Trim / Close sends a limit exit at bid / ask; a moving market may leave the exit working." : "TP / SL preview only · drag the labels. No orders are sent.")
                    Text("Prices and market-data permissions come from the connected IB account.")
                    Text("ETH includes available extended-hours data. Time: New York.")
                    Text("TradingView Lightweight Charts™ · Copyright © 2025 TradingView, Inc.")
                    Link("TradingView", destination: URL(string: "https://www.tradingview.com/")!)
                }.navigationTitle("Chart details")
                    .toolbar { Button("Done") { showInfo = false } }
            }.presentationDetents([.medium, .large])
        }
        .onAppear {
            if !barCountOpacityMigrated {
                if barCountColor.lowercased() == "#351044" { barCountColor = "#521c6e" }
                barCountOpacityMigrated = true
            }
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
            if !oneMinuteShortcutAdded {
                favoriteIntervals = intervals.filter { favorites.contains($0) || $0 == 1 }.map(String.init).joined(separator: ",")
                oneMinuteShortcutAdded = true
            }
            visible = true
            store.chartVisible = true
        }
        .onChange(of: cacheKey) { rememberChart() }
        .onDisappear { rememberChart(); visible = false; store.chartVisible = false }
        .task(id: "ema-" + emaRequestKey) {
            emaFrames = [:]; emaFrameContext = ""; emaHistoryNotice = nil
            guard visible, phase == .active, !store.demo, let cid = chartID else { return }
            let requestKey = emaRequestKey
            let historyKey = emaCacheKey
            if let cached = RecentStockCharts.load(historyKey)?.1["frames"] as? [String: Any] {
                emaFrames = cached; emaFrameContext = requestKey
                emaHistoryNotice = "EMA · Cached timeframe history; refreshing"
            }
            var retryDelay = 1.0
            let recoveryStarted = Date()
            while !Task.isCancelled {
                do {
                    let result = try await store.trading.get("api/portfolio/chart-ema/\(cid)", base: store.address, query: [URLQueryItem(name: "frames", value: requestedEMAFrames.map(String.init).joined(separator: ",")), URLQueryItem(name: "session", value: session)])
                    try Task.checkCancellation()
                    guard requestKey == emaRequestKey, result["con_id"] as? Int == cid else { return }
                    let incoming = result["frames"] as? [String: Any] ?? [:]
                    for (frame, value) in incoming {
                        if let bars = value as? [[String: Any]], !bars.isEmpty { emaFrames[frame] = bars }
                    }
                    emaFrameContext = requestKey
                    if incoming.values.contains(where: { ($0 as? [[String: Any]])?.isEmpty == false }) {
                        RecentStockCharts.save(["frames": emaFrames], key: historyKey)
                    }
                    retryDelay = requestedEMAFrames.allSatisfy { (incoming[String($0)] as? [[String: Any]])?.isEmpty == false } ? 10 : min(5, retryDelay * 2)
                    emaHistoryNotice = requestedEMAFrames.contains { (incoming[String($0)] as? [[String: Any]])?.isEmpty != false } ? "EMA · Waiting for fresh timeframe history" : nil
                } catch {
                    if Task.isCancelled { return }
                    retryDelay = min(30, max(2, retryDelay * 2))
                    if !requestedEMAFrames.isEmpty {
                        let cached = requestedEMAFrames.allSatisfy { (emaFrames[String($0)] as? [[String: Any]])?.isEmpty == false }
                        emaHistoryNotice = cached && Date().timeIntervalSince(recoveryStarted) < 15
                            ? "EMA · Cached timeframe history; refreshing"
                            : "EMA · Timeframe history unavailable; retrying"
                    }
                }
                do { try await Task.sleep(for: .seconds(retryDelay)) } catch { return }
            }
        }
        .task(id: "executions-" + context) {
            accountExecutions = []; executionCID = nil
            guard visible, phase == .active, !store.demo, let cid = chartID else { return }
            while !Task.isCancelled {
                do {
                    let result = try await store.trading.get("api/portfolio/chart-executions/\(cid)", base: store.address)
                    try Task.checkCancellation()
                    guard chartID == cid, result["con_id"] as? Int == cid else { return }
                    accountExecutions = result["executions"] as? [[String: Any]] ?? []
                    executionCID = cid
                } catch { if Task.isCancelled { return } }
                do { try await Task.sleep(for: .seconds(15)) } catch { return }
            }
        }
        .task(id: "paper-" + context + String(store.chartTradingAvailable)) {
            paperState = [:]; paperReceived = nil
            guard visible, phase == .active, store.chartTradingAvailable, let cid = chartID else { return }
            while !Task.isCancelled {
                do {
                    await store.trading.reconcilePaper(base: store.address, conID: cid)
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
            // Fetch a finite snapshot before opening a long-lived connection. Mobile
            // networks may delay or buffer SSE even while ordinary requests work.
            var snapshotLoaded = false
            var nextStreamAttempt = Date.distantPast
            let recoveryStarted = Date()
            while !Task.isCancelled {
                do {
                    if snapshotLoaded && Date() >= nextStreamAttempt && interval < 1440 && !(interval == 480 && session == "rth") {
                        do {
                            try await store.trading.chartStream(base: store.address, conID: conID, interval: interval, marketSession: session) { result in
                                guard !Task.isCancelled, context == requestContext, result["con_id"] as? Int == conID else { return }
                                packet = result; received = .now; packet["chart_received_at"] = Date().timeIntervalSince1970; failures = 0
                                RecentStockCharts.save(packet, key: requestCacheKey)
                                notice = chartType == "OPT" ? (result["data_notice"] as? String ?? "Historical option bars · waiting for updates") : (result["status"] as? String == "live" ? "IB Last ticks · live push" : "Historical bars · waiting for IB Last ticks")
                            }
                        } catch {
                            try Task.checkCancellation()
                            // Keep finite snapshots flowing instead of repeatedly waiting
                            // for the same broken stream. Never retry a trading write here.
                            nextStreamAttempt = Date().addingTimeInterval(30)
                        }
                    }
                    let result = try await store.trading.get("api/portfolio/stock-chart/\(conID)", base: store.address,
                        query: [URLQueryItem(name: "interval", value: String(interval)), URLQueryItem(name: "session", value: session)])
                    try Task.checkCancellation()
                    guard context == requestContext else { return }
                    guard result["con_id"] as? Int == conID, result["bars"] is [[String: Any]] else { throw AppError.message("Invalid chart response") }
                    if (result["bars"] as? [[String: Any]])?.isEmpty == true,
                       (packet["bars"] as? [[String: Any]])?.isEmpty == false {
                        throw AppError.message("Historical stock bars unavailable; retry shortly")
                    }
                    snapshotLoaded = true
                    packet = result; received = .now; packet["chart_received_at"] = Date().timeIntervalSince1970; failures = 0
                    RecentStockCharts.save(packet, key: requestCacheKey)
                    notice = chartType == "OPT" ? (result["data_notice"] as? String ?? "Historical option bars · waiting for updates") : (interval >= 1440 || (interval == 480 && session == "rth")) ? "IB historical bars · chart updates" : result["status"] as? String == "live" ? "IB Last ticks · display batches ≈250ms" : "Historical bars · waiting for IB Last ticks"
                } catch {
                    guard !Task.isCancelled else { return }
                    failures = min(failures + 1, 5)
                    let message = connectionMessage(error)
                    let transientHistory = message.contains("No historical trades returned") || message.contains("cooling down") || message.contains("Historical stock bars unavailable")
                    let hasCachedBars = (packet["bars"] as? [[String: Any]])?.isEmpty == false
                    notice = transientHistory && hasCachedBars && Date().timeIntervalSince(recoveryStarted) < 15
                        ? "Saved chart · refreshing history" : message
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
    var executions: [[String: Any]]
    var holdings: [[String: Any]]
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
    var tpEnabled: Bool = true
    var slEnabled: Bool = true
    var tpMode: String = "distance"
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
            let addJS = resource("chart-add-orders", "js").flatMap { try? String(contentsOf: $0, encoding: .utf8) } ?? ""
            let html = template.replacingOccurrences(of: "/*LIBRARY*/", with: js)
                .replacingOccurrences(of: "</body>", with: "<script>" + drawingJS + "</script><script>" + addJS + "</script></body>")
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
        context.coordinator.config = ["executions": executions, "holdings": holdings, "display": display, "entry": entry, "quantity": quantity, "dark": dark, "entryType": entryType, "joinSide": joinSide, "joinRevision": joinRevision, "beRevision": beRevision, "tpDistance": tpDistance.isFinite ? tpDistance : 0, "slDistance": slDistance.isFinite ? slDistance : 0, "tpEnabled": tpEnabled, "slEnabled": slEnabled, "tpMode": tpMode, "templateRevision": templateRevision, "priceRules": packet["price_rules"] ?? [], "paper": paperState, "con_id": conID, "multiplier": packet["multiplier"] ?? 1]
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
                // A queued WebKit message may arrive after the native chart has switched.
                // Persist against the originating chart, never the new selection.
                let sourceKey = value["key"] as? String ?? loadedDrawingKey
                guard !sourceKey.isEmpty else { return }
                UserDefaults.standard.set(data, forKey: "chartDrawings-" + sourceKey)
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
                    let restoringKey = drawingKey
                    bridgeBusy = true
                    web?.evaluateJavaScript("window.configureDrawings(\(json)); true") { [weak self] result, error in
                        guard let self else { return }
                        self.bridgeBusy = false
                        guard error == nil, result as? Bool == true else { return }
                        self.loadedDrawingKey = restoringKey
                        self.update()
                    }
                    return
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


private struct PositionProtectionEditor: View {
    let state: [String: Any]
    let rules: [[String: Any]]
    let apply: ([String: Any]) -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var tpEnabled = false
    @State private var slEnabled = false
    @State private var tp = ""
    @State private var sl = ""
    @State private var mode = "price"
    @State private var confirm = false
    private var targetTP: Double? {
        ChartProtectionMath.target(entry: state["entry"] as? Double ?? 0, side: state["side"] as? Double ?? 1, value: Double(tp), percent: mode == "percent", rules: rules)
    }
    private var valid: Bool {
        (!tpEnabled || targetTP != nil) && (!slEnabled || (Double(sl).map { $0.isFinite && $0 > 0 } ?? false))
    }
    var body: some View {
        NavigationStack {
            Form {
                Section("Optional TP / SL · GTC") {
                    Toggle("Enable TP", isOn: $tpEnabled)
                    if tpEnabled {
                        Picker("TP input", selection: $mode) { Text("Target price").tag("price"); Text("Profit %").tag("percent") }
                            .onChange(of: mode) { _, value in tp = value == "percent" ? "75" : String(state["tp"] as? Double ?? 0) }
                        TextField("TP", text: $tp).keyboardType(.decimalPad)
                        if let targetTP { Text("TP target: " + String(format: "%.4f", targetTP)).font(.caption) }
                    }
                    Toggle("Enable SL", isOn: $slEnabled)
                    if slEnabled { TextField("SL target price", text: $sl).keyboardType(.decimalPad) }
                }
                Section {
                    if state["position_only"] as? Bool == true {
                        Text("Add exits to the current position. Profit % uses the broker cost basis, which may include fees.").font(.caption)
                    } else {
                        Text("Existing exits will be canceled before replacement. Protection may be interrupted. A fill or uncertain response stops replacement; inspect the refreshed orders.").font(.caption)
                    }
                    Toggle(isOn: $confirm) {
                        if state["position_only"] as? Bool == true { Text("Confirm adding exits") }
                        else { Text("Confirm replacing protection") }
                    }
                    Button("Apply TP / SL") {
                        var request: [String: Any] = ["action": "set_protection", "expected_ref": state["order_ref"] ?? "", "expected_snapshot": state["edit_snapshot"] ?? [], "confirm_replace_protection": true]
                        if tpEnabled { request["tp"] = targetTP }
                        if slEnabled { request["sl"] = Double(sl) }
                        apply(request)
                    }.disabled(!valid || !confirm)
                    if state["position_only"] as? Bool != true {
                    Button("Cancel all TP / SL", role: .destructive) {
                        apply(["action": "cancel_protection", "expected_ref": state["order_ref"] ?? "", "confirm_remove_protection": true])
                    }.disabled(!confirm)
                    }
                }
            }.navigationTitle("Position TP / SL").toolbar { Button("Back") { dismiss() } }
        }.onAppear { tp = String(state["tp"] as? Double ?? 0); sl = String(state["sl"] as? Double ?? 0); tpEnabled = (state["tp"] as? Double ?? 0) > 0; slEnabled = (state["sl"] as? Double ?? 0) > 0; if state["position_only"] as? Bool == true { tpEnabled = true; mode = "percent"; tp = "75" } }
    }
}


enum ChartProtectionMath {
    static func target(entry: Double, side: Double, value: Double?, percent: Bool, rules: [[String: Any]]) -> Double? {
        guard let value, value.isFinite, value > 0 else { return nil }
        if !percent { return value }
        guard entry.isFinite, entry > 0, side == -1 || side == 1 else { return nil }
        let raw = entry * (1 + side * value / 100)
        guard raw.isFinite, raw > 0, let tick = rules.last(where: { ($0["low"] as? Double ?? 0) <= raw })?["increment"] as? Double, tick.isFinite, tick > 0 else { return nil }
        let result = (raw / tick).rounded() * tick
        return result.isFinite && result > 0 ? result : nil
    }
}
