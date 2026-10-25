import Foundation

/// Call-scoped choices. Never carry recording or retention consent into a new connection.
public struct RewindControls {
    public private(set) var on = false
    public private(set) var keep = false
    public private(set) var locked = false
    private var requestedKeep: Bool?
    public var pending: Bool { requestedKeep != nil }

    public init() {}

    public mutating func request(keep: Bool) {
        requestedKeep = keep
    }

    public mutating func receive(_ status: RewindStatus) {
        locked = status.locked == true
        on = status.on && !locked
        // The existing server acknowledges the rewind command but does not echo `keep`.
        keep = !locked && (requestedKeep ?? keep)
        requestedKeep = nil
    }
}
