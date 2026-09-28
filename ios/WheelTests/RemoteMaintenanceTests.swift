import XCTest
@testable import Wheel

final class RemoteMaintenanceTests: XCTestCase {
    func testUsesBackendHostWithoutForwardingHTTPSPortOrPath() {
        XCTAssertEqual(RemoteMaintenance.screenURL(" https://example.test:8443/api ")?.absoluteString,
                       "vnc://example.test")
    }
    func testRejectsCredentialsAndNonHTTPSAddresses() {
        for input in ["", "http://example.test", "https://user:secret@example.test", "https://example.test?token=secret", "https://example.test#secret"] {
            XCTAssertNil(RemoteMaintenance.screenURL(input))
        }
    }
}
