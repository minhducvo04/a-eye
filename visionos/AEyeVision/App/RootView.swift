import AEyeCore
import SwiftUI

struct RootView: View {
    var body: some View {
        Text(Modes.all[Modes.defaultIndex].title)
            .font(.title)
    }
}
