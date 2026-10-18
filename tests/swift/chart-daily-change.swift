import Foundation

@main struct DailyChangeChecks {
    static func main() {
        let now = Date(timeIntervalSince1970: 1000)
        var packet: [String: Any] = ["con_id": 7, "account_epoch": "paper", "last_price": 101.25, "previous_close": 100.0]
        func value(_ packet: [String: Any], cid: Int = 7, epoch: String = "paper", backend: String = "test", received: Date? = now, reference: ChartDailyChange.Reference? = nil, at: Date = now) -> Double? {
            ChartDailyChange.percent(packet: packet, conID: cid, epoch: epoch, backend: backend, received: received, reference: reference, now: at)
        }
        precondition(value(packet) == 1.25)
        packet["last_price"] = 98.5; precondition(value(packet) == -1.5)
        packet["last_price"] = 99.999; precondition(value(packet) == 0)
        precondition(ChartDailyChange.text(value(packet)) == "0.00%")
        precondition(ChartDailyChange.text(-1.5) == "-1.50%")
        precondition(ChartDailyChange.text(1.25) == "+1.25%")
        precondition(value(packet, cid: 8) == nil && value(packet, epoch: "live") == nil)
        precondition(value(packet, received: nil) == nil && value(packet, at: now.addingTimeInterval(30)) == nil)
        packet["previous_close"] = 0.0; precondition(value(packet) == nil)
        packet["previous_close"] = Double.nan; precondition(value(packet) == nil)
        packet["last_price"] = 102.0
        let ref = ChartDailyChange.Reference(conID: 7, epoch: "paper", backend: "test", close: 100, received: now)
        precondition(value(packet, reference: ref) == 2)
        precondition(value(packet, backend: "other", reference: ref) == nil)
        precondition(value(packet, received: now.addingTimeInterval(30), reference: ref, at: now.addingTimeInterval(30)) == nil)
        packet["previous_close"] = 200.0; precondition(value(packet, reference: ref) == -49)
        packet["last_price"] = Double.infinity; precondition(value(packet, reference: ref) == nil)
        precondition(ChartDailyChange.text(nil) == "—")
        print("PASS native daily change: signs, rounded zero, missing/invalid values, contract/account/backend isolation, freshness and reference precedence")
    }
}
