import XCTest
import SwiftUI
@testable import Wheel

@MainActor final class HoldingsShareTests: XCTestCase {
    func testWeightsIncludeShortExposureAndPositiveCash() throws {
        let json = #"{"summary":{"account_value":950,"cash_balance":50},"positions":[{"symbol":"AAA","position":10,"security_type":"STK","market_value":1000},{"symbol":"AAA","position":-1,"security_type":"OPT","market_value":-100},{"symbol":"BBB","position":1,"security_type":"STK","market_value":null}]}"#
        let portfolio = try JSONDecoder().decode(Bootstrap.self, from: Data(json.utf8))
        let slices = HoldingsShareSlice.make(portfolio)
        XCTAssertEqual(slices.map(\.name), ["AAA", "Cash"])
        XCTAssertEqual(slices.map(\.value), [1100, 50])
        XCTAssertTrue(HoldingsShareSlice.make(nil).isEmpty)
    }
    func testImportedImageIsDownsampledAndInvalidDataRejected() throws {
        XCTAssertNil(ShareBackgroundImport.decode(Data("not an image".utf8)))
        let source = UIGraphicsImageRenderer(size: CGSize(width: 2400, height: 1800)).image { context in
            UIColor.blue.setFill(); context.fill(CGRect(x: 0, y: 0, width: 2400, height: 1800))
        }
        let decoded = try XCTUnwrap(ShareBackgroundImport.decode(try XCTUnwrap(source.jpegData(compressionQuality: 0.8))))
        XCTAssertLessThanOrEqual(max(decoded.size.width, decoded.size.height), 1600)
        let renderer = ImageRenderer(content: HoldingsShareArtwork(slices: [.init(name: "AAA", value: 1)], customImage: decoded).frame(width: 1080, height: 1080))
        XCTAssertNotNil(renderer.uiImage)
    }
    func testEveryBackgroundRendersExport() throws {
        XCTAssertEqual(HoldingsShareBackground.allCases.count, 7)
        for background in HoldingsShareBackground.allCases {
            XCTAssertNotNil(UIImage(named: background.rawValue))
            let renderer = ImageRenderer(content: HoldingsShareArtwork(slices: [.init(name: "AAA", value: 80), .init(name: "BBB", value: 20)], background: background).frame(width: 1080, height: 1080))
            let image = try XCTUnwrap(renderer.uiImage)
            XCTAssertEqual(image.size.width, 1080)
            let png = try XCTUnwrap(image.pngData())
            try png.write(to: URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("preview-\(background.rawValue).png"))
        }
    }
}
