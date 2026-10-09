import SwiftUI
import Charts


// Keep native navigation and its accessibility action without a visible disclosure arrow.
struct ArrowlessNavigationLink<Destination: View, Label: View>: View {
    private let destination: () -> Destination
    private let label: () -> Label

    init(@ViewBuilder destination: @escaping () -> Destination, @ViewBuilder label: @escaping () -> Label) {
        self.destination = destination
        self.label = label
    }

    init(_ title: LocalizedStringKey, @ViewBuilder destination: @escaping () -> Destination) where Label == Text {
        self.destination = destination
        self.label = { Text(title) }
    }

    var body: some View {
        label()
            .frame(maxWidth: .infinity, alignment: .leading)
            .contentShape(Rectangle())
            .overlay {
                NavigationLink(destination: destination) { EmptyView() }
                    .opacity(0)
            }
            .accessibilityRepresentation {
                NavigationLink(destination: destination, label: label)
            }
    }
}

private struct ArrowlessDisclosureStyle: DisclosureGroupStyle {
    func makeBody(configuration: Configuration) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Button { configuration.isExpanded.toggle() } label: {
                configuration.label.frame(maxWidth: .infinity, alignment: .leading)
                    .contentShape(Rectangle())
            }.buttonStyle(.plain)
            if configuration.isExpanded { configuration.content }
        }
    }
}

@main
struct WheelApp: App {
    @State private var store = WheelStore()
    var body: some Scene {
        WindowGroup { RootView().environment(store) }
    }
}

struct ReportedStockCost: Decodable {
    var date: String
    var quantity: Double
    var basis: Double
    var average: Double
    var currency: String
}

struct Position: Decodable, Identifiable {
    var symbol: String
    var position: Double
    var market_price: Double?
    var market_value: Double?
    var unrealized_pnl: Double?
    var security_type: String
    var strike: Double?
    var expiration: String?
    var option_type: String?
    var con_id: Int?
    var entry_fill_price: Double? = nil
    var reported_cost: ReportedStockCost? = nil
    var avg_cost: Double?
    var multiplier: Double?
    var day_low: Double? = nil
    var day_high: Double? = nil
    var day_range_price: Double? = nil
    var day_range_status: String? = nil
    var id: String { "\(symbol)-\(security_type)-\(con_id ?? 0)-\(expiration ?? "")-\(strike ?? 0)" }
    var optionAveragePrice: Double? {
        guard security_type == "OPT" else { return nil }
        if let fill = entry_fill_price, fill.isFinite, fill > 0 { return fill }
        guard let cost = avg_cost, cost.isFinite, cost > 0,
              let multiplier, multiplier.isFinite, multiplier > 0 else { return nil }
        let value = cost / multiplier
        return value.isFinite && value > 0 ? value : nil
    }
    var optionAverageUsesBrokerCost: Bool {
        optionAveragePrice != nil && !(entry_fill_price.map { $0.isFinite && $0 > 0 } ?? false)
    }
    var hasChart: Bool { ["STK", "OPT", "FUT"].contains(security_type) && position != 0 && (con_id ?? 0) > 0 }
    var chartLabel: String { security_type == "OPT" ? "\(symbol) \(expiration ?? "") \((strike ?? 0).formatted()) \(option_type ?? "")" : symbol }
    var detail: String {
        security_type == "OPT" ? "\(expiration ?? "") · \((strike ?? 0).formatted()) · \(option_type ?? "")" : security_type == "FUT" ? "\(position.formatted()) contracts" : "\(Int(position)) shares"
    }
}

struct Summary: Decodable {
    var account_value: Double
    var cash_balance: Double
    var excess_liquidity: Double?
    var is_frozen: Bool?
    var initial_margin: Double?
    var leverage_percentage: Double?
}
struct AccountConnection: Decodable {
    var account_epoch: String? = nil
    var mode: String
    var execution_enabled: Bool
    var chart_execution_enabled: Bool
    var label: String { mode == "paper" ? "Paper" : mode == "live" ? "Live" : "Unknown" }
}
struct Bootstrap: Decodable { var summary: Summary; var positions: [Position]; var connection: AccountConnection? = nil }
struct LivePortfolio: Decodable { var positions: [Position]; var is_frozen: Bool; var streaming: Bool?; var connection: AccountConnection? = nil }
struct WeeklyIncome: Decodable { var total_income: Double; var positions_count: Int; var total_put_notional: Double?; var this_friday: String? }
struct Order: Decodable, Identifiable {
    var id: OrderID
    var ticker: String?
    var symbol: String?
    var action: String?
    var option_type: String?
    var strike: Double?
    var expiration: String?
    var premium: Double?
    var quantity: Double?
    var status: String
    var tif: String?
    var timingLabel: String {
        let value = tif ?? (intent == "CLOSE" ? "GTC" : "DAY")
        return value == "OVERNIGHT" ? "OVT" : value
    }
    var intent: String? = nil
    var con_id: Int? = nil
    var chart_con_id: Int? = nil
    var chart_order_ref: String? = nil
    var chart_protection_ref: String? = nil
    var chart_protection_group_id: String? = nil
    var chartPosition: Position? {
        guard let cid = [chart_con_id, con_id].compactMap({ $0 }).first(where: { $0 > 0 }) else { return nil }
        let type: String
        switch option_type {
        case "STOCK": type = "STK"
        case "FUTURE": type = "FUT"
        case "CALL", "PUT": type = "OPT"
        default: return nil
        }
        return Position(symbol: name, position: 0, security_type: type,
                        strike: strike, expiration: expiration, option_type: option_type, con_id: cid)
    }
    var external_ib: Bool? = nil
    var ib_status: String? = nil
    var executed: Bool? = nil
    var ib_order_id: Int? = nil
    var perm_id: Int? = nil
    var amendment_pending: String? = nil
    var error_message: String? = nil
    var isRollover: Bool? = nil
    var filled: Double? = nil
    var gross_pnl: Double? = nil
    var net_pnl: Double? = nil
    var round_trip_commission: Double? = nil
    var order_type: String? = nil
    var avg_fill_price: Double? = nil
    var fill_time: String? = nil
    var fill_action: String? = nil
    var commission: Double? = nil
    var commission_currency: String? = nil
    var realized_pnl: Double? = nil
    var statusExplanation: String {
        let state = status.lowercased()
        let broker = (ib_status ?? "").lowercased()
        if state == "unknown" { return "Result unconfirmed. Verify in IB before another action." }
        if amendment_pending != nil { return "Modification awaiting confirmation; displayed terms may still be the previous terms." }
        if state == "rejected" || broker == "inactive" { return "Order rejected or inactive. Check the broker details." }
        if state == "pendingcancel" || broker == "pendingcancel" { return "Cancellation requested; fills remain possible until IB confirms cancellation." }
        if ["filled", "executed"].contains(state) || broker == "filled" { return "Filled. Review the recorded fill quantity and price." }
        if ["cancelled", "canceled"].contains(state) { return "Canceled. Any earlier fills remain valid." }
        if (filled ?? 0) > 0 { return "Partially filled; the remaining quantity is not yet confirmed filled." }
        if TradeRules.editable(self) { return "Local draft. Not yet sent to IB." }
        if ["submitted", "presubmitted"].contains(broker) { return "IB reports the order as working; this is not a fill confirmation." }
        return "Awaiting an updated broker status. Processing does not mean filled."
    }
    var isTerminal: Bool {
        ["filled", "executed", "cancelled", "canceled", "rejected"].contains(status.lowercased())
    }
    var fillDate: Date? {
        guard let fill_time else { return nil }
        return (try? Date.ISO8601FormatStyle(includingFractionalSeconds: true).parse(fill_time))
            ?? (try? Date.ISO8601FormatStyle(includingFractionalSeconds: false).parse(fill_time))
    }
    static func latestFillsFirst(_ orders: [Order]) -> [Order] {
        orders.map { ($0, $0.fillDate ?? .distantPast) }.sorted { lhs, rhs in
            if lhs.1 != rhs.1 { return lhs.1 > rhs.1 }
            let leftID = lhs.0.perm_id ?? lhs.0.ib_order_id ?? lhs.0.id.local ?? 0
            let rightID = rhs.0.perm_id ?? rhs.0.ib_order_id ?? rhs.0.id.local ?? 0
            if leftID != rightID { return leftID > rightID }
            return lhs.0.id.description > rhs.0.id.description
        }.map { $0.0 }
    }
    var fillTimeLabel: String {
        guard let date = fillDate else { return "—" }
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(identifier: "America/New_York")
        formatter.dateFormat = "yyyy-MM-dd HH:mm:ss zzz"
        return formatter.string(from: date)
    }
    var commissionLabel: String {
        guard let commission, commission.isFinite, abs(commission) < 1e100,
              commission_currency == nil || commission_currency == "USD" else { return "—" }
        return "$" + commission.formatted(.number.precision(.fractionLength(2)).rounded(rule: .toNearestOrAwayFromZero))
    }

    var fillPrice: Double? {
        guard let value = avg_fill_price, value.isFinite, value > 0 else { return nil }
        return value
    }
    var filledQuantity: Double? {
        guard let value = filled, value.isFinite, value > 0 else { return nil }
        return value
    }
    var hasFill: Bool {
        if let filled, filled.isFinite, filled > 0 { return true }
        return ib_status?.lowercased() == "filled" || ["filled", "executed"].contains(status.lowercased())
    }
    var name: String { ticker ?? symbol ?? "Option" }
}
struct Orders: Decodable { var orders: [Order] }

struct TradeChartDestination: Hashable {
    let id = UUID()
    let position: Position
    var resumeLast = false
    static func == (lhs: Self, rhs: Self) -> Bool { lhs.id == rhs.id }
    func hash(into hasher: inout Hasher) { hasher.combine(id) }
}

@MainActor @Observable
final class WheelStore {
    var performanceHistoryCache: [String: Data] = [:]
    var demo = true
    var address = UserDefaults.standard.string(forKey: "backendURL") ?? ""
    var portfolio: Bootstrap?
    var accountModeLabel: String { demo ? "Demo" : portfolio?.connection?.label ?? "Unknown" }
    var tradingAccessLabel: String {
        if demo { return "Demo" }
        guard isConnected(to: address) else { return "Disconnected" }
        return portfolio?.connection?.execution_enabled == true ? "Trading enabled" : "Read only"
    }
    var chartTradingAvailable: Bool { !demo && isConnected(to: address) && portfolio?.connection?.chart_execution_enabled == true }
    var priceDirections: [String: Int] = [:]
    var orders: [Order] = []
    var filledOrders: [Order] = []
    var filledUpdated: Date?
    var filledError: String?
    private var filledBusy = false
    var weekly: WeeklyIncome?
    var orderError: String?
    var ordersRetrying = false
    var busy = false
    var ordersBusy = false
    var ordersUpdated: Date?
    var error: String?
    var updated: Date?
    var fillPreview = FillPreview()
    private var fillTracker = FillTracker()
    private var fillSnapshot: [Order] = []
    private var fillSnapshotAt: Date?
    var completedOrders: [OrderID: Order] = [:]
    func retainCompleted(_ records: [Order]) {
        for order in records where order.isTerminal { completedOrders[order.id] = order }
    }
    var trading = TradingSession()
    var opportunities = OpportunityBook()
    var chartVisible = false
    var selectedTab = "settings"
    var requestedTradeChart: TradeChartDestination?
    func openOrderChart(_ order: Order) {
        guard let position = order.chartPosition else { return }
        openTradeChart(position)
    }
    func openTradeChart(_ position: Position, resumeLast: Bool = false) {
        requestedTradeChart = TradeChartDestination(position: position, resumeLast: resumeLast)
        selectedTab = "trade"
    }
    private let session: URLSession
    private var connectingEpoch: String?
    private var connectingMode: String?
    init(session: URLSession = .shared) { self.session = session; opportunities.configure(context: "demo") }
    private var revision = 0
    private var lastSummary: Date?
    func isConnected(to candidate: String) -> Bool {
        !demo && candidate.trimmingCharacters(in: .whitespacesAndNewlines) == address &&
        portfolio != nil && error == nil && Date().timeIntervalSince(updated ?? .distantPast) < 15
    }

