import XCTest
@testable import AEyeCore

final class TuningTests: XCTestCase {
    func testFrameSizeKeepsAspect() {
        XCTAssertTrue(frameSize(width: 1920, height: 1080) == (640, 360))
        XCTAssertTrue(frameSize(width: 1080, height: 1920) == (360, 640))
        XCTAssertTrue(frameSize(width: 500, height: 400) == (500, 400))   // never upscales
    }
    func testServerURLNormalises() {
        XCTAssertEqual(serverURL(from: "ws://192.168.1.5:8000/ws2")?.absoluteString, "ws://192.168.1.5:8000/ws2")
        XCTAssertEqual(serverURL(from: "192.168.1.5:8000")?.absoluteString, "ws://192.168.1.5:8000/ws2")
        XCTAssertEqual(serverURL(from: "https://mac.tail1.ts.net")?.absoluteString, "wss://mac.tail1.ts.net/ws2")
        XCTAssertEqual(serverURL(from: " http://10.0.0.2:8000/ ")?.absoluteString, "ws://10.0.0.2:8000/ws2")
        XCTAssertNil(serverURL(from: ""))
        XCTAssertNil(serverURL(from: "   "))
    }
}
