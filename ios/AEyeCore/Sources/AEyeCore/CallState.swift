import Foundation

public enum LinkStatus: Equatable {
    case connecting, live, reconnecting
}

public struct Caption: Equatable {
    public let agent: Agent
    public let text: String
    public let utteranceId: String

    public init(agent: Agent, text: String, utteranceId: String) {
        self.agent = agent
        self.text = text
        self.utteranceId = utteranceId
    }
}

public enum CallEvent: Equatable {
    case connected
    case disconnected
    case server(ServerMessage)
    case powerOffTapped
    case marketDismissed
}

/// Everything the call screen renders. `reduce` is pure: it returns a new value and never mutates `self`.
public struct CallState: Equatable {
    public var link: LinkStatus
    public var caption: Caption?
    public var presence: [Agent: PresenceState]
    public var powerOffConfirmed: Bool
    public var draw: DrawState
    public var market: MarketResponse?
    public var errorText: String?

    public init(link: LinkStatus, caption: Caption?, presence: [Agent: PresenceState], powerOffConfirmed: Bool,
                draw: DrawState, market: MarketResponse?, errorText: String?) {
        self.link = link
        self.caption = caption
        self.presence = presence
        self.powerOffConfirmed = powerOffConfirmed
        self.draw = draw
        self.market = market
        self.errorText = errorText
    }

    public static let initial = CallState(
        link: .connecting,
        caption: nil,
        presence: [:],
        powerOffConfirmed: false,
        draw: .empty,
        market: nil,
        errorText: nil
    )

    public func reduce(_ event: CallEvent, nowMs: Double) -> CallState {
        var next = self
        switch event {
        case .connected:
            // A fresh socket is a fresh session on the server: the power-off gate and drawing start over.
            next.link = .live
            next.powerOffConfirmed = false
            next.draw = .empty
            next.presence = [:]
            next.errorText = nil
        case .disconnected:
            next.link = .reconnecting
        case .powerOffTapped:
            next.powerOffConfirmed = true
        case .marketDismissed:
            next.market = nil
        case .server(let message):
            switch message {
            case .draw(let agent, let seq, let ops):
                next.draw = draw.applying(agent: agent, seq: seq, ops: ops, nowMs: nowMs)
            case .say(let agent, let utteranceId, let text):
                next.caption = Caption(agent: agent, text: text, utteranceId: utteranceId)
                next.errorText = nil
            case .agentState(let agent, let state):
                next.presence[agent] = state
                // The server never sends idle or listening for the agent that just finished, so when one agent
                // starts working the other one is no longer the active speaker.
                if state == .thinking || state == .speaking {
                    let other: Agent = agent == .helper ? .shopper : .helper
                    next.presence[other] = .idle
                }
            case .marketResults(let response):
                next.market = response
            case .error(_, let errorMessage):
                next.errorText = errorMessage
            case .ignored:
                break
            }
        }
        return next
    }

    /// The "Power is off" button shows for modes that need it, until it has been tapped on this connection.
    public func showsPowerOffButton(for mode: Mode) -> Bool {
        mode.requiresPowerOff && !powerOffConfirmed
    }
}
