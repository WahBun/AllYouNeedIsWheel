import SwiftUI

struct TradingAccessView: View {
    @Environment(WheelStore.self) private var store
    @Environment(\.locale) private var locale
    @State private var showingFeedback = false

    var body: some View {
        Form {
            Section {
                LabeledContent("Account mode") {
                    Text(verbatim: localizedLabel(store.accountModeLabel, locale: locale))
                }
            }
            Section {
                LabeledContent("Trading access") { Text(verbatim: localizedLabel(store.tradingAccessLabel, locale: locale)) }
            }
            Section("Remote maintenance") {
                NavigationLink { RemoteMaintenanceView() } label: {
                    Label("Mini screen sharing", systemImage: "desktopcomputer")
                }
            }
            Section {
                Button { showingFeedback = true } label: {
                    Label("Feedback", systemImage: "bubble.left.and.text.bubble.right")
                }
            }
        }
        .navigationTitle(localizedLabel("Access & Feedback", locale: locale))
        .sheet(isPresented: $showingFeedback) {
            FeedbackView().ignoresSafeArea()
        }
    }
}