    func showPortfolioAfterConnection(to requestedAddress: String, mode: String) {
        guard selectedTab == "settings", isConnected(to: requestedAddress),
              portfolio?.connection?.mode == mode, ["paper", "live"].contains(mode) else { return }
        selectedTab = "portfolio"
    }

    func completeAccountConnection(to base: String, mode: String, epoch: String,
                                   attempts: Int = 30, retryDelay: Duration = .seconds(1)) async throws {
        guard ["paper", "live"].contains(mode), !epoch.isEmpty, address == base else { throw CancellationError() }
        demo = false; changeMode(); connectingEpoch = epoch; connectingMode = mode; trading.accountEpoch = epoch
        let context = revision, deadline = Date().addingTimeInterval(45)
        defer { if revision == context { connectingEpoch = nil; connectingMode = nil } }
        for attempt in 0..<attempts {
            try Task.checkCancellation()
            guard revision == context, !demo, address == base else { throw CancellationError() }
            if !busy && !trading.busy { await refreshPortfolio(includeWeekly: false) }
            guard revision == context, !demo, address == base else { throw CancellationError() }
            if error == nil, portfolio?.connection?.mode == mode, portfolio?.connection?.account_epoch == epoch,
               Date().timeIntervalSince(updated ?? .distantPast) < 15 {
                showPortfolioAfterConnection(to: base, mode: mode)
                return
            }
            if Date() >= deadline || attempt == attempts - 1 { break }
            try await Task.sleep(for: retryDelay)
        }
        throw AppError.message(error ?? "Account data is not ready. Retry connection.")
    }

    func refresh() async {
        await refreshPortfolio()
        await refreshOrders()
    }

    func refreshPortfolio(includeWeekly: Bool = true) async {
        guard !busy, !trading.busy else { return }
        busy = true
        let requestedRevision = revision
        let requestedTradeVersion = trading.version
        defer { busy = false }
        if demo {
            portfolio = Bootstrap(summary: Summary(account_value: 25000, cash_balance: 2693, excess_liquidity: 14500, is_frozen: true, initial_margin: 4500, leverage_percentage: 18), positions: [
                Position(symbol: "TSLL", position: 300, market_price: 10.25, market_value: 3075, unrealized_pnl: 125, security_type: "STK", con_id: 2, avg_cost: 2950.0 / 300),
                Position(symbol: "CRCL", position: 100, market_price: 92.5, market_value: 9250, unrealized_pnl: -150, security_type: "STK", con_id: 3, avg_cost: 94),
                // Synthetic preview holding for the core-asset finish; never used in Live.
                Position(symbol: "VOO", position: 20, market_price: 500, market_value: 10000, unrealized_pnl: 200, security_type: "STK", con_id: 4, avg_cost: 490),
                Position(symbol: "TSLL", position: -1, market_price: 0.18, market_value: -18, unrealized_pnl: 32, security_type: "OPT", strike: 9, expiration: "20261016", option_type: "PUT", con_id: 1, avg_cost: 50, multiplier: 100)
            ])
            weekly = WeeklyIncome(total_income: 0, positions_count: 0, total_put_notional: 0)
            error = nil
            updated = Date()
            return
        }
        do {
            guard let base = URL(string: address.trimmingCharacters(in: .whitespacesAndNewlines)), base.scheme == "https", base.host != nil, base.user == nil, base.password == nil, base.query == nil, base.fragment == nil else {
                throw AppError.message("Enter your private HTTPS backend address in Settings.")
            }
            let next: Bootstrap
            let reloadSummary = portfolio == nil || Date().timeIntervalSince(lastSummary ?? .distantPast) > 30
            if reloadSummary {
                next = try await read(base.appendingPathComponent("api/portfolio/bootstrap"))
            } else {
                let live: LivePortfolio = try await read(base.appendingPathComponent("api/portfolio/live"))
                var summary = portfolio!.summary
                summary.is_frozen = live.is_frozen
                next = Bootstrap(summary: summary, positions: live.positions, connection: live.connection)
            }
            guard requestedRevision == revision, requestedTradeVersion == trading.version, !trading.busy, !Task.isCancelled else { return }
            let previousPrices = Dictionary((portfolio?.positions ?? []).compactMap { position in
                position.market_price.map { (position.id, $0) }
            }, uniquingKeysWith: { _, latest in latest })
            priceDirections = Dictionary(next.positions.map { position in
                (position.id, TradingMath.priceDirection(
                    previous: previousPrices[position.id],
                    current: position.market_price))
            }, uniquingKeysWith: { _, latest in latest })
            if let expected = UserDefaults.standard.string(forKey: "selectedBrokerMode"),
               next.connection?.mode != expected {
                throw AppError.message("Gateway account does not match the selected mode. Log in to the selected account on Mini.")
            }
            if let connectingEpoch, next.connection?.account_epoch != connectingEpoch || next.connection?.mode != connectingMode {
                throw AppError.message("Another device changed the selected account. Select your account again.")
            }
            trading.accountEpoch = next.connection?.account_epoch
            portfolio = next
            if reloadSummary { lastSummary = Date() }
            updated = Date()
            error = nil
            UserDefaults.standard.set(address, forKey: "backendURL")
            if includeWeekly && reloadSummary && selectedTab != "trade" {
                let income: WeeklyIncome? = try? await read(base.appendingPathComponent("api/portfolio/weekly-income"))
                guard requestedRevision == revision, !Task.isCancelled else { return }
                weekly = income
            }
        } catch is CancellationError {
        } catch {
            guard requestedRevision == revision, !Task.isCancelled else { return }
            self.error = connectionMessage(error)
        }
    }

    func refreshOrders() async {
        guard !ordersBusy, !trading.busy else { return }
        ordersBusy = true
        let token = revision
        let tradeVersion = trading.version
        defer { ordersBusy = false; ordersRetrying = false }
        if demo {
            orders = trading.demoOrders; ordersUpdated = Date(); orderError = nil
            opportunities.synchronizeEntries(orders: orders)
            trading.ordersDidRefresh(); return
        }
        do {
            let result: Orders
            do {
                result = try await trading.synchronizedOrders(base: address)
            } catch let failure as BackendHTTPError where failure.status == 502 {
                guard token == revision, tradeVersion == trading.version, !trading.busy, !Task.isCancelled else { return }
                orderError = failure.localizedDescription
                ordersRetrying = true
                try await Task.sleep(for: .seconds(1))
                guard token == revision, tradeVersion == trading.version, !trading.busy else { return }
                result = try await trading.synchronizedOrders(base: address)
            }
            guard token == revision, tradeVersion == trading.version, !trading.busy, !Task.isCancelled else { return }
            let disappeared = !Set(orders.map(\.id)).subtracting(result.orders.map(\.id)).isEmpty
            orders = result.orders; ordersUpdated = Date(); orderError = nil
            if fillSnapshotAt == nil || disappeared || Date().timeIntervalSince(fillSnapshotAt!) >= 10 {
                do {
                    let payload = try await trading.get("api/options/pending-orders", base: address,
                        query: [URLQueryItem(name: "executed", value: "true")])
                    let history = try JSONDecoder().decode(Orders.self, from: JSONSerialization.data(withJSONObject: payload))
                    guard token == revision, tradeVersion == trading.version, !trading.busy, !Task.isCancelled else { return }
                    retainCompleted(history.orders)
                    fillSnapshot = history.orders
                    fillSnapshotAt = Date()
                } catch {
                    // Keep known quantities on failures; a missing response is never a fill.
                    guard token == revision, tradeVersion == trading.version, !Task.isCancelled else { return }
                }
            }
            if fillSnapshotAt != nil {
                fillPreview.updateMetadata(fillSnapshot + orders)
                fillPreview.enqueue(fillTracker.ingest(fillSnapshot + orders))
            }
            ChartTradeSounds.shared.observeOrders(scope: "\(address):\(trading.accountEpoch ?? "")", orders: Array(completedOrders.values) + orders)
            opportunities.synchronizeEntries(orders: orders)
            trading.ordersDidRefresh()
        } catch {
            guard token == revision, tradeVersion == trading.version, !Task.isCancelled else { return }
            orderError = "Order refresh failed; displayed data may be outdated. " + connectionMessage(error)
        }
    }

    private func read<T: Decodable>(_ url: URL) async throws -> T {
        var request = URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 15)
        request.httpMethod = "GET"
        let (data, response) = try await session.data(for: request)
        guard let response = response as? HTTPURLResponse, response.statusCode == 200 else { throw AppError.message("Backend unavailable. Check your connection and Tailscale.") }
        return try JSONDecoder().decode(T.self, from: data)
    }
    func loadFilled() async {
        guard !filledBusy, !trading.busy else { return }
        filledBusy = true
        defer { filledBusy = false }
        let token = revision
        let version = trading.version
        if demo { filledOrders = Order.latestFillsFirst(trading.demoOrders.filter { $0.hasFill }); filledError = nil; filledUpdated = .now; return }
        do {
            let result = try await trading.get("api/options/pending-orders", base: address, query: [URLQueryItem(name: "executed", value: "true")])
            let decoded = try JSONDecoder().decode(Orders.self, from: JSONSerialization.data(withJSONObject: result))
            guard token == revision, version == trading.version, !Task.isCancelled else { return }
            let completedIDs = Set(decoded.orders.map(\.id))
            filledOrders = Order.latestFillsFirst((decoded.orders + orders.filter { !completedIDs.contains($0.id) }).filter { $0.hasFill })
            filledError = nil; filledUpdated = .now
        } catch {
            if token == revision, version == trading.version, !Task.isCancelled { filledError = connectionMessage(error) }
        }
    }
    func changeMode() { ChartTradeSounds.shared.reset(); connectingEpoch = nil; connectingMode = nil; completedOrders = [:]; performanceHistoryCache = [:]; fillPreview.clear(); fillTracker = FillTracker(); fillSnapshot = []; fillSnapshotAt = nil; revision += 1; portfolio = nil; priceDirections = [:]; orders = []; filledOrders = []; filledError = nil; filledUpdated = nil; weekly = nil; lastSummary = nil; updated = nil; ordersUpdated = nil; error = nil; orderError = nil; trading.resetContext(); opportunities.configure(context: demo ? "demo" : address) }
}

func connectionMessage(_ error: Error) -> String {
    let code = (error as NSError).code
    if (error as NSError).domain == NSURLErrorDomain && [-1200, -1201, -1202, -1203, -1204].contains(code) {
        return "Secure connection failed (\(code)). Check Tailscale and open this exact HTTPS address in Safari on this iPhone. Verify automatic date/time and any VPN or proxy interference. Certificate checks remain enabled."
    }
    if (error as NSError).domain == NSURLErrorDomain {
        switch code {
        case NSURLErrorTimedOut: return "Connection timed out. Check your network and Tailscale, then retry."
        case NSURLErrorNotConnectedToInternet: return "No internet connection. Check Wi-Fi or cellular data."
        case NSURLErrorCannotFindHost, NSURLErrorCannotConnectToHost, NSURLErrorDNSLookupFailed:
            return "Cannot reach the backend. Check the address and Tailscale connection."
        case NSURLErrorNetworkConnectionLost: return "Connection interrupted. Retrying…"
        default: break
        }
    }
    return error.localizedDescription
}

struct KeyboardDismissal: ViewModifier {
    func body(content: Content) -> some View {
        content.scrollDismissesKeyboard(.interactively)
            .toolbar {
                ToolbarItemGroup(placement: .keyboard) {
                    Spacer()
                    Button("Done") { UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder), to: nil, from: nil, for: nil) }
                }
            }
    }
}
enum AppError: LocalizedError {
    case message(String)
    var errorDescription: String? { if case .message(let text) = self { return text }; return nil }
}

func money(_ value: Double?) -> String {
    guard let value, value.isFinite else { return "—" }
    return value.formatted(.currency(code: "USD").locale(Locale(identifier: "en_US")))
}

func localizedLabel(_ key: String, locale: Locale) -> String {
    let identifier = locale.identifier
    let language = identifier.hasPrefix("zh") ? (identifier.contains("Hant") || identifier.contains("TW") || identifier.contains("HK") ? "zh-Hant" : "zh-Hans") : "en"
    guard let path = Bundle.main.path(forResource: language, ofType: "lproj"), let bundle = Bundle(path: path) else { return key }
    return bundle.localizedString(forKey: key, value: key, table: nil)
}

