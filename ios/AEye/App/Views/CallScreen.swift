import AEyeCore
import SwiftUI

/// Call controls remain available even without camera or microphone permission.
struct CallScreen: View {
    let controller: CallController

    /// Text being typed in the message bar.
    @State private var draft = ""
    @State private var showSettings = false
    @State private var memoryPanel: CallMemoryPanel?
    @GestureState private var pressingMic = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion


    var body: some View {
        let state = controller.state

        ZStack {
            // Draw ops, under the controls. It fills the same area as the camera preview (which ignores the
            // safe area), so boxes land on the object they mark.
            OverlayView(draw: state.draw, frameSize: controller.lastFrameSize)
                .ignoresSafeArea()
                .allowsHitTesting(false)
                .accessibilityHidden(true)

            // Respect Reduce Motion while the helper reads the picture.
            if !reduceMotion {
                TimelineView(.periodic(from: .now, by: 1)) { context in
                    if Tuning.showScanSweep, let wait = visibleWait(state, at: context.date), wait.agent == .helper {
                        ScanSweep(color: Palette.helper)
                            .ignoresSafeArea()
                            .transition(.opacity)
                    }
                }
            }

            VStack(spacing: 12) {
                topBar(state: state)
                Spacer(minLength: 0)
                waitCard(state: state)
                CaptionCard(caption: state.caption, errorText: state.errorText, isLarge: false)
                if controller.isInputResolved, controller.inputMode == .voice {
                    ListeningStrip(levels: controller.isLive ? controller.liveAudio.levels : controller.listener.levels,
                                   heard: controller.isLive ? controller.liveAudio.interim : controller.listener.interim,
                                   isMuted: controller.isMuted)
                }
                typedBar
                bottomBar
            }
            .padding(.horizontal, 16)
            .padding(.bottom, 20)
        }
        .animation(reduceMotion ? nil : .easeOut(duration: 0.25), value: state.wait?.turnId)
        .animation(reduceMotion ? nil : .easeOut(duration: 0.25), value: state.wait == nil)
        .animation(reduceMotion ? nil : .easeOut(duration: 0.25), value: state.isExpertChecking)
        .sheet(item: marketBinding) { presentation in
            MarketSheet(market: presentation.response)
        }
        .onChange(of: pressingMic) { _, pressed in controller.setTalking(pressed) }
        .onDisappear { controller.setTalking(false) }
        .sheet(item: $memoryPanel) { panel in
            CallMemorySheet(controller: controller, panel: panel)
        }
        .sheet(isPresented: $showSettings) {
            SettingsSheet(controller: controller)
        }
    }

    // MARK: - Top

