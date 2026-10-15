import Foundation
import Observation

@MainActor @Observable
final class ChartFavorites {
    private(set) var items: [ChartInstrument] = []
    private(set) var ready = false
    private(set) var busy = false
    private(set) var message: String?
    private var revision = 0
    private var base = ""
    private var generation = 0
    private let session: URLSession
    private let defaults: UserDefaults
    private var cacheKey: String { "wheel.native.synced-favorites:\(base)" }
    private var migrationKey: String { "wheel.native.favorites-imported:\(base)" }

    init(session: URLSession = .shared, defaults: UserDefaults = .standard) {
        self.session = session; self.defaults = defaults
    }
    func configure(base: String) {
        let address = base.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        guard address != self.base else { return }
        generation += 1; self.base = address; ready = false; busy = false; revision = 0; message = nil
        items = defaults.data(forKey: cacheKey).flatMap { try? JSONDecoder().decode([ChartInstrument].self, from: $0) } ?? []
    }
    private func request(_ operations: [[String: Any]]? = nil) async throws -> [String: Any] {
        guard let url = URL(string: base), url.scheme == "https", url.host != nil,
              url.user == nil, url.password == nil, url.query == nil, url.fragment == nil else {
            throw AppError.message("A private HTTPS backend address is required.")
        }
        var request = URLRequest(url: url.appendingPathComponent("api/chart-favorites"), cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 15)
        if let operations {
            request.httpMethod = "POST"
            request.setValue("1", forHTTPHeaderField: "X-All-You-Need-Is-Wheel")
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try JSONSerialization.data(withJSONObject: ["operations": operations])
        }
        let (data, response) = try await session.data(for: request)
        guard let response = response as? HTTPURLResponse, (200..<300).contains(response.statusCode) else {
            throw AppError.message("Favorites sync unavailable. Check the backend and try again.")
        }
        guard let result = try JSONSerialization.jsonObject(with: data) as? [String: Any],
              result["revision"] is Int, result["favorites"] is [[String: Any]] else {
            throw AppError.message("Invalid favorites response.")
        }
        return result
    }
    private func accept(_ response: [String: Any]) throws {
        let data = try JSONSerialization.data(withJSONObject: response["favorites"] ?? [])
        items = try JSONDecoder().decode([ChartInstrument].self, from: data)
        revision = response["revision"] as? Int ?? 0; ready = true
        defaults.set(data, forKey: cacheKey)
        let conflicts = response["conflicts"] as? [[String: Any]] ?? []
        message = conflicts.isEmpty ? nil : conflicts.contains { $0["reason"] as? String == "limit" }
            ? "Favorites limit: 100. Some local favorites were not imported."
            : "Favorites changed on another device. Review the list and try again."
    }
    func refresh() async {
        guard !busy, !base.isEmpty else { return }
        let token = generation; busy = true
        defer { if token == generation { busy = false } }
        do {
            let response = try await request()
            guard token == generation else { return }
            try accept(response)
            if !defaults.bool(forKey: migrationKey) {
                let legacy = defaults.data(forKey: "wheel.native.favorite-contracts")
                    .flatMap { try? JSONSerialization.jsonObject(with: $0) as? [[String: Any]] } ?? []
                let operations: [[String: Any]] = legacy.prefix(100).compactMap { value in
                    guard let id = value["id"] as? Int, id > 0 else { return nil }
                    return ["op": UUID().uuidString, "kind": "import", "id": id, "base": revision, "value": value]
                }
                if !operations.isEmpty {
                    let imported = try await request(operations)
                    guard token == generation else { return }
                    try accept(imported)
                }
                // Keep the original local list as a migration backup.
                defaults.set(true, forKey: migrationKey)
            }
        } catch {
            if token == generation { ready = false; message = connectionMessage(error) }
        }
    }
    func toggle(_ item: ChartInstrument) async {
        guard ready, !busy else { return }
        let token = generation; busy = true; message = nil
        defer { if token == generation { busy = false } }
        let remove = items.contains { $0.id == item.id }
        do {
            let value = try JSONSerialization.jsonObject(with: JSONEncoder().encode(item))
            let result = try await request([["op": UUID().uuidString, "kind": remove ? "delete" : "put",
                "id": item.id, "base": revision, "value": value]])
            guard token == generation else { return }
            try accept(result)
        } catch {
            // An unknown response is reconciled by the next read, never a replayed write.
            if token == generation { ready = false; message = "Favorites update could not be confirmed. Refresh to check the saved list." }
        }
    }
}
