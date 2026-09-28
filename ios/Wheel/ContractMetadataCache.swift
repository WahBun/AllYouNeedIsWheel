import Foundation

/// Only contract lists belong here. Quotes, capacity and orders are never cached.
@MainActor
final class ContractMetadataCache {
    private struct Entry {
        let payload: [String: Any]
        let expires: Date
        let day: String
    }
    private var entries: [URL: Entry] = [:]
    private var pending: [URL: Task<[String: Any], Error>] = [:]
    private var generation = 0
    private let now: () -> Date
    private let dayFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(identifier: "America/New_York")
        formatter.dateFormat = "yyyyMMdd"
        return formatter
    }()
    init(now: @escaping () -> Date = Date.init) { self.now = now }

    func clear() {
        generation += 1
        entries.removeAll()
        pending.values.forEach { $0.cancel() }
        pending.removeAll()
    }

    func load(_ url: URL, fetch: @escaping @MainActor () async throws -> [String: Any]) async throws -> [String: Any] {
        guard ["expirations", "strikes"].contains(url.lastPathComponent) else { return try await fetch() }
        try Task.checkCancellation()
        let token = generation
        let date = now()
        let day = dayFormatter.string(from: date)
        if let entry = entries[url], entry.expires > date, entry.day == day { return entry.payload }
        if let task = pending[url] {
            let value = try await task.value
            try Task.checkCancellation()
            guard token == generation else { throw CancellationError() }
            return value
        }
        let task = Task { try await fetch() }
        pending[url] = task
        defer { if token == generation { pending[url] = nil } }
        let payload = try await task.value
        if token == generation, dayFormatter.string(from: now()) == day {
            let valid: Bool
            if url.lastPathComponent == "expirations" {
                valid = (payload["expirations"] as? [[String: Any]])?.contains { ($0["value"] as? String)?.isEmpty == false } == true
            } else {
                valid = (payload["strikes"] as? [Double])?.contains { $0.isFinite && $0 > 0 } == true
            }
            if valid {
                entries = entries.filter { $0.value.expires > now() && $0.value.day == day }
                if entries.count >= 64, let oldest = entries.min(by: { $0.value.expires < $1.value.expires })?.key { entries[oldest] = nil }
                entries[url] = Entry(payload: payload, expires: now().addingTimeInterval(300), day: day)
            }
        }
        try Task.checkCancellation()
        guard token == generation else { throw CancellationError() }
        return payload
    }
}
