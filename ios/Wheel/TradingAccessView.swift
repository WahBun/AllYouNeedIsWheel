import SwiftUI

struct TradingAccessView: View {
    @Environment(WheelStore.self) private var store
    @Environment(\.locale) private var locale
    @State private var showingFeedback = false
    @State private var maintenance: BackendMaintenanceModel
    @State private var editingToken: Bool
    @State private var expandedPerformance: Bool
    private var account: NotificationAccount? { .current(store) }

    @MainActor init(maintenanceModel: BackendMaintenanceModel? = nil, editingToken: Bool = false, expandedPerformance: Bool = false) {
        _maintenance = State(initialValue: maintenanceModel ?? BackendMaintenanceModel())
        _editingToken = State(initialValue: editingToken)
        _expandedPerformance = State(initialValue: expandedPerformance || editingToken)
    }

    var body: some View {
        ScrollViewReader { proxy in
        Form {
            Section {
                LabeledContent("Account mode") {
                    Text(verbatim: localizedLabel(store.accountModeLabel, locale: locale))
                }
                LabeledContent("Trading access") { Text(verbatim: localizedLabel(store.tradingAccessLabel, locale: locale)) }
            }
            BackendMaintenanceSections(model: maintenance, editing: $editingToken, expanded: $expandedPerformance)
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
        .onChange(of: editingToken) { _, editing in
            if editing { withAnimation { proxy.scrollTo("tokenEditor", anchor: .top) } }
        }
        .navigationTitle(localizedLabel("Access & Feedback", locale: locale))
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button { Task { await maintenance.refresh() } } label: { Image(systemName: "arrow.clockwise") }
                    .accessibilityLabel(Text(verbatim: "Refresh backend status"))
                    .disabled(maintenance.busy || account == nil)
            }
        }
        .refreshable { await maintenance.refresh() }
        .task(id: account) {
            if maintenance.account != account { editingToken = false; expandedPerformance = false }
            maintenance.select(account)
            await maintenance.refresh()
            if editingToken { proxy.scrollTo("tokenEditor", anchor: .top) }
        }
        .onDisappear { maintenance.select(nil); editingToken = false }
        .sheet(isPresented: $showingFeedback) {
            FeedbackView().ignoresSafeArea()
        }
        }
    }
}
