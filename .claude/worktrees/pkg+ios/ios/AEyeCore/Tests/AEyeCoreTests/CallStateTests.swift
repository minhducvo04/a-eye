import XCTest
@testable import AEyeCore

final class CallStateTests: XCTestCase {
    func testReconnectResetsPowerOffAndDrawing() {
        let box = DrawOp(kind: "box", id: "a", role: nil, label: nil, ttlMs: nil, bbox: [0, 0, 1, 1], center: nil,
                         r: nil, from: nil, to: nil, points: nil, at: nil, text: nil)
        let s = CallState.initial
            .reduce(.connected, nowMs: 0)
            .reduce(.powerOffTapped, nowMs: 0)
            .reduce(.server(.draw(agent: .helper, seq: 1, ops: [box])), nowMs: 0)
            .reduce(.disconnected, nowMs: 0)
        XCTAssertEqual(s.link, .reconnecting)
        let back = s.reduce(.connected, nowMs: 0)
        XCTAssertEqual(back.link, .live)
        XCTAssertFalse(back.powerOffConfirmed)
        XCTAssertTrue(back.draw.visible(nowMs: 0).isEmpty)
        XCTAssertTrue(back.showsPowerOffButton(for: Modes.all[1]))
    }
    func testSayBecomesCaptionAndClearsError() {
        let s = CallState.initial
            .reduce(.server(.error(code: "vision_unavailable", message: "Vision is unavailable.")), nowMs: 0)
        XCTAssertEqual(s.errorText, "Vision is unavailable.")
        let t = s.reduce(.server(.say(agent: .helper, utteranceId: "u1", text: "Hi")), nowMs: 0)
        XCTAssertEqual(t.caption, Caption(agent: .helper, text: "Hi", utteranceId: "u1")); XCTAssertNil(t.errorText)
    }
    func testPresenceAndMarket() {
        let r = MarketResponse(category: "ram", items: [], note: nil)
        let s = CallState.initial
            .reduce(.server(.agentState(agent: .shopper, state: .thinking)), nowMs: 0)
            .reduce(.server(.marketResults(r)), nowMs: 0)
        XCTAssertEqual(s.presence[.shopper], .thinking); XCTAssertEqual(s.market, r)
        XCTAssertNil(s.reduce(.marketDismissed, nowMs: 0).market)
    }
    func testHelperSpeakingAfterShopperSpeakingLeavesShopperIdle() {
        let s = CallState.initial
            .reduce(.server(.agentState(agent: .shopper, state: .speaking)), nowMs: 0)
            .reduce(.server(.agentState(agent: .helper, state: .speaking)), nowMs: 0)
        XCTAssertEqual(s.presence[.helper], .speaking)
        XCTAssertEqual(s.presence[.shopper], .idle)
    }
    func testConnectedClearsPresence() {
        let s = CallState.initial
            .reduce(.server(.agentState(agent: .shopper, state: .speaking)), nowMs: 0)
            .reduce(.connected, nowMs: 0)
        XCTAssertTrue(s.presence.isEmpty)
    }
    func testIgnoredMessageLeavesStateUnchanged() {
        let s = CallState.initial.reduce(.connected, nowMs: 0)
        XCTAssertEqual(s.reduce(.server(.ignored(type: "metrics")), nowMs: 0), s)
    }
    func testPowerOffButtonOnlyForPCBuild() {
        XCTAssertFalse(CallState.initial.showsPowerOffButton(for: Modes.all[0]))
        XCTAssertFalse(CallState.initial.reduce(.powerOffTapped, nowMs: 0).showsPowerOffButton(for: Modes.all[1]))
    }
}
