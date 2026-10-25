import Foundation

/// Existing /api/memory/settings payload. Preserve rooms, homes and retention when changing the switch.
public struct MemorySettings: Codable, Equatable {
    public struct Consent: Codable, Equatable {
        public var person: Bool
        public var caregiver: Bool
    }
    public struct Item: Codable, Equatable {
        public var item: String
        public var home: String
    }
    public var consent: Consent
    public var items: [Item]
    public var rooms: [String]
    public var kept_days: Int
    public var remembering: Bool

    public var canRemember: Bool { consent.person && consent.caregiver }

    public func changing(remembering on: Bool) -> MemorySettings {
        var next = self
        next.remembering = on && canRemember
        return next
    }
}

public struct RewindStatus: Decodable {
    public let on: Bool
    public let locked: Bool?
    public let notice: String?

    public static func decode(_ data: Data) -> RewindStatus? {
        guard let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              object["type"] as? String == "rewind_state" else { return nil }
        return try? JSONDecoder().decode(Self.self, from: data)
    }
}
