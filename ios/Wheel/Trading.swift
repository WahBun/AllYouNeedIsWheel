import SwiftUI

struct OrderID: Decodable, Hashable, ExpressibleByIntegerLiteral, CustomStringConvertible {
    let description: String
    init(integerLiteral value: Int) { description = String(value) }
    init(_ value: Int) { description = String(value) }
    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let number = try? container.decode(Int.self) { description = String(number) }
        else { description = try container.decode(String.self) }
    }
    var local: Int? { Int(description).flatMap { $0 > 0 ? $0 : nil } }
}

enum TradeRules {
    static func price(_ text: String) -> Double? {
        guard let value = Decimal(string: text, locale: Locale(identifier: "en_US_POSIX")), value > 0,
              text.range(of: #"^\d+(\.\d{1,2})?$"#, options: .regularExpression) != nil else { return nil }
        let number = NSDecimalNumber(decimal: value).doubleValue
        return number.isFinite ? number : nil
    }
    static func editable(_ order: Order) -> Bool {
        order.id.local != nil && order.external_ib != true && order.executed != true && order.status.lowercased() == "pending"
    }
    static func cancelable(_ order: Order) -> Bool {
        order.id.local != nil && order.external_ib != true && ["pending", "processing", "submitted", "presubmitted"].contains(order.status.lowercased())
    }
    static func hasUnsavedEdits(_ order: Order, price: String, quantity: Int) -> Bool {
        TradeRules.price(price) != order.premium || (order.intent != "CLOSE" && Double(quantity) != order.quantity)
    }
}

// Writes use a redirect-free session and are never automatically retried.
final class NoRedirect: NSObject, URLSessionTaskDelegate, @unchecked Sendable {
    func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse, newRequest request: URLRequest, completionHandler: @escaping (URLRequest?) -> Void) { completionHandler(nil) }
}

@MainActor @Observable
final class TradingSession {
    var busy = false
    var version = 0
    var message: String?
    var uncertain = UserDefaults.standard.bool(forKey: "unresolvedTradingWrite")
    var demoOrders = [Order(id: 1, ticker: "TSLL", action: "BUY", option_type: "PUT", strike: 9, expiration: "20261016", premium: 0.01, quantity: 1, status: "pending", tif: "GTC", intent: "CLOSE")]
    private let session: URLSession
    init(session: URLSession? = nil) {
        self.session = session ?? URLSession(configuration: .ephemeral, delegate: NoRedirect(), delegateQueue: nil)
    }
    private var nextDemoID = 2
    func resetContext() { message = nil }
    func acknowledgeReview() {
        uncertain = false
        UserDefaults.standard.set(false, forKey: "unresolvedTradingWrite")
        message = nil
    }

    func get(_ path: String, base: String, query: [URLQueryItem] = []) async throws -> [String: Any] {
        var components = URLComponents(url: try endpoint(base, path), resolvingAgainstBaseURL: false)!
        components.queryItems = query.isEmpty ? nil : query
        var request = URLRequest(url: components.url!, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 30)
        request.httpMethod = "GET"
        return try await send(request)
    }

