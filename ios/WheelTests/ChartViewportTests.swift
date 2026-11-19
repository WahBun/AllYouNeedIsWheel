import XCTest
import WebKit
import SwiftUI
@testable import Wheel

@MainActor
final class ChartViewportTests: XCTestCase {
    func testTradingPageStartsLockedAndPricePlusOpensAlert() async throws {
        let savedPlus = UserDefaults.standard.object(forKey: "chartPlusButton")
        UserDefaults.standard.set(true, forKey: "chartPlusButton")
        let store = WheelStore(); store.demo = true; store.address = ""
        let position = Position(symbol: "TEST", position: 1, security_type: "STK", con_id: 7)
        let controller = UIHostingController(rootView: NavigationStack {
            StockChartView(position: position).environment(store).environment(\.scenePhase, .active)
        }.environment(\.locale, Locale(identifier: "en")))
        let scene = try XCTUnwrap(UIApplication.shared.connectedScenes.first as? UIWindowScene)
        let window = UIWindow(windowScene: scene)
        window.rootViewController = controller; window.makeKeyAndVisible()
        defer {
            window.rootViewController = nil; window.isHidden = true
            UserDefaults.standard.set(savedPlus, forKey: "chartPlusButton")
        }
        func findWeb(_ view: UIView) -> WKWebView? {
            if let web = view as? WKWebView { return web }
            return view.subviews.lazy.compactMap { findWeb($0) }.first
        }
        var chart: WKWebView?
        for _ in 0..<60 {
            if let web = findWeb(controller.view),
               (try? await web.evaluateJavaScript("typeof nativeTradingLocked==='function' && paperCID===7")) as? Bool == true {
                chart = web; break
            }
            try await Task.sleep(for: .milliseconds(100))
        }
        let web = try XCTUnwrap(chart)
        let locked = try await web.evaluateJavaScript("nativeTradingLocked()") as? Bool
        XCTAssertEqual(locked, true, "The actual SwiftUI page must supply the locked default")
        let result = try await web.evaluateJavaScript("""
        receive({con_id:7,generation:'fixture',interval:5,bars:[{time:1000,open:100,close:100,high:110,low:90}]});
        cursorOrderPrice=101.25;priceAdd.hidden=false;priceAdd.style.top='150px';priceAdd.click();
        const alertButton=priceMenu.querySelector('[data-price-alert]');
        const count=priceMenu.querySelectorAll('button').length;alertButton?.click();
        ({locked:nativeTradingLocked(),plusDisabled:priceAdd.disabled,count,price:document.querySelector('#chart-alert-editor [data-price]')?.value});
        """) as? [String: Any]
        XCTAssertEqual(result?["locked"] as? Bool, true)
        XCTAssertEqual(result?["plusDisabled"] as? Bool, false)
        XCTAssertEqual(result?["count"] as? Int, 1)
        XCTAssertEqual(result?["price"] as? String, "101.25")
        try await Task.sleep(for: .milliseconds(500))
        controller.view.layoutIfNeeded()
        let image = UIGraphicsImageRenderer(bounds: controller.view.bounds).image { _ in
            controller.view.drawHierarchy(in: controller.view.bounds, afterScreenUpdates: true)
        }
        let attachment = XCTAttachment(image: image); attachment.name = "Locked-native-price-alert"; attachment.lifetime = .keepAlways
        add(attachment)
        let webImage = try await web.takeSnapshot(configuration: nil)
        let webAttachment = XCTAttachment(image: webImage); webAttachment.name = "Native-alert-editor"; webAttachment.lifetime = .keepAlways
        add(webAttachment)
    }

    @MainActor func testPortfolioShortcutRoutesEachHeldContract() {
        let store = WheelStore(); store.demo = true
        for (kind, id) in [("OPT", 55), ("OPT", 60), ("STK", 2), ("FUT", 3)] {
            let position = Position(symbol: "TQQQ", position: kind == "STK" ? 10 : -1,
                                    security_type: kind, strike: kind == "OPT" ? Double(id) : nil,
                                    expiration: "20261120", option_type: "PUT", con_id: id)
            XCTAssertTrue(position.hasChart)
            store.selectedTab = "portfolio"
            store.openTradeChart(position)
            XCTAssertEqual(store.selectedTab, "trade")
            XCTAssertEqual(store.requestedTradeChart?.position.con_id, id)
            XCTAssertEqual(store.requestedTradeChart?.position.security_type, kind)
            XCTAssertEqual(store.requestedTradeChart?.position.strike, position.strike)
            XCTAssertEqual(store.requestedTradeChart?.resumeLast, false)
        }
        XCTAssertFalse(Position(symbol: "TQQQ", position: 0, security_type: "OPT", con_id: 55).hasChart)
        XCTAssertFalse(Position(symbol: "TQQQ", position: -1, security_type: "OPT").hasChart)
    }

