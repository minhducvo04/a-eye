import AEyeCore
import AVFoundation
import SwiftUI
import UIKit

struct RootView: View {
    @StateObject private var camera: CameraService
    @State private var controller: CallController
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
            Palette.sheet.ignoresSafeArea()
            if controller.mode != nil {
                if controller.isCameraOn && camera.permission == .authorized {
                    CameraPreview(session: camera.session, isFront: camera.isFront)
                        .ignoresSafeArea()
                } else {
                    cameraStatus
                }
                // Permission failures never hide End Call or the other call controls.
                CallScreen(controller: controller)
            } else {
                StartScreen { startCall(Modes.dad) }
            }
        }
        .sheet(isPresented: $showSettings) { SettingsSheet(controller: controller) }
        .task(id: controller.serverURLString + controller.accessToken) { await controller.loadProductSettings() }
        .onAppear { autostartIfAsked() }
        .onChange(of: scenePhase) { _, phase in
            if phase == .active, controller.mode != nil, controller.isCameraOn { camera.start() }
            else if phase != .active {
                controller.setTalking(false)
                camera.stop()
            }
        }
        .onChange(of: controller.mode != nil) { _, isInCall in
            UIApplication.shared.isIdleTimerDisabled = isInCall
            if !isInCall { camera.stop() }
        }
    }

    private var cameraStatus: some View {
        VStack(spacing: 12) {
            Image(systemName: "video.slash").font(.system(size: 36, weight: .light))
            Text(controller.isCameraOn ? "Camera access is off" : "Camera is off")
                .font(.subheadline)
        }
        .foregroundStyle(Palette.text2)
        .frame(maxHeight: .infinity, alignment: .center)
        .allowsHitTesting(false)
    }

    private func autostartIfAsked() {
        let arguments = ProcessInfo.processInfo.arguments
        guard arguments.contains("-aeye-start") else { return }
        startCall(Modes.dad)
    }

    private func startCall(_ mode: Mode) {
        guard controller.socketURL != nil else {
            showSettings = true
            return
        }
        UIImpactFeedbackGenerator(style: .medium).impactOccurred()
        controller.start(mode)
    }
}
