import Foundation
import Observation

enum RefreshLoop {
    static func delay(elapsed: TimeInterval, failed: Bool) -> TimeInterval {
        max(0.25, (failed ? 10 : 2) - elapsed)
    }
    @MainActor static func run(_ operation: () async -> Bool) async {
        let clock = ContinuousClock()
        while !Task.isCancelled {
            let start = clock.now
            let failed = await operation()
            guard !Task.isCancelled else { return }
            let elapsed = start.duration(to: clock.now).components
            let seconds = Double(elapsed.seconds) + Double(elapsed.attoseconds) / 1e18
            do { try await Task.sleep(for: .seconds(delay(elapsed: seconds, failed: failed))) }
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
