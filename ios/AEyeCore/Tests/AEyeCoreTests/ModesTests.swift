import XCTest
@testable import AEyeCore

final class ModesTests: XCTestCase {
    func testRingContents() {
        XCTAssertEqual(Modes.all.filter(\.isAvailable).compactMap(\.pack),
                       ["general", "pc_build", "cooking", "assemble", "memory", "home", "general"])
        XCTAssertEqual(Modes.all.filter { !$0.isAvailable }.map(\.title), ["Mechanic", "Engineering"])
        XCTAssertEqual(Modes.all[Modes.defaultIndex].id, "gemini-live")
        XCTAssertEqual(Modes.all.filter(\.requiresPowerOff).map(\.id), ["pc_build"])
    }

    func testRingOrderMatchesWeb() {
        // Same ids and order as client-web/agent.js MODES.
        XCTAssertEqual(Modes.all.map(\.id),
                       ["general", "pc_build", "cooking", "assemble", "memory", "mechanic", "plumbing", "engineering", "gemini-live"])
        XCTAssertEqual(Modes.all.first { $0.id == "plumbing" }?.title, "Sink")
    }

    func testHomeStart() {
        XCTAssertEqual(Modes.homePack, "home")
        XCTAssertEqual(Modes.homeStartText, "sink")
        XCTAssertTrue(Modes.all.contains { $0.pack == Modes.homePack })
    }
}
