import Foundation

/// One entry in the camera screen's mode ring. `pack` is the server skill pack id; nil means "coming soon".
public struct Mode: Equatable, Identifiable {
    public let id: String
    public let title: String
    public let symbol: String
    public let pack: String?
    public let requiresPowerOff: Bool

    public var isAvailable: Bool { pack != nil }

    public init(id: String, title: String, symbol: String, pack: String?, requiresPowerOff: Bool) {
        self.id = id
        self.title = title
        self.symbol = symbol
        self.pack = pack
        self.requiresPowerOff = requiresPowerOff
    }
}

public enum Modes {
    /// Ring order: the four server packs, then the coming-soon modes.
    public static let all: [Mode] = [
        Mode(id: "general", title: "General", symbol: "sparkles", pack: "general", requiresPowerOff: false),
        Mode(id: "pc_build", title: "PC Build", symbol: "desktopcomputer", pack: "pc_build", requiresPowerOff: true),
        Mode(id: "cooking", title: "Cooking", symbol: "frying.pan", pack: "cooking", requiresPowerOff: false),
        Mode(id: "assemble", title: "Assembly", symbol: "hammer", pack: "assemble", requiresPowerOff: false),
        Mode(id: "mechanic", title: "Mechanic", symbol: "car", pack: nil, requiresPowerOff: false),
        Mode(id: "plumbing", title: "Plumbing", symbol: "drop", pack: nil, requiresPowerOff: false),
        Mode(id: "engineering", title: "Engineering", symbol: "gearshape.2", pack: nil, requiresPowerOff: false),
    ]

    /// PC Build is centred at launch.
    public static let defaultIndex = 1
}
