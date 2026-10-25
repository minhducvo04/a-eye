import Foundation

/// The server owns persona content; new JSON entries require no app release.
public struct Persona: Decodable, Identifiable, Equatable {
    public let id: String
    public let displayName: String
    enum CodingKeys: String, CodingKey { case id; case displayName = "display_name" }
}

public struct PersonaRegistry: Decodable {
    public let personas: [Persona]
    public let defaultPersona: String
    enum CodingKeys: String, CodingKey { case personas; case defaultPersona = "default" }
}

public struct ProductFeatures: Decodable {
    public let extraModes: Bool
    public let shopping: Bool
    enum CodingKeys: String, CodingKey { case extraModes = "extra_modes"; case shopping }
}
