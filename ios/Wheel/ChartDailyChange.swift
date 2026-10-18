import Foundation

// Display-only daily change. Never use these values as an executable quote.
enum ChartDailyChange {
    struct Reference {
        let conID: Int
        let epoch: String
        let backend: String
        let close: Double
        let received: Date
    }

    static func percent(packet: [String: Any], conID: Int?, epoch: String?, backend: String,
                        received: Date?, reference: Reference?, now: Date = .now) -> Double? {
        guard let conID, conID > 0, let epoch, !epoch.isEmpty,
              packet["con_id"] as? Int == conID, packet["account_epoch"] as? String == epoch,
              let received, fresh(received, now),
              let price = positive(packet["last_price"]) else { return nil }
        var close = positive(packet["previous_close"])
        if close == nil, let reference, reference.conID == conID, reference.epoch == epoch,
           reference.backend == backend, fresh(reference.received, now) {
            close = positive(reference.close)
        }
        guard let close else { return nil }
        let value = (price / close - 1) * 100
        guard value.isFinite, (value * 100).isFinite else { return nil }
        let rounded = (value * 100).rounded() / 100
        return rounded == 0 ? 0 : rounded
    }

    static func text(_ percent: Double?) -> String {
        guard let percent else { return "—" }
        return String(format: percent == 0 ? "%.2f%%" : "%+.2f%%", locale: Locale(identifier: "en_US_POSIX"), percent)
    }

    private static func positive(_ value: Any?) -> Double? {
        guard let value = value as? Double, value.isFinite, value > 0 else { return nil }
        return value
    }

    private static func fresh(_ received: Date, _ now: Date) -> Bool {
        (0..<30).contains(now.timeIntervalSince(received))
    }
}