    func testOptionHoldingsOpenExactContractChartsForBothSides() throws {
        for quantity in [-2, 2] {
            let data = Data("{\"symbol\":\"TSLA\",\"position\":\(quantity),\"security_type\":\"OPT\",\"strike\":250,\"expiration\":\"20261218\",\"option_type\":\"C\",\"con_id\":70}".utf8)
            var position = try JSONDecoder().decode(Position.self, from: data)
            XCTAssertTrue(position.hasChart)
            XCTAssertEqual(position.chartLabel, "TSLA · 12/18/26 · 250C")
            XCTAssertEqual(position.chartContractSymbol, "TSLA 20261218 250 C")
            position.con_id = nil
            XCTAssertFalse(position.hasChart)
        }
    }

    func testHoldingOverlayUsesExactContractAndFeeExclusiveFills() {
        let stock = Position(symbol: "TSLL", position: 200, security_type: "STK", con_id: 1, entry_fill_price: 9.5, avg_cost: 9.51)
        let call = Position(symbol: "TSLL", position: -2, security_type: "OPT", strike: 11, expiration: "20261120", option_type: "CALL", con_id: 2, entry_fill_price: 0.78, avg_cost: 77, multiplier: 100)
        let other = Position(symbol: "TSLA", position: -1, security_type: "OPT", strike: 11, expiration: "20261120", option_type: "CALL", con_id: 3, avg_cost: 50, multiplier: 100)
        let future = Position(symbol: "MES", position: 4, security_type: "FUT", con_id: 4, entry_fill_price: 7800, avg_cost: 39001, multiplier: 5)
        let all = [stock, call, other, future]
        let option = ChartHoldingOverlay.rows(positions: all, conID: 2, symbol: "TSLL", type: "OPT", chinese: false)
        XCTAssertEqual(option.count, 1)
        XCTAssertEqual(option[0]["price"] as? Double, 0.78)
        XCTAssertEqual(option[0]["title"] as? String, "-2 · Avg")
        XCTAssertEqual(ChartHoldingOverlay.rows(positions: all, conID: 1, symbol: "WRONG", type: "STK", chinese: false).count, ChartHoldingOverlay.rows(positions: all, conID: 1, symbol: "TSLL", type: "STK", chinese: false).count)
        let underlying = ChartHoldingOverlay.rows(positions: all, conID: 1, symbol: "TSLL", type: "STK", chinese: false)
        XCTAssertEqual(underlying.count, 2)
        XCTAssertEqual(underlying[0]["price"] as? Double, 9.5)
        XCTAssertEqual(underlying[1]["price"] as? Double, 11)
        XCTAssertEqual(underlying[1]["title"] as? String, "-2 11C@0.78")
        XCTAssertEqual(ChartHoldingOverlay.rows(positions: all, conID: 4, symbol: "MES", type: "FUT", chinese: false).first?["price"] as? Double, 7800)
        var closed = call; closed.position = 0
        XCTAssertTrue(ChartHoldingOverlay.rows(positions: [closed], conID: 2, symbol: "TSLL", type: "OPT", chinese: false).isEmpty)
        var unknown = call; unknown.entry_fill_price = nil
        let fallback = ChartHoldingOverlay.rows(positions: [unknown], conID: 2, symbol: "TSLL", type: "OPT", chinese: false)
        XCTAssertEqual(fallback.first?["price"] as? Double, 0.77)
        XCTAssertEqual(fallback.first?["title"] as? String, "-2 · IB Avg*")
        unknown.avg_cost = nil
        XCTAssertTrue(ChartHoldingOverlay.rows(positions: [unknown], conID: 2, symbol: "TSLL", type: "OPT", chinese: false).first?["price"] is NSNull)
    }

    func testStockReportedAverageRetainsDividendFractions() {
        var stock = Position(symbol: "TSLL", position: 302.1533, security_type: "STK", con_id: 1,
            reported_cost: ReportedStockCost(date: "2026-10-01", quantity: 302.1533, basis: 3999.48, average: 13.2366, currency: "USD"), avg_cost: 13.934)
        let rows = ChartHoldingOverlay.rows(positions: [stock], conID: 1, symbol: "TSLL", type: "STK", chinese: false)
        XCTAssertEqual(rows.first?["price"] as? Double, 13.2366)
        XCTAssertEqual(rows.first?["title"] as? String, "302.1533 · Avg")
        stock.position = 400
        XCTAssertTrue(ChartHoldingOverlay.rows(positions: [stock], conID: 1, symbol: "TSLL", type: "STK", chinese: false).first?["price"] is NSNull)
    }

