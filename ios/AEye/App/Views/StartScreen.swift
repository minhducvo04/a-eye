import SwiftUI

/// Static light and expressive type keep the welcome quiet, including with Reduce Motion enabled.
/// Uses only the shared palette; the polish owner can restyle this independently of call behavior.
struct StartScreen: View {
    let onCall: () -> Void

    var body: some View {
        GeometryReader { geometry in
            ZStack {
                background
                    .frame(width: geometry.size.width, height: geometry.size.height)
                    .clipped()
                VStack(spacing: 0) {
                    Spacer(minLength: 32)
                    hero
                    Spacer(minLength: 48)
                    Button(action: onCall) {
                        Label("Call", systemImage: "phone.fill")
                            .font(.title3.weight(.semibold))
                            .foregroundStyle(Palette.sheet)
                            .frame(width: 190, height: 64)
                            .background(Palette.helper, in: Capsule())
                            .overlay(Capsule().stroke(Palette.helper.opacity(0.18), lineWidth: 1).padding(-7))
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("Call")
                    .padding(.bottom, 36)

                    Text("A companion call that watches, points, and guides as you learn.")
                        .font(.footnote)
                        .foregroundStyle(Palette.text2)
                        .multilineTextAlignment(.center)
                        .fixedSize(horizontal: false, vertical: true)
                        .frame(maxWidth: 310)
                        .padding(.bottom, 24)
                }
                .frame(width: max(0, geometry.size.width - 56), height: geometry.size.height)
                .padding(.horizontal, 28)
            }
        }
    }

    private var hero: some View {
        VStack(alignment: .leading, spacing: 18) {
            VStack(alignment: .leading, spacing: -4) {
                Text("Dad,")
                    .font(.system(size: 72, weight: .regular, design: .serif).italic())
                    .foregroundStyle(Palette.helper)
                Text("how do I?")
                    .font(.system(size: 49, weight: .medium))
                    .tracking(-2)
                    .foregroundStyle(.white)
            }
            .minimumScaleFactor(0.65)
            .lineLimit(1)
            .accessibilityElement(children: .ignore)
            .accessibilityLabel("Dad, how do I?")
            .accessibilityAddTraits(.isHeader)

            Capsule().fill(Palette.helper.opacity(0.6)).frame(width: 44, height: 2)
                .accessibilityHidden(true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var background: some View {
        ZStack {
            Palette.sheet
            RadialGradient(colors: [Palette.helper.opacity(0.16), .clear],
                           center: .init(x: 0.85, y: 0.3), startRadius: 5, endRadius: 360)
            Circle().stroke(Palette.helper.opacity(0.08), lineWidth: 1)
                .frame(width: 510, height: 510).offset(x: 170, y: -90)
            Circle().stroke(Palette.helper.opacity(0.05), lineWidth: 1)
                .frame(width: 570, height: 570).offset(x: 170, y: -90)
        }
        .ignoresSafeArea()
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }
}
