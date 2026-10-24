import XCTest
@testable import AEyeCore

final class ModesTests: XCTestCase {
    func testRingContents() {
        XCTAssertEqual(Modes.all.filter(\.isAvailable).compactMap(\.pack), ["general", "pc_build", "cooking", "assemble"])
        XCTAssertEqual(Modes.all.filter { !$0.isAvailable }.map(\.title), ["Mechanic", "Plumbing", "Engineering"])
        XCTAssertEqual(Modes.all[Modes.defaultIndex].pack, "pc_build")
        XCTAssertEqual(Modes.all.filter(\.requiresPowerOff).map(\.id), ["pc_build"])
    }
}
