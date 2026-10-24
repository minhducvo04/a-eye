import AEyeCore
import SwiftUI

/// Server address and connection status. Nothing else.
struct SettingsSheet: View {
    @Bindable var controller: CallController
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("192.168.1.10:8000", text: $controller.serverURLString)
                        .keyboardType(.URL)
                        .textContentType(.URL)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .submitLabel(.done)
                } header: {
                    Text("Server")
                } footer: {
                    Text(hint)
                }

                Section("Connection") {
                    Text(status)
                }

                Section {
                    Text("Camera frames go only to this server and are not saved on the phone.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
            }
            .navigationTitle("Settings")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                }
            }
        }
        .presentationDetents([.medium, .large])
    }

    /// What `serverURL(from:)` makes of the input, so a typo is visible before a call fails.
    private var hint: String {
        if let url = serverURL(from: controller.serverURLString) {
            return "Will connect to \(url.absoluteString)"
        }
        let isEmpty = controller.serverURLString.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        return isEmpty ? "No server set. Enter your Mac's address, for example 192.168.1.10:8000." : "That does not look like a server address."
    }

    private var status: String {
        guard controller.mode != nil else { return "Not in a call" }
        switch controller.state.link {
        case .connecting: return "Connecting…"
        case .live: return "Connected"
        case .reconnecting: return "Reconnecting…"
        }
    }
}
