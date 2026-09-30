import SwiftUI

struct TradingAccessView: View {
    @Environment(WheelStore.self) private var store
    @Environment(\.locale) private var locale
    var body: some View {
        Form {
            Section {
                LabeledContent("Trading access") {
                    Text(verbatim: store.demo ? localizedLabel("Simulated", locale: locale) : "Live")
                }
            }
            Section("Remote maintenance") {
                NavigationLink { RemoteMaintenanceView() } label: {
                    Label("Mini screen sharing", systemImage: "desktopcomputer")
                }
            }
        }.navigationTitle(localizedLabel("Trading access", locale: locale))
    }
}