// Resolve dynamic notices at display time so changing the app language also updates existing errors.
func localizedNotice(_ message: String, locale: Locale) -> String {
    let translated = localizedLabel(message, locale: locale)
    if translated != message { return translated }
    let refreshPrefix = "Order refresh failed; displayed data may be outdated. "
    let lockSuffix = " Do not resubmit. Verify in IB and the web app; trading is locked pending review."
    if message.hasPrefix(refreshPrefix) {
        return localizedLabel(String(refreshPrefix.dropLast()), locale: locale) + " " +
            localizedNotice(String(message.dropFirst(refreshPrefix.count)), locale: locale)
    }
    if message.hasSuffix(lockSuffix) {
        return localizedNotice(String(message.dropLast(lockSuffix.count)), locale: locale) + " " +
            localizedLabel(String(lockSuffix.dropFirst()), locale: locale)
    }
    if let diagnostics = message.range(of: " [") {
        return localizedNotice(String(message[..<diagnostics.lowerBound]), locale: locale) + String(message[diagnostics.lowerBound...])
    }
    let securePrefix = "Secure connection failed ("
    if message.hasPrefix(securePrefix), let end = message.range(of: "). "),
       let code = Int(message[message.index(message.startIndex, offsetBy: securePrefix.count)..<end.lowerBound]) {
        let format = localizedLabel("Secure connection failed (%@). Check Tailscale and open this exact HTTPS address in Safari on this iPhone. Verify automatic date/time and any VPN or proxy interference. Certificate checks remain enabled.", locale: locale)
        return String(format: format, String(code))
    }
    return message
}

struct NoticeText: View {
    let message: String
    @Environment(\.locale) private var locale
    init(_ message: String) { self.message = message }
    var body: some View { Text(verbatim: localizedNotice(message, locale: locale)) }
}

struct RootView: View {
    @AppStorage("allHighGildedV3") private var spreadWarningRedApplied = false
    @AppStorage("demoCustomColors") private var customColorsJSON = "{}"
    @AppStorage("appearance") private var appearance = "system"
    @AppStorage("appLanguage") private var appLanguage = "system"
    @Environment(WheelStore.self) private var store
    @Environment(\.scenePhase) private var phase
    @State private var portfolioPath = NavigationPath()
    @State private var ordersPath = NavigationPath()
    @State private var tradePath = NavigationPath()
    private var appLocale: Locale { Locale(identifier: appLanguage == "system" ? (Locale.preferredLanguages.first ?? "en") : appLanguage) }
    @Environment(\.colorScheme) private var systemScheme
    private var appAccent: Color {
        let dark = appearance == "dark" || (appearance == "system" && systemScheme == .dark)
        return CustomPalette(json: customColorsJSON).color("accent", scheme: dark ? .dark : .light, fallback: dark ? Color(red: 0.93, green: 0.92, blue: 0.89) : Color(red: 0.27, green: 0.28, blue: 0.30))
    }
    var body: some View {
        @Bindable var store = store
        TabView(selection: $store.selectedTab) {
            NavigationStack(path: $portfolioPath) { PortfolioView().modifier(KeyboardDismissal()) }.tabItem { Label(localizedLabel("Portfolio", locale: appLocale), systemImage: "chart.pie") }.tag("portfolio")
            NavigationStack(path: $tradePath) {
                OpportunitiesView().modifier(KeyboardDismissal())
                    .navigationDestination(for: TradeChartDestination.self) { destination in
                        StockChartView(position: destination.position, resumeLast: destination.resumeLast).id(destination.id)
                    }
            }.tabItem { Label(localizedLabel("Trade", locale: appLocale), systemImage: "arrow.left.arrow.right") }.tag("trade")
            NavigationStack(path: $ordersPath) { OrdersView().modifier(KeyboardDismissal()) }.tabItem { Label(localizedLabel("Orders", locale: appLocale), systemImage: "list.bullet.rectangle") }.tag("orders")
            NavigationStack { SettingsView().modifier(KeyboardDismissal()) }.tabItem { Label(localizedLabel("Settings", locale: appLocale), systemImage: "gearshape") }.tag("settings")
        }
        .onChange(of: phase, initial: true) { _, phase in
            ChartTradeSounds.shared.reset()
            ChartTradeSounds.shared.active = phase == .active && !store.demo
        }
        .onChange(of: store.demo) { _, demo in
            ChartTradeSounds.shared.reset()
            ChartTradeSounds.shared.active = phase == .active && !demo
        }
        .onChange(of: store.isConnected(to: store.address)) { _, connected in
            ChartTradeSounds.shared.connection(connected, enabled: ChartTradeSounds.shared.enabled)
        }
        .onChange(of: store.requestedTradeChart) {
            guard let destination = store.requestedTradeChart else { return }
            tradePath = NavigationPath([destination])
        }
        .onAppear {
            if !spreadWarningRedApplied {
                var palette = CustomPalette(json: customColorsJSON).values
                for metric in ["delta", "spread", "iv"] {
                    palette[metric + ".high.dark"] = "#AD6417"
                    palette[metric + ".high.light"] = "#854A0F"
                }
                if let data = try? JSONEncoder().encode(palette), let text = String(data: data, encoding: .utf8) {
                    customColorsJSON = text; spreadWarningRedApplied = true
                }
            }
        }
        .modifier(FillBannerOverlay(preview: store.fillPreview))
        .environment(\.demoMetricPalette, true)
        .environment(\.customPalette, CustomPalette(json: customColorsJSON))
        .onChange(of: phase) { if phase != .active { store.fillPreview.clear() } }
        .tint(appAccent)
        .environment(\.locale, Locale(identifier: appLanguage == "system" ? (Locale.preferredLanguages.first ?? "en") : appLanguage))
        .preferredColorScheme(appearance == "dark" ? .dark : appearance == "light" ? .light : nil)
        // Keep each tab's navigation controller stable on iOS 18 when reconnecting.
        .onChange(of: "\(store.demo)-\(store.address)") {
            portfolioPath = NavigationPath(); ordersPath = NavigationPath(); tradePath = NavigationPath(); store.requestedTradeChart = nil
        }
        .task(id: "\(phase)-\(store.demo)-\(store.address)") {
            guard phase == .active else { return }
            await RefreshLoop.run {
                if store.chartVisible || RefreshLoop.shouldRefreshPortfolio(tab: store.selectedTab, hasPortfolio: store.portfolio != nil,
                    age: Date().timeIntervalSince(store.updated ?? .distantPast),
                    quotesLoading: store.opportunities.loading || store.opportunities.rows.values.contains { $0.loading }) {
                    await store.refreshPortfolio()
                }
                return store.error != nil
            }
        }
        .task(id: "orders-\(phase)-\(store.demo)-\(store.address)") {
            guard phase == .active else { return }
            await RefreshLoop.run {
                if store.selectedTab != "trade" || Date().timeIntervalSince(store.ordersUpdated ?? .distantPast) >= 10 {
                    await store.refreshOrders()
                }
                return store.orderError != nil
            }
        }
    }
}

struct StatusView: View {
    var orders = false
    @Environment(WheelStore.self) private var store
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var showHealth = false
    @State private var copiedDiagnostics = false
    private var error: String? { orders ? store.orderError : store.error }
    private var busy: Bool { orders ? store.ordersBusy : store.busy }
    private var updated: Date? { orders ? store.ordersUpdated : store.updated }
    var body: some View {
        TimelineView(.periodic(from: .now, by: 1)) { context in
            let status = DataHealth.status(demo: store.demo, failed: error != nil, updated: updated,
                frozen: !orders && store.portfolio?.summary.is_frozen == true, now: context.date)
            Button { copiedDiagnostics = false; showHealth = true } label: {
                HStack(spacing: 6) {
                    Circle().fill(status == "STALE" || status == "FROZEN" ? Color.orange : .teal).frame(width: 6, height: 6)
                        .opacity(busy && !reduceMotion ? 0.35 : 1)
                        .animation(reduceMotion ? nil : .easeInOut(duration: 0.45), value: busy)
                        .accessibilityHidden(true)
                    if !store.demo { Text(LocalizedStringKey(store.accountModeLabel)).fontWeight(.semibold) }
                    Text(LocalizedStringKey(status))
                    Spacer()
                    if let date = updated { Text(date.formatted(.dateTime.hour().minute().second())).monospacedDigit() }
                    Image(systemName: "info.circle").accessibilityHidden(true)
                }.font(.caption).foregroundStyle(.secondary).contentShape(Rectangle())
            }.buttonStyle(.plain)
        }
        .sheet(isPresented: $showHealth) {
            NavigationStack {
                Form {
                    Section("Data status") {
                        LabeledContent("Account mode") { Text(LocalizedStringKey(store.accountModeLabel)) }
                        LabeledContent("Trading access") { Text(LocalizedStringKey(store.tradingAccessLabel)) }
                        if let date = updated { LabeledContent("Last backend response", value: date.formatted(.dateTime.hour().minute().second())) }
                        Text("The time shown is the last successful backend refresh, not the exchange quote time.")
                        if store.demo { Text("Demo quote") }
                        else if !orders && store.portfolio?.summary.is_frozen == true { Text("Frozen portfolio · verify quote") }
                    }
                    Section("Troubleshooting") {
                        if let error { NoticeText(error).foregroundStyle(.orange) }
                        Text(LocalizedStringKey(DataHealth.guidance(error)))
                    }
                    Section("Diagnostics") {
                        let report = SafeDiagnostics.report(demo: store.demo, orders: orders,
                            frozen: store.portfolio?.summary.is_frozen == true,
                            marketOpen: store.opportunities.marketOpen, updated: updated, error: error,
                            uncertain: store.trading.uncertain, now: .now,
                            version: "\(Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "") (\(Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String ?? ""))",
                            systemVersion: UIDevice.current.systemVersion)
                        Text("Includes app version, refresh status and request reference only. No account, positions, private address or credentials.")
                            .font(.caption).foregroundStyle(.secondary)
                        DisclosureGroup("Preview diagnostics") {
                            Text(report).font(.caption.monospaced()).textSelection(.enabled)
                        }
                        Button(copiedDiagnostics ? "Diagnostics copied" : "Copy diagnostics", systemImage: "doc.on.doc") {
                            UIPasteboard.general.setItems([["public.utf8-plain-text": report]],
                                options: [.localOnly: true, .expirationDate: Date().addingTimeInterval(300)])
                            copiedDiagnostics = true
                        }
                    }
                }.navigationTitle("Data status")
                    .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { showHealth = false } } }
            }
        }
    }
}

