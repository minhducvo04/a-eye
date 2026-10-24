# ios/ (Duc)

Native SwiftUI client. Placeholder until Duc creates the Xcode project here.

- Same WebSocket contract as `client-web/` (`contracts/schema.json`, mirror in `contracts/types.ts`).
- Camera: ARKit `ARSession` as the camera source only, 640 px JPEG with `seq` and orientation.
- Overlay: 2D, seeded by each server box, tracked with Vision `VNTrackObjectRequest`.
- Audio: `AVAudioEngine`, PCM16 16 kHz `audio` messages both ways.
- Screens: Projects, New build, Project home, Call, Market sheet, Summary.
- Safari (`client-web/`) stays the committed demo; native demos only if it passes the same rehearsal.