    final class ReadyBridge: NSObject, WKScriptMessageHandler {
        let ready: XCTestExpectation
        init(_ ready: XCTestExpectation) { self.ready = ready }
        func userContentController(_ controller: WKUserContentController, didReceive message: WKScriptMessage) {
            ready.fulfill()
        }
    }
    private func loadNativeChart() async throws -> (ChartViewportWebView, UIWindow) {
        let bundle = Bundle(for: ChartViewportWebView.self)
        func resource(_ name: String, _ ext: String) throws -> String {
            let url = try XCTUnwrap(bundle.url(forResource: name, withExtension: ext) ?? bundle.url(forResource: name, withExtension: ext, subdirectory: "ChartAssets"))
            return try String(contentsOf: url, encoding: .utf8)
        }
        let html = try resource("stock-chart", "html").replacingOccurrences(of: "/*LIBRARY*/", with: resource("lightweight-charts.standalone.production", "js"))
            .replacingOccurrences(of: "</body>", with: "<script>" + resource("chart-add-orders", "js") + "</script></body>")
        let ready = expectation(description: "Chart script ready")
        let config = WKWebViewConfiguration()
        config.userContentController.add(ReadyBridge(ready), name: "chartReady")
        let web = ChartViewportWebView(frame: .zero, configuration: config)
        let window = UIWindow(frame: CGRect(x: 0, y: 0, width: 393, height: 852))
        let controller = UIViewController(); window.rootViewController = controller
        window.isHidden = false; controller.view.addSubview(web)
        web.loadHTMLString(html, baseURL: nil)
        await fulfillment(of: [ready], timeout: 10)
        web.viewportReady = true
        return (web, window)
    }
    func testNativeStockTailFollowsFreshLastEvenWithPriceLineHidden() async throws {
        let (web, window) = try await loadNativeChart()
        defer { window.isHidden = true; web.removeFromSuperview(); web.stopLoading() }
        let result = try await web.callAsyncJavaScript("""
        const t=Math.floor(Date.now()/300000)*300-300, base={time:t,open:660.4,high:661,low:660,close:660.91};
        const cfg=show=>({con_id:7,entry:0,quantity:1,priceRules:[{low:0,increment:.01}],display:{nativeCompact:true,showPriceLine:show}});
        const p={con_id:7,generation:'native',symbol:'QQQ',security_type:'STK',session:'rth',interval:5,
                 last_tick:t+20,server_time:t+23.6,bar_closes_at:t+300};
        function send(packet,show=true){applyChartState({width:393,height:700,config:cfg(show),packet});}
        send({...p,mode:'snapshot',bars:[{...base,time:t-300,high:662,low:659},base]});
        function tick(price,at,show,end=t+300){send({...p,mode:'delta',server_time:at,bars:[],bar_closes_at:end,
          display_last:{price,time:at,expires_at:at+3,ray_only:true}},show);}
        tick(661.11,t+24,true);
        const shownClose=series.data().at(-1).close;
        tick(660.31,t+25,false);
        await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
        const badge=document.getElementById('countdown');
        const hiddenWorks=getComputedStyle(currentPriceRay).display==='none'&&!badge.hidden&&
          !document.getElementById('countdown-time').hidden&&Number(document.getElementById('countdown-price').textContent)===660.31;
        const hiddenClose=series.data().at(-1).close, confirmedClose=previous.at(-1).close;
        send({},true);
        const shownAgain=getComputedStyle(currentPriceRay).display!=='none';
        tick(662,t+301,true,null);
        return [shownClose,hiddenClose,confirmedClose,hiddenWorks,shownAgain,series.data().at(-1).close,previous.length];
        """, arguments: [:], in: nil, contentWorld: .page)
        let rows = try XCTUnwrap(result as? [NSNumber])
        XCTAssertEqual(rows.map(\.doubleValue), [661.11, 660.31, 660.91, 1, 1, 660.91, 2])
    }