    private func topBar(state: CallState) -> some View {
        VStack(spacing: 8) {
            HStack(spacing: 8) {
                PresenceDot(presence: state.presence)
                Text("A-Eye")
                    .fontWeight(.bold)
                separator
                elapsedText
                separator
                Button { showSettings = true } label: {
                    Image(systemName: "gearshape").frame(width: 32, height: 32)
                }
                .accessibilityLabel("Settings")
            }
            .font(.system(.footnote).weight(.medium))
            .foregroundStyle(.white)
            .padding(.horizontal, 14)
            .padding(.vertical, 8)
            .callGlass(Capsule())
            .accessibilityElement(children: .contain)

            // One badge style under the pill. Expert: a stronger model is checking this answer.
            if state.isExpertChecking {
                StatusBadge(text: "Expert", color: Palette.helper)
                    .transition(.opacity)
            }

            if state.link != .live {
                Text(state.link == .reconnecting ? "Reconnecting…" : "Connecting…")
                    .font(.footnote.weight(.semibold))
                    .foregroundStyle(Palette.warn)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 6)
                    .callGlass(Capsule())
            }
        }
        .padding(.top, 8)
    }

    private var separator: some View {
        Text("·").foregroundStyle(Color.white.opacity(0.5)).accessibilityHidden(true)
    }

    private var elapsedText: some View {
        TimelineView(.periodic(from: .now, by: 1)) { context in
            Text(elapsed(at: context.date))
                .monospacedDigit()
        }
    }

    private func elapsed(at date: Date) -> String {
        guard let start = controller.callStartedAt else { return "0:00" }
        let seconds = max(0, Int(date.timeIntervalSince(start)))
        return String(format: "%d:%02d", seconds / 60, seconds % 60)
    }

    // MARK: - Middle

    /// Percentage card while an agent works on an answer, so a slow answer does not look like a frozen app.
    private func waitCard(state: CallState) -> some View {
        TimelineView(.periodic(from: .now, by: 1)) { context in
            if let wait = visibleWait(state, at: context.date) {
                WaitCard(wait: wait)
                    .transition(.opacity.combined(with: .scale(scale: 0.96)))
            }
        }
    }

    private func visibleWait(_ state: CallState, at date: Date) -> Wait? {
        state.visibleWait(nowMs: date.timeIntervalSince1970 * 1000)
    }

    // MARK: - Typed input

    /// Always shown, as on the web (`#composer`): a keyboard works in a noisy room even when voice is on.
    private var typedBar: some View {
        HStack(spacing: 8) {
            TextField(
                "Message",
                text: $draft,
                prompt: Text("Type a message").foregroundStyle(Palette.text3)
            )
            .font(.body)
            .foregroundStyle(.white)
            .submitLabel(.send)
            .onSubmit(sendDraft)

            Button(action: sendDraft) {
                Image(systemName: "arrow.up.circle.fill")
                    .font(.system(size: 30))
                    .foregroundStyle(canSend ? Palette.helper : Color.white.opacity(0.3))
            }
            .disabled(!canSend)
            .accessibilityLabel("Send")
        }
        .padding(.leading, 18)
        .padding(.trailing, 8)
        .padding(.vertical, 8)
        .callGlass(Capsule())
    }

    private var canSend: Bool {
        !draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    private func sendDraft() {
        guard canSend else { return }
        controller.send(text: draft)
        draft = ""
    }

    // MARK: - Bottom

    private var bottomBar: some View {
        HStack(spacing: 10) {
            cameraButton
            micButton
            Button { controller.end() } label: {
                Image(systemName: "phone.down.fill")
                    .font(.system(size: 25, weight: .semibold))
                    .foregroundStyle(.white)
                    .frame(width: 60, height: 60)
                    .background(Palette.endCall, in: Circle())
            }
            .accessibilityLabel("End call")
            Spacer(minLength: 0)
            HStack(spacing: 2) {
                memoryButton(.rewind, symbol: "clock.arrow.circlepath", on: controller.rewind.on)
                memoryButton(.remember, symbol: "bookmark", on: controller.rewind.keep)
            }
            .padding(4)
            .callGlass(Capsule())
            .accessibilityElement(children: .contain)
            .accessibilityLabel("Memory controls")
        }
        .frame(maxWidth: .infinity)
    }

    private func memoryButton(_ panel: CallMemoryPanel, symbol: String, on: Bool) -> some View {
        Button { memoryPanel = panel } label: {
            Image(systemName: symbol)
                .font(.system(size: 20, weight: .medium))
                .foregroundStyle(on ? Palette.amber : .white)
                .frame(width: 44, height: 48)
        }
        .accessibilityLabel(panel.rawValue)
        .accessibilityValue(on ? "On" : "Off")
    }

    /// Stops capture and frame transport together.
    private var cameraButton: some View {
        let isOn = controller.isCameraOn
        return Button {
            controller.toggleCamera()
        } label: {
            Image(systemName: isOn ? "video" : "video.slash")
                .font(.system(size: 22, weight: .medium))
                .foregroundStyle(isOn ? Color.white : Palette.warn)
                .frame(width: 48, height: 48)
                .callGlass(Circle())
        }
        .accessibilityLabel("Camera")
        .accessibilityValue(isOn ? "On" : "Off")
    }

    /// Mutes and unmutes on-device listening. Filled in the helper colour while it is hearing, like the web
    /// (`#mic[aria-pressed="true"]`). Inactive while typing is the input (permission off, or no on-device speech).
    private var micButton: some View {
        let isVoice = controller.isInputResolved && controller.inputMode == .voice
        let isMuted = controller.isMuted
        let isHearing = isVoice && !isMuted
        return Button {
            if !controller.holdToTalk { controller.toggleMute() }
        } label: {
            Image(systemName: isHearing ? "mic.fill" : "mic.slash.fill")
                .font(.system(size: 22, weight: .medium))
                .foregroundStyle(isHearing ? Color.black : (isVoice ? Palette.warn : Color.white))
                .frame(width: 48, height: 48)
                .background {
                    if isHearing {
                        Circle().fill(Palette.helper)
                            .overlay(Circle().stroke(Palette.helper.opacity(0.3), lineWidth: 4).padding(-2))
                    }
                }
                .modifier(GlassWhen(isOn: !isHearing))
        }
        .simultaneousGesture(DragGesture(minimumDistance: 0).updating($pressingMic) { _, pressed, _ in
            if controller.holdToTalk { pressed = true }
        })
        .accessibilityAction(named: "Start talking") { controller.setTalking(true) }
        .accessibilityAction(named: "Stop talking") { controller.setTalking(false) }
        .disabled(!isVoice)
        .opacity(isVoice ? 1 : 0.5)
        .accessibilityLabel("Microphone")
        .accessibilityValue(isVoice ? (isMuted ? "Muted" : "On") : "Off")
        .accessibilityHint(isVoice ? (controller.holdToTalk ? "Hold while speaking" : "Double tap to mute or unmute") : "Voice input is off. Use the text field.")
    }

    // MARK: - Market sheet

    /// Presents the shopper's offers while `state.market` is set. Closing the sheet (swipe or button) clears it.
    private var marketBinding: Binding<MarketPresentation?> {
        Binding(
            get: { controller.state.market.map(MarketPresentation.init(response:)) },
            set: { newValue in
                if newValue == nil { controller.dismissMarket() }
            }
        )
    }
}

/// Call glass on a circle, only when `isOn` (the filled mic has no glass under it).
private struct GlassWhen: ViewModifier {
    let isOn: Bool

    func body(content: Content) -> some View {
        if isOn {
            content.callGlass(Circle())
        } else {
            content
        }
    }
}