struct PortfolioView: View {
    @Environment(\.locale) private var locale
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @AppStorage("portfolioShowCashMetrics") private var showCashMetrics = false
    @State private var cashMetricsHeight: CGFloat = 0
    @Environment(WheelStore.self) private var store
    private enum SummaryDestination: String, Identifiable {
        case performance, margin, allocation
        var id: String { rawValue }
    }
    @State private var summaryDestination: SummaryDestination?
    private struct PositionDestination: Hashable {
        let conID: Int
        let rollover: Bool
    }
    @State private var positionDestination: PositionDestination?
    var body: some View {
        List {
            Section {
                StatusView()
                VStack(alignment: .leading, spacing: 0) {
                    HStack {
                        Text("Net liquidation").font(.subheadline).foregroundStyle(.secondary)
                        Spacer(minLength: 12)
                        Button { summaryDestination = .performance } label: {
                            PerformanceShimmerLabel().font(.subheadline)
                            .frame(minHeight: 44)
                            .contentShape(Rectangle())
                        }.buttonStyle(.plain)
                    }.padding(.bottom, 8)
                    HStack(alignment: .bottom, spacing: 8) {
                        Button { summaryDestination = .allocation } label: {
                            VStack(alignment: .leading, spacing: 8) {
                                Text(money(store.portfolio?.summary.account_value)).font(.system(size: 32, weight: .semibold, design: .rounded)).monospacedDigit().minimumScaleFactor(0.6).lineLimit(1)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .contentShape(Rectangle())
                        }.buttonStyle(.plain)
                        Spacer(minLength: 0)
                        Button {
                            withAnimation(reduceMotion ? nil : .easeInOut(duration: 0.2)) {
                                showCashMetrics.toggle()
                            }
                        } label: {
                            Color.clear
                                .frame(width: 44, height: 44)
                                .contentShape(Rectangle())
                        }.buttonStyle(.plain)
                            .accessibilityLabel(showCashMetrics ? Text("Hide liquidity and cash") : Text("Show liquidity and cash"))
                    }
                    .fixedSize(horizontal: false, vertical: true)
                    .layoutPriority(1)
                    VStack(spacing: 0) {
                        HStack {
                            metric("Excess liquidity", money(store.portfolio?.summary.excess_liquidity))
                            Spacer()
                            metric("Cash", money(store.portfolio?.summary.cash_balance))
                        }.padding(.top, 12)
                    }
                    .fixedSize(horizontal: false, vertical: true)
                    .onGeometryChange(for: CGFloat.self) { $0.size.height } action: { cashMetricsHeight = $0 }
                    .frame(height: showCashMetrics ? cashMetricsHeight : 0, alignment: .top)
                    .clipped()
                    .accessibilityHidden(!showCashMetrics)
                    .allowsHitTesting(showCashMetrics)
                }.padding(.vertical, 6)
                VStack(spacing: 8) {
                    HStack(alignment: .firstTextBaseline, spacing: 12) {
                        Button { summaryDestination = .margin } label: {
                            VStack(alignment: .leading, spacing: 4) {
                                Text("Initial margin").font(.caption).foregroundStyle(.secondary)
                                MarginWarningAmount(amount: store.portfolio?.summary.initial_margin,
                                    netValue: store.portfolio?.summary.account_value,
                                    active: store.selectedTab == "portfolio" && summaryDestination == nil)
                            }
                        }.buttonStyle(.plain)
                        Spacer(minLength: 8)
                        VStack(alignment: .trailing, spacing: 4) {
                            Text("Leverage").font(.caption).foregroundStyle(.secondary)
                            Text(store.portfolio?.summary.leverage_percentage.map { String(format: "%.1f%%", $0) } ?? "—")
                                .monospacedDigit()
                        }
                    }
                    LeverageMeter(percentage: store.portfolio?.summary.leverage_percentage, showsLabel: false)
                }.font(.subheadline).padding(.vertical, 4)
            }
            if let error = store.error { Section { Label { NoticeText(error) } icon: { Image(systemName: "wifi.exclamationmark") }.foregroundStyle(.orange) } }
            let heldPositions = (store.portfolio?.positions ?? []).filter { $0.position != 0 }
            ForEach(["OPT", "STK", "FUT"].filter { type in
                heldPositions.contains { $0.security_type == type }
            }, id: \.self) { type in
                Section(LocalizedStringKey(type == "STK" ? "Stocks" : type == "FUT" ? "Futures" : "Options")) {
                    ForEach(heldPositions.filter { $0.security_type == type }) { position in
                        ExpandablePositionRow(position: position) { expanded in
                            if position.security_type == "OPT" {
                                PortfolioOptionRow(position: position, showsRange: false)
                            } else {
                            VStack(alignment: .leading, spacing: 8) {
                            HStack(alignment: .top) {
                                HStack(alignment: .firstTextBaseline, spacing: 8) {
                                    SymbolText(symbol: position.symbol).font(.headline)
                                    Text(verbatim: position.position.formatted())
                                        .font(.caption).foregroundStyle(.secondary).monospacedDigit()
                                        .accessibilityLabel(Text("Quantity"))
                                        .accessibilityValue(position.position.formatted())
                                }
                                Spacer()
                                VStack(alignment: .trailing, spacing: 5) {
                                    PositionMarketPrice(position: position)
                                    PositionPnLMeter(position: position)
                                }
                            }
                            }.padding(.vertical, 6)
                            }
                        }
                        .swipeActions(edge: .trailing, allowsFullSwipe: false) {
                            if let conID = position.con_id, conID > 0, position.position != 0,
                               position.security_type == "OPT" || (position.security_type == "STK" && position.position > 0) {
                                Button("Close") {
                                    positionDestination = PositionDestination(conID: conID, rollover: false)
                                }.tint(.orange).disabled(stockHasCall(position))
                                if position.security_type == "OPT" && position.position < 0 {
                                    Button("Rollover") {
                                        positionDestination = PositionDestination(conID: conID, rollover: true)
                                    }.tint(.blue)
                                }
                            }
                        }
                    }
                }
            }
            if let weekly = store.weekly {
                Section("Expiring this Friday") {
                    LabeledContent("Entry premium · not realized profit") { PremiumValue(amount: weekly.total_income, perSymbol: true) }
                    LabeledContent("Positions", value: String(weekly.positions_count))
                    LabeledContent("Put notional", value: money(weekly.total_put_notional))
                }
            }
            if store.portfolio == nil && !store.busy { ContentUnavailableView("No portfolio", systemImage: "chart.pie", description: Text("Connect your backend in Settings.")) }
        }.navigationTitle(localizedLabel("Portfolio", locale: locale)).refreshable { await store.refresh() }
            .navigationDestination(item: $positionDestination) { destination in
                if let position = store.portfolio?.positions.first(where: { $0.con_id == destination.conID && $0.position != 0 }) {
                    if destination.rollover && position.security_type == "OPT" && position.position < 0 {
                        RolloverTicket(position: position)
                    } else if !destination.rollover && !stockHasCall(position) {
                        CloseTicket(position: position)
                    } else { Text("Position changed. Return to Portfolio and review.") }
                } else { Text("Position changed. Return to Portfolio and review.") }
            }
            .navigationDestination(item: $summaryDestination) { destination in
                switch destination {
                case .performance: PerformanceView()
                case .margin: MarginOverview()
                case .allocation: AllocationView()
                }
            }
    }
    private func stockHasCall(_ position: Position) -> Bool {
        guard position.security_type == "STK" else { return false }
        return store.portfolio?.positions.contains { $0.symbol == position.symbol && $0.security_type == "OPT" && $0.option_type == "CALL" && $0.position < 0 } == true || store.orders.contains {
            $0.name == position.symbol && $0.option_type == "CALL" && $0.action == "SELL" && $0.intent != "CLOSE" && !["canceled", "cancelled", "rejected", "executed", "filled"].contains($0.status)
        }
    }
    func metric(_ title: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 4) { Text(LocalizedStringKey(title)).font(.caption).foregroundStyle(.secondary); Text(value).font(.subheadline.weight(.medium)).monospacedDigit() }
    }
}

struct AllocationItem: Identifiable {
    let id: String
    let name: String
    let value: Double
}

struct AllocationData {
    let assets: [AllocationItem]
    let liabilities: [AllocationItem]
    let missingCount: Int
    let net: Double?
    var total: Double { assets.reduce(0) { $0 + $1.value } }
    var accountedNet: Double { total + liabilities.reduce(0) { $0 + $1.value } }
    var difference: Double? { net.map { $0 - accountedNet } }

    init(_ portfolio: Bootstrap?) {
        var positive: [String: Double] = [:]
        var negative: [String: Double] = [:]
        var missing = 0
        for position in portfolio?.positions ?? [] where position.position != 0 {
            guard let value = position.market_value, value.isFinite else { missing += 1; continue }
            let symbol = position.symbol.uppercased()
            if value > 0 { positive[symbol, default: 0] += value }
            if value < 0 { negative[symbol, default: 0] += value }
        }
        var assets = positive.map { AllocationItem(id: "asset:\($0.key)", name: $0.key, value: $0.value) }
        var liabilities = negative.map { AllocationItem(id: "liability:\($0.key)", name: $0.key, value: $0.value) }
        if let cash = portfolio?.summary.cash_balance, cash.isFinite {
            if cash > 0 { assets.append(AllocationItem(id: "cash", name: "Cash", value: cash)) }
            if cash < 0 { liabilities.append(AllocationItem(id: "cash", name: "Cash", value: cash)) }
        } else if portfolio != nil { missing += 1 }
        self.assets = assets.sorted { $0.value == $1.value ? $0.id < $1.id : $0.value > $1.value }
        self.liabilities = liabilities.sorted { $0.value == $1.value ? $0.id < $1.id : $0.value < $1.value }
        missingCount = missing
        net = portfolio?.summary.account_value.flatMapFinite
    }
}

private extension Double {
    var flatMapFinite: Double? { isFinite ? self : nil }
}

struct AllocationView: View {
    @Environment(\.locale) private var locale
    @Environment(WheelStore.self) private var store
    @Environment(\.colorScheme) private var scheme
    @State private var selected: String?
    @State private var sharePresented = false
    @State private var angle: Double?
    private var data: AllocationData { AllocationData(store.portfolio) }
    private func color(_ item: AllocationItem) -> Color {
        if CoreAssetStyle.contains(item.name) { return TradingColors.symbol(item.name, scheme: scheme) }
        if item.id == "cash" { return .gray }
        let colors: [Color] = [.teal, .blue, .pink, .orange, .mint, .indigo]
        let keys = data.assets.filter { !CoreAssetStyle.contains($0.name) && $0.id != "cash" }.map(\.id).sorted()
        return colors[(keys.firstIndex(of: item.id) ?? 0) % colors.count]
    }
    var body: some View {
        List {
            Section {
                if data.total > 0 {
                    Chart(data.assets.sorted { $0.id < $1.id }) { item in
                        SectorMark(angle: .value("Market value", item.value), innerRadius: .ratio(0.72), angularInset: 1.5)
                            .foregroundStyle(color(item))
                            .opacity(selected == nil || selected == item.id ? 1 : 0.35)
                            .accessibilityLabel(item.name)
                            .accessibilityValue("\((item.value / data.total).formatted(.percent.precision(.fractionLength(1))))")
                    }
                    .chartAngleSelection(value: $angle)
                    .chartBackground { _ in
                        VStack(spacing: 5) {
                            Text("Net liquidation").font(.caption).foregroundStyle(.secondary)
                            Text(money(data.net)).font(.title3.weight(.semibold)).monospacedDigit()
                                .lineLimit(1).minimumScaleFactor(0.6)
                        }.frame(maxWidth: 160).allowsHitTesting(false)
                    }
                    .frame(height: 270)
                    .overlay {
                        ForEach(data.assets.filter { CoreAssetStyle.contains($0.name) }) { item in
                            CoreAssetAllocationFlow(items: data.assets.sorted { $0.id < $1.id }, symbol: item.name,
                                                    active: !sharePresented,
                                                    highlighted: selected == nil || selected == item.id)
                        }
                    }
                    .listRowBackground(Color.clear)
                } else { ContentUnavailableView("No portfolio", systemImage: "chart.pie") }
            }
            Section("Positive assets") {
                ForEach(data.assets) { item in
                    Button { selected = selected == item.id ? nil : item.id } label: {
                        HStack(spacing: 10) {
                            Circle().fill(color(item)).frame(width: 8, height: 8)
                            if item.id == "cash" { Text("Cash") } else { SymbolText(symbol: item.name) }
                            Spacer(minLength: 8)
                            VStack(alignment: .trailing, spacing: 3) {
                                Text(money(item.value)).monospacedDigit()
                                Text((item.value / data.total).formatted(.percent.precision(.fractionLength(1))))
                                    .font(.caption).foregroundStyle(.secondary).monospacedDigit()
                            }
                            if selected == item.id { Image(systemName: "checkmark").foregroundStyle(color(item)) }
                        }.contentShape(Rectangle())
                    }.buttonStyle(.plain)
                }
                LabeledContent {
                    Text(money(data.total)).monospacedDigit()
                } label: {
                    HStack(spacing: 10) {
                        Image(systemName: "square.3.layers.3d")
                            .font(.system(size: 11, weight: .medium))
                            .foregroundStyle(Color(red: 0.66, green: 0.59, blue: 0.43))
                            .frame(width: 8, height: 8)
                            .accessibilityHidden(true)
                        Text("Total")
                    }
                }
            }
            if !data.liabilities.isEmpty {
                Section("Short positions & negative cash") {
                    ForEach(data.liabilities) { item in
                        HStack {
                            if item.id == "cash" { Text("Cash") } else { SymbolText(symbol: item.name) }
                            Spacer()
                            Text(money(item.value)).monospacedDigit().foregroundStyle(.secondary)
                        }
                    }
                }
            }
            Section("Reconciliation") {
                LabeledContent("Estimated net value", value: money(data.accountedNet))
                LabeledContent("Net liquidation", value: money(data.net))
                LabeledContent("Difference", value: money(data.difference))
                if data.missingCount > 0 { Label("Some market values are unavailable", systemImage: "exclamationmark.triangle").foregroundStyle(.orange) }
                if let error = store.error { NoticeText(error).font(.caption).foregroundStyle(.orange) }
            }
        }
        .navigationTitle(localizedLabel("Allocation", locale: locale))
        .toolbar { ToolbarItem(placement: .topBarTrailing) {
            Button { sharePresented = true } label: { Image(systemName: "square.and.arrow.up") }
                .accessibilityLabel("Share holdings")
                .disabled(store.portfolio == nil)
        } }
        .sheet(isPresented: $sharePresented) { HoldingsSharePreview(portfolio: store.portfolio) }
        .refreshable { await store.refreshPortfolio() }
        .onChange(of: angle) {
            guard let angle else { return }
            var end = 0.0
            selected = data.assets.sorted { $0.id < $1.id }.first { item in end += item.value; return angle < end }?.id
        }
        .onChange(of: data.assets.map(\.id)) {
            if !data.assets.contains(where: { $0.id == selected }) { selected = nil }
        }
    }
}

