import SwiftUI
import Charts

@main
struct WheelApp: App {
    @State private var store = WheelStore()
    var body: some Scene {
        WindowGroup { RootView().environment(store) }
    }
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
    var avg_cost: Double?
    var multiplier: Double?
    var id: String { "\(symbol)-\(security_type)-\(con_id ?? 0)-\(expiration ?? "")-\(strike ?? 0)" }
    var detail: String {
        security_type == "OPT" ? "\(expiration ?? "") · \((strike ?? 0).formatted()) \(option_type ?? "")" : "\(Int(position)) shares"
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
struct Bootstrap: Decodable { var summary: Summary; var positions: [Position] }
struct LivePortfolio: Decodable { var positions: [Position]; var is_frozen: Bool; var streaming: Bool? }
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
    var intent: String? = nil
    var external_ib: Bool? = nil
    var ib_status: String? = nil
    var executed: Bool? = nil
    var ib_order_id: Int? = nil
    var perm_id: Int? = nil
    var error_message: String? = nil
    var isRollover: Bool? = nil
    var filled: Double? = nil
    var avg_fill_price: Double? = nil
    var fill_time: String? = nil
    var fill_action: String? = nil
    var commission: Double? = nil
    var commission_currency: String? = nil
    var realized_pnl: Double? = nil
    var fillTimeLabel: String {
        guard let fill_time else { return "—" }
        let parser = ISO8601DateFormatter()
        parser.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let fractional = parser.date(from: fill_time)
        parser.formatOptions = [.withInternetDateTime]
        guard let date = fractional ?? parser.date(from: fill_time) else { return "—" }
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(identifier: "America/New_York")
        formatter.dateFormat = "yyyy-MM-dd HH:mm:ss zzz"
        return formatter.string(from: date)
    }
    var commissionLabel: String {
        guard let commission, commission.isFinite, abs(commission) < 1e100,
              commission_currency == nil || commission_currency == "USD" else { return "—" }
        return "$" + commission.formatted(.number.precision(.fractionLength(2...6)))
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

@MainActor @Observable
final class WheelStore {
    var demo = true
    var address = UserDefaults.standard.string(forKey: "backendURL") ?? ""
    var portfolio: Bootstrap?
    var priceDirections: [String: Int] = [:]
    var orders: [Order] = []
    var filledOrders: [Order] = []
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
    var trading = TradingSession()
    var opportunities = OpportunityBook()
    var selectedTab = "settings"
    init() { opportunities.configure(context: "demo") }
    private var revision = 0
    private var lastSummary: Date?
    func isConnected(to candidate: String) -> Bool {
        !demo && candidate.trimmingCharacters(in: .whitespacesAndNewlines) == address &&
        portfolio != nil && error == nil && Date().timeIntervalSince(updated ?? .distantPast) < 15
    }

    func refresh() async {
        await refreshPortfolio()
        await refreshOrders()
    }

    func refreshPortfolio() async {
        guard !busy, !trading.busy else { return }
        busy = true
        let requestedRevision = revision
        let requestedTradeVersion = trading.version
        defer { busy = false }
        if demo {
            portfolio = Bootstrap(summary: Summary(account_value: 25000, cash_balance: 12693, excess_liquidity: 14500, is_frozen: true, initial_margin: 4500, leverage_percentage: 18), positions: [
                Position(symbol: "TSLL", position: 300, market_price: 10.25, market_value: 3075, unrealized_pnl: 125, security_type: "STK", con_id: 2, avg_cost: 2950.0 / 300),
                Position(symbol: "CRCL", position: 100, market_price: 92.5, market_value: 9250, unrealized_pnl: -150, security_type: "STK", con_id: 3, avg_cost: 94),
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
                next = Bootstrap(summary: summary, positions: live.positions)
            }
            guard requestedRevision == revision, requestedTradeVersion == trading.version, !trading.busy, !Task.isCancelled else { return }
            priceDirections = Dictionary(next.positions.map { position in
                (position.id, TradingMath.priceDirection(
                    previous: portfolio?.positions.first { $0.id == position.id }?.market_price,
                    current: position.market_price))
            }, uniquingKeysWith: { _, latest in latest })
            portfolio = next
            if reloadSummary { lastSummary = Date() }
            updated = Date()
            error = nil
            UserDefaults.standard.set(address, forKey: "backendURL")
            if reloadSummary && selectedTab != "trade" {
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
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let response = response as? HTTPURLResponse, response.statusCode == 200 else { throw AppError.message("Backend unavailable. Check your connection and Tailscale.") }
        return try JSONDecoder().decode(T.self, from: data)
    }
    func loadFilled() async {
        guard !filledBusy, !trading.busy else { return }
        filledBusy = true
        defer { filledBusy = false }
        let token = revision
        let version = trading.version
        if demo { filledOrders = trading.demoOrders.filter { $0.hasFill }; filledError = nil; return }
        do {
            let result = try await trading.get("api/options/pending-orders", base: address, query: [URLQueryItem(name: "executed", value: "true")])
            let decoded = try JSONDecoder().decode(Orders.self, from: JSONSerialization.data(withJSONObject: result))
            guard token == revision, version == trading.version, !Task.isCancelled else { return }
            let completedIDs = Set(decoded.orders.map(\.id))
            filledOrders = (decoded.orders + orders.filter { !completedIDs.contains($0.id) }).filter { $0.hasFill }
            filledError = nil
        } catch {
            if token == revision, version == trading.version, !Task.isCancelled { filledError = connectionMessage(error) }
        }
    }
    func changeMode() { fillPreview.clear(); fillTracker = FillTracker(); fillSnapshot = []; fillSnapshotAt = nil; revision += 1; portfolio = nil; priceDirections = [:]; orders = []; filledOrders = []; filledError = nil; weekly = nil; lastSummary = nil; updated = nil; ordersUpdated = nil; error = nil; orderError = nil; trading.resetContext(); opportunities.configure(context: demo ? "demo" : address) }
}

func connectionMessage(_ error: Error) -> String {
    let code = (error as NSError).code
    if (error as NSError).domain == NSURLErrorDomain && [-1200, -1201, -1202, -1203, -1204].contains(code) {
        return "Secure connection failed (\(code)). Check Tailscale and open this exact HTTPS address in Safari on this iPhone. Verify automatic date/time and any VPN or proxy interference. Certificate checks remain enabled."
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

struct RootView: View {
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
            NavigationStack(path: $tradePath) { OpportunitiesView().modifier(KeyboardDismissal()) }.tabItem { Label(localizedLabel("Trade", locale: appLocale), systemImage: "arrow.left.arrow.right") }.tag("trade")
            NavigationStack(path: $ordersPath) { OrdersView().modifier(KeyboardDismissal()) }.tabItem { Label(localizedLabel("Orders", locale: appLocale), systemImage: "list.bullet.rectangle") }.tag("orders")
            NavigationStack { SettingsView().modifier(KeyboardDismissal()) }.tabItem { Label(localizedLabel("Settings", locale: appLocale), systemImage: "gearshape") }.tag("settings")
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
            portfolioPath = NavigationPath(); ordersPath = NavigationPath(); tradePath = NavigationPath()
        }
        .task(id: "\(phase)-\(store.demo)-\(store.address)") {
            guard phase == .active else { return }
            await RefreshLoop.run {
                if RefreshLoop.shouldRefreshPortfolio(tab: store.selectedTab, hasPortfolio: store.portfolio != nil,
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
    private var error: String? { orders ? store.orderError : store.error }
    private var busy: Bool { orders ? store.ordersBusy : store.busy }
    private var updated: Date? { orders ? store.ordersUpdated : store.updated }
    var body: some View {
        HStack(spacing: 6) {
            Circle().fill(error == nil ? Color.teal : .orange).frame(width: 6, height: 6)
                .opacity(busy && !reduceMotion ? 0.35 : 1)
                .animation(reduceMotion ? nil : .easeInOut(duration: 0.45), value: busy)
                .accessibilityHidden(true)
            Text(LocalizedStringKey(store.demo ? "DEMO" : error != nil || updated == nil ? "STALE" : !orders && store.portfolio?.summary.is_frozen == true ? "FROZEN" : "CONNECTED"))
            Spacer()
            if let date = updated { Text(date.formatted(.dateTime.hour().minute().second())).monospacedDigit() }
        }.font(.caption).foregroundStyle(.secondary)
    }
}

struct PortfolioView: View {
    @Environment(\.locale) private var locale
    @Environment(WheelStore.self) private var store
    var body: some View {
        List {
            Section {
                StatusView()
                VStack(alignment: .leading, spacing: 12) {
                    NavigationLink { AllocationView() } label: {
                        VStack(alignment: .leading, spacing: 12) {
                    Text("Net liquidation").font(.subheadline).foregroundStyle(.secondary)
                    Text(money(store.portfolio?.summary.account_value)).font(.system(size: 36, weight: .semibold, design: .rounded)).minimumScaleFactor(0.6).lineLimit(1)
                        }
                    }.buttonStyle(.plain)
                    HStack {
                        metric("Cash", money(store.portfolio?.summary.cash_balance))
                        Spacer()
                        metric("Excess liquidity", money(store.portfolio?.summary.excess_liquidity))
                    }
                }.padding(.vertical, 10)
            }
            if let error = store.error { Section { Label(error, systemImage: "wifi.exclamationmark").foregroundStyle(.orange) } }
            Section("Margin") {
                NavigationLink { MarginOverview() } label: {
                    LabeledContent("Initial margin", value: money(store.portfolio?.summary.initial_margin))
                }
                LeverageMeter(percentage: store.portfolio?.summary.leverage_percentage)
            }
            ForEach(["OPT", "STK"], id: \.self) { type in
                Section(LocalizedStringKey(type == "STK" ? "Stocks" : "Options")) {
                    ForEach((store.portfolio?.positions ?? []).filter { $0.security_type == type }) { position in
                        NavigationLink { PositionDetail(position: position) } label: {
                            if position.security_type == "OPT" {
                                PortfolioOptionRow(position: position)
                            } else {
                            HStack(alignment: .top) {
                                VStack(alignment: .leading, spacing: 5) {
                                    Text(position.symbol).font(.headline)
                                    Text(position.detail).font(.caption).foregroundStyle(.secondary)
                                }
                                Spacer()
                                VStack(alignment: .trailing, spacing: 5) {
                                    PositionMarketPrice(position: position)
                                    PositionPnLMeter(position: position)
                                }
                            }.padding(.vertical, 6)
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
    }
    func metric(_ title: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 4) { Text(LocalizedStringKey(title)).font(.caption).foregroundStyle(.secondary); Text(value).font(.subheadline.weight(.medium)).monospacedDigit() }
    }
}


struct PositionMarketPrice: View {
    @Environment(\.customPalette) private var customPalette
    let position: Position
    @Environment(WheelStore.self) private var store
    @Environment(\.colorScheme) private var scheme
    var body: some View {
        TimelineView(.periodic(from: .now, by: 1)) { context in
            let fresh = !store.demo && store.error == nil && context.date.timeIntervalSince(store.updated ?? .distantPast) < 15
            let direction = fresh ? (store.priceDirections[position.id] ?? 0) : 0
            Text(money(position.market_price)).monospacedDigit()
                .foregroundStyle(direction > 0 ? customPalette.color("gain", scheme: scheme, fallback: FinancialColors.gain) : direction < 0 ? customPalette.color("loss", scheme: scheme, fallback: FinancialColors.loss) : Color.primary)
        }
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
    private var value: Double? { percentage.flatMap { $0.isFinite ? $0 : nil } }
    private var tint: Color {
        guard let value else { return .secondary }
        return value < 30 ? .green : value < 60 ? .yellow : .red
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            LabeledContent("Leverage", value: value.map { String(format: "%.1f%%", $0) } ?? "—")
                .monospacedDigit()
            ProgressView(value: min(100, max(0, value ?? 0)), total: 100)
                .tint(tint)
                .accessibilityHidden(true)
        }.padding(.vertical, 4)
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
        if item.name == "SGOV" { return TradingColors.symbol("SGOV", scheme: scheme) }
        if item.id == "cash" { return .gray }
        let colors: [Color] = [.teal, .blue, .pink, .orange, .mint, .indigo]
        let keys = data.assets.filter { $0.name != "SGOV" && $0.id != "cash" }.map(\.id).sorted()
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
                LabeledContent("Total", value: money(data.total))
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
                if let error = store.error { Text(error).font(.caption).foregroundStyle(.orange) }
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

struct SymbolText: View {
    let symbol: String
    @Environment(\.colorScheme) private var scheme
    var body: some View {
        if symbol.uppercased() == "SGOV" {
            Text(symbol).foregroundStyle(TradingColors.symbol(symbol, scheme: scheme))
        } else {
            Text(symbol)
        }
    }
}

extension View {
    @ViewBuilder func symbolTitle(_ symbol: String) -> some View {
        if symbol.uppercased() == "SGOV" {
            self.navigationTitle(symbol).navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .principal) { SymbolText(symbol: symbol).font(.headline) } }
        } else {
            self.navigationTitle(symbol)
        }
    }
}

enum TradingColors {
    static func symbol(_ symbol: String, scheme: ColorScheme) -> Color {
        guard symbol.uppercased() == "SGOV" else { return .primary }
        return scheme == .dark ? Color(red: 1.00, green: 0.88, blue: 0.58) : Color(red: 0.78, green: 0.60, blue: 0.16)
    }
    static func profit(_ scheme: ColorScheme) -> Color {
        FinancialColors.gain
    }
}

struct PositionDetail: View {
    let position: Position
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
            Section(position.detail) {
                LabeledContent("Quantity", value: latest.position.formatted())
                LabeledContent("Average cost", value: money(latest.avg_cost))
                LabeledContent("Current price", value: money(latest.market_price))
                LabeledContent("Market value", value: money(latest.market_value))
                LabeledContent("Unrealized P&L", value: money(latest.unrealized_pnl))
                NavigationLink("Margin impact") { PositionMarginView(position: latest) }
            }
            if store.portfolio?.positions.contains(where: { $0.id == position.id && $0.position != 0 }) == true,
               (position.security_type == "OPT" || (position.security_type == "STK" && latest.position > 0)), let conID = position.con_id, conID > 0 {
                Section {
                    NavigationLink("Close") { CloseTicket(position: latest) }.disabled(stockHasCall)
                    if stockHasCall { Text("Close covered CALLs before selling shares.").font(.caption).foregroundStyle(.orange) }
                    if latest.security_type == "OPT" && latest.position < 0 { NavigationLink("Rollover") { RolloverTicket(position: latest) } }
                }
            }
        }.navigationTitle(position.symbol)
    }
}

struct OrdersView: View {
    @Environment(\.scenePhase) private var phase
    @Environment(\.locale) private var locale
    @Environment(WheelStore.self) private var store
    @AppStorage("confirmBeforeOrderExecution") private var confirmExecution = true
    @State private var history = false
    @State private var preferences = false
    @State private var cancelAll = false
    @State private var cancelling = false
    @State private var quickOrder: Order?
    @State private var quickCancel = false
    private var refreshHistory: Bool { RefreshLoop.shouldRefreshHistory(tab: store.selectedTab, showingHistory: history, active: phase == .active) }
    private var cancelable: [Order] { store.orders.filter { TradeRules.cancelable($0) } }
    var body: some View {
        List {
            StatusView(orders: true)
            Picker("Orders", selection: $history) { Text("Pending").tag(false); Text("Executed records").tag(true) }.pickerStyle(.segmented)
            if history, let error = store.filledError {
                Text(error).font(.caption).foregroundStyle(.orange)
            }
            if preferences { Toggle("Confirm execution and cancellation", isOn: $confirmExecution) }
            if store.ordersRetrying {
                Text("Connection interrupted. Retrying…").font(.caption).foregroundStyle(.orange)
            } else if let error = store.orderError {
                DisclosureGroup("Order status needs verification") {
                    Text(error).font(.caption).textSelection(.enabled)
                }.foregroundStyle(.orange)
            } else if let error = store.error { Text(error).foregroundStyle(.orange) }
            if (history ? store.filledOrders : store.orders).isEmpty && store.orderError == nil && store.error == nil && (!history || store.filledError == nil) {
                ContentUnavailableView("No orders", systemImage: "checkmark.circle")
            }
            ForEach(history ? store.filledOrders : store.orders) { order in
                NavigationLink {
                    if history { Form { Text(order.name); Text("\(order.expiration ?? "") · \(money(order.strike)) \(order.option_type ?? "")"); LabeledContent("Status", value: order.ib_status ?? order.status); LabeledContent("Action", value: order.fill_action ?? order.action ?? "—"); LabeledContent("Last fill time", value: order.fillTimeLabel); LabeledContent("Commission", value: order.commissionLabel); if order.intent == "CLOSE" { LabeledContent("Realized P&L") { RealizedProfit(order: order) } }; LabeledContent("Average fill price", value: money(order.fillPrice)); LabeledContent("Filled quantity", value: order.filledQuantity?.formatted() ?? "—"); LabeledContent("Limit", value: money(order.premium)) } }
                    else { OrderDetail(initial: order) }
                } label: {
                    VStack(alignment: .leading, spacing: 8) {
                        HStack { Text(order.name).font(.headline); Spacer(); Text(money(history ? order.fillPrice : order.premium)).monospacedDigit() }
                        HStack { Text("\(order.action ?? "") · \(order.option_type ?? "")"); Spacer(); Text(order.status).foregroundStyle(.teal) }.font(.caption)
                        if !history, let filled = order.filledQuantity {
                            Text("Filled \(filled.formatted()) / \(order.quantity?.formatted() ?? "—") · \(money(order.fillPrice))")
                                .font(.caption).foregroundStyle(.secondary)
                        }
                        if order.option_type == "STOCK" {
                            Text("\((history ? order.filledQuantity : order.quantity)?.formatted() ?? "—") shares").font(.caption).foregroundStyle(.secondary)
                        } else {
                            Text("\(order.expiration ?? "") · \(money(order.strike)) · Qty \((history ? order.filledQuantity : order.quantity)?.formatted() ?? "—") · \(order.tif ?? (order.intent == "CLOSE" ? "GTC" : "DAY"))").font(.caption).foregroundStyle(.secondary)
                        }
                        if history && order.intent == "CLOSE" && order.hasFill {
                            HStack { Text("Realized P&L"); Spacer(); RealizedProfit(order: order) }.font(.subheadline)
                        }
                        if order.external_ib == true { Text("IB managed").font(.caption).foregroundStyle(.secondary) }
                        if order.isRollover == true { Text("Rollover leg · independent order").font(.caption).foregroundStyle(.orange) }
                    }.padding(.vertical, 6)
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
                        Button("Cancel order", systemImage: "xmark.circle") {
                            if confirmExecution { quickCancel = true; quickOrder = order }
                            else { performQuick(order, cancel: true) }
                        }.tint(.red)
                    }
                }
            }
            if !history { Button("Cancel all eligible (\(cancelable.count))", role: .destructive) {
                if confirmExecution { cancelAll = true } else { performCancelAll() }
            }.disabled(cancelable.isEmpty) }
            TradingNotice()
        }.navigationTitle(localizedLabel("Orders", locale: locale)).refreshable { if history { await store.loadFilled() } else { await store.refresh() } }
        .toolbar { Button("Order preferences", systemImage: "gearshape") { preferences.toggle() } }
        .task(id: "history-\(refreshHistory)-\(store.demo)-\(store.address)") {
            if refreshHistory { await store.loadFilled() }
        }
        .onChange(of: store.ordersUpdated) { if refreshHistory { Task { await store.loadFilled() } } }
        .onChange(of: "\(store.demo)-\(store.address)") { quickOrder = nil; cancelAll = false }
        .disabled(cancelling || store.trading.busy || store.opportunities.batchRunning || (!store.demo && store.trading.uncertain))
        .confirmationDialog(LocalizedStringKey(quickCancel ? "Cancel order" : "Execute"), isPresented: Binding(get: { quickOrder != nil }, set: { if !$0 { quickOrder = nil } }), titleVisibility: .visible) {
            Button(LocalizedStringKey(quickCancel ? "Cancel order" : "Execute"), role: quickCancel ? .destructive : nil) {
                if let order = quickOrder { performQuick(order, cancel: quickCancel) }
                quickOrder = nil
            }
        } message: {
            if let order = quickOrder {
                Text("\(order.name) · \(order.action ?? "") · \(order.option_type ?? "") · \(money(order.strike)) · \(order.expiration ?? "")\n\(order.quantity?.formatted() ?? "—") · \(money(order.premium)) · \(order.tif ?? (order.intent == "CLOSE" ? "GTC" : "DAY"))\n\(store.demo ? "Simulation only" : "Connected backend · real orders may execute")")
            }
        }
        .confirmationDialog("Cancel \(cancelable.count) eligible orders?", isPresented: $cancelAll, titleVisibility: .visible) {
            Button("Cancel eligible orders", role: .destructive) {
                performCancelAll()
            }
        } message: { Text("IB-managed and unknown orders are excluded. Stops on the first failure. Cancellation remains pending until IB confirms it.") }
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
                      TradeRules.cancelable(current), let id = current.id.local else { continue }
                if !(await store.trading.write("api/options/cancel/\(id)", store: store)) { break }
            }
            await store.refreshOrders()
        }
    }
    private func performQuick(_ snapshot: Order, cancel: Bool) {
        let context = "\(store.demo)-\(store.address)"
        Task {
            guard context == "\(store.demo)-\(store.address)", !history, !cancelling, !store.trading.busy, !store.opportunities.batchRunning,
                  let current = store.orders.first(where: { $0.id == snapshot.id }), let id = current.id.local,
                  cancel ? TradeRules.cancelable(current) : TradeRules.editable(current),
                  TradeRules.unchanged(current, since: snapshot) else { return }
            _ = await store.trading.write("api/options/\(cancel ? "cancel" : "execute")/\(id)", store: store)
            await store.refreshOrders()
        }
    }
}

struct SettingsView: View {
    @Environment(\.locale) private var locale
    @AppStorage("appearance") private var appearance = "system"
    @AppStorage("appLanguage") private var appLanguage = "system"
    @Environment(WheelStore.self) private var store
    @State private var draft = ""
    @State private var reviewed = false
    @State private var connecting = false
    @FocusState private var addressFocused: Bool
    var body: some View {
        @Bindable var store = store
        Form {
            Section("Connection") {
                Toggle("Demo mode", isOn: $store.demo).tint(.teal).onChange(of: store.demo) { store.changeMode() }
                TextField("https://your-mini.ts.net", text: $draft).textInputAutocapitalization(.never).autocorrectionDisabled().keyboardType(.URL).focused($addressFocused).submitLabel(.done).onSubmit { addressFocused = false }
                Button {
                    addressFocused = false; connecting = true
                    store.address = draft.trimmingCharacters(in: .whitespacesAndNewlines); store.demo = false; store.changeMode()
                    let requestedAddress = store.address
                    Task {
                        defer { connecting = false }
                        while store.busy {
                            do { try await Task.sleep(for: .milliseconds(100)) } catch { return }
                        }
                        guard !store.demo, store.address == requestedAddress else { return }
                        await store.refreshPortfolio()
                        if store.isConnected(to: requestedAddress), store.selectedTab == "settings" {
                            store.selectedTab = "portfolio"
                        }
                    }
                } label: {
                    HStack(spacing: 12) {
                        Group {
                            if connecting {
                                ProgressView().tint(Color.black.opacity(0.8))
                            } else {
                                Image(systemName: store.isConnected(to: draft) ? "checkmark.circle.fill" : "link")
                                    .font(.title3.weight(.semibold))
                            }
                        }
                        .frame(width: 36, height: 36)
                        .background(.white.opacity(0.22), in: RoundedRectangle(cornerRadius: 11, style: .continuous))
                        .overlay { RoundedRectangle(cornerRadius: 11, style: .continuous).strokeBorder(.white.opacity(0.3), lineWidth: 0.5) }
                        .accessibilityHidden(true)
                        Text(LocalizedStringKey(connecting ? "Connecting…" : store.isConnected(to: draft) ? "CONNECTED" : "Connect"))
                            .font(.headline)
                        Spacer(minLength: 8)
                    }
                    .foregroundStyle(Color.black.opacity(0.85))
                    .padding(.horizontal, 18)
                    .padding(.vertical, 12)
                    .frame(maxWidth: .infinity, minHeight: 60)
                    .background {
                        RoundedRectangle(cornerRadius: 16, style: .continuous)
                            .fill(LinearGradient(colors: [Color(red: 0.40, green: 0.94, blue: 0.89), Color(red: 0.25, green: 0.73, blue: 0.98)], startPoint: .topLeading, endPoint: .bottomTrailing))
                    }
                    .overlay {
                        RoundedRectangle(cornerRadius: 16, style: .continuous)
                            .fill(LinearGradient(colors: [.white.opacity(0.18), .clear], startPoint: .top, endPoint: .center))
                            .allowsHitTesting(false)
                    }
                    .overlay {
                        RoundedRectangle(cornerRadius: 16, style: .continuous)
                            .strokeBorder(LinearGradient(colors: [.white.opacity(0.6), .white.opacity(0.10)], startPoint: .topLeading, endPoint: .bottomTrailing), lineWidth: 1)
                            .allowsHitTesting(false)
                    }
                    .shadow(color: .cyan.opacity(draft.isEmpty ? 0 : 0.20), radius: 10, y: 4)
                    .opacity(draft.isEmpty ? 0.45 : connecting ? 0.75 : 1)
                    .contentShape(RoundedRectangle(cornerRadius: 16))
                }.buttonStyle(.plain)
                    .listRowSeparator(.hidden)
                    .disabled(draft.isEmpty || connecting)
                if let error = store.error { Text(error).font(.footnote).foregroundStyle(.orange) }
            }
            if store.demo {
                Section("Demo Test") {
                    Button("Preview fill notifications", systemImage: "bell.badge") { store.fillPreview.start() }
                    Text("Switch to any tab: a partial fill appears after 3 seconds, followed by a full fill after 11 seconds.")
                        .font(.footnote).foregroundStyle(.secondary)
                }
            }
            Section("Appearance") {
                Picker(selection: $appLanguage) {
                    Text("System").tag("system")
                    Text(verbatim: "English").tag("en")
                    Text(verbatim: "简体中文").tag("zh-Hans")
                    Text(verbatim: "繁體中文").tag("zh-Hant")
                } label: {
                    Label("Language", systemImage: "globe")
                }
                .accessibilityLabel(Text("Language"))
                Picker(selection: $appearance) {
                    Text("System").tag("system")
                    Text("Light").tag("light")
                    Text("Dark").tag("dark")
                } label: {
                    Label("Theme", systemImage: "circle.lefthalf.filled")
                }
                .accessibilityLabel(Text("Theme"))
                NavigationLink { MetricPalettePreview() } label: {
                    Label("Custom colors", systemImage: "paintpalette")
                }
            }.tint(.teal)
            if store.trading.uncertain {
                Section("Unconfirmed request") {
                    Text("Check the exact order in IB and the web app, including fills and pending orders. Clearing this lock does not cancel or resubmit anything.")
                    Button("I have verified the order outcome") { reviewed = true }
                }
            }
            Section("App") {
                LabeledContent("Minimum iOS") { Text("18.0").padding(.trailing, 20) }
                NavigationLink { TradingAccessView() } label: {
                    LabeledContent("Trading access") { Text(verbatim: store.demo ? localizedLabel("Simulated", locale: locale) : "Live") }
                }
                LabeledContent("Version") { Text("0.2").padding(.trailing, 20) }
            }
        }.navigationTitle(localizedLabel("Settings", locale: locale)).onAppear { draft = store.address }
        .toolbar {
            if addressFocused { ToolbarItem(placement: .topBarTrailing) { Button("Done") { addressFocused = false } } }
        }
        .disabled(store.trading.busy || store.opportunities.batchRunning)
        .confirmationDialog("Have you verified the order in IB and the web app?", isPresented: $reviewed, titleVisibility: .visible) {
            Button("Verified · unlock trading") { store.trading.acknowledgeReview() }
        }
    }
}
