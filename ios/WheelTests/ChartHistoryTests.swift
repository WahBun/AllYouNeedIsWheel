import XCTest
import WebKit
@testable import Wheel

@MainActor
final class ChartHistoryTests: XCTestCase {
    final class Bridge: NSObject, WKScriptMessageHandler {
        let ready: XCTestExpectation
        var requests: [[String: Any]] = []
        init(_ ready: XCTestExpectation) { self.ready = ready }
        func userContentController(_ controller: WKUserContentController, didReceive message: WKScriptMessage) {
            if message.name == "chartReady" { ready.fulfill() }
            else if let body = message.body as? [String: Any] { requests.append(body) }
        }
    }
    func testHistoryPrefixPreservesCurrentCorrectionAndBounds() {
        let saved = (1...20000).map { ["time": Double($0), "close": 100.0] }
        let current: [[String: Any]] = [["time": 19999.0, "close": 101.0], ["time": 20000.0, "close": 102.0], ["time": 20001.0, "close": 103.0]]
        let result = ChartHistoryBuffer.prepending(saved, to: current)
        XCTAssertEqual(result.count, 20000)
        XCTAssertEqual(result.first?["time"] as? Double, 2)
        XCTAssertEqual(result[result.count-3]["close"] as? Double, 101)
        XCTAssertEqual(result.last?["close"] as? Double, 103)
        XCTAssertEqual(ChartHistoryBuffer.prepending(saved, to: []).count, 20000)
    }
    func testHistoryInsertionSurvivesCoalescedTickAndContextSwitch() {
        var bridge = ChartPacketDelivery()
        var packet: [String: Any] = ["stream_id": "s", "con_id": 7, "generation": "g", "interval": 5, "session": "rth", "sequence": 1, "mode": "snapshot", "bars": [["time": 2]], "history_revision": 0]
        XCTAssertEqual(bridge.outgoing(packet)["mode"] as? String, "snapshot")
        packet["sequence"] = 2; packet["mode"] = "delta"; packet["changed_bars"] = [["time": 3]]
        packet["bars"] = [["time": 2], ["time": 3]]
        XCTAssertEqual((bridge.outgoing(packet)["bars"] as? [[String: Int]])?.count, 1)
        // A page arrives while the JS bridge is busy; the next tick overwrites
        // that pending packet. The retained revision still forces full delivery.
        packet["bars"] = [["time": 1], ["time": 2], ["time": 3], ["time": 4]]
        packet["history_revision"] = 1; packet["sequence"] = 3; packet["changed_bars"] = [["time": 4]]
        let insertion = bridge.outgoing(packet)
        XCTAssertEqual(insertion["mode"] as? String, "snapshot")
        XCTAssertEqual((insertion["bars"] as? [[String: Int]])?.count, 4)
        XCTAssertTrue(bridge.outgoing(packet).isEmpty)
        packet["sequence"] = 4
        XCTAssertEqual(bridge.outgoing(packet)["mode"] as? String, "delta")
        packet["history_revision"] = 2
        XCTAssertEqual(bridge.outgoing(packet)["mode"] as? String, "snapshot", "History also delivers with an unchanged tick sequence")
        for (cid, interval) in [(8, 15), (9, 480), (7, 5)] {
            packet["con_id"] = cid; packet["interval"] = interval
            XCTAssertEqual(bridge.outgoing(packet)["mode"] as? String, "snapshot")
        }
        bridge.reset()
        XCTAssertEqual(bridge.outgoing(packet)["mode"] as? String, "snapshot")
    }
    func testWKHistoryBridgeAllIntervalsAndAutomaticPreload() async throws {
        let bundle = Bundle(for: ChartViewportWebView.self)
        func resource(_ name: String, _ ext: String) throws -> String {
            let url = try XCTUnwrap(bundle.url(forResource: name, withExtension: ext) ?? bundle.url(forResource: name, withExtension: ext, subdirectory: "ChartAssets"))
            return try String(contentsOf: url, encoding: .utf8)
        }
        let html = try resource("stock-chart", "html").replacingOccurrences(of: "/*LIBRARY*/", with: resource("lightweight-charts.standalone.production", "js"))
        let ready = expectation(description: "WK chart ready"), bridge = Bridge(ready)
        let config = WKWebViewConfiguration()
        config.userContentController.add(bridge, name: "chartReady")
        config.userContentController.add(bridge, name: "historyRequest")
        let web = ChartViewportWebView(frame: CGRect(x: 0, y: 0, width: 393, height: 750), configuration: config)
        let window = UIWindow(frame: web.frame), controller = UIViewController()
        window.rootViewController = controller; window.isHidden = false; controller.view.addSubview(web)
        defer { window.isHidden = true; web.removeFromSuperview(); web.stopLoading() }
        web.loadHTMLString(html, baseURL: nil)
        await fulfillment(of: [ready], timeout: 15)
        // No input events are synthesized: this also covers slow/momentum pans
        // after the old 1.5-second gesture deadline.
        try await Task.sleep(for: .seconds(1.6))
        for dark in [false, true] {
            for interval in [1, 3, 5, 10, 15, 60, 480, 1440, 10080, 43200] {
                for session in ["rth", "all"] {
                    let cid = interval + 7 + (session == "all" ? 100000 : 0)
                    bridge.requests = []
                    _ = try await web.evaluateJavaScript("""
                    window.recent=Array.from({length:400},(_,i)=>({time:1791984600-(399-i)*\(interval)*60,open:100,high:101,low:99,close:100}));
                    window.payload={con_id:\(cid),security_type:'\(["STK", "OPT", "FUT"][interval % 3])',generation:'\(dark)-\(interval)-\(session)',account_epoch:'epoch',interval:\(interval),session:'\(session)',history_expanded:true,history_expansion_attempted:true,bars:recent};
                    applyChartState({width:393,height:750,config:{dark:\(dark),display:{nativeCompact:true},con_id:7,entry:0,quantity:1,paper:{enabled:false}},packet:payload});
                    true
                    """)
                    try await Task.sleep(for: .milliseconds(50))
                    bridge.requests = []
                    _ = try await web.evaluateJavaScript("chart.timeScale().setVisibleLogicalRange({from:0,to:45});true")
                    for _ in 0..<50 {
                        if bridge.requests.contains(where: { ($0["before"] as? Double ?? 0) > 0 }) { break }
                        try await Task.sleep(for: .milliseconds(20))
                    }
                    let request = try XCTUnwrap(bridge.requests.first { ($0["before"] as? Double ?? 0) > 0 })
                    XCTAssertEqual(request["con_id"] as? Int, cid)
                    XCTAssertEqual(request["interval"] as? Int, interval)
                    XCTAssertEqual(request["session"] as? String, session)
                    XCTAssertEqual(request["account_epoch"] as? String, "epoch")
                    _ = try await web.evaluateJavaScript("""
                    var older=Array.from({length:100},(_,i)=>({...recent[0],time:recent[0].time-(100-i)*payload.interval*60}));
                    applyChartState({width:393,height:750,packet:{...payload,bars:[...older,...recent]}});true
                    """)
                    let from = try await web.evaluateJavaScript("chart.timeScale().getVisibleLogicalRange().from") as? Double
                    XCTAssertEqual(try XCTUnwrap(from), 100, accuracy: 1)
                    bridge.requests = []
                    _ = try await web.evaluateJavaScript("applyChartState({width:393,height:750,packet:{...payload,generation:payload.generation+'-short',bars:recent.slice(-80)}});chart.timeScale().setVisibleLogicalRange({from:32,to:84});true")
                    for _ in 0..<50 {
                        if bridge.requests.contains(where: { ($0["before"] as? Double ?? 0) > 0 }) { break }
                        try await Task.sleep(for: .milliseconds(20))
                    }
                    XCTAssertTrue(bridge.requests.contains { ($0["before"] as? Double ?? 0) > 0 }, "Automatic preload: \(interval) \(session)")
                    _ = try await web.callAsyncJavaScript("await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));chart.timeScale().setVisibleLogicalRange({from:32,to:84});return true", arguments: [:], in: nil, contentWorld: .page)
                    let tail = try await web.evaluateJavaScript("chart.timeScale().getVisibleLogicalRange().from") as? Double
                    XCTAssertGreaterThan(try XCTUnwrap(tail), 5)
                }
            }
        }
    }
}
