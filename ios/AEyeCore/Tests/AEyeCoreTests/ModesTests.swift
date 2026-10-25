import XCTest
@testable import AEyeCore

final class ModesTests: XCTestCase {
    func testDadCallUsesLiveWithoutStartingSinkGuide() {
        XCTAssertEqual(Modes.dad.pack, "general")
        XCTAssertNil(Modes.startText(for: Modes.dad))
        XCTAssertTrue(LiveConfiguration.enabled(mode: Modes.dad.id, google: true, privateMode: false))
        XCTAssertFalse(LiveConfiguration.enabled(mode: Modes.dad.id, google: true, privateMode: true))
        XCTAssertEqual(Modes.startText(for: Modes.all[0]), "sink")
    }
    func testRingContents() {
        XCTAssertEqual(Modes.all.map(\.id), ["plumbing", "general", "memory"])
        XCTAssertEqual(Modes.all.map(\.title), ["Sink", "General", "Memory"])
        XCTAssertEqual(Modes.all[Modes.defaultIndex].id, "plumbing")
        XCTAssertEqual(Modes.available(extraModes: false), Modes.all)
        XCTAssertEqual(Modes.available(extraModes: true).map(\.id),
                       ["plumbing", "general", "memory", "pc_build", "cooking", "assemble", "mechanic", "engineering"])
        XCTAssertEqual(Modes.extras.filter(\.requiresPowerOff).map(\.id), ["pc_build"])
    }

    func testEngineering() {
        let mode = Modes.extras.first { $0.id == "engineering" }!
        XCTAssertTrue(mode.isAvailable)
        XCTAssertEqual(mode.pack, "general")
        XCTAssertEqual(Modes.startText(for: mode), "light an LED")
        let base = URL(string: "ws://localhost/ws2?token=fixture")!
        let url = LiveConfiguration.url(base, live: false, google: true, privateMode: true, engineering: true)!
        let query = URLComponents(url: url, resolvingAgainstBaseURL: false)!.queryItems!
        XCTAssertTrue(query.contains(URLQueryItem(name: "mode", value: "engineering")))
        XCTAssertFalse(query.contains { $0.name == "google" })
    }

    func testHomeStart() {
        XCTAssertEqual(Modes.homePack, "home")
        XCTAssertEqual(Modes.homeStartText, "sink")
        XCTAssertTrue(Modes.all.contains { $0.pack == Modes.homePack })
    }
}