private struct CoreAssetAllocationFlow: View {
    let items: [AllocationItem]
    let symbol: String
    let active: Bool
    let highlighted: Bool
    @Environment(\.scenePhase) private var phase
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.colorScheme) private var scheme
    @Environment(WheelStore.self) private var store
    @State private var visible = false

    var body: some View {
        if let index = items.firstIndex(where: { $0.name == symbol }), !reduceMotion {
            let total = items.reduce(0) { $0 + $1.value }
            let start = -90 + items.prefix(index).reduce(0) { $0 + $1.value } / max(total, 1) * 360
            let span = items[index].value / max(total, 1) * 360
            let feather = min(28.0, span * 0.16)
            TimelineView(.animation(minimumInterval: 1.0 / 30,
                                    paused: !visible || !active || phase != .active || store.selectedTab != "portfolio")) { context in
                let cycle = context.date.timeIntervalSinceReferenceDate.truncatingRemainder(dividingBy: 12) / 12
                let travel = (1 - cos(cycle * 2 * .pi)) / 2
                // Move the soft front fully beyond both ends before reversing.
                // Everything behind it stays gold, so the sector is revealed rather than scanned.
                let front = -feather + (span + 2 * feather) * travel
                let gold = Color(red: 0.66, green: 0.36, blue: 0.07)
                let strength = scheme == .dark ? 0.72 : 0.65
                // Only the feather needs intermediate stops; the rest is a solid fill.
                let colorAnchors = symbol == "SGOV" ? [Double]() : [span / 2, span]
                let angles = Set([0.0, 360.0] + colorAnchors + (-4...4).map { front + feather * Double($0) / 4 }
                    .filter { $0 > 0 && $0 < 360 }).sorted()
                let stops: [Gradient.Stop] = angles.map { angle in
                    let location = angle / 360
                    let coverage = min(1, max(0, (front - angle + feather) / max(2 * feather, 0.001)))
                    let softened = coverage * coverage * (3 - 2 * coverage)
                    let finish = symbol == "SGOV" ? gold : CoreAssetStyle.sectorColor(angle / max(span, 0.001))
                    return .init(color: finish.opacity((symbol == "SGOV" ? strength : 0.9) * softened), location: location)
                }
                AngularGradient(stops: stops, center: .center,
                                startAngle: .degrees(start), endAngle: .degrees(start + 360))
            }
            .mask {
                Chart(items) { item in
                    SectorMark(angle: .value("Market value", item.value), innerRadius: .ratio(0.72), angularInset: 1.5)
                        .foregroundStyle(item.name == symbol ? Color.white : Color.clear)
                }
            }
            .opacity(highlighted ? 1 : 0.35)
            .allowsHitTesting(false).accessibilityHidden(true)
            .onAppear { visible = true }.onDisappear { visible = false }
        }
    }
}

private struct PerformanceShimmerLabel: View {
    @Environment(\.locale) private var locale
    @Environment(\.customPalette) private var palette
    @Environment(\.colorScheme) private var scheme
    @Environment(\.scenePhase) private var phase
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(WheelStore.self) private var store
    @State private var visible = false

    private var lettering: Text {
        let title = localizedLabel("Performance", locale: locale)
        return Text(verbatim: title == "Performance" ? "𝒫ℯ𝓇𝒻ℴ𝓇𝓂𝒶𝓃𝒸ℯ" : title)
    }
    var body: some View {
        let gain = palette.color("gain", scheme: scheme, fallback: FinancialColors.gain)
        let loss = palette.color("loss", scheme: scheme, fallback: FinancialColors.loss)
        TimelineView(.animation(minimumInterval: 1.0 / 30,
                                paused: !visible || phase != .active || reduceMotion || store.selectedTab != "portfolio")) { context in
            let progress = reduceMotion ? 0 : context.date.timeIntervalSinceReferenceDate.truncatingRemainder(dividingBy: 8) / 8
            lettering.hidden()
                .overlay {
                    GeometryReader { geometry in
                        LinearGradient(colors: [PerformanceColors.spx, .orange, gain, loss, PerformanceColors.spx, .orange, gain, loss, PerformanceColors.spx],
                                       startPoint: .leading, endPoint: .trailing)
                            .frame(width: geometry.size.width * 2)
                            .offset(x: -geometry.size.width * progress)
                    }
                    .mask(lettering)
                    .allowsHitTesting(false)
                }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(Text("Performance"))
        .onAppear { visible = true }
        .onDisappear { visible = false }
    }
}

enum CoreAssetStyle {
    static let symbols = ["SGOV", "VTI", "QQQ", "SPY", "VOO"]
    static func contains(_ symbol: String) -> Bool { symbols.contains(symbol.uppercased()) }
    static func lettering(_ symbol: String) -> String {
        ["SGOV": "𝕊𝔾𝕆𝕍", "VTI": "𝕍𝕋𝕀", "QQQ": "ℚℚℚ", "SPY": "𝕊ℙ𝕐", "VOO": "𝕍𝕆𝕆"][symbol.uppercased()] ?? symbol
    }
    static let red = Color(red: 0.84, green: 0.13, blue: 0.09)
    static let brightGold = Color(red: 1, green: 0.84, blue: 0.32)
    static let darkGold = Color(red: 0.58, green: 0.30, blue: 0.05)
    static let signatureFlow: [Color] = [.clear, red, brightGold, darkGold, .clear]
    static func sectorColor(_ fraction: Double) -> Color {
        let stops: [(Double, Double, Double)] = [(0.84, 0.13, 0.09), (1, 0.84, 0.32), (0.58, 0.30, 0.05)]
        let t = min(1, max(0, fraction)) * 2
        let index = min(1, Int(t)), mix = t - Double(min(1, Int(t)))
        let a = stops[index], b = stops[index + 1]
        return Color(red: a.0 + (b.0 - a.0) * mix, green: a.1 + (b.1 - a.1) * mix, blue: a.2 + (b.2 - a.2) * mix)
    }
}

struct SymbolText: View {
    let symbol: String
    @Environment(\.colorScheme) private var scheme
    @Environment(\.scenePhase) private var phase
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var visible = false
    var body: some View {
        if CoreAssetStyle.contains(symbol) {
            TimelineView(.animation(minimumInterval: 1.0 / 30, paused: !visible || phase != .active || reduceMotion)) { context in
                let progress = reduceMotion ? 0.5 : context.date.timeIntervalSinceReferenceDate.truncatingRemainder(dividingBy: 5) / 5
                Text(verbatim: CoreAssetStyle.lettering(symbol)).foregroundStyle(TradingColors.symbol(symbol, scheme: scheme))
                    .overlay {
                        if !reduceMotion {
                            GeometryReader { geometry in
                                LinearGradient(colors: symbol.uppercased() == "SGOV" ? [.clear, scheme == .dark ? Color.white : Color(red: 0.48, green: 0.23, blue: 0.02), .clear] : CoreAssetStyle.signatureFlow, startPoint: .leading, endPoint: .trailing)
                                    .frame(width: geometry.size.width * 0.65)
                                    .offset(x: geometry.size.width * (progress * 1.65 - 0.65))
                            }.mask(Text(verbatim: CoreAssetStyle.lettering(symbol))).allowsHitTesting(false)
                        }
                    }
            }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(Text(verbatim: symbol))
            .onAppear { visible = true }.onDisappear { visible = false }
        } else {
            Text(symbol)
        }
    }
}

extension View {
    @ViewBuilder func symbolTitle(_ symbol: String) -> some View {
        if CoreAssetStyle.contains(symbol) {
            self.navigationTitle(symbol).navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .principal) { SymbolText(symbol: symbol).font(.headline) } }
        } else {
            self.navigationTitle(symbol)
        }
    }
}

enum TradingColors {
    static func symbol(_ symbol: String, scheme: ColorScheme) -> Color {
        guard CoreAssetStyle.contains(symbol) else { return .primary }
        if symbol.uppercased() != "SGOV" { return scheme == .dark ? CoreAssetStyle.brightGold : CoreAssetStyle.darkGold }
        return scheme == .dark ? Color(red: 1.00, green: 0.88, blue: 0.58) : Color(red: 0.78, green: 0.60, blue: 0.16)
    }
    static func profit(_ scheme: ColorScheme) -> Color {
        FinancialColors.gain
    }
}

struct PositionMarketPrice: View {
    @Environment(\.customPalette) private var customPalette
    @Environment(\.scenePhase) private var phase
    @State private var visible = false
    let position: Position
    @Environment(WheelStore.self) private var store
    @Environment(\.colorScheme) private var scheme
    var body: some View {
        TimelineView(.animation(minimumInterval: 1, paused: !visible || phase != .active || store.selectedTab != "portfolio")) { context in
            let fresh = !store.demo && store.error == nil && context.date.timeIntervalSince(store.updated ?? .distantPast) < 15
            let direction = fresh ? (store.priceDirections[position.id] ?? 0) : 0
            Text(money(position.market_price)).monospacedDigit()
                .foregroundStyle(direction > 0 ? customPalette.color("gain", scheme: scheme, fallback: FinancialColors.gain) : direction < 0 ? customPalette.color("loss", scheme: scheme, fallback: FinancialColors.loss) : Color.primary)
        }
        .onAppear { visible = true }
        .onDisappear { visible = false }
    }
}

struct PositionPnLMeter: View {
    @Environment(\.customPalette) private var customPalette
    @Environment(\.colorScheme) private var colorScheme
    let position: Position
    private var profitColor: Color {
        customPalette.color("gain", scheme: colorScheme, fallback: FinancialColors.gain)
    }
    private var lossColor: Color {
        customPalette.color("loss", scheme: colorScheme, fallback: FinancialColors.loss)
    }
    private var amountColor: Color {
        guard let pnl = position.unrealized_pnl, pnl.isFinite, pnl != 0 else { return .secondary }
        return pnl > 0 ? profitColor : lossColor
    }
    private var glowColor: Color {
        guard colorScheme == .dark, let pnl = position.unrealized_pnl,
              pnl.isFinite, pnl != 0 else { return .clear }
        return amountColor.opacity(0.35)
    }
    private var percentage: Double? {
        guard let cost = position.avg_cost, let pnl = position.unrealized_pnl else { return nil }
        // IB average cost already includes the option contract multiplier.
        let basis = abs(cost * position.position)
        guard basis.isFinite, basis > 0, pnl.isFinite else { return nil }
        let result = pnl / basis * 100
        return result.isFinite ? result : nil
    }
    var body: some View {
        VStack(alignment: .trailing, spacing: 5) {
            ViewThatFits(in: .horizontal) {
                HStack(spacing: 6) { amount; returnRate }
                VStack(alignment: .trailing, spacing: 3) { amount; returnRate }
            }
        }
    }
    private var amount: some View {
        Text(money(position.unrealized_pnl))
            .font(.caption).monospacedDigit()
            .foregroundStyle(amountColor)
            .shadow(color: glowColor, radius: 2)
    }
    @ViewBuilder private var returnRate: some View {
        if let percentage {
            Text(percentage.formatted(.number.precision(.fractionLength(1)).sign(strategy: .always())) + "%")
                .font(.caption2).monospacedDigit()
                .foregroundStyle(percentage == 0 ? Color.secondary : (percentage > 0 ? profitColor : lossColor))
                .shadow(color: percentage == 0 ? .clear : glowColor, radius: 2)
        }
    }
}

