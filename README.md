# Spectral

An offline iOS guide to recording vocals and mixing them into a beat.

- `Web/` — the guide itself (HTML/CSS/JS, no network needed)
- `Sources/` — SwiftUI shell that hosts it
- `project.yml` — XcodeGen project definition

## Build an unsigned IPA

Every push runs `.github/workflows/build-ipa.yml`, which uploads `Spectral-unsigned.ipa` as a workflow artifact. Locally on a Mac: `xcodegen generate`, then build the `Spectral` scheme with `CODE_SIGNING_ALLOWED=NO` and zip the `.app` inside a `Payload/` folder.

Sideload with AltStore, Sideloadly, TrollStore or similar (they sign it for your device).