    func synchronizedOrders(base: String) async throws -> Orders {
        // This endpoint reconciles status only; it does not submit or cancel orders.
        var request = URLRequest(url: try endpoint(base, "api/options/check-orders"), timeoutInterval: 30)
        request.httpMethod = "POST"
        request.setValue("1", forHTTPHeaderField: "X-All-You-Need-Is-Wheel")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: ["force_discovery": true])
        let payload = try await send(request)
        guard payload["success"] as? Bool == true else { throw AppError.message("Order status could not be verified.") }
        return try JSONDecoder().decode(Orders.self, from: JSONSerialization.data(withJSONObject: payload))
    }

    private func endpoint(_ base: String, _ path: String) throws -> URL {
        guard let url = URL(string: base.trimmingCharacters(in: .whitespacesAndNewlines)), url.scheme == "https", url.host != nil, url.user == nil, url.password == nil, url.query == nil, url.fragment == nil else { throw AppError.message("A private HTTPS backend address is required.") }
        return url.appendingPathComponent(path)
    }

    private func send(_ request: URLRequest) async throws -> [String: Any] {
        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse else { throw AppError.message("Invalid backend response.") }
        let payload = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
        guard (200..<300).contains(http.statusCode), let payload else {
            throw AppError.message(payload?["error"] as? String ?? "Backend returned HTTP \(http.statusCode).")
        }
        if let error = payload["error"] as? String { throw AppError.message(error) }
        return payload
    }

    func write(_ path: String, method: String = "POST", body: [String: Any] = [:], store: WheelStore) async -> Bool {
        guard !busy, store.demo || !uncertain else { return false }
        busy = true
        version += 1
        message = nil
        defer { busy = false; version += 1 }
        do {
            if store.demo {
                if path == "api/options/rollover" {
                    guard let id = body["current_con_id"] as? Int, let position = store.portfolio?.positions.first(where: { $0.con_id == id }), position.position < 0 else { throw AppError.message("Short position not found.") }
                    let qty = Double(body["quantity"] as? Int ?? 1)
                    demoOrders.append(Order(id: OrderID(nextDemoID), ticker: position.symbol, action: "BUY", option_type: position.option_type, strike: position.strike, expiration: position.expiration, premium: body["current_limit_price"] as? Double, quantity: qty, status: "pending", tif: "GTC", intent: "CLOSE", isRollover: true))
                    nextDemoID += 1
                    demoOrders.append(Order(id: OrderID(nextDemoID), ticker: position.symbol, action: "SELL", option_type: position.option_type, strike: body["new_strike"] as? Double, expiration: body["new_expiration"] as? String, premium: body["new_limit_price"] as? Double, quantity: qty, status: "pending", tif: "DAY", intent: "OPEN", isRollover: true))
                    nextDemoID += 1
                } else if path.hasSuffix("close-order") {
                    guard let id = body["con_id"] as? Int,
                          let position = store.portfolio?.positions.first(where: { $0.con_id == id }),
                          let qty = body["quantity"] as? Int, qty > 0, Double(qty) <= abs(position.position) else {
                        throw AppError.message("Position quote is invalid. Refresh before staging.")
                    }
                    demoOrders.append(Order(id: OrderID(nextDemoID), ticker: position.symbol,
                        action: position.position < 0 ? "BUY" : "SELL", option_type: position.option_type,
                        strike: position.strike, expiration: position.expiration, premium: body["limit_price"] as? Double,
                        quantity: Double(qty), status: "pending", tif: "GTC", intent: "CLOSE"))
                    nextDemoID += 1
                } else { try simulate(path, body: body) }
                store.orders = demoOrders
                message = "Demo updated. No broker request was sent."
                return true
            }
            var request = URLRequest(url: try endpoint(store.address, path), timeoutInterval: 30)
            request.httpMethod = method
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.setValue("1", forHTTPHeaderField: "X-All-You-Need-Is-Wheel")
            request.httpBody = try JSONSerialization.data(withJSONObject: body)
            // Persist before dispatch, including app termination while awaiting an acknowledgement.
            uncertain = true
            UserDefaults.standard.set(true, forKey: "unresolvedTradingWrite")
            let result = try await send(request)
            guard result["success"] as? Bool == true, result["status"] as? String != "unknown" else {
                throw AppError.message(result["message"] as? String ?? "Order outcome needs verification in IB and the web app.")
            }
            uncertain = false
            UserDefaults.standard.set(false, forKey: "unresolvedTradingWrite")
            message = result["message"] as? String ?? "Request acknowledged. Refresh Orders to check broker status."
            return true
        } catch {
            message = error.localizedDescription + (uncertain && !store.demo ? " Do not resubmit. Verify in IB and the web app; trading is locked pending review." : "")
            return false
        }
    }

    private func simulate(_ path: String, body: [String: Any]) throws {
        if path.hasSuffix("close-order") || path == "api/options/order" {
            let close = path.hasSuffix("close-order")
            let order = Order(id: OrderID(nextDemoID), ticker: body["ticker"] as? String ?? "TSLL", action: close ? "BUY" : "SELL", option_type: body["option_type"] as? String ?? "PUT", strike: body["strike"] as? Double ?? 9, expiration: body["expiration"] as? String ?? "20261016", premium: body[close ? "limit_price" : "premium"] as? Double, quantity: Double(body["quantity"] as? Int ?? 1), status: "pending", tif: close ? "GTC" : "DAY", intent: close ? "CLOSE" : "OPEN")
            demoOrders.append(order); nextDemoID += 1
        } else {
            let parts = path.split(separator: "/")
            guard let id = parts.compactMap({ Int($0) }).first, let index = demoOrders.firstIndex(where: { $0.id.local == id }) else { throw AppError.message("Order no longer exists.") }
            if path.contains("execute") { demoOrders[index].status = "processing" }
            else if path.contains("cancel") { demoOrders.remove(at: index) }
            else if path.hasSuffix("premium") { demoOrders[index].premium = body["premium"] as? Double }
            else if path.hasSuffix("quantity") { demoOrders[index].quantity = (body["quantity"] as? Int).map(Double.init) }
        }
    }
}

