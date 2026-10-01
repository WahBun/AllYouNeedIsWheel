import SwiftUI
import SafariServices

/// The hosted form owns submission, attachments and confirmation.
/// No account, portfolio, connection or diagnostic data is added to the URL.
struct FeedbackView: UIViewControllerRepresentable {
    private let formURL = URL(string: "https://tally.so/r/LZRO5j")!

    func makeUIViewController(context: Context) -> SFSafariViewController {
        let configuration = SFSafariViewController.Configuration()
        configuration.entersReaderIfAvailable = false
        let controller = SFSafariViewController(url: formURL, configuration: configuration)
        controller.dismissButtonStyle = .close
        return controller
    }

    func updateUIViewController(_ controller: SFSafariViewController, context: Context) {}
}
