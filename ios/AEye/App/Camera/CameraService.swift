import AVFoundation
import AEyeCore
import CoreImage
import ImageIO

/// Owns the capture session on its own queues. Kept separate from the main-actor `CameraService` so the
/// sample-buffer delegate and the blocking `startRunning()` never touch main-actor state.
/// Only the newest pixel buffer is kept, in memory. Nothing is written to disk.
///
/// `nonisolated` on purpose: AVFoundation calls the delegate on `sampleQueue`, not on the main actor, so this type
/// must not pick up an implicit `@MainActor` when the project's Default Actor Isolation is MainActor.
/// All mutable state is guarded by `lock` or confined to `sessionQueue`.
nonisolated final class CaptureRig: NSObject, AVCaptureVideoDataOutputSampleBufferDelegate, @unchecked Sendable {
    let session = AVCaptureSession()

    private let sessionQueue = DispatchQueue(label: "aeye.capture.session")
    private let sampleQueue = DispatchQueue(label: "aeye.capture.samples")
    private let lock = NSLock()
    private var newestBuffer: CVPixelBuffer?
    private var newestAt = Date.distantPast
    private var isConfigured = false  // only touched on sessionQueue

    func start() {
        sessionQueue.async { [self] in
            configureIfNeeded()
            if isConfigured, !session.isRunning {
                session.startRunning()
            }
        }
    }

    func stop() {
        sessionQueue.async { [self] in
            if session.isRunning {
                session.stopRunning()
            }
            storeBuffer(nil)
        }
    }

    func latestBuffer() -> CVPixelBuffer? {
        lock.lock()
        defer { lock.unlock() }
        return Date().timeIntervalSince(newestAt) <= 1.5 ? newestBuffer : nil
    }

    private func storeBuffer(_ buffer: CVPixelBuffer?) {
        lock.lock()
        newestBuffer = buffer
        newestAt = Date()
        lock.unlock()
    }

    private func configureIfNeeded() {
        guard !isConfigured else { return }

        session.beginConfiguration()
        defer { session.commitConfiguration() }

        session.sessionPreset = .hd1280x720

        guard let device = AVCaptureDevice.default(.builtInWideAngleCamera, for: .video, position: .back),
              let input = try? AVCaptureDeviceInput(device: device),
              session.canAddInput(input)
        else { return }
        session.addInput(input)

        let output = AVCaptureVideoDataOutput()
        output.alwaysDiscardsLateVideoFrames = true
        output.videoSettings = [kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA]
        output.setSampleBufferDelegate(self, queue: sampleQueue)
        guard session.canAddOutput(output) else { return }
        session.addOutput(output)

        // Buffers arrive upright for a portrait phone (sensor is landscape, so rotate 90 degrees).
        if let connection = output.connection(with: .video), connection.isVideoRotationAngleSupported(90) {
            connection.videoRotationAngle = 90
        }
        isConfigured = true
    }

    func captureOutput(_ output: AVCaptureOutput, didOutput sampleBuffer: CMSampleBuffer,
                       from connection: AVCaptureConnection) {
        guard let pixelBuffer = CMSampleBufferGetImageBuffer(sampleBuffer) else { return }
        storeBuffer(pixelBuffer)
    }
}

@MainActor
final class CameraService: NSObject, ObservableObject {
    @Published private(set) var permission: AVAuthorizationStatus = AVCaptureDevice.authorizationStatus(for: .video)

    var session: AVCaptureSession { rig.session }

    private let rig = CaptureRig()
    private let ciContext = CIContext()
    private var isRequestingAccess = false

    func start() {
        let status = AVCaptureDevice.authorizationStatus(for: .video)
        permission = status
        switch status {
        case .authorized:
            rig.start()
        case .notDetermined:
            guard !isRequestingAccess else { return }
            isRequestingAccess = true
            Task { [self] in
                let granted = await AVCaptureDevice.requestAccess(for: .video)
                isRequestingAccess = false
                permission = AVCaptureDevice.authorizationStatus(for: .video)
                if granted { rig.start() }
            }
        default:
            break  // denied or restricted: RootView shows PermissionNotice
        }
    }

    func stop() {
        rig.stop()
    }

    /// The newest camera frame scaled to the wire size and JPEG-encoded. Memory only.
    func latestJPEG(maxSide: Int = 640) -> (data: Data, width: Int, height: Int)? {
        guard let pixelBuffer = rig.latestBuffer() else { return nil }

        let source = CIImage(cvPixelBuffer: pixelBuffer)
        let sourceWidth = Int(source.extent.width)
        let sourceHeight = Int(source.extent.height)
        let target = frameSize(width: sourceWidth, height: sourceHeight, maxSide: maxSide)
        guard target.width > 0, target.height > 0 else { return nil }

        let scale = CGAffineTransform(scaleX: CGFloat(target.width) / CGFloat(sourceWidth),
                                      y: CGFloat(target.height) / CGFloat(sourceHeight))
        let bounds = CGRect(x: 0, y: 0, width: target.width, height: target.height)
        let scaled = source.transformed(by: scale).cropped(to: bounds)

        let colorSpace = CGColorSpace(name: CGColorSpace.sRGB) ?? CGColorSpaceCreateDeviceRGB()
        let qualityKey = CIImageRepresentationOption(rawValue: kCGImageDestinationLossyCompressionQuality as String)
        let options: [CIImageRepresentationOption: Any] = [qualityKey: Tuning.jpegQuality]
        guard let data = ciContext.jpegRepresentation(of: scaled, colorSpace: colorSpace, options: options) else {
            return nil
        }
        return (data, target.width, target.height)
    }
}
