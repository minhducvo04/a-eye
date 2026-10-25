import AEyeCore
import SwiftUI

struct SettingsSheet: View {
    @Bindable var controller: CallController
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            Form {
                Section("Call") {
                    Picker("Dad", selection: $controller.persona) {
                        if controller.personas.isEmpty { Text("Chill dad").tag("chill-dad") }
                        ForEach(controller.personas) { Text($0.displayName).tag($0.id) }
                    }
                    Toggle("Hold to talk", isOn: $controller.holdToTalk)
                }
                Section("Voice & privacy") {
                    Toggle("Share with Google", isOn: $controller.googleConsent)
                    Toggle("Private mode", isOn: $controller.privateMode)
                    Text("Calls use Gemini Live, with Claude as fallback. Private mode blocks cloud services.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
                Section("Connection") {
                    TextField("Server address", text: $controller.serverURLString)
                        .keyboardType(.URL)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                    SecureField("Access token", text: $controller.accessToken)
                        .textContentType(.password)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                }
                Section {
                    Text("Google receives call audio and video when sharing is on. Changing dad or privacy ends the call.")
                    if controller.socketURL == nil { Text("Enter your server address to call.") }
                    if !controller.productSettingsNotice.isEmpty { Text(controller.productSettingsNotice) }
                }
                .font(.footnote)
                .foregroundStyle(.secondary)
            }
            .navigationTitle("Settings")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } }
            }
        }
        .task(id: controller.serverURLString + controller.accessToken) { await controller.loadProductSettings() }
        .presentationDetents([.large])
    }
}
