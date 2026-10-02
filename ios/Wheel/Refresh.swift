import Foundation
import Observation

enum RefreshLoop {
    static func shouldRefreshHistory(tab: String, showingHistory: Bool, active: Bool) -> Bool {
        active && tab == "orders" && showingHistory
    }

    static func shouldRefreshPortfolio(tab: String, hasPortfolio: Bool, age: TimeInterval = 0, quotesLoading: Bool = false) -> Bool {
        if !hasPortfolio || tab == "portfolio" { return true }
        // Hidden holdings need only a periodic summary refresh. Keep the separate
        // order loop running so fills are still detected on every tab.
        return age >= 60 && (tab != "trade" || !quotesLoading)
    }
    static func delay(elapsed: TimeInterval, failed: Bool, interval: TimeInterval = 2, consecutiveFailures: Int = 1) -> TimeInterval {
        failed ? min(10, pow(2, Double(min(4, max(0, consecutiveFailures - 1))))) : max(0.25, interval - elapsed)
    }
    @MainActor static func run(interval: TimeInterval = 2, _ operation: () async -> Bool) async {
        let clock = ContinuousClock()
        var consecutiveFailures = 0
        while !Task.isCancelled {
            let start = clock.now
            let failed = await operation()
            consecutiveFailures = failed ? min(5, consecutiveFailures + 1) : 0
            guard !Task.isCancelled else { return }
            let elapsed = start.duration(to: clock.now).components
            let seconds = Double(elapsed.seconds) + Double(elapsed.attoseconds) / 1e18
            do { try await Task.sleep(for: .seconds(delay(elapsed: seconds, failed: failed, interval: interval, consecutiveFailures: consecutiveFailures))) }
            catch { return }
        }
    }
}

@MainActor @Observable
final class CloseQuoteState {
    var quote: [String: Any]?
    var price = ""
    var quantity = 1
    var loading = false
    var error: String?
    var receivedAt: Date?
    var priceInitialized = false
    private var generation = 0
    var held: Int {
        guard let raw = quote?["position"] as? Double, raw.isFinite, abs(raw) < Double(Int.max) else { return 0 }
        return max(0, Int(abs(raw)))
    }
    var valid: Bool { quote != nil && error == nil && Date().timeIntervalSince(receivedAt ?? .distantPast) < 15 && TradeRules.price(price) != nil && quantity > 0 && quantity <= held }
    func invalidate(clear: Bool = false) {
        generation += 1
        if clear { quote = nil; receivedAt = nil; price = ""; quantity = 1; priceInitialized = false; error = nil }
    }
    func markPriceEdited(_ value: String) { price = value; priceInitialized = true }
    func refresh(fetch: () async throws -> [String: Any], allowed: () -> Bool = { true }) async {
        guard !loading, allowed() else { return }
        let token = generation
        loading = true
        defer { loading = false }
        do {
            let next = try await fetch()
            guard token == generation, !Task.isCancelled, allowed() else { return }
            guard let count = next["position"] as? Double, count.isFinite, abs(count) < Double(Int.max),
                  let action = next["close_action"] as? String, action == (count < 0 ? "BUY" : "SELL") else {
                throw AppError.message("Position quote is invalid. Refresh before staging.")
            }
            quote = next; receivedAt = Date(); error = nil
            // Only the initial quote may fill a blank price; user edits never follow ticks.
            if !priceInitialized, let mid = next["mid"] as? Double, mid.isFinite, mid > 0 {
                price = String(format: "%.2f", mid); priceInitialized = true
            }
        } catch {
            guard token == generation, !Task.isCancelled, allowed() else { return }
            self.error = connectionMessage(error)
        }
    }
}


enum DataHealth {
    static func status(demo: Bool, failed: Bool, updated: Date?, frozen: Bool, now: Date) -> String {
        if demo { return "DEMO" }
        guard !failed, let updated, now.timeIntervalSince(updated) < 15 else { return "STALE" }
        return frozen ? "FROZEN" : "Backend responding"
    }
    static func guidance(_ error: String?) -> String {
        let message = (error ?? "").lowercased()
        if message.contains("ib requests are busy") {
            return "The backend is reachable, but IB requests are busy. Allow automatic retries to back off. If this persists, check Mini and Gateway; this does not by itself mean Gateway disconnected."
        }
        if message.contains("secure connection failed") {
            return "Check Tailscale, automatic date and time, and this HTTPS address in Safari. Do not bypass certificate verification."
        }
        if message.contains("no internet") || message.contains("cannot reach the backend") || message.contains("timed out") {
            return "Check Wi-Fi or cellular data and Tailscale first, then confirm the backend address and Mini service. A timeout alone cannot identify which connection failed."
        }
        return "A successful response confirms backend access, not live market data. Frozen or missing prices can reflect the market session, subscriptions or broker data permissions. Check the quote timestamp and Gateway status before deciding what to restart."
    }
}
