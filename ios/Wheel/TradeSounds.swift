import Foundation
import AVFoundation

/// Mirrors the browser's confirmed-state transition rules; snapshots are silent.
struct TradeSoundTransitions {
    var scope: String?
    var rows: [String: [String: Any]] = [:]
    var fills: Set<String> = []
    var started = Date().timeIntervalSince1970
    mutating func observe(scope next: String, state: [String: Any]) -> String? {
        guard state["known"] as? Bool == true, state["sync_error"] as? Bool != true else { return nil }
        let orders = state["orders"] as? [[String: Any]] ?? []
        var incoming: [String: [String: Any]] = [:]
        for row in orders { if let id = row["order_id"] { incoming[String(describing: id)] = row } }
        let executions = state["executions"] as? [[String: Any]] ?? []
        let ids = Set(executions.compactMap { $0["id"].map { String(describing: $0) } })
        defer { scope = next; rows = incoming; fills = ids }
        guard scope == next else { return nil }
        var filled = executions.contains { row in
            guard let id = row["id"] else { return false }
            return !fills.contains(String(describing: id)) && (row["time"] as? Double ?? 0) >= started
        }
        var cancelled = false, rejected = false
        let cancellations = ["Cancelled", "ApiCancelled"]
        for (id, row) in incoming {
            guard let old = rows[id] else { continue }
            if (row["filled"] as? Double ?? 0) > (old["filled"] as? Double ?? 0) { filled = true }
            let status = row["status"] as? String ?? "", prior = old["status"] as? String ?? ""
            if status != prior {
                cancelled = cancelled || (cancellations.contains(status) && !cancellations.contains(prior))
                rejected = rejected || status == "Inactive"
            }
        }
        return filled ? "filled" : rejected ? "rejected" : cancelled ? "cancelled" : nil
    }
}

@MainActor
final class ChartTradeSounds {
    static let shared = ChartTradeSounds()
    private let output: ((String) -> Void)?
    init(output: ((String) -> Void)? = nil) { self.output = output }
    var active = false
    private var transitions = TradeSoundTransitions()
    private var tracker = FillTracker()
    private var orderScope: String?
    private var retained: [OrderID: Order] = [:]
    var enabled: Bool { UserDefaults.standard.object(forKey: "wheel.native.sounds") as? Bool ?? true }
    func observeOrders(scope: String, orders: [Order]) {
        guard active else { return }
        if orderScope != scope { reset(); orderScope = scope }
        for order in orders { retained[order.id] = order }
        let orders = Array(retained.values)
        let fills = tracker.ingest(orders)
        let rows: [[String: Any]] = orders.map { order in
            let raw = (order.ib_status ?? order.status).lowercased()
            let status = ["cancelled", "canceled", "apicancelled"].contains(raw) ? "Cancelled" : ["inactive", "rejected"].contains(raw) ? "Inactive" : raw
            return ["order_id": String(describing: order.id), "status": status, "filled": 0.0]
        }
        let event = transitions.observe(scope: scope, state: ["known": true, "orders": rows])
        if !fills.isEmpty { play("filled", enabled: enabled) }
        else if let event { play(event, enabled: enabled) }
    }
    private var connected: Bool?
    private var players: [AVAudioPlayer] = []
    private var last: [String: Date] = [:]
    private var next: TimeInterval = 0
    func reset() { transitions = TradeSoundTransitions(); connected = nil; tracker = FillTracker(); orderScope = nil; retained = [:]; stop() }
    func stop() { players.forEach { $0.stop() }; players.removeAll(); next = 0 }
    func connection(_ verified: Bool, enabled: Bool) {
        if connected == true && !verified { play("disconnected", enabled: enabled) }
        connected = verified
    }
    func observe(scope: String, state: [String: Any], enabled: Bool) {
        if let event = transitions.observe(scope: scope, state: state) { play(event, enabled: enabled) }
    }
    func play(_ name: String, enabled: Bool) {
        guard active, enabled, Date().timeIntervalSince(last[name] ?? .distantPast) >= 1 else { return }
        if let output { last[name] = .now; output(name); return }
        guard let url = Bundle.main.url(forResource: name, withExtension: "wav") else { return }
        do {
            // Respect the iPhone silent switch and mix with existing audio.
            try AVAudioSession.sharedInstance().setCategory(.ambient)
            let player = try AVAudioPlayer(contentsOf: url)
            let now = player.deviceCurrentTime
            guard next - now <= 3 else { return }
            players.removeAll { !$0.isPlaying && $0.deviceCurrentTime >= next }
            player.prepareToPlay()
            let at = max(now, next)
            guard player.play(atTime: at) else { return }
            last[name] = .now; next = at + player.duration; players.append(player)
        } catch { /* Audio failure must never affect order handling. */ }
    }
}
