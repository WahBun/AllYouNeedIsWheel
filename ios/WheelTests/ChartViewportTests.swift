import XCTest
import WebKit
@testable import Wheel

@MainActor
final class ChartViewportTests: XCTestCase {
    func testOptionHoldingsOpenExactContractChartsForBothSides() throws {
        for quantity in [-2, 2] {
            let data = Data("{\"symbol\":\"TSLA\",\"position\":\(quantity),\"security_type\":\"OPT\",\"strike\":250,\"expiration\":\"20261218\",\"option_type\":\"C\",\"con_id\":70}".utf8)
            var position = try JSONDecoder().decode(Position.self, from: data)
            XCTAssertTrue(position.hasChart)
            XCTAssertEqual(position.chartLabel, "TSLA 20261218 250 C")
            position.con_id = nil
            XCTAssertFalse(position.hasChart)
        }
    }

    func testHoldingOverlayUsesExactContractAndNormalizesCost() {
        let stock = Position(symbol: "TSLL", position: 200, security_type: "STK", con_id: 1, avg_cost: 9.5)
        let call = Position(symbol: "TSLL", position: -2, security_type: "OPT", strike: 11, expiration: "20261120", option_type: "CALL", con_id: 2, avg_cost: 78, multiplier: 100)
        let other = Position(symbol: "TSLA", position: -1, security_type: "OPT", strike: 11, expiration: "20261120", option_type: "CALL", con_id: 3, avg_cost: 50, multiplier: 100)
        let future = Position(symbol: "MES", position: 4, security_type: "FUT", con_id: 4, avg_cost: 39000, multiplier: 5)
        let all = [stock, call, other, future]
        let option = ChartHoldingOverlay.rows(positions: all, conID: 2, symbol: "TSLL", type: "OPT", chinese: false)
        XCTAssertEqual(option.count, 1)
        XCTAssertEqual(option[0]["price"] as? Double, 0.78)
        XCTAssertEqual(option[0]["title"] as? String, "Short × 2 · Avg cost")
        let underlying = ChartHoldingOverlay.rows(positions: all, conID: 1, symbol: "TSLL", type: "STK", chinese: false)
        XCTAssertEqual(underlying.count, 2)
        XCTAssertEqual(underlying[0]["price"] as? Double, 9.5)
        XCTAssertEqual(underlying[1]["price"] as? Double, 11)
        XCTAssertTrue((underlying[1]["title"] as? String)?.contains("20261120 CALL") == true)
        XCTAssertEqual(ChartHoldingOverlay.rows(positions: all, conID: 4, symbol: "MES", type: "FUT", chinese: false).first?["price"] as? Double, 7800)
        var legacyFuture = future; legacyFuture.multiplier = nil
        XCTAssertEqual(ChartHoldingOverlay.rows(positions: [legacyFuture], conID: 4, symbol: "MES", type: "FUT", chinese: false, chartMultiplier: 5).first?["price"] as? Double, 7800)
        var closed = call; closed.position = 0
        XCTAssertTrue(ChartHoldingOverlay.rows(positions: [closed], conID: 2, symbol: "TSLL", type: "OPT", chinese: false).isEmpty)
        var unknown = call; unknown.multiplier = nil
        XCTAssertTrue(ChartHoldingOverlay.rows(positions: [unknown], conID: 2, symbol: "TSLL", type: "OPT", chinese: false).isEmpty)
    }

    final class ReadyBridge: NSObject, WKScriptMessageHandler {
        let ready: XCTestExpectation
        init(_ ready: XCTestExpectation) { self.ready = ready }
        func userContentController(_ controller: WKUserContentController, didReceive message: WKScriptMessage) {
            ready.fulfill()
        }
    }
    func testNativeFirstFrameAndFullscreenWithoutMarketRefresh() async throws {
        let bundle = Bundle(for: ChartViewportWebView.self)
        func resource(_ name: String, _ ext: String) throws -> String {
            let url = try XCTUnwrap(bundle.url(forResource: name, withExtension: ext) ?? bundle.url(forResource: name, withExtension: ext, subdirectory: "ChartAssets"))
            return try String(contentsOf: url, encoding: .utf8)
        }
        let html = try resource("stock-chart", "html").replacingOccurrences(of: "/*LIBRARY*/", with: resource("lightweight-charts.standalone.production", "js"))
        let ready = expectation(description: "Chart script ready")
        let config = WKWebViewConfiguration()
        config.userContentController.add(ReadyBridge(ready), name: "chartReady")
        let web = ChartViewportWebView(frame: .zero, configuration: config)
        let window = UIWindow(frame: CGRect(x: 0, y: 0, width: 393, height: 852))
        let controller = UIViewController(); window.rootViewController = controller
        window.isHidden = false; controller.view.addSubview(web)
        defer { window.isHidden = true; web.removeFromSuperview(); web.stopLoading() }
        web.loadHTMLString(html, baseURL: nil)
        await fulfillment(of: [ready], timeout: 10)
        web.viewportReady = true
        _ = try await web.evaluateJavaScript("""
        applyChartState({width:0,height:0,config:{entry:9.14,quantity:1,entryType:'LMT',joinSide:-1,joinRevision:1,tpDistance:.25,slDistance:.25,templateRevision:1,priceRules:[]},packet:{generation:'native',interval:5,session:'rth',bars:Array.from({length:70},(_,i)=>({time:1000+i*300,open:9.1,high:9.2,low:8.97,close:8.97}))}});true
        """)
        var coldAxis: Double?
        for height in [680, 420, 680, 420] {
            web.frame = CGRect(x: 0, y: 0, width: 393, height: height)
            web.setNeedsLayout(); web.layoutIfNeeded(); web.synchronizeViewport(force: true)
            // Observe the very next render frames, with no new packet or timer refresh.
            let state = try await web.callAsyncJavaScript("""
            await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
            const c=document.querySelector('#chart table').getBoundingClientRect();
            return {width:c.width,height:c.height,bars:series.data().length,axis:chart.priceScale('right').width(),entryRight:parseFloat(document.getElementById('entry').style.right),label:document.getElementById('entry').textContent};
            """, arguments: [:], in: nil, contentWorld: .page) as? [String: Any]
            let result = try XCTUnwrap(state)
            XCTAssertEqual(try XCTUnwrap(result["width"] as? Double), 393, accuracy: 1)
            XCTAssertEqual(try XCTUnwrap(result["height"] as? Double), Double(height), accuracy: 1)
            XCTAssertEqual(result["bars"] as? Int, 70)
            XCTAssertTrue((result["entryRight"] as? Double ?? 0) >= (result["axis"] as? Double ?? 0) + 35)
            XCTAssertTrue((result["label"] as? String ?? "").contains("Sell LMT"))
            let axis = try XCTUnwrap(result["axis"] as? Double)
            XCTAssertLessThan(axis, 55)
            if let coldAxis { XCTAssertEqual(axis, coldAxis) } else { coldAxis = axis }
            _ = try await web.evaluateJavaScript("configure({entry:9.14,quantity:1,entryType:'LMT',priceRules:[{low:0,increment:.0001},{low:1,increment:.01}],tpDistance:.25,slDistance:.25,templateRevision:1});true")
        }
    }
}
