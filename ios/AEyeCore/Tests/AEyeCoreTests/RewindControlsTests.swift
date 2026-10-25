import XCTest
@testable import AEyeCore

final class RewindControlsTests: XCTestCase {
    func testRewindRetentionAndServerRefusal() throws {
        var state = RewindControls()
        let on = try XCTUnwrap(RewindStatus.decode(Data(#"{"type":"rewind_state","on":true}"#.utf8)))
        state.request(keep: false)
        XCTAssertTrue(state.pending)
        XCTAssertFalse(state.on)
        state.receive(on)
        XCTAssertTrue(state.on)
        XCTAssertFalse(state.keep)
        XCTAssertFalse(state.pending)
        state.request(keep: true)
        XCTAssertFalse(state.keep)
        state.receive(on)
        XCTAssertTrue(state.keep)
        let payload = try XCTUnwrap(JSONSerialization.jsonObject(with:
            ClientMessage.rewind(sessionId: "fixture", on: true, keep: state.keep)) as? [String: Any])
        XCTAssertEqual(payload["keep"] as? Bool, true)
        state.request(keep: true)
        state.receive(try XCTUnwrap(RewindStatus.decode(Data(#"{"type":"rewind_state","on":false}"#.utf8))))
        XCTAssertFalse(state.on)
        XCTAssertTrue(state.keep, "Stopping capture must not discard the user's retention choice")
        state.request(keep: false)
        state.receive(try XCTUnwrap(RewindStatus.decode(Data(#"{"type":"rewind_state","on":false,"locked":true}"#.utf8))))
        XCTAssertFalse(state.on)
        XCTAssertFalse(state.keep)
        XCTAssertTrue(state.locked)
        XCTAssertFalse(state.pending)
        XCTAssertFalse(RewindControls().keep)
        XCTAssertNil(RewindStatus.decode(Data(#"{"type":"say","on":true}"#.utf8)))
    }
}
