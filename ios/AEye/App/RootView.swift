import AEyeCore
import AVFoundation
import SwiftUI
import UIKit

/// Launch screen and call screen share one camera preview, so the camera never restarts or flashes black.
struct RootView: View {
    @StateObject private var camera: CameraService
    @State private var controller: CallController
    @State private var ringIndex = Modes.defaultIndex
    @State private var showSettings = false
    @Environment(\.scenePhase) private var scenePhase

    @MainActor
    init() {
        let camera = CameraService()
        _camera = StateObject(wrappedValue: camera)
        _controller = State(initialValue: CallController(camera: camera))
    }

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()

            if isCameraBlocked {
                PermissionNotice(
                    title: "Camera access is off",
                    message: "A-eye looks through the camera to point at parts while you work. Turn the camera on for A-eye in Settings."
                )
            } else {
                CameraPreview(session: camera.session)
                    .ignoresSafeArea()
            }

            if !isCameraBlocked {
                if controller.mode != nil {
                    CallScreen(controller: controller)
                } else {
                    cameraChrome
                }
            }
        }
        .sheet(isPresented: $showSettings) {
            SettingsSheet(controller: controller)
        }
        .onAppear { camera.start() }
        .onChange(of: scenePhase) { _, phase in
            switch phase {
            case .active: camera.start()
            case .background: camera.stop()
            default: break
            }
        }
        .onChange(of: controller.mode != nil) { _, isInCall in
            // Keep the screen awake while a call is running.
            UIApplication.shared.isIdleTimerDisabled = isInCall
        }
    }

    private var isCameraBlocked: Bool {
        camera.permission == .denied || camera.permission == .restricted
    }

    private var needsServer: Bool {
        controller.socketURL == nil
    }

    // MARK: - Camera screen

    private var cameraChrome: some View {
        VStack(spacing: 0) {
            HStack(spacing: 10) {
                Button {
                    showSettings = true
                } label: {
                    Image(systemName: "gearshape.fill")
                        .font(.system(size: 18, weight: .medium))
                        .foregroundStyle(.white)
                        .frame(width: 44, height: 44)
                        .glass(Circle())
                }
                .accessibilityLabel("Settings")

                if needsServer {
                    Button {
                        showSettings = true
                    } label: {
                        Label("Set server", systemImage: "network")
                            .font(.system(.footnote, design: .monospaced).weight(.semibold))
                            .foregroundStyle(Palette.warn)
                            .padding(.horizontal, 12)
                            .padding(.vertical, 10)
                            .glass(Capsule())
                    }
                }
                Spacer()
            }
            .padding(.horizontal, 16)
            .padding(.top, 8)

            Spacer()

            ModeRing(index: $ringIndex, onStart: startCall)
                .padding(.bottom, 24)
        }
    }

    private func startCall(_ mode: Mode) {
        guard !needsServer else {
            showSettings = true
            return
        }
        UIImpactFeedbackGenerator(style: .medium).impactOccurred()
        controller.start(mode)
    }
}
