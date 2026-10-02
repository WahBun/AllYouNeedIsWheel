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
        // Cache history only: never persist quote eligibility or transient stream state.
        var history = packet
        for field in ["bid", "ask", "quote_time", "quote_expires_at", "bar_closes_at", "sequence", "mode", "changed_bars"] { history.removeValue(forKey: field) }
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
    @AppStorage("chartTPDistance") private var tpDistance = "0.20"
    @AppStorage("chartSLDistance") private var slDistance = "0.10"
    @State private var showTemplate = false
    @State private var templateRevision = 1
    private var validTemplate: Bool { [tpDistance, slDistance].allSatisfy { Double($0).map { $0.isFinite && $0 > 0 } ?? false } }
    @State private var packet: [String: Any] = [:]
    @State private var notice = "Loading chart…"
    @State private var visible = false
    @State private var received: Date?
    private var cacheKey: String { "\(store.address)-\(position.con_id ?? 0)-\(interval)-\(session)" }
    private var context: String { "\(store.demo)-\(store.address)-\(position.con_id ?? 0)-\(interval)-\(session)-\(phase == .active)-\(visible)" }
    private var validEntry: Double { Double(entry).flatMap { $0.isFinite && $0 > 0 ? $0 : nil } ?? 0 }
    private var validQuantity: Double { Double(quantity).flatMap { $0.isFinite && $0 > 0 && $0 <= 1_000_000 ? $0 : nil } ?? 0 }
    private func joinPrice(_ side: String) -> Double? {
        guard let received, Date().timeIntervalSince(received) < 3,
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
            StockChartWeb(drawingKey: "\(store.address)-\(position.con_id ?? 0)", packet: packet, entry: validEntry, quantity: validQuantity, dark: colors == .dark, entryType: entryType, joinSide: joinSide, joinRevision: joinRevision, beRevision: beRevision, tpDistance: Double(tpDistance) ?? 0, slDistance: Double(slDistance) ?? 0, templateRevision: templateRevision, onBE: { beApplied = $0 }, onEntry: { entry = String($0) })
                .clipShape(RoundedRectangle(cornerRadius: 12))
            if !fullScreen {
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
                    Button { showTemplate = true } label: { Image(systemName: "slider.horizontal.3").frame(width: 28, height: 30) }.accessibilityLabel("TP / SL template")
                }
                VStack(spacing: 6) {
                    HStack(spacing: 8) {
                        Button { join("bid") } label: { Text("Join Bid").frame(maxWidth: .infinity, minHeight: 30) }.tint(.green).disabled(joinPrice("bid") == nil)
                        Button { join("ask") } label: { Text("Join Ask").frame(maxWidth: .infinity, minHeight: 30) }.tint(.red).disabled(joinPrice("ask") == nil)
                    }
                    HStack(spacing: 8) {
                        Button { if validEntry > 0 { entry = "0" } else { showClosePreview = true } } label: { Text("Close Position").frame(maxWidth: .infinity, minHeight: 30) }.tint(.orange).disabled(validEntry <= 0)
                        Button { beRevision += 1 } label: { Text("BE").frame(maxWidth: .infinity, minHeight: 30) }.tint(.purple).disabled(beApplied || validEntry <= 0 || (packet["price_rules"] as? [[String: Any]])?.isEmpty != false)
                    }
                }.font(.system(size: 13, weight: .semibold))
            }.buttonStyle(.bordered)
            }
        }.padding(.horizontal, 12).padding(.bottom, 8)
        .navigationTitle(position.symbol).navigationBarTitleDisplayMode(.inline)
        .toolbar(fullScreen ? .hidden : .visible, for: .navigationBar, .tabBar)
        .modifier(KeyboardDismissal())
        .alert("Close Position · Preview", isPresented: $showClosePreview) {
            Button("Done", role: .cancel) { }
        } message: {
            Text("This will close the current symbol when live chart trading is enabled. No order has been sent; your position is unchanged.")
        }
        .sheet(isPresented: $showTemplate) {
            NavigationStack {
                Form {
                    Section("Price distance") {
                        distanceRow("TP", value: $tpDistance)
                        distanceRow("SL", value: $slDistance)
                    }
                    Text("Distances are saved for new previews. Apply replaces the current preview levels; no broker order is changed.")
                    Button("Apply to preview") { templateRevision += 1; showTemplate = false }.disabled(!validTemplate || validEntry <= 0)
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
                    Text("TP / SL preview only · drag the labels. Estimated P&L excludes fees and slippage. No orders are sent.")
                    Text("LMT and STP select the preview entry type. Join Bid / Ask copies an available recent live quote once; it does not follow future quotes or submit an order.")
                    Text("ETH includes available extended-hours data. Time: New York.")
                    Text("TradingView Lightweight Charts™ · Copyright © 2025 TradingView, Inc.")
                    Link("TradingView", destination: URL(string: "https://www.tradingview.com/")!)
                }.navigationTitle("Chart details")
                    .toolbar { Button("Done") { showInfo = false } }
            }.presentationDetents([.medium, .large])
        }
        .onAppear {
            visible = true
            if entry.isEmpty { entry = String(position.market_price ?? 0) }
        }
        .onDisappear { visible = false }
        .task(id: context) {
            packet = [:]; received = nil; notice = "Loading chart…"
            guard visible, phase == .active else { return }
            guard !store.demo else { notice = "Chart pilot requires a connected held stock"; return }
            guard let conID = position.con_id, conID > 0 else { return }
            if let cached = RecentStockCharts.load(cacheKey) {
                packet = cached.1
                packet["bid"] = NSNull(); packet["ask"] = NSNull(); packet["bar_closes_at"] = NSNull()
                notice = "Saved chart · connecting to live data"
            }
            var failures = 0
            while !Task.isCancelled {
                do {
                    if interval < 1440 && !(interval == 480 && session == "rth") {
                        try await store.trading.chartStream(base: store.address, conID: conID, interval: interval, marketSession: session) { result in
                            packet = result; received = .now; failures = 0
                            RecentStockCharts.save(result, key: cacheKey)
                            notice = result["status"] as? String == "live" ? "IB Last ticks · live push" : "Historical bars · waiting for IB Last ticks"
                        }
                    }
                    let result = try await store.trading.get("api/portfolio/stock-chart/\(conID)", base: store.address,
                        query: [URLQueryItem(name: "interval", value: String(interval)), URLQueryItem(name: "session", value: session)])
                    try Task.checkCancellation()
                    guard result["con_id"] as? Int == conID, result["bars"] is [[String: Any]] else { throw AppError.message("Invalid chart response") }
                    packet = result; received = .now; failures = 0
                    RecentStockCharts.save(result, key: cacheKey)
                    notice = (interval >= 1440 || (interval == 480 && session == "rth")) ? "IB historical bars · chart updates" : result["status"] as? String == "live" ? "IB Last ticks · display batches ≈250ms" : "Historical bars · waiting for IB Last ticks"
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

private struct StockChartWeb: UIViewRepresentable {
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
    func makeCoordinator() -> Coordinator { Coordinator() }
    func makeUIView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        config.websiteDataStore = .nonPersistent()
        config.userContentController.add(context.coordinator, name: "drawingsChanged")
        config.userContentController.add(context.coordinator, name: "chartReady")
        config.userContentController.add(context.coordinator, name: "entryChanged")
        config.userContentController.add(context.coordinator, name: "beState")
        let web = WKWebView(frame: .zero, configuration: config)
        web.scrollView.isScrollEnabled = false
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
        context.coordinator.config = ["entry": entry, "quantity": quantity, "dark": dark, "entryType": entryType, "joinSide": joinSide, "joinRevision": joinRevision, "beRevision": beRevision, "tpDistance": tpDistance.isFinite ? tpDistance : 0, "slDistance": slDistance.isFinite ? slDistance : 0, "templateRevision": templateRevision, "priceRules": packet["price_rules"] ?? []]
        context.coordinator.update()
    }
    static func dismantleUIView(_ web: WKWebView, coordinator: Coordinator) {
        web.configuration.userContentController.removeScriptMessageHandler(forName: "drawingsChanged")
        web.configuration.userContentController.removeScriptMessageHandler(forName: "chartReady")
        web.configuration.userContentController.removeScriptMessageHandler(forName: "entryChanged")
        web.configuration.userContentController.removeScriptMessageHandler(forName: "beState")
        web.stopLoading(); web.loadHTMLString("", baseURL: nil)
    }
    class Coordinator: NSObject, WKScriptMessageHandler {
        weak var web: WKWebView?
        var ready = false
        var drawingKey = ""
        var loadedDrawingKey = ""
        var lastStreamSequence = 0
        var lastStreamKey = ""
        var packet: [String: Any] = [:]
        var config: [String: Any] = [:]
        var onEntry: ((Double) -> Void)?
        var onBE: ((Bool) -> Void)?
        func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
            if message.name == "drawingsChanged", let value = message.body as? [String: Any],
               let data = try? JSONSerialization.data(withJSONObject: value), data.count < 2_000_000 {
                UserDefaults.standard.set(data, forKey: "chartDrawings-" + drawingKey)
                if let favorites = value["favorites"] as? [String] { UserDefaults.standard.set(favorites, forKey: "chartDrawingFavorites") }
                if let order = value["order"] as? [String] { UserDefaults.standard.set(order, forKey: "chartDrawingOrder") }
                if let magnet = value["magnet"] as? String { UserDefaults.standard.set(magnet, forKey: "chartDrawingMagnet") }
                if let collapsed = value["collapsed"] as? Bool { UserDefaults.standard.set(collapsed, forKey: "chartDrawingCollapsed") }
            } else if message.name == "beState", let applied = message.body as? Bool { onBE?(applied)
            } else if message.name == "entryChanged", let price = message.body as? Double, price.isFinite, price >= 0 {
                onEntry?(price)
            } else if message.name == "chartReady" { ready = true; update() }
        }
        func update() {
            guard ready else { return }
            if drawingKey != loadedDrawingKey {
                var value: [String: Any] = [:]
                if let data = UserDefaults.standard.data(forKey: "chartDrawings-" + drawingKey),
                   let saved = try? JSONSerialization.jsonObject(with: data) as? [String: Any] { value = saved }
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
                let key = "\(packet["generation"] ?? "")-\(packet["interval"] ?? "")-\(packet["session"] ?? "")"
                if sequence == lastStreamSequence && key == lastStreamKey { outgoing = [:] }
                else {
                    if lastStreamKey == key && sequence == lastStreamSequence + 1 && packet["mode"] as? String == "delta" {
                        outgoing["bars"] = packet["changed_bars"] ?? []
                    } else { outgoing["mode"] = "snapshot" }
                    lastStreamKey = key; lastStreamSequence = sequence
                }
                outgoing.removeValue(forKey: "changed_bars")
            } else { lastStreamSequence = 0; lastStreamKey = "" }
            for (function, value) in [("configure", config), ("receive", outgoing)] {
                guard !value.isEmpty, let data = try? JSONSerialization.data(withJSONObject: value), let json = String(data: data, encoding: .utf8) else { continue }
                web?.evaluateJavaScript("window.\(function)(\(json))", completionHandler: nil)
            }
        }
    }
}