struct TradingNotice: View {
    @Environment(WheelStore.self) private var store
    var body: some View {
        if !store.demo && store.trading.uncertain {
            Label("Unconfirmed request. Check IB and the web app before further trading.", systemImage: "exclamationmark.triangle").foregroundStyle(.orange)
        }
        if let message = store.trading.message { Text(LocalizedStringKey(message)).font(.footnote).foregroundStyle(.secondary) }
        if store.trading.busy { ProgressView("Sending request…") }
    }
}

struct OrderDetail: View {
    @Environment(\.locale) private var locale
    private var localizedAction: String { localizedLabel(action ?? "Confirm", locale: locale) }
    let initial: Order
    @Environment(WheelStore.self) private var store
    @State private var price = ""
    @State private var action: String?
    @State private var quantity = 1
    @AppStorage("confirmBeforeOrderExecution") private var confirmExecution = true
    private var current: Order? { store.orders.first { $0.id == initial.id } }
    var body: some View {
        Form {
            if let order = current {
                Section(order.name) {
                    LabeledContent("Contract", value: "\(order.expiration ?? "") · \(money(order.strike)) \(order.option_type ?? "")")
                    LabeledContent("Action", value: "\(order.action ?? "") TO \(order.intent ?? "OPEN")")
                    LabeledContent("Quantity", value: order.quantity?.formatted() ?? "—")
                    LabeledContent("Limit", value: money(order.premium))
                    LabeledContent("Time in force", value: order.tif ?? (order.intent == "CLOSE" ? "GTC" : "DAY"))
                    LabeledContent("Status", value: order.ib_status ?? order.status)
                    if let id = order.ib_order_id { LabeledContent("IB order ID", value: String(id)) }
                    if let id = order.perm_id { LabeledContent("Permanent ID", value: String(id)) }
                    if let error = order.error_message, !error.isEmpty { Text(error).foregroundStyle(.orange) }
                }
                if order.external_ib == true { Text("IB-managed order. Modify or cancel in IB.").foregroundStyle(.secondary) }
                if TradeRules.editable(order) {
                    Section("Limit price") {
                        TextField("0.00", text: $price).keyboardType(.decimalPad)
                        Button("Save price") { action = "Save price" }.disabled(TradeRules.price(price) == nil)
                    }
                    if order.intent != "CLOSE" {
                        Section("Quantity") {
                            Stepper("Contracts: \(quantity)", value: $quantity, in: 1...100)
                            Button("Save quantity") { action = "Save quantity" }
                        }
                    }
                    Section {
                        Button("Execute", systemImage: "paperplane") { if confirmExecution { action = "Execute" } else { perform("Execute") } }
                            .disabled(TradeRules.hasUnsavedEdits(order, price: price, quantity: quantity))
                        if TradeRules.hasUnsavedEdits(order, price: price, quantity: quantity) { Text("Save price and quantity changes before Execute.").font(.caption).foregroundStyle(.orange) }
                    }
                }
                if TradeRules.cancelable(order) { Section { Button("Cancel order", role: .destructive) { action = "Cancel order" } } }
            } else { ContentUnavailableView("Order no longer pending", systemImage: "checkmark.circle") }
            Section { TradingNotice() }
        }
        .modifier(KeyboardDismissal())
        .disabled(store.trading.busy || store.opportunities.batchRunning || (!store.demo && store.trading.uncertain))
        .navigationTitle(initial.name)
        .onAppear { price = String(format: "%.2f", current?.premium ?? 0); quantity = max(1, min(100, Int(current?.quantity ?? 1))) }
        .confirmationDialog(LocalizedStringKey(action ?? "Confirm"), isPresented: Binding(get: { action != nil }, set: { if !$0 { action = nil } }), titleVisibility: .visible) {
            Button(store.demo ? LocalizedStringKey("Confirm demo action") : "Confirm \(localizedAction)") {
                guard let action else { return }
                perform(action)
                self.action = nil
            }
        } message: {
            Text("\(current?.name ?? initial.name) · \(current?.action ?? "") \(action == "Save quantity" ? String(quantity) : current?.quantity?.formatted() ?? "") · \(current?.option_type ?? "") \(money(current?.strike)) · \(current?.expiration ?? "")\nLimit \(money(action == "Save price" ? TradeRules.price(price) : current?.premium)) · \(current?.tif ?? (current?.intent == "CLOSE" ? "GTC" : "DAY"))\n\(store.demo ? "Simulation only" : "Connected backend · real orders may execute")")
        }
    }
    private func perform(_ action: String) {
        guard let order = current, let id = order.id.local else { return }
        guard action == "Cancel order" ? TradeRules.cancelable(order) : TradeRules.editable(order) else { return }
        guard action != "Save quantity" || order.intent != "CLOSE" else { return }
        guard action != "Execute" || !TradeRules.hasUnsavedEdits(order, price: price, quantity: quantity) else { return }
        let suffix = action == "Save quantity" ? "quantity" : "premium"
        let path = action == "Execute" ? "api/options/execute/\(id)" : action == "Cancel order" ? "api/options/cancel/\(id)" : "api/options/order/\(id)/\(suffix)"
        let body: [String: Any] = action == "Save price" ? ["premium": TradeRules.price(price) ?? 0] : action == "Save quantity" ? ["quantity": quantity] : [:]
        Task { _ = await store.trading.write(path, method: action.hasPrefix("Save") ? "PUT" : "POST", body: body, store: store); await store.refresh() }
    }
}

