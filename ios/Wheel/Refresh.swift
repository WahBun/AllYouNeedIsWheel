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
    static func optionMetricsDelay(frozen: Bool, marketClosed: Bool, missing: Bool, failed: Bool, failures: Int) -> TimeInterval {
        // Frozen alone can mean delayed data during an open session. Only a
        // confirmed closed session makes missing Greeks normal, not a failure.
        if !failed && frozen && marketClosed { return 30 }
        if failed || missing { return delay(elapsed: 0, failed: true, consecutiveFailures: failures) }
        return 15
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

// Construct an allowlisted report; never export raw backend errors or URLs.
enum SafeDiagnostics {
    static func errorCategory(_ error: String?) -> String {
        guard let error else { return "none" }
        let text = error.lowercased()
        if text.contains("ib requests are busy") { return "ib_busy" }
        if text.contains("secure connection failed") { return "tls" }
        if text.contains("no internet") { return "offline" }
        if text.contains("timed out") { return "timeout" }
        if text.contains("cannot reach the backend") { return "unreachable" }
        return "other"
    }
    static func report(demo: Bool, orders: Bool, frozen: Bool, marketOpen: Bool?,
                       updated: Date?, error: String?, uncertain: Bool, now: Date,
                       version: String, systemVersion: String) -> String {
        let age = updated.map { String(Int(min(999999, max(0, now.timeIntervalSince($0))))) } ?? "unknown"
        let status = DataHealth.status(demo: demo, failed: error != nil, updated: updated, frozen: !orders && frozen, now: now)
        // Only app-generated numeric versions are accepted, including when testing.
        func numeric(_ value: String) -> String {
            value.range(of: #"^[0-9.() ]{1,40}$"#, options: .regularExpression) != nil ? value : "unknown"
        }
        var lines = ["Wheel diagnostics v1", "Generated UTC: \(ISO8601DateFormatter().string(from: now))",
            "App: \(numeric(version))", "iOS: \(numeric(systemVersion))",
            "Mode: \(demo ? "demo" : "backend")", "Screen: \(orders ? "orders" : "portfolio")",
            "Data status: \(status)", "Backend response age seconds: \(age)",
            "Frozen: \(frozen)", "Market session: \(marketOpen.map { $0 ? "open" : "closed" } ?? "unknown")",
            "Unresolved trading write: \(uncertain)", "Error category: \(errorCategory(error))"]
        if let error {
            // Match only the structured suffix generated by TradingSession.send.
            let pattern = #"\[(?:HTTP ([1-5][0-9]{2}) · (?:application|unverified origin) · )?(?:GET|POST|PUT|DELETE) [a-zA-Z0-9_-]+ · ref ([a-f0-9]{32})\]$"#
            if let regex = try? NSRegularExpression(pattern: pattern),
               let match = regex.firstMatch(in: error, range: NSRange(error.startIndex..., in: error)) {
                if let range = Range(match.range(at: 1), in: error) { lines.append("HTTP: \(error[range])") }
                if let range = Range(match.range(at: 2), in: error) { lines.append("Request reference: \(error[range])") }
            }
        }
        return lines.joined(separator: "\n")
    }
}
