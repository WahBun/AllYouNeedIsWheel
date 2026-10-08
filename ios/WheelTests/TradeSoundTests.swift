import XCTest
@testable import Wheel

final class TradeSoundTests: XCTestCase {
    func state(_ status: String = "Submitted", filled: Double = 0, known: Bool = true) -> [String: Any] {
        ["known": known, "orders": [["order_id": 1, "status": status, "filled": filled]]]
    }
    func testSnapshotReplayAndAccountSwitchSilent() {
        var detector = TradeSoundTransitions()
        XCTAssertNil(detector.observe(scope: "paper", state: state("Filled", filled: 2)))
        XCTAssertNil(detector.observe(scope: "paper", state: state("Filled", filled: 2)))
        XCTAssertNil(detector.observe(scope: "live", state: state("Filled", filled: 4)))
    }
    func testConfirmedChangesAndUnknownRead() {
        var detector = TradeSoundTransitions()
        XCTAssertNil(detector.observe(scope: "one", state: state()))
        XCTAssertNil(detector.observe(scope: "one", state: state("Filled", filled: 2, known: false)))
        XCTAssertEqual(detector.observe(scope: "one", state: state(filled: 1)), "filled")
        XCTAssertEqual(detector.observe(scope: "one", state: state("Cancelled", filled: 1)), "cancelled")
        XCTAssertNil(detector.observe(scope: "one", state: state("ApiCancelled", filled: 1)))
    }
    func testFillWinsOverOcaCancellation() {
        var detector = TradeSoundTransitions()
        _ = detector.observe(scope: "one", state: state())
        XCTAssertEqual(detector.observe(scope: "one", state: state("Cancelled", filled: 2)), "filled")
    }
    func testRejectionAndOldExecutionReplay() {
        var detector = TradeSoundTransitions()
        _ = detector.observe(scope: "one", state: state())
        var next = state("Inactive")
        next["executions"] = [["id":"old", "time":0.0]]
        XCTAssertEqual(detector.observe(scope: "one", state: next), "rejected")
        XCTAssertNil(detector.observe(scope: "one", state: next))
    }
    func testAudioAssetsBundled() {
        for name in ["filled", "cancelled", "rejected", "disconnected"] {
            XCTAssertNotNil(Bundle.main.url(forResource: name, withExtension: "wav"))
        }
    }

    @MainActor
    func testGlobalOrdersSurvivePagesAndResetOnAccountChange() {
        let defaults = UserDefaults.standard
        let saved = defaults.object(forKey: "wheel.native.sounds")
        defaults.set(true, forKey: "wheel.native.sounds")
        defer { if let saved { defaults.set(saved, forKey: "wheel.native.sounds") } else { defaults.removeObject(forKey: "wheel.native.sounds") } }
        var heard: [String] = []
        let sounds = ChartTradeSounds(output: { heard.append($0) })
        sounds.active = true
        var row = Order(id: 1, ticker: "TEST", quantity: 2, status: "processing", filled: 0)
        sounds.observeOrders(scope: "paper", orders: [row])
        row.filled = 1
        sounds.observeOrders(scope: "paper", orders: [row])
        sounds.observeOrders(scope: "paper", orders: [row])
        XCTAssertEqual(heard, ["filled"])
        sounds.observeOrders(scope: "paper", orders: []) // disappearance is not cancellation
        row.status = "cancelled"
        sounds.observeOrders(scope: "paper", orders: [row])
        XCTAssertEqual(heard, ["filled", "cancelled"])
        sounds.observeOrders(scope: "live", orders: [row])
        XCTAssertEqual(heard.count, 2)
        sounds.active = false
        sounds.play("rejected", enabled: true)
        XCTAssertEqual(heard.count, 2)
    }

    @MainActor
    func testDisconnectOnlyAfterKnownConnectionAndMute() {
        var heard: [String] = []
        let sounds = ChartTradeSounds(output: { heard.append($0) })
        sounds.active = true
        sounds.connection(false, enabled: true)
        sounds.connection(true, enabled: true)
        sounds.connection(false, enabled: true)
        sounds.connection(false, enabled: true)
        sounds.play("rejected", enabled: false)
        XCTAssertEqual(heard, ["disconnected"])
    }
}