    func testRecheckingBrokerEntryDoesNotDrawABuyOrSellPreview() async throws {
        let (web, window) = try await loadNativeChart()
        defer { window.isHidden = true; web.removeFromSuperview(); web.stopLoading() }
        var reference = ChartEntryReference.broker(100.125)
        func line(_ paper: [String: Any]) async throws -> String {
            let active = paper["active"] as? Bool == true
            let price = try XCTUnwrap(Double(reference.text(brokerActive: active)))
            let result = try await web.callAsyncJavaScript("""
            applyChartState({width:393,height:700,
              config:{entry:price,quantity:1,con_id:7,display:{nativeCompact:true},priceRules:[{low:0,increment:0.01}],paper},
              packet:{con_id:7,generation:'test',interval:5,bars:[{time:1000,open:100,high:101,low:99,close:100}]}});
            const entry=document.getElementById('entry');
            return entry.hidden ? 'hidden' : entry.getAttribute('aria-label');
            """, arguments: ["price": price, "paper": paper], in: nil, contentWorld: .page)
            return try XCTUnwrap(result as? String)
        }
        let position: [String: Any] = ["active": true, "known": true, "entry": 100.125, "position": 1, "side": 1]
        let held = try await line(position)
        XCTAssertNotEqual(held, "hidden")
        reference.updateFromChart(100.13)
        let rechecking = try await line([:])
        XCTAssertEqual(rechecking, "hidden")
        let restored = try await line(position)
        XCTAssertEqual(restored, held)
        let working = try await line(["active": true, "known": true, "position": 0, "entry": 100.125, "side": 1])
        XCTAssertTrue(working.contains("LMT"))
        let closed = try await line(["active": false, "known": true])
        XCTAssertEqual(closed, "hidden")
        reference = .draft("99.50")
        let preview = try await line([:])
        XCTAssertTrue(preview.contains("Buy"))
    }

    func testNativeFirstFrameAndFullscreenWithoutMarketRefresh() async throws {
        let (web, window) = try await loadNativeChart()
        defer { window.isHidden = true; web.removeFromSuperview(); web.stopLoading() }
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
            return {width:c.width,height:c.height,bars:series.data().length,axis:chart.priceScale('right').width(),entryRight:parseFloat(document.getElementById('entry').style.right),direction:document.getElementById('order-direction').textContent,type:document.getElementById('order-type').textContent};
            """, arguments: [:], in: nil, contentWorld: .page) as? [String: Any]
            let result = try XCTUnwrap(state)
            XCTAssertEqual(try XCTUnwrap(result["width"] as? Double), 393, accuracy: 1)
            XCTAssertEqual(try XCTUnwrap(result["height"] as? Double), Double(height), accuracy: 1)
            XCTAssertEqual(result["bars"] as? Int, 70)
            XCTAssertTrue((result["entryRight"] as? Double ?? 0) >= (result["axis"] as? Double ?? 0) + 35)
            XCTAssertEqual(result["direction"] as? String, "Sell")
            XCTAssertTrue((result["type"] as? String ?? "").hasPrefix("LMT"))
            let axis = try XCTUnwrap(result["axis"] as? Double)
            XCTAssertLessThan(axis, 55)
            if let coldAxis { XCTAssertEqual(axis, coldAxis) } else { coldAxis = axis }
            _ = try await web.evaluateJavaScript("configure({entry:9.14,quantity:1,entryType:'LMT',priceRules:[{low:0,increment:.0001},{low:1,increment:.01}],tpDistance:.25,slDistance:.25,templateRevision:1});true")
        }
        let cachedHistory = try await web.callAsyncJavaScript("""
        const snapshot={...countdownPacket,bars:previous.map(b=>({...b}))};
        await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
        const before=timeToScreenCoordinate(previous.at(-1).time);
        receive({...snapshot,bars:snapshot.bars.slice(-20)});
        await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
        const shortCount=previous.length;
        receive(snapshot);
        await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
        return {before,after:timeToScreenCoordinate(previous.at(-1).time),shortCount,count:previous.length};
        """, arguments: [:], in: nil, contentWorld: .page) as? [String: Any]
        let historyState = try XCTUnwrap(cachedHistory)
        XCTAssertEqual(historyState["shortCount"] as? Int, 70)
        XCTAssertEqual(historyState["count"] as? Int, 70)
        XCTAssertEqual(try XCTUnwrap(historyState["before"] as? Double), try XCTUnwrap(historyState["after"] as? Double), accuracy: 0.1)
        let labels = try await web.callAsyncJavaScript("""
        const saved={...countdownPacket,bars:previous.map(b=>({...b}))};
        receive({...saved,bars:[]});updateVisibleExtrema();positionExtremaLabels();
        receive(saved);
        await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
        const live=document.getElementById('countdown'),low=extremaLabels.Low,high=extremaLabels.High;
        const rects=[live,low,high].map(e=>e.getBoundingClientRect());
        const widths=[live,low.lastChild,high.lastChild].map(e=>e.getBoundingClientRect().width);
        return {restored:[low,high].every(e=>!e.hidden&&getComputedStyle(e).display!=='none'),
          separated:rects.every((a,i)=>rects.every((b,j)=>i===j||a.bottom<=b.top+.02||b.bottom<=a.top+.02)),
          uniform:widths.every(w=>Math.abs(w-widths[0])<.1)};
        """, arguments: [:], in: nil, contentWorld: .page) as? [String: Any]
        XCTAssertEqual(labels?["restored"] as? Bool, true)
        XCTAssertEqual(labels?["separated"] as? Bool, true)
        XCTAssertEqual(labels?["uniform"] as? Bool, true)
    }
}
