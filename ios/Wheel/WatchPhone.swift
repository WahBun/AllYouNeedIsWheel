import Foundation
import WatchConnectivity

/// Only the phone knows the backend address. The watch can request two fixed reads.
@MainActor
final class WatchPhone: NSObject, WCSessionDelegate {
    static let shared = WatchPhone()
    private struct Account: Codable, Equatable {
        let mode: String
        let epoch: String
        let address: String
    }
    private static let accountKey = "wheel.watch.selectedAccount"
    private var themeData = UserDefaults.standard.data(forKey: "wheel.watch.theme")
    private var account: Account?

    func setTheme(_ theme: WatchTheme) {
        if let data = themeData, (try? JSONDecoder().decode(WatchTheme.self, from: data)) == theme { return }
        themeData = try? JSONEncoder().encode(theme)
        UserDefaults.standard.set(themeData, forKey: "wheel.watch.theme")
        publishIdentity()
    }

    private weak var store: WheelStore?

    func start(store: WheelStore) {
        self.store = store
        if let data = UserDefaults.standard.data(forKey: Self.accountKey) {
            account = try? JSONDecoder().decode(Account.self, from: data)
        }
        guard WCSession.isSupported() else { return }
        WCSession.default.delegate = self
        WCSession.default.activate()
    }

    func synchronize(_ store: WheelStore) {
        guard store === self.store else { return }
        let binding: Account?
        if store.demo {
            binding = Account(mode: "demo", epoch: "demo", address: "")
        } else if let connection = store.portfolio?.connection,
                  let epoch = connection.account_epoch, !epoch.isEmpty,
                  epoch == store.trading.accountEpoch, ["live", "paper"].contains(connection.mode) {
            binding = Account(mode: connection.mode, epoch: epoch, address: store.address)
        } else {
            binding = nil
        }
        guard binding != account else { return }
        account = binding
        if let binding, let data = try? JSONEncoder().encode(binding) {
            UserDefaults.standard.set(data, forKey: Self.accountKey)
        } else {
            UserDefaults.standard.removeObject(forKey: Self.accountKey)
        }
        publishIdentity()
    }

    private func publishIdentity() {
        guard WCSession.isSupported() else { return }
        let session = WCSession.default
        guard session.activationState == .activated, session.isPaired, session.isWatchAppInstalled else { return }
        var context: [String: Any] = ["mode": account?.mode ?? "", "epoch": account?.epoch ?? ""]
        context["theme"] = themeData
        try? session.updateApplicationContext(context)
    }

    nonisolated func session(_ session: WCSession, activationDidCompleteWith activationState: WCSessionActivationState, error: Error?) {
        Task { @MainActor in self.publishIdentity() }
    }
    nonisolated func sessionWatchStateDidChange(_ session: WCSession) { Task { @MainActor in self.publishIdentity() } }
    nonisolated func sessionDidBecomeInactive(_ session: WCSession) {}
    nonisolated func sessionDidDeactivate(_ session: WCSession) { session.activate() }

    nonisolated func session(_ session: WCSession, didReceiveMessage message: [String: Any],
                             replyHandler: @escaping ([String: Any]) -> Void) {
        Task { @MainActor in
            guard let section = WatchSection(rawValue: message["section"] as? String ?? ""),
                  let page = message["page"] as? Int, (0...10000).contains(page),
                  let account = self.account else { replyHandler(["error": "account"]); return }
            do {
                let snapshot: WatchSnapshot
                let symbol = section == .holdings ? message["symbol"] as? String : nil
                if account.mode == "demo" {
                    snapshot = await self.demo(section: section, page: page, symbol: symbol)
                } else {
                    guard let url = URL(string: account.address), url.scheme == "https", url.host != nil,
                          url.user == nil, url.password == nil, url.fragment == nil, url.query == nil else {
                        replyHandler(["error": "account"]); return
                    }
                    var query: [URLQueryItem] = [
                        .init(name: "mode", value: account.mode), .init(name: "epoch", value: account.epoch),
                        .init(name: "section", value: section.rawValue), .init(name: "page", value: String(page))
                    ]
                    if section == .holdings { query.append(.init(name: "allocation", value: "1")) }
                    if let symbol { query.append(.init(name: "symbol", value: symbol)) }
                    let endpoint = url.appendingPathComponent("api/portfolio/watch").appending(queryItems: query)
                    var request = URLRequest(url: endpoint, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 8)
                    request.setValue(account.epoch, forHTTPHeaderField: "X-Wheel-Account-Epoch")
                    let (data, response) = try await URLSession.shared.data(for: request)
                    if (response as? HTTPURLResponse)?.statusCode == 409 { replyHandler(["error": "account"]); return }
                    guard (response as? HTTPURLResponse)?.statusCode == 200 else { throw URLError(.badServerResponse) }
                    snapshot = try JSONDecoder().decode(WatchSnapshot.self, from: data)
                }
                guard account == self.account, account.mode == snapshot.mode, account.epoch == snapshot.epoch else {
                    replyHandler(["error": "account"]); return
                }
                var reply: [String: Any] = ["data": try JSONEncoder().encode(snapshot)]
                reply["theme"] = self.themeData
                replyHandler(reply)
            } catch { replyHandler(["error": self.account == account ? "offline" : "account"]) }
        }
    }

    private func demo(section: WatchSection, page: Int, symbol: String?) async -> WatchSnapshot {
        // Only read from a Demo store. A real account's holdings never enter a Demo reply.
        if let store, store.demo, store.portfolio == nil { await store.refreshPortfolio(includeWeekly: false) }
        let portfolio = store?.demo == true ? store?.portfolio : nil
        let rows = (portfolio?.positions ?? []).filter { $0.position != 0 && (symbol == nil || $0.symbol.uppercased() == symbol) }
        let now = Date.now.timeIntervalSince1970
        let quotes = [("QQQ", 512.35), ("SPY", 605.42), ("MES", 6085.25), ("MNQ", 21345.5)]
        return WatchSnapshot(mode: "demo", epoch: "demo", sampledAt: now, positions: section == .holdings ? rows.dropFirst(page * 30).prefix(30).map {
            WatchHolding(id: $0.con_id ?? 0, symbol: $0.symbol, contract: $0.chartLabel, quantity: $0.position,
                         price: $0.market_price, currency: "USD",
                         averageCost: $0.security_type == "STK" ? $0.reported_cost?.average : $0.optionAveragePrice,
                         costSource: $0.security_type == "STK" ? "report" : "position",
                         reportDate: $0.reported_cost?.date, reportedShares: $0.reported_cost?.quantity)
        } : [], quotes: section == .quotes ? quotes.map {
            WatchQuote(symbol: $0.0, contract: ["MNQ": "MNQZ6", "MES": "MESZ6"][$0.0] ?? $0.0, price: $0.1, source: "last", dataType: 1, sampledAt: now)
        } : [], total: rows.count, allocation: section == .holdings ? portfolio.map(AllocationSnapshot.init) : nil,
                             symbolFilter: symbol)
    }
}
