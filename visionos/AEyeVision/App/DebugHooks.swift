#if DEBUG
import AEyeCore
import Foundation
import UIKit

/// Debug builds only: lets a simulator run be driven from the command line, since visionOS simulator UI
/// cannot be scripted from `simctl`. Launch arguments (they land in `UserDefaults`):
///   -AEyeDebugPhoto /path/to/photo.jpg   use this file as the picked photo
///   -AEyeDebugStart general              start a call in that mode id
///   -AEyeDebugSay "what am I looking at" send this typed line once connected
///   -AEyeDebugTyped YES                  typed input, never ask for the mic (read in `CallController`)
/// Nothing here exists in a Release build.
@MainActor
enum DebugHooks {
    static func run(controller: CallController, photo: PhotoSource) {
        let defaults = UserDefaults.standard
        if let path = defaults.string(forKey: "AEyeDebugPhoto"), let image = UIImage(contentsOfFile: path) {
            photo.use(image)
        }
        guard let id = defaults.string(forKey: "AEyeDebugStart"),
              let mode = Modes.all.first(where: { $0.id == id }) else { return }
        controller.start(mode)
        guard let line = defaults.string(forKey: "AEyeDebugSay") else { return }
        Task {
            for _ in 0..<50 where controller.state.link != .live {
                try? await Task.sleep(nanoseconds: 200_000_000)
            }
            try? await Task.sleep(nanoseconds: 1_500_000_000)  // let a frame go out first
            controller.send(text: line)
        }
    }
}
#endif
