import SwiftUI
import WebKit

struct StockChartView: View {
    let position: Position
    @Environment(WheelStore.self) private var store
    @Environment(\.scenePhase) private var phase
    @Environment(\.colorScheme) private var colors
    @State private var interval = 5
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
    @State private var packet: [String: Any] = [:]
    @State private var notice = "Loading chart…"
    @State private var visible = false
    @State private var received: Date?
    private var context: String { "\(store.demo)-\(store.address)-\(position.con_id ?? 0)-\(interval)-\(session)-\(phase == .active)-\(visible)" }
    private var validEntry: Double { Double(entry).flatMap { $0.isFinite && $0 > 0 ? $0 : nil } ?? 0 }
    private var validQuantity: Double { Double(quantity).flatMap { $0.isFinite && $0 > 0 && $0 <= 1_000_000 ? $0 : nil } ?? 0 }
    private func joinPrice(_ side: String) -> Double? {
        guard let received, Date().timeIntervalSince(received) < 3,
              let stamp = packet["quote_time"] as? Double, Date().timeIntervalSince1970 - stamp < 3,
              let price = packet[side] as? Double, price.isFinite, price > 0 else { return nil }
        return price
    }
    private func join(_ side: String) {
        guard let price = joinPrice(side) else { return }
        entryType = "LMT"; entry = String(format: "%.2f", price)
        joinSide = side == "bid" ? 1 : -1; joinRevision += 1
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
            }
            TimelineView(.periodic(from: .now, by: 1)) { time in
                Text(received.map { time.date.timeIntervalSince($0) > 3 } == true ? "Chart updates paused · verify connection" : LocalizedStringKey(notice))
                    .font(.caption).foregroundStyle(.secondary).frame(maxWidth: .infinity, alignment: .leading)
            }
            StockChartWeb(packet: packet, entry: validEntry, quantity: validQuantity, dark: colors == .dark, entryType: entryType, joinSide: joinSide, joinRevision: joinRevision, beRevision: beRevision, onEntry: { entry = String(format: "%.2f", $0) })
                .clipShape(RoundedRectangle(cornerRadius: 12))
            HStack(spacing: 8) {
                TextField("Shares", text: $quantity).keyboardType(.decimalPad)
                    .multilineTextAlignment(.center).textFieldStyle(.roundedBorder).frame(width: 48)
                Stepper("Shares", value: Binding(get: { max(1, Int(validQuantity)) }, set: { quantity = String($0) }), in: 1...1_000_000).labelsHidden()
                Spacer(minLength: 0)
                if validEntry == 0 {
                    Button { entry = String(format: "%.2f", ((packet["bars"] as? [[String: Any]])?.last?["close"] as? Double) ?? position.market_price ?? 0) } label: { Image(systemName: "plus.circle").frame(minWidth: 32, minHeight: 44) }.accessibilityLabel("Entry reference")
                }
                Picker("Entry type", selection: $entryType) {
                    Text("LMT").tag("LMT"); Text("STP").tag("STP")
                }.pickerStyle(.segmented).frame(maxWidth: 140)
            }
            HStack(spacing: 10) {
                Button { showInfo = true } label: { Image(systemName: "info.circle").frame(width: 28, height: 36) }.accessibilityLabel("Chart details")
                VStack(spacing: 6) {
                    HStack(spacing: 8) {
                        Button { join("bid") } label: { Text("Join Bid").frame(maxWidth: .infinity, minHeight: 30) }.tint(.green).disabled(joinPrice("bid") == nil)
                        Button { join("ask") } label: { Text("Join Ask").frame(maxWidth: .infinity, minHeight: 30) }.tint(.red).disabled(joinPrice("ask") == nil)
                    }
                    HStack(spacing: 8) {
                        Button { showClosePreview = true } label: { Text("Close Position").frame(maxWidth: .infinity, minHeight: 30) }.tint(.orange)
                        Button { beRevision += 1 } label: { Text("BE +1 tick").frame(maxWidth: .infinity, minHeight: 30) }.tint(.purple).disabled(validEntry <= 0 || (packet["price_rules"] as? [[String: Any]])?.isEmpty != false)
                    }
                }.font(.system(size: 13, weight: .semibold))
            }.buttonStyle(.bordered)
        }.padding(.horizontal, 12).padding(.bottom, 8)
        .navigationTitle(position.symbol).navigationBarTitleDisplayMode(.inline)
        .modifier(KeyboardDismissal())
        .alert("Close Position · Preview", isPresented: $showClosePreview) {
            Button("Done", role: .cancel) { }
        } message: {
            Text("This will close the current symbol when live chart trading is enabled. No order has been sent; your position is unchanged.")
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
            if entry.isEmpty { entry = String(format: "%.2f", position.market_price ?? 0) }
        }
        .onDisappear { visible = false }
        .task(id: context) {
            packet = [:]; received = nil; notice = "Loading chart…"
            guard visible, phase == .active else { return }
            guard !store.demo else { notice = "Chart pilot requires a connected held stock"; return }
            guard let conID = position.con_id, conID > 0 else { return }
            var failures = 0
            while !Task.isCancelled {
                do {
                    let result = try await store.trading.get("api/portfolio/stock-chart/\(conID)", base: store.address,
                        query: [URLQueryItem(name: "interval", value: String(interval)), URLQueryItem(name: "session", value: session)])
                    try Task.checkCancellation()
                    guard result["con_id"] as? Int == conID, result["bars"] is [[String: Any]] else { throw AppError.message("Invalid chart response") }
                    packet = result; received = .now; failures = 0
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
    var packet: [String: Any]
    var entry: Double
    var quantity: Double
    var dark: Bool
    var entryType: String
    var joinSide: Int
    var joinRevision: Int
    var beRevision: Int
    var onEntry: (Double) -> Void
    func makeCoordinator() -> Coordinator { Coordinator() }
    func makeUIView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        config.websiteDataStore = .nonPersistent()
        config.userContentController.add(context.coordinator, name: "chartReady")
        config.userContentController.add(context.coordinator, name: "entryChanged")
        let web = WKWebView(frame: .zero, configuration: config)
        web.scrollView.isScrollEnabled = false
        web.isOpaque = false
        context.coordinator.web = web
        func resource(_ name: String, _ ext: String) -> URL? {
            Bundle.main.url(forResource: name, withExtension: ext) ?? Bundle.main.url(forResource: name, withExtension: ext, subdirectory: "ChartAssets")
        }
        if let html = resource("stock-chart", "html"), let library = resource("lightweight-charts.standalone.production", "js"),
           let template = try? String(contentsOf: html, encoding: .utf8), let js = try? String(contentsOf: library, encoding: .utf8) {
            web.loadHTMLString(template.replacingOccurrences(of: "/*LIBRARY*/", with: js), baseURL: nil)
        } else { web.loadHTMLString("<p>Chart resources unavailable</p>", baseURL: nil) }
        return web
    }
    func updateUIView(_ web: WKWebView, context: Context) {
        context.coordinator.packet = packet.isEmpty ? ["bars": [], "generation": "clear", "interval": 0, "session": ""] : packet
        context.coordinator.onEntry = onEntry
        context.coordinator.config = ["entry": entry, "quantity": quantity, "dark": dark, "entryType": entryType, "joinSide": joinSide, "joinRevision": joinRevision, "beRevision": beRevision]
        context.coordinator.update()
    }
    static func dismantleUIView(_ web: WKWebView, coordinator: Coordinator) {
        web.configuration.userContentController.removeScriptMessageHandler(forName: "chartReady")
        web.configuration.userContentController.removeScriptMessageHandler(forName: "entryChanged")
        web.stopLoading(); web.loadHTMLString("", baseURL: nil)
    }
    class Coordinator: NSObject, WKScriptMessageHandler {
        weak var web: WKWebView?
        var ready = false
        var packet: [String: Any] = [:]
        var config: [String: Any] = [:]
        var onEntry: ((Double) -> Void)?
        func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
            if message.name == "entryChanged", let price = message.body as? Double, price.isFinite, price >= 0 {
                onEntry?(price)
            } else if message.name == "chartReady" { ready = true; update() }
        }
        func update() {
            guard ready else { return }
            for (function, value) in [("configure", config), ("receive", packet)] {
                guard !value.isEmpty, let data = try? JSONSerialization.data(withJSONObject: value), let json = String(data: data, encoding: .utf8) else { continue }
                web?.evaluateJavaScript("window.\(function)(\(json))", completionHandler: nil)
            }
        }
    }
}
