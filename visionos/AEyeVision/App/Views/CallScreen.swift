import AEyeCore
import SwiftUI

/// Chrome drawn over the live camera during a call. The camera preview itself lives in `RootView`, so it
/// never restarts when a call begins or ends.
struct CallScreen: View {
    let controller: CallController

    /// Text being typed in typed-input mode.
    @State private var draft = ""

    var body: some View {
        let state = controller.state

        ZStack {
            // Draw ops, under the controls. It fills the same area as the camera preview (which ignores the
            // safe area), so boxes land on the object they mark.
            OverlayView(draw: state.draw, frameSize: controller.lastFrameSize)
                .ignoresSafeArea()
                .allowsHitTesting(false)
                .accessibilityHidden(true)

            VStack(spacing: 12) {
                topBar(state: state)
                Spacer(minLength: 0)
                CaptionCard(caption: state.caption, errorText: state.errorText)
                interimLine
                powerOffGate(state: state)
                if controller.isInputResolved, controller.inputMode == .typed {
                    typedBar
                }
                bottomBar
            }
            .padding(.horizontal, 16)
            .padding(.bottom, 20)
        }
        .sheet(item: marketBinding) { presentation in
            MarketSheet(market: presentation.response)
        }
    }

    // MARK: - Top

    private func topBar(state: CallState) -> some View {
        VStack(spacing: 8) {
            HStack(spacing: 8) {
                PresenceDot(presence: state.presence)
                Text("A-eye")
                    .fontWeight(.bold)
                separator
                Text(controller.mode?.title ?? "")
                separator
                elapsedText
            }
            .font(.system(.footnote, design: .monospaced).weight(.medium))
            .foregroundStyle(.white)
            .padding(.horizontal, 14)
            .padding(.vertical, 8)
            .glass(Capsule())
            .accessibilityElement(children: .combine)

            if state.link != .live {
                Text(state.link == .reconnecting ? "Reconnecting…" : "Connecting…")
                    .font(.system(.footnote, design: .monospaced).weight(.semibold))
                    .foregroundStyle(Palette.warn)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 6)
                    .glass(Capsule())
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

    /// What the recogniser has heard so far, faint, until the utterance is final.
    @ViewBuilder
    private var interimLine: some View {
        let heard = controller.listener.interim
        if !heard.isEmpty {
            Text(heard)
                .font(.subheadline)
                .foregroundStyle(Color.white.opacity(0.6))
                .lineLimit(2)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.horizontal, 6)
                .shadow(color: .black.opacity(0.6), radius: 3)
                .accessibilityLabel("Heard: \(heard)")
        }
    }

    /// PC Build only: asks the user to confirm the PC is off before the agent goes on.
    /// It comes back by itself after a reconnect because `CallState` clears the confirmation then.
    @ViewBuilder
    private func powerOffGate(state: CallState) -> some View {
        if let mode = controller.mode, state.showsPowerOffButton(for: mode) {
            VStack(spacing: 6) {
                Button {
                    controller.confirmPowerOff()
                } label: {
                    Label("Power is off", systemImage: "bolt.slash")
                        .font(.headline)
                        .foregroundStyle(Color.black)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 14)
                        .background(Palette.warn, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                }
                .accessibilityHint("Confirms the PSU is switched off and unplugged")

                Text("Switch the PSU off and unplug it first.")
                    .font(.footnote.weight(.medium))
                    .foregroundStyle(Color.white.opacity(0.9))
                    .shadow(color: .black.opacity(0.6), radius: 3)
                    .multilineTextAlignment(.center)
            }
        }
    }

    // MARK: - Typed input

    private var typedBar: some View {
        HStack(spacing: 8) {
            TextField(
                "Message",
                text: $draft,
                prompt: Text("Type to A-eye…").foregroundStyle(Color.white.opacity(0.55))
            )
            .foregroundStyle(.white)
            .submitLabel(.send)
            .onSubmit(sendDraft)
            .padding(.leading, 6)

            Button(action: sendDraft) {
                Image(systemName: "arrow.up.circle.fill")
                    .font(.system(size: 30))
                    .foregroundStyle(canSend ? Palette.helper : Color.white.opacity(0.3))
            }
            .disabled(!canSend)
            .accessibilityLabel("Send")
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .glass(Capsule())
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
        HStack(spacing: 28) {
            micButton

            Button {
                controller.end()
            } label: {
                Image(systemName: "phone.down.fill")
                    .font(.system(size: 26, weight: .semibold))
                    .foregroundStyle(.white)
                    .frame(width: 68, height: 68)
                    .background(Palette.endCall, in: Circle())
            }
            .accessibilityLabel("End call")
        }
    }

    /// Mutes and unmutes on-device listening. Inactive while typing is the input (permission off, or no
    /// on-device speech recognition).
    private var micButton: some View {
        let isVoice = controller.isInputResolved && controller.inputMode == .voice
        let isMuted = controller.listener.isMuted
        return Button {
            controller.toggleMute()
        } label: {
            Image(systemName: isVoice && !isMuted ? "mic.fill" : "mic.slash.fill")
                .font(.system(size: 22, weight: .medium))
                .foregroundStyle(isVoice && isMuted ? Palette.warn : Color.white)
                .frame(width: 56, height: 56)
                .glass(Circle())
        }
        .disabled(!isVoice)
        .opacity(isVoice ? 1 : 0.5)
        .accessibilityLabel("Microphone")
        .accessibilityValue(isVoice ? (isMuted ? "Muted" : "On") : "Off")
        .accessibilityHint(isVoice ? "Double tap to mute or unmute" : "Voice input is off. Use the text field.")
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
