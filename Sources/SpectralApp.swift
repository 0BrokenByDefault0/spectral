import SwiftUI
import UIKit
import WebKit

@main
struct SpectralApp: App {
    private let night = Color(red: 5 / 255, green: 8 / 255, blue: 22 / 255)

    var body: some Scene {
        WindowGroup {
            WebView()
                .ignoresSafeArea()
                .background(night.ignoresSafeArea())
                .preferredColorScheme(.dark)
        }
    }
}

/// Hosts the bundled, fully offline guide (Web/index.html).
struct WebView: UIViewRepresentable {
    func makeCoordinator() -> Coordinator { Coordinator() }

    func makeUIView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        config.userContentController.add(context.coordinator, name: "haptic")

        let night = UIColor(red: 5 / 255, green: 8 / 255, blue: 22 / 255, alpha: 1)
        let webView = WKWebView(frame: .zero, configuration: config)
        webView.isOpaque = false
        webView.backgroundColor = night
        webView.scrollView.backgroundColor = night
        webView.scrollView.bounces = false
        webView.scrollView.contentInsetAdjustmentBehavior = .never
        webView.scrollView.showsVerticalScrollIndicator = false
        webView.allowsLinkPreview = false

        if let dir = Bundle.main.url(forResource: "Web", withExtension: nil) {
            webView.loadFileURL(dir.appendingPathComponent("index.html"), allowingReadAccessTo: dir)
        }
        return webView
    }

    func updateUIView(_ uiView: WKWebView, context: Context) {}

    final class Coordinator: NSObject, WKScriptMessageHandler {
        func userContentController(_ userContentController: WKUserContentController,
                                   didReceive message: WKScriptMessage) {
            let kind = message.body as? String ?? "light"
            DispatchQueue.main.async {
                if kind == "success" {
                    UINotificationFeedbackGenerator().notificationOccurred(.success)
                } else {
                    UIImpactFeedbackGenerator(style: kind == "medium" ? .medium : .light).impactOccurred()
                }
            }
        }
    }
}