struct CloseTicket: View {
    @Environment(\.locale) private var locale
    let position: Position
    @Environment(WheelStore.self) private var store
    @Environment(\.scenePhase) private var phase
    @State private var state = CloseQuoteState()
    @State private var visible = false
    private var quote: [String: Any]? { state.quote }
    private var price: String { state.price }
    private var quantity: Int { state.quantity }
    private var loading: Bool { state.loading }
    private var error: String? { state.error }
    private var active: Bool { visible && phase == .active && store.selectedTab == "portfolio" && !confirm && !staged }
    private var context: String { "\(store.demo)-\(store.address)-\(position.con_id ?? 0)" }
    @State private var confirm = false
    @State private var staged = false
    private var held: Int { state.held }
    var body: some View {
        @Bindable var state = state
        Form {
            Section(position.symbol) {
                Text(position.detail)
                LabeledContent("Action", value: "\(quote?["close_action"] as? String ?? "—") TO CLOSE")
                LabeledContent("Account", value: quote?["account_suffix"] as? String ?? "—")
                LabeledContent("Quote") { Text(LocalizedStringKey((quote?["is_frozen"] as? Bool == true) ? "Frozen" : "Check quote time")) }
                LabeledContent("Server snapshot", value: (quote?["quote_time"] as? String)?.replacingOccurrences(of: "T", with: " ") ?? "—")
                if let date = state.receivedAt { LabeledContent("Last refreshed", value: date.formatted(.dateTime.hour().minute().second())) }
                Text(LocalizedStringKey(active ? "Auto refresh · about 2 seconds" : "Auto refresh paused")).font(.caption).foregroundStyle(.secondary)
                if loading && quote != nil { ProgressView().controlSize(.small) }
                HStack { ForEach(["bid", "mid", "ask"], id: \.self) { field in
                    Button { if let value = quote?[field] as? Double, value > 0 { state.markPriceEdited(String(format: "%.2f", value)) } } label: { VStack { Text(LocalizedStringKey(field.capitalized)); Text(money(quote?[field] as? Double)) } }.buttonStyle(.borderless).frame(maxWidth: .infinity)
                } }
            }
            if loading && quote == nil { ProgressView() }
            if let error { Text(LocalizedStringKey("Quote refresh failed. The last quote is not current; staging is disabled.")).foregroundStyle(.orange); Text(error).font(.caption) }
            if held > 0 {
                Section("Close quantity") {
                    if quantity > held { Text("Position quantity changed. Review the close quantity.").foregroundStyle(.orange) }
                    Stepper("\(quantity) of \(held)", value: $state.quantity, in: 1...max(held, quantity))
                    HStack {
                        Button("Half") { state.quantity = max(1, held / 2) }
                        Spacer()
                        Button("Leave runner") { state.quantity = max(1, held - 1) }.disabled(held < 2)
                        Spacer()
                        Button("All") { state.quantity = held }
                    }.buttonStyle(.borderless)
                    TextField("Limit per share", text: Binding(get: { price }, set: { state.markPriceEdited($0) })).keyboardType(.decimalPad)
                    LabeledContent("Remaining", value: String(max(0, held - quantity)))
                    LabeledContent("Limit total", value: money(TradeRules.price(price).map { $0 * Double(quantity) * (quote?["multiplier"] as? Double ?? 100) }))
                    LabeledContent("Time in force", value: "GTC")
                    LabeledContent("Estimated P&L before fees", value: money(TradingMath.closePnL(entry: quote?["avg_cost_per_share"] as? Double, limit: TradeRules.price(price), quantity: quantity, multiplier: quote?["multiplier"] as? Double ?? 100, buy: quote?["close_action"] as? String == "BUY")))
                    LabeledContent("Spread", value: (quote?["spread_percent"] as? Double).map { String(format: "%.1f%%", $0) } ?? "—")
                }
            }
            Section {
                Button("Refresh quote", systemImage: "arrow.clockwise") { Task { await load() } }.disabled(loading)
                Button(LocalizedStringKey(staged ? "Staged in Orders" : "Stage close order"), systemImage: "plus.circle") { confirm = true }
                    .disabled(!state.valid || staged)
                TradingNotice()
            }
        }.navigationTitle(localizedLabel("Close / Take profit", locale: locale))
        .modifier(KeyboardDismissal())
        .disabled(store.trading.busy || (!store.demo && store.trading.uncertain))
        .onAppear { visible = true }
        .onDisappear { visible = false; state.invalidate() }
        .onChange(of: context) { state.invalidate(clear: true); staged = false }
        .task(id: "\(active)-\(context)") {
            guard active else { state.invalidate(); return }
            await RefreshLoop.run { await load(); return state.error != nil }
        }
        .confirmationDialog("Stage \(quantity) \(position.symbol) at \(money(TradeRules.price(price)))?", isPresented: $confirm, titleVisibility: .visible) {
            Button("Stage · Execute separately in Orders") {
                guard let value = TradeRules.price(price), let id = position.con_id, state.valid else { state.error = "Quote expired or quantity changed. Refresh and review before staging."; return }
                Task { staged = await store.trading.write("api/options/close-order", body: ["con_id": id, "quantity": quantity, "limit_price": value], store: store); await store.refresh(); if staged { store.selectedTab = "orders" } }
            }
        }
    }
    private func load() async {
        guard active, !store.trading.busy else { return }
        let requestedContext = context
        let tradeVersion = store.trading.version
        await state.refresh(fetch: {
            if store.demo { return ["position": position.position, "close_action": position.position < 0 ? "BUY" : "SELL", "bid": 0.17, "mid": 0.18, "ask": 0.19, "multiplier": 100.0, "account_suffix": "DEMO", "is_frozen": true, "quote_time": "Demo"] }
            return try await store.trading.get("api/portfolio/option-position/\(position.con_id ?? 0)/quote", base: store.address)
        }, allowed: { active && context == requestedContext && !store.trading.busy && store.trading.version == tradeVersion })
    }
}