struct LeverageMeter: View {
    let percentage: Double?
    var showsLabel = true
    private var value: Double? { percentage.flatMap { $0.isFinite ? $0 : nil } }
    private var tint: Color {
        guard let value else { return .secondary }
        return value < 30 ? .green : value < 60 ? .yellow : .red
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if showsLabel {
                LabeledContent("Leverage", value: value.map { String(format: "%.1f%%", $0) } ?? "—")
                    .monospacedDigit()
            }
            ProgressView(value: min(100, max(0, value ?? 0)), total: 100)
                .tint(tint)
                .accessibilityHidden(true)
        }.padding(.vertical, 4)
    }
}

struct PositionDetail: View {
    let position: Position
    @Environment(\.locale) private var locale
    @Environment(WheelStore.self) private var store
    private var latest: Position { store.portfolio?.positions.first { $0.id == position.id } ?? position }
    private var stockHasCall: Bool {
        guard latest.security_type == "STK" else { return false }
        return store.portfolio?.positions.contains { $0.symbol == latest.symbol && $0.security_type == "OPT" && $0.option_type == "CALL" && $0.position < 0 } == true || store.orders.contains {
            $0.name == latest.symbol && $0.option_type == "CALL" && $0.action == "SELL" && $0.intent != "CLOSE" && !["canceled", "cancelled", "rejected", "executed", "filled"].contains($0.status)
        }
    }
    var body: some View {
        Form {
            if latest.hasChart {
                Section { Button("𝑺𝒖𝒑𝒆𝒓𝒄𝒉𝒂𝒓𝒕𝒔") { store.openTradeChart(latest) } }
            }
            if latest.security_type == "STK", let cost = latest.reported_cost {
                Section {
                    LabeledContent("Average cost", value: cost.average.formatted(.currency(code: cost.currency)))
                    LabeledContent("Cost basis", value: cost.basis.formatted(.currency(code: cost.currency)))
                    LabeledContent("Report date", value: cost.date)
                    LabeledContent("Reported shares", value: cost.quantity.formatted())
                    if abs(cost.quantity - latest.position) > 0.000001 {
                        Text("Reported shares differ from current holdings. This cost snapshot does not describe the current position.")
                            .font(.caption).foregroundStyle(.orange)
                    }
                } header: {
                    Text("IBKR reported cost")
                } footer: {
                    Text("Official report snapshot. Live Gateway cost and P&L below use a separate basis; recent trades may not yet be included.")
                }
            }
            Section(position.detail) {
                LabeledContent("Quantity", value: latest.position.formatted())
                LabeledContent("Gateway average cost", value: money(latest.avg_cost))
                if latest.optionAverageUsesBrokerCost {
                    Text(locale.language.languageCode?.identifier == "zh" ? "* IB 平均成本，可能含手续费" : "* IB average cost; may include fees")
                        .font(.caption).foregroundStyle(.secondary)
                }
                LabeledContent("Current price", value: money(latest.market_price))
                LabeledContent("Market value", value: money(latest.market_value))
                LabeledContent("Unrealized P&L", value: money(latest.unrealized_pnl))
                ArrowlessNavigationLink("Margin impact") { PositionMarginView(position: latest) }
            }
            if store.portfolio?.positions.contains(where: { $0.id == position.id && $0.position != 0 }) == true,
               (position.security_type == "OPT" || (position.security_type == "STK" && latest.position > 0)), let conID = position.con_id, conID > 0 {
                Section {
                    ArrowlessNavigationLink("Close") { CloseTicket(position: latest) }.disabled(stockHasCall)
                    if stockHasCall { Text("Close covered CALLs before selling shares.").font(.caption).foregroundStyle(.orange) }
                    if latest.security_type == "OPT" && latest.position < 0 { ArrowlessNavigationLink("Rollover") { RolloverTicket(position: latest) } }
                }
            }
        }.symbolTitle(position.symbol)
    }
}

// Build one linear projection per render; never re-filter the complete history per row.
struct ExecutionHistoryPage {
    var orders: [Order]
    var headings: [OrderID: String]
    var total: Int
    static var empty: Self { Self(orders: [], headings: [:], total: 0) }
    static func build(_ source: [Order], days: Int, asset: String, search: String, limit: Int, now: Date = .now) -> Self {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "America/New_York")!
        let today = calendar.startOfDay(for: now)
        let start = (days == 0 || days == 30)
            ? calendar.date(from: calendar.dateComponents([.year, .month], from: today))!
            : calendar.date(byAdding: .day, value: -(max(1, days) - 1), to: today)!
        let end = calendar.date(byAdding: .day, value: 1, to: today)!
        let query = search.trimmingCharacters(in: .whitespacesAndNewlines)
        let fractional = Date.ISO8601FormatStyle(includingFractionalSeconds: true)
        let integral = Date.ISO8601FormatStyle(includingFractionalSeconds: false)
        let label = DateFormatter()
        label.locale = Locale(identifier: "en_US_POSIX")
        label.timeZone = calendar.timeZone; label.dateFormat = "MMM d, yyyy"
        var result = Self.empty
        var seenDays = Set<Date>()
        var seenIDs = Set<OrderID>()
        for order in source {
            guard seenIDs.insert(order.id).inserted, let text = order.fill_time,
                  let date = (try? fractional.parse(text)) ?? (try? integral.parse(text)), date >= start, date < end else { continue }
            let kind = (order.option_type ?? "").uppercased()
            let category = kind == "STOCK" ? "STOCK" : kind == "FUTURE" ? "FUTURE" : ["CALL", "PUT", "C", "P"].contains(kind) ? "OPTION" : "UNKNOWN"
            guard asset == "ALL" || asset == category else { continue }
            guard query.isEmpty || [order.name, order.expiration ?? "", order.option_type ?? ""].joined(separator: " ").localizedCaseInsensitiveContains(query) else { continue }
            result.total += 1
            guard result.orders.count < max(0, limit) else { continue }
            result.orders.append(order)
            if seenDays.insert(calendar.startOfDay(for: date)).inserted { result.headings[order.id] = label.string(from: date) }
        }
        return result
    }
}

