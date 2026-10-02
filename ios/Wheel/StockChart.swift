import SwiftUI
import WebKit

struct StockChartView: View {
    let position: Position
    @Environment(WheelStore.self) private var store
    @Environment(\.scenePhase) private var phase
    @Environment(\.colorScheme) private var colors
    @State private var interval = 5
    @AppStorage("stockChartSession") private var session = "rth"
    @State private var quantity = "1"
    @State private var entry = ""
    @State private var packet: [String: Any] = [:]
    @State private var notice = "Loading chart…"
    @State private var visible = false
    @State private var received: Date?
    private var context: String { "\(store.demo)-\(store.address)-\(position.con_id ?? 0)-\(interval)-\(session)-\(phase == .active)-\(visible)" }
    private var validEntry: Double { Double(entry).flatMap { $0.isFinite && $0 > 0 ? $0 : nil } ?? 0 }
    private var validQuantity: Double { Double(quantity).flatMap { $0.isFinite && $0 > 0 && $0 <= 1_000_000 ? $0 : nil } ?? 0 }
    var body: some View {
        VStack(spacing: 8) {
            HStack {
                Picker("Interval", selection: $interval) {
                    Text("1m").tag(1); Text("5m").tag(5); Text("15m").tag(15); Text("1h").tag(60)
                }.pickerStyle(.segmented)
                Picker("Session", selection: $session) {
                    Text("RTH").tag("rth"); Text("All hours").tag("all")
                }.fixedSize()
            }
            TimelineView(.periodic(from: .now, by: 1)) { time in
                Text(received.map { time.date.timeIntervalSince($0) > 3 } == true ? "Chart updates paused · verify connection" : LocalizedStringKey(notice))
                    .font(.caption).foregroundStyle(.secondary).frame(maxWidth: .infinity, alignment: .leading)
            }
            StockChartWeb(packet: packet, entry: validEntry, quantity: validQuantity, dark: colors == .dark)
                .clipShape(RoundedRectangle(cornerRadius: 12))
            HStack {
                VStack(alignment: .leading) {
                    Text("Entry reference").font(.caption).foregroundStyle(.secondary)
                    TextField("Price", text: $entry).keyboardType(.decimalPad)
                }
                VStack(alignment: .leading) {
                    Text("Preview shares").font(.caption).foregroundStyle(.secondary)
                    TextField("Quantity", text: $quantity).keyboardType(.decimalPad)
                }
            }.textFieldStyle(.roundedBorder)
            if validEntry == 0 || validQuantity == 0 { Text("Enter a valid price and quantity.").font(.caption).foregroundStyle(.orange) }
            Text("TP / SL preview only · drag the labels. Estimated P&L excludes fees and slippage. No orders are sent.")
                .font(.caption).foregroundStyle(.secondary)
            HStack {
                Text("New York · © 2025 TradingView, Inc.").font(.caption2)
                Spacer()
                Link("TradingView Lightweight Charts™", destination: URL(string: "https://www.tradingview.com/")!).font(.caption2)
            }
        }.padding(.horizontal, 12).padding(.bottom, 8)
        .navigationTitle(position.symbol).navigationBarTitleDisplayMode(.inline)
        .modifier(KeyboardDismissal())
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
                    notice = result["status"] as? String == "live" ? "IB Last ticks · display batches ≈250ms" : "Historical bars · waiting for IB Last ticks"
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
    func makeCoordinator() -> Coordinator { Coordinator() }
    func makeUIView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        config.websiteDataStore = .nonPersistent()
        config.userContentController.add(context.coordinator, name: "chartReady")
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
        context.coordinator.config = ["entry": entry, "quantity": quantity, "dark": dark]
        context.coordinator.update()
    }
    static func dismantleUIView(_ web: WKWebView, coordinator: Coordinator) {
        web.configuration.userContentController.removeScriptMessageHandler(forName: "chartReady")
        web.stopLoading(); web.loadHTMLString("", baseURL: nil)
    }
    class Coordinator: NSObject, WKScriptMessageHandler {
        weak var web: WKWebView?
        var ready = false
        var packet: [String: Any] = [:]
        var config: [String: Any] = [:]
        func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) { ready = true; update() }
        func update() {
            guard ready else { return }
            for (function, value) in [("configure", config), ("receive", packet)] {
                guard !value.isEmpty, let data = try? JSONSerialization.data(withJSONObject: value), let json = String(data: data, encoding: .utf8) else { continue }
                web?.evaluateJavaScript("window.\(function)(\(json))", completionHandler: nil)
            }
        }
    }
}
