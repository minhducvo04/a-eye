import SwiftUI

enum CallMemoryPanel: String, Identifiable {
    case rewind = "Rewind"
    case remember = "Remember this call"
    var id: String { rawValue }
}

struct CallMemorySheet: View {
    let controller: CallController
    let panel: CallMemoryPanel
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    if panel == .rewind {
                        Toggle("Rewind", isOn: Binding(
                            get: { controller.rewind.on },
                            set: { controller.setRewind($0) }
                        ))
                        .disabled(!controller.canChangeRewind)
                        Text("Look back during this call. Silent video is sent to TwelveLabs and deleted after the call unless you choose to remember it.")
                    } else {
                        Toggle("Remember this call", isOn: Binding(
                            get: { controller.rewind.keep },
                            set: { controller.setKeepCall($0) }
                        ))
                        .disabled(!controller.canChangeRewind || (!controller.rewind.on && !controller.rewind.keep))
                        Text("Building memories together. Keep this call’s Rewind clips after you hang up.")
                        if !controller.rewind.on && !controller.rewind.keep { Text("Turn on Rewind first.") }
                    }
                }
                if controller.rewind.pending {
                    ProgressView("Updating…")
                } else if controller.privateMode || controller.rewind.locked {
                    Text("Rewind is unavailable in Private mode.")
                } else if !controller.canChangeRewind {
                    Text("Connect to the call to use Rewind.")
                }
            }
            .tint(Palette.amber)
            .navigationTitle(panel.rawValue)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } }
            }
        }
        .presentationDetents([.medium, .large])
    }
}