struct OrdersView: View {
    @Environment(\.scenePhase) private var phase
    @Environment(\.locale) private var locale
    @Environment(WheelStore.self) private var store
    @AppStorage("confirmBeforeOrderExecution") private var confirmExecution = true
    @State private var history = false
    @AppStorage("executionHistoryDaysV2") private var historyDays = 1
    @State private var historySearch = ""
    @State private var historySearchExpanded = false
    @AppStorage("executionHistoryAsset") private var historyAsset = "ALL"
    @FocusState private var historySearchFocused: Bool
    @State private var historyLimit = 50
    @State private var cancelAll = false
    @State private var cancelling = false
    @State private var quickOrder: Order?
    @State private var quickCancel = false
    private var refreshHistory: Bool { RefreshLoop.shouldRefreshHistory(tab: store.selectedTab, showingHistory: true, active: phase == .active) }
    private var cancelable: [Order] { store.orders.filter { TradeRules.cancelable($0) } }
    var body: some View {
        let page = history ? ExecutionHistoryPage.build(store.filledOrders, days: historyDays, asset: historyAsset, search: historySearch, limit: historyLimit) : ExecutionHistoryPage.empty
        let displayedOrders = history ? page.orders : store.orders
        List {
            HStack(alignment: .lastTextBaseline) {
                Text(localizedLabel("Orders", locale: locale)).font(.largeTitle.bold())
                Spacer(minLength: 12)
                if !history {
                    Menu {
                        Toggle("Confirm execution and cancellation", isOn: $confirmExecution)
                    } label: {
                        Image(systemName: confirmExecution ? "checkmark.shield.fill" : "shield.slash")
                            .font(.system(size: 18, weight: .medium))
                            .foregroundStyle(confirmExecution ? Color.primary : Color.secondary)
                            .frame(width: 44, height: 44)
                            .background(Color.secondary.opacity(0.12), in: RoundedRectangle(cornerRadius: 12))
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("Confirm execution and cancellation")
                    .accessibilityValue(confirmExecution ? Text("On") : Text("Off"))
                }
                OrdersDailyProfit(days: history ? historyDays : 1)
            }.listRowBackground(Color.clear).listRowSeparator(.hidden)
            StatusView(orders: true)
            Picker("Orders", selection: $history) { Text("Pending").tag(false); Text("Executed records").tag(true) }.pickerStyle(.segmented)
            if history {
                HStack {
                    Picker("Date range", selection: $historyDays) {
                        Text("Today").tag(1)
                        Text("7 Days").tag(7)
                        Text("MTD").tag(0)
                    }.labelsHidden().pickerStyle(.menu).fixedSize()
                    Spacer(minLength: 4)
                    if historySearchExpanded {
                        TextField("Search", text: $historySearch)
                            .focused($historySearchFocused).submitLabel(.search)
                            .onSubmit { historySearchFocused = false }
                            .textInputAutocapitalization(.characters).autocorrectionDisabled()
                            .frame(maxWidth: 150)
                        Button { historySearch = ""; historySearchFocused = false; historySearchExpanded = false } label: {
                            Image(systemName: "xmark").frame(width: 32, height: 40)
                        }.buttonStyle(.plain).accessibilityLabel("Close search")
                    } else {
                        Button { historySearchExpanded = true; historySearchFocused = true } label: {
                            Image(systemName: "magnifyingglass").frame(width: 40, height: 40)
                        }.buttonStyle(.plain).accessibilityLabel("Search executions")
                    }
                    Menu {
                        Picker("Asset type", selection: $historyAsset) {
                            Text("All").tag("ALL")
                            Text("Stock").tag("STOCK")
                            Text("Future").tag("FUTURE")
                            Text("Option").tag("OPTION")
                        }
                    } label: {
                        Label(historyAsset == "ALL" ? "Filter" : historyAsset == "STOCK" ? "Stock" : historyAsset == "FUTURE" ? "Future" : "Option", systemImage: "line.3.horizontal.decrease")
                            .font(.subheadline).fixedSize().frame(minHeight: 40)
                    }.tint(.primary)

                }
            }
            if history, let error = store.filledError {
                NoticeText(error).font(.caption).foregroundStyle(.orange)
            }
            if store.ordersRetrying {
                Text("Connection interrupted. Retrying…").font(.caption).foregroundStyle(.orange)
            } else if let error = store.orderError {
                DisclosureGroup("Order status needs verification") {
                    NoticeText(error).font(.caption).textSelection(.enabled)
                }.disclosureGroupStyle(ArrowlessDisclosureStyle()).foregroundStyle(.orange)
            } else if let error = store.error { NoticeText(error).foregroundStyle(.orange) }
            if displayedOrders.isEmpty && store.orderError == nil && store.error == nil && (!history || store.filledError == nil) {
                ContentUnavailableView("No orders", systemImage: "checkmark.circle")
            }
            ForEach(displayedOrders) { order in
                if history, let heading = page.headings[order.id] {
                    Text(heading).font(.subheadline.weight(.semibold))
                        .listRowBackground(Color.secondary.opacity(0.12))
                }
                ArrowlessNavigationLink {
                    Group {
                    if history { Form { SymbolText(symbol: order.name); Text(order.option_type == "FUTURE" ? "\(order.expiration ?? "") · FUTURE" : "\(order.expiration ?? "") · \(money(order.strike)) · \(order.option_type ?? "")"); LabeledContent("Status", value: order.ib_status ?? order.status); LabeledContent("Action", value: order.fill_action ?? order.action ?? "—"); LabeledContent("Last fill time", value: order.fillTimeLabel); LabeledContent("Commission", value: order.commissionLabel); if order.option_type == "FUTURE" { FuturesProfit(order: order) } else if order.intent == "CLOSE" { LabeledContent("Realized P&L") { RealizedProfit(order: order) } }; LabeledContent("Average fill price", value: money(order.fillPrice)); LabeledContent("Filled quantity", value: order.filledQuantity?.formatted() ?? "—"); LabeledContent("Limit", value: money(order.premium)) } }
                    else { OrderDetail(initial: order) }
                    }.toolbar(.visible, for: .navigationBar)
                } label: {
                    CompactOrderRow(order: order, history: history)
                }
                .swipeActions(edge: .trailing, allowsFullSwipe: false) {
                    if !history && TradeRules.editable(order) {
                        Button("Execute", systemImage: "paperplane") {
                            if confirmExecution { quickCancel = false; quickOrder = order }
                            else { performQuick(order, cancel: false) }
                        }.tint(.teal)
                    }
                }
                .swipeActions(edge: .leading, allowsFullSwipe: false) {
                    if !history && TradeRules.cancelable(order) {
                        Button(TradeRules.protectionCancelable(order) ? "Cancel TP/SL" : "Cancel order", systemImage: "xmark.circle") {
                            if confirmExecution || TradeRules.protectionCancelable(order) { quickCancel = true; quickOrder = order }
                            else { performQuick(order, cancel: true) }
                        }.tint(.red)
                    }
                }
            }
            if history && page.total > displayedOrders.count {
                Button(locale.language.languageCode?.identifier == "zh" ? "加载更多（已显示 \(displayedOrders.count) / \(page.total)）" : "Load more (\(displayedOrders.count) / \(page.total))") { historyLimit += 50 }
            }
            if !history { Button("Cancel all eligible (\(cancelable.count))", role: .destructive) {
                if confirmExecution || cancelable.contains(where: TradeRules.protectionCancelable) { cancelAll = true } else { performCancelAll() }
            }.disabled(cancelable.isEmpty) }
            TradingNotice()
        }.scrollDismissesKeyboard(.immediately)
        .onAppear { if historyDays == 30 { historyDays = 0 } }
        .onChange(of: history) { historySearchFocused = false }
        .onChange(of: historyDays) { historySearchFocused = false; historyLimit = 50 }
        .onChange(of: historyAsset) { historySearchFocused = false; historyLimit = 50 }
        .onChange(of: historySearch) { historyLimit = 50 }
        .onDisappear { historySearchFocused = false }
        .toolbar { ToolbarItemGroup(placement: .keyboard) { Spacer(); Button("Done") { historySearchFocused = false } } }
        .navigationTitle("").navigationBarTitleDisplayMode(.inline).toolbar(.hidden, for: .navigationBar).refreshable { if history { await store.loadFilled() } else { await store.refresh() } }
        .task(id: "history-\(refreshHistory)-\(store.demo)-\(store.address)") {
            if refreshHistory { await store.loadFilled() }
        }
        .onChange(of: store.ordersUpdated) { if refreshHistory { Task { await store.loadFilled() } } }
        .onChange(of: "\(store.demo)-\(store.address)") { quickOrder = nil; cancelAll = false }
        .disabled(cancelling || store.trading.busy || store.opportunities.batchRunning)
        .confirmationDialog(LocalizedStringKey(quickCancel ? "Cancel order" : "Execute"), isPresented: Binding(get: { quickOrder != nil }, set: { if !$0 { quickOrder = nil } }), titleVisibility: .visible) {
            Button(LocalizedStringKey(quickCancel ? "Cancel order" : "Execute"), role: quickCancel ? .destructive : nil) {
                if let order = quickOrder { performQuick(order, cancel: quickCancel) }
                quickOrder = nil
            }
        } message: {
            if let order = quickOrder {
                if quickCancel && TradeRules.protectionCancelable(order) { Text("Both TP and SL will be canceled. The position remains open without protection.") }
                Text("\(order.name) · \(order.action ?? "") · \(order.option_type ?? "") · \(money(order.strike)) · \(order.expiration ?? "")\n\(order.quantity?.formatted() ?? "—") · \(money(order.premium)) · \(order.timingLabel)\n\(localizedLabel(store.demo ? "Simulation only" : "Connected backend · real orders may execute", locale: locale))")
            }
        }
        .confirmationDialog("Cancel \(cancelable.count) eligible orders?", isPresented: $cancelAll, titleVisibility: .visible) {
            Button("Cancel eligible orders", role: .destructive) {
                performCancelAll()
            }
        } message: { Text("Unknown and unsupported orders are excluded. TP/SL pairs are canceled together; positions remain open without protection. Stops on the first failure. Wait for IB confirmation.") }
    }
    private func performCancelAll() {
        guard !cancelling, !store.trading.busy, !store.opportunities.batchRunning else { return }
        let snapshot = cancelable
        let context = "\(store.demo)-\(store.address)"
        cancelling = true
        Task {
            defer { cancelling = false }
            for order in snapshot {
                guard context == "\(store.demo)-\(store.address)" else { break }
                guard let current = store.orders.first(where: { $0.id == order.id }),
                      TradeRules.cancelable(current) else { continue }
                if !(await store.trading.cancelFromOrders(current, store: store)) { break }
            }
            await store.refreshOrders()
        }
    }
    private func performQuick(_ snapshot: Order, cancel: Bool) {
        let context = "\(store.demo)-\(store.address)"
        Task {
            guard context == "\(store.demo)-\(store.address)", !history, !cancelling, !store.trading.busy, !store.opportunities.batchRunning,
                  let current = store.orders.first(where: { $0.id == snapshot.id }),
                  cancel ? TradeRules.cancelable(current) : TradeRules.editable(current),
                  TradeRules.unchanged(current, since: snapshot) else { return }
            if cancel { _ = await store.trading.cancelFromOrders(current, store: store) }
            else if let id = current.id.local { _ = await store.trading.write("api/options/execute/\(id)", store: store) }
            await store.refreshOrders()
        }
    }
}

struct SettingsView: View {
    @AppStorage("wheel.native.sounds") private var tradingSoundsEnabled = true
    private static let appVersion: String = {
        let version = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String
        let build = Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String
        let label = version.flatMap { $0.isEmpty ? nil : $0 } ?? "—"
        guard let build, !build.isEmpty else { return label }
        return "\(label) (\(build))"
    }()
    @Environment(\.locale) private var locale
    @AppStorage("appearance") private var appearance = "system"
    @AppStorage("appLanguage") private var appLanguage = "system"
    @Environment(WheelStore.self) private var store
    @State private var draft = "https://"
    @State private var reviewed = false
    @State private var requestedMode = "demo"
    @State private var switchingAccount = false
    @State private var accountSwitchMessage: String?
    private var hasAddress: Bool {
        let value = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        return !value.isEmpty && value != "https://"
    }
    @FocusState private var addressFocused: Bool
    private func selectMode(_ mode: String, force: Bool = false) {
        guard !switchingAccount, !store.trading.busy else { return }
        requestedMode = mode
        if !force && requestedMode == (store.demo ? "demo" : store.portfolio?.connection?.mode) && (store.demo || store.isConnected(to: draft.trimmingCharacters(in: .whitespacesAndNewlines))) { return }
        if requestedMode == "demo" { store.demo = true; store.changeMode(); accountSwitchMessage = nil; return }
        guard hasAddress else { accountSwitchMessage = "Enter your private HTTPS backend address in Settings."; return }
        let target = requestedMode
        let requestedAddress = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        UserDefaults.standard.set(target, forKey: "selectedBrokerMode")
        switchingAccount = true; addressFocused = false
        store.address = requestedAddress
        store.demo = true; store.changeMode()
        RecentStockCharts.packets.removeAll(); RecentStockCharts.lastSaved.removeAll()
        UserDefaults.standard.removeObject(forKey: RecentStockCharts.diskKey)
        Task {
            defer { switchingAccount = false }
            do {
                var result = try await store.trading.selectAccount(base: requestedAddress, mode: target)
                let deadline = Date().addingTimeInterval(180)
                while try AccountConnectionRules.verifiedEpoch(result, mode: target) == nil && Date() < deadline {
                    accountSwitchMessage = result["message"] as? String ?? "Waiting for Gateway login…"
                    if let gateway = result["gateway"] as? [String: Any], let error = gateway["error"] as? String {
                        throw AppError.message(error)
                    }
                    try await Task.sleep(for: .seconds(1))
                    do {
                        result = try await store.trading.get("api/account/profiles", base: requestedAddress)
                    } catch let failure as BackendHTTPError where [502, 503, 504].contains(failure.status) {
                        continue // Gateway login temporarily occupies the serialized IB connection.
                    } catch let failure as URLError where failure.code == .timedOut {
                        continue
                    }
                    guard result["selected"] as? String == target else {
                        throw AppError.message("Another device changed the selected account. Select your account again.")
                    }
                }
                guard let epoch = try AccountConnectionRules.verifiedEpoch(result, mode: target) else {
                    throw AppError.message("Gateway login is still pending. Complete IB Key if prompted, then retry connection.")
                }
                accountSwitchMessage = "Loading account…"
                try await store.completeAccountConnection(to: requestedAddress, mode: target, epoch: epoch)
                accountSwitchMessage = nil
            } catch {
                accountSwitchMessage = connectionMessage(error)
            }
        }
    }
    private var accessLabel: String {
        localizedLabel(store.accountModeLabel, locale: locale)
    }
    var body: some View {
        @Bindable var store = store
        Form {
            Section("Connection") {
                HStack(spacing: 3) {
                    ForEach(["demo", "live", "paper"], id: \.self) { mode in
                        let selected = requestedMode == mode
                        let color: Color = mode == "live" ? .green : mode == "paper" ? .red : Color(uiColor: .systemGray)
                        Button { selectMode(mode) } label: {
                            Text(mode == "demo" ? "Demo" : mode == "live" ? "Live" : "Paper")
                                .font(.subheadline.weight(.semibold))
                                .frame(maxWidth: .infinity, minHeight: 32)
                                .foregroundStyle(selected ? Color.white : Color.primary)
                                .background(selected ? color : Color.clear, in: RoundedRectangle(cornerRadius: 7))
                        }
                        .buttonStyle(.plain)
                        .accessibilityAddTraits(selected ? .isSelected : [])
                    }
                }
                .padding(3)
                .background(Color(uiColor: .tertiarySystemFill), in: RoundedRectangle(cornerRadius: 9))
                .disabled(switchingAccount || store.trading.busy)
                if switchingAccount { ProgressView("Switching account…") }
                if let accountSwitchMessage { Text(localizedLabel(accountSwitchMessage, locale: locale)).font(.footnote).foregroundStyle(.orange) }
                if requestedMode != "demo" {
                TextField("https://your-mini.ts.net", text: $draft).textInputAutocapitalization(.never).autocorrectionDisabled().keyboardType(.URL).focused($addressFocused).submitLabel(.done)
                    .disabled(switchingAccount)
                    .onSubmit { addressFocused = false; selectMode(requestedMode, force: true) }
                    .onChange(of: addressFocused) { previous, focused in
                        if previous && !focused && hasAddress && draft.trimmingCharacters(in: .whitespacesAndNewlines) != store.address {
                            selectMode(requestedMode, force: true)
                        }
                    }
                if !switchingAccount && store.isConnected(to: draft) && store.portfolio?.connection?.mode == requestedMode {
                    Label("Connected", systemImage: "checkmark.circle.fill").foregroundStyle(.green)
                } else if !switchingAccount && (accountSwitchMessage != nil || store.error != nil) {
                    Button("Retry connection") { selectMode(requestedMode, force: true) }
                        .disabled(!hasAddress || store.trading.busy)
                }
                if !switchingAccount, let error = store.error { NoticeText(error).font(.footnote).foregroundStyle(.orange) }
                }
            }
            Section("Appearance") {
                HStack {
                    Label("Language", systemImage: "globe")
                    Spacer(minLength: 8)
                    Menu {
                        Picker("Language", selection: $appLanguage) {
                            Text("System").tag("system")
                            Text(verbatim: "English").tag("en")
                            Text(verbatim: "简体中文").tag("zh-Hans")
                            Text(verbatim: "繁體中文").tag("zh-Hant")
                        }
                    } label: {
                        SettingsChoiceLabel(value: appLanguage == "en" ? "English" : appLanguage == "zh-Hans" ? "简体中文" : appLanguage == "zh-Hant" ? "繁體中文" : localizedLabel("System", locale: locale), widthReference: appLanguage == "en" ? "System" : nil)
                    }.buttonStyle(.plain).accessibilityLabel(Text("Language"))
                }
                HStack {
                    Label("Theme", systemImage: "circle.lefthalf.filled")
                    Spacer(minLength: 8)
                    Menu {
                        Picker("Theme", selection: $appearance) {
                            Text("System").tag("system")
                            Text("Light").tag("light")
                            Text("Dark").tag("dark")
                        }
                    } label: {
                        SettingsChoiceLabel(value: localizedLabel(appearance == "light" ? "Light" : appearance == "dark" ? "Dark" : "System", locale: locale))
                    }.buttonStyle(.plain).accessibilityLabel(Text("Theme"))
                }
                NavigationLink { MetricPalettePreview() } label: {
                    Label("Custom colors", systemImage: "paintpalette")
                }
                Toggle(isOn: $tradingSoundsEnabled) {
                    Label(locale.language.languageCode?.identifier == "zh" ? "交易提示音" : "Trading sounds", systemImage: "speaker.wave.2")
                }
                .onChange(of: tradingSoundsEnabled) { _, enabled in if !enabled { ChartTradeSounds.shared.stop() } }
            }.tint(.teal)
            if store.trading.uncertain {
                Section("Unconfirmed request") {
                    Text("Check the exact order in IB and the web app, including fills and pending orders. Clearing this lock does not cancel or resubmit anything.")
                    Button("I have verified the order outcome") { reviewed = true }
                }
            }
            Section {
                LabeledContent("Minimum iOS") { Text(verbatim: "18.0") }
                ArrowlessNavigationLink { TradingAccessView() } label: {
                    LabeledContent("Access & Feedback") { Text(verbatim: accessLabel) }
                }
                LabeledContent("Version") { Text(verbatim: Self.appVersion) }
            } header: {
                Text("App")
            } footer: {
                GildedSignature()
                    .textCase(nil)
                    .frame(maxWidth: .infinity, alignment: .center)
                    .padding(.top, 8)
                    .padding(.bottom, 4)
                    .accessibilityLabel(Text(verbatim: "Ben"))
            }
        }
        .listSectionSpacing(12)
        .navigationTitle(localizedLabel("Settings", locale: locale)).onAppear { if !switchingAccount && accountSwitchMessage == nil { requestedMode = store.demo ? "demo" : (store.portfolio?.connection?.mode ?? UserDefaults.standard.string(forKey: "selectedBrokerMode") ?? "paper") }; draft = store.address.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? "https://" : store.address }
        .disabled(store.trading.busy || store.opportunities.batchRunning)
        .confirmationDialog("Have you verified the order in IB and the web app?", isPresented: $reviewed, titleVisibility: .visible) {
            Button("Verified · unlock trading") { store.trading.acknowledgeReview() }
        }
    }
}

private struct SettingsChoiceLabel: View {
    let value: String
    var widthReference: String? = nil
    var body: some View {
        HStack(spacing: 8) {
            ZStack {
                if let widthReference { Text(verbatim: widthReference).hidden().accessibilityHidden(true) }
                Text(verbatim: value)
            }.lineLimit(1).minimumScaleFactor(0.8)
            Image(systemName: "chevron.up.chevron.down")
                .font(.caption.weight(.semibold)).accessibilityHidden(true)
        }
        .foregroundStyle(.teal)
        .padding(.horizontal, 10)
        .frame(minHeight: 36)
        .background(Color(uiColor: .tertiarySystemFill), in: RoundedRectangle(cornerRadius: 7))
        .contentShape(Rectangle())
    }
}

private struct GildedSignature: View {
    @Environment(WheelStore.self) private var store
    @Environment(\.scenePhase) private var phase
    @Environment(\.colorScheme) private var scheme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var visible = false
    private var lettering: some View {
        Text(verbatim: "𝓑𝓮𝓷").font(.system(size: 26, weight: .regular))
    }
    var body: some View {
        TimelineView(.animation(minimumInterval: 1.0 / 30,
                                paused: !visible || phase != .active || store.selectedTab != "settings" || reduceMotion)) { context in
            let progress = context.date.timeIntervalSinceReferenceDate.truncatingRemainder(dividingBy: 5) / 5
            lettering.foregroundStyle(scheme == .dark
                ? Color(red: 0.68, green: 0.39, blue: 0.09)
                : Color(red: 0.52, green: 0.29, blue: 0.06))
                .overlay {
                    if !reduceMotion {
                        GeometryReader { geometry in
                            LinearGradient(colors: CoreAssetStyle.signatureFlow,
                                startPoint: .leading, endPoint: .trailing)
                                .frame(width: geometry.size.width * 0.8)
                                .offset(x: geometry.size.width * (progress * 1.8 - 0.8))
                        }.mask(lettering).allowsHitTesting(false)
                    }
                }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(Text(verbatim: "Ben"))
        .onAppear { visible = true }.onDisappear { visible = false }
    }
}

private struct GildedConnectionLabel: View {
    let active: Bool
    @State private var visible = false
    @Environment(\.scenePhase) private var phase
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    private var lettering: some View {
        Text(verbatim: "𝓢𝓾𝓬𝓬𝓮𝓼𝓼𝓯𝓾𝓵")
            .font(.system(.headline, design: .default, weight: .regular))
            .lineLimit(1).minimumScaleFactor(0.7)
    }
    var body: some View {
        TimelineView(.animation(minimumInterval: 1.0 / 30, paused: !visible || !active || phase != .active || reduceMotion)) { context in
            let progress = reduceMotion ? 0.5 : context.date.timeIntervalSinceReferenceDate.truncatingRemainder(dividingBy: 5) / 5
            lettering.hidden()
                .overlay {
                    Color(red: 0.34, green: 0.16, blue: 0.02)
                        .overlay {
                            GeometryReader { geometry in
                                LinearGradient(colors: [.clear, Color(red: 0.76, green: 0.42, blue: 0.06), Color(red: 1, green: 0.87, blue: 0.48), Color(red: 0.76, green: 0.42, blue: 0.06), .clear], startPoint: .leading, endPoint: .trailing)
                                    .frame(width: geometry.size.width * 0.7)
                                    .offset(x: geometry.size.width * (progress * 1.7 - 0.7))
                            }
                        }
                        // Mask the lettering with the gold finish.
                        .mask(lettering)
                        .allowsHitTesting(false)
                }
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(Text("CONNECTED"))
        }
        .onAppear { visible = true }.onDisappear { visible = false }
    }
}

private struct ConnectingGlow: View {
    let active: Bool
    @State private var visible = false
    @Environment(\.scenePhase) private var phase
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    var body: some View {
        TimelineView(.animation(minimumInterval: 1.0 / 30, paused: !visible || !active || phase != .active || reduceMotion)) { context in
            let intensity = reduceMotion ? 0.0 : (sin(context.date.timeIntervalSinceReferenceDate * .pi / 1.5) + 1) / 2
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .strokeBorder(.white.opacity(0.15 + intensity * 0.4), lineWidth: 1.5)
                .shadow(color: .cyan.opacity(0.1 + intensity * 0.25), radius: 3 + intensity * 5)
        }
        .onAppear { visible = true }.onDisappear { visible = false }
    }
}

private struct MarginWarningAmount: View {
    let amount: Double?
    let netValue: Double?
    let active: Bool
    @Environment(\.scenePhase) private var phase
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var visible = false
    private var warning: Bool {
        guard let amount, let netValue, amount.isFinite, netValue.isFinite, amount > 0 else { return false }
        return netValue <= 0 || amount / netValue >= 0.7
    }
    var body: some View {
        let label = Text(money(amount)).monospacedDigit()
        Group {
            if warning {
                TimelineView(.animation(minimumInterval: 1.0 / 30,
                    paused: !active || !visible || phase != .active || reduceMotion)) { context in
                    let progress = context.date.timeIntervalSinceReferenceDate.truncatingRemainder(dividingBy: 2) / 2
                    label.foregroundStyle(.red)
                        .overlay {
                            if !reduceMotion {
                                GeometryReader { geometry in
                                    LinearGradient(colors: [.clear, .red, Color(red: 1, green: 0.65, blue: 0.65), .red, .clear], startPoint: .leading, endPoint: .trailing)
                                        .frame(width: geometry.size.width * 0.7)
                                        .offset(x: geometry.size.width * (progress * 1.7 - 0.7))
                                }.mask(label).allowsHitTesting(false).accessibilityHidden(true)
                            }
                        }
                }
            } else {
                label
            }
        }
        .onAppear { visible = true }
        .onDisappear { visible = false }
    }
}


enum AccountConnectionRules {
    static func verifiedEpoch(_ state: [String: Any], mode: String) throws -> String? {
        guard ["paper", "live"].contains(mode), state["selected"] as? String == mode else {
            throw AppError.message("Another device changed the selected account. Select your account again.")
        }
        guard state["verified"] as? Bool == true else { return nil }
        guard let epoch = state["epoch"] as? String, !epoch.isEmpty else {
            throw AppError.message("Account verification is incomplete. Retry connection.")
        }
        return epoch
    }
}


/// The header opens details after expansion; the separate range button collapses it.
struct ExpandablePositionRow<Content: View>: View {
    let position: Position
    @ViewBuilder let content: (Bool) -> Content
    @State private var expanded = false
    @State private var showDetails = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.locale) private var locale

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Button {
                if expanded { showDetails = true }
                else { withAnimation(reduceMotion ? nil : .easeInOut(duration: 0.2)) { expanded = true } }
            } label: {
                content(expanded)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityHint(Text(verbatim: locale.language.languageCode?.identifier == "zh"
                ? (expanded ? "打开持仓详情" : "展开当日价格区间")
                : (expanded ? "Open position details" : "Show daily price range")))
            if expanded {
                Button {
                    withAnimation(reduceMotion ? nil : .easeInOut(duration: 0.2)) { expanded = false }
                } label: {
                    PositionDayRange(position: position)
                        .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel(Text(verbatim: locale.language.languageCode?.identifier == "zh" ? "收起价格区间" : "Hide daily price range"))
            }
        }
        .navigationDestination(isPresented: $showDetails) { PositionDetail(position: position) }
    }
}

struct PositionDayRange: View {
    let position: Position
    @State private var movementColor: Color = .secondary
    @Environment(\.locale) private var locale
    private var chinese: Bool { locale.language.languageCode?.identifier == "zh" }
    private var bounds: (Double, Double)? {
        guard let low = position.day_low, let high = position.day_high,
              low.isFinite, high.isFinite, low > 0, high >= low else { return nil }
        return (low, high)
    }
    private var status: String {
        switch position.day_range_status {
        case "live": return chinese ? "今日波动" : "Today's range"
        case "delayed": return chinese ? "日内区间 · 延迟" : "Session range · Delayed"
        case "frozen": return chinese ? "日内区间 · 冻结" : "Session range · Frozen"
        default: return chinese ? "日内区间 · 暂无行情" : "Session range · Unavailable"
        }
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            if let (low, high) = bounds {
                GeometryReader { geometry in
                    let width = geometry.size.width
                    let price = position.day_range_price
                    let valid = price.map { $0.isFinite && $0 > 0 } ?? false
                    let fraction = valid ? (high > low ? min(1, max(0, (price! - low) / (high - low))) : 0.5) : 0
                    ZStack(alignment: .leading) {
                        Capsule().fill(Color.secondary.opacity(0.2)).frame(height: 5)
                        if valid {
                            Capsule().fill(movementColor).frame(width: width * fraction, height: 5)
                            Image(systemName: "arrowtriangle.down.fill").font(.system(size: 8))
                                .foregroundStyle(.primary).offset(x: min(max(0, width * fraction - 4), max(0, width - 8)), y: -8)
                        }
                    }.frame(height: 14, alignment: .bottom)
                }.frame(height: 14)
                HStack {
                    Text(verbatim: low.formatted(.number.precision(.fractionLength(2...4))))
                    Spacer()
                    Text(verbatim: high.formatted(.number.precision(.fractionLength(2...4))))
                }.font(.caption2).monospacedDigit().foregroundStyle(.secondary)
            }
        }.frame(maxWidth: 160, alignment: .leading)
            .onChange(of: position.day_range_price) { oldPrice, newPrice in
                guard let oldPrice, let newPrice,
                      oldPrice.isFinite, newPrice.isFinite, oldPrice > 0, newPrice > 0 else {
                    movementColor = .secondary
                    return
                }
                if newPrice > oldPrice { movementColor = .green }
                else if newPrice < oldPrice { movementColor = .red }
            }
            .onChange(of: position.id) { _, _ in movementColor = .secondary }
            .accessibilityElement(children: .combine)
            .accessibilityLabel(Text(verbatim: status))
    }
}
