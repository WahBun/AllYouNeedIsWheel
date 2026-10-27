import SwiftUI
import Observation

struct NotificationAccount: Equatable {
    let address: String
    let mode: String
    let epoch: String

    @MainActor static func current(_ store: WheelStore) -> Self? {
        guard !store.demo, let mode = store.portfolio?.connection?.mode,
              ["paper", "live"].contains(mode), let epoch = store.trading.accountEpoch, !epoch.isEmpty else { return nil }
        return Self(address: store.address, mode: mode, epoch: epoch)
    }
}

@MainActor @Observable
final class PhoneNotificationSettingsModel {
    private(set) var account: NotificationAccount?
    private(set) var enabled: Bool?
    private(set) var busy = false
    private(set) var message: String?
    private(set) var error: String?
    var pushAddress = ""
    @ObservationIgnored private var revision = UUID()
    @ObservationIgnored private let session: URLSession

    init(session: URLSession = URLSession(configuration: .ephemeral, delegate: NoRedirect(), delegateQueue: nil)) {
        self.session = session
    }

    func select(_ account: NotificationAccount?) {
        guard self.account != account else { return }
        self.account = account; revision = UUID()
        enabled = nil; busy = false; message = nil; error = nil; pushAddress = ""
    }

    func refresh() async { await perform() }
    func save() async { await perform(body: ["enabled": true, "url": pushAddress.trimmingCharacters(in: .whitespacesAndNewlines)]) }
    func disable() async { await perform(body: ["enabled": false]) }
    func sendTest() async { await perform(path: "bark/test", body: ["id": UUID().uuidString]) }

    private func perform(path: String = "bark", body: [String: Any]? = nil) async {
        guard !busy, let account else { return }
        if path == "bark/test" && enabled != true { return }
        let requested = revision
        busy = true; error = nil; message = nil
        defer { if requested == revision { busy = false } }
        do {
            guard let base = URL(string: account.address), base.scheme == "https", base.host != nil else {
                throw AppError.message("Connect to your private HTTPS backend first.")
            }
            var request = URLRequest(url: base.appendingPathComponent("api/notifications/" + path), cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 12)
            request.httpMethod = body == nil ? "GET" : "POST"
            request.setValue("1", forHTTPHeaderField: "X-All-You-Need-Is-Wheel")
            request.setValue(account.epoch, forHTTPHeaderField: "X-Wheel-Account-Epoch")
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            if let body { request.httpBody = try JSONSerialization.data(withJSONObject: body) }
            let (data, response) = try await session.data(for: request)
            guard requested == revision else { return }
            let reply = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] ?? [:]
            guard (response as? HTTPURLResponse)?.statusCode == 200 else {
                throw AppError.message(reply["error"] as? String ?? "Notification settings are unavailable. Try again.")
            }
            if path == "bark/test" {
                guard reply["status"] as? String == "queued" else { throw AppError.message("Test delivery could not be confirmed. Check Bark before trying again.") }
                message = "Test queued. Check Bark on your iPhone."
            } else {
                guard let value = reply["enabled"] as? Bool else { throw AppError.message("Notification status is unavailable. Try again.") }
                enabled = value
                if body != nil { pushAddress = "" }
                if value {
                    switch reply["test_state"] as? String {
                    case "sent": message = "Last test accepted by Bark. Check your iPhone for delivery."
                    case "pending": message = "Test delivery is pending. Pull to refresh its status."
                    case "invalid_device": message = "Bark rejected this address. Copy a fresh push address from Bark."
                    case "expired": message = "The last test expired. Send a new test."
                    default: break
                    }
                }
            }
        } catch {
            guard requested == revision else { return }
            // An uncertain response must never become an On/Off claim or replay a write.
            if path == "bark" { enabled = nil }
            self.error = "Could not update notification settings. Pull to refresh before trying again."
            if let appError = error as? AppError { self.error = appError.localizedDescription }
        }
    }
}

struct PushNotificationSettings: View {
    @Environment(WheelStore.self) private var store
    @State private var settings = PhoneNotificationSettingsModel()
    @MainActor init(settings: PhoneNotificationSettingsModel? = nil) {
        _settings = State(initialValue: settings ?? PhoneNotificationSettingsModel())
    }
    private var account: NotificationAccount? { .current(store) }
    private var status: String {
        guard let account else { return "Not connected" }
        guard settings.account == account else { return "Checking…" }
        if settings.busy && settings.enabled == nil { return "Checking…" }
        return settings.enabled.map { $0 ? "On" : "Off" } ?? "Unavailable"
    }
    var body: some View {
        Section {
            NavigationLink {
                PhoneNotificationDetails(settings: settings)
            } label: {
                HStack(spacing: 12) {
                    Image(systemName: "bell.badge").font(.title3).frame(width: 25)
                    VStack(alignment: .leading, spacing: 3) {
                        Text("Notifications")
                        Text("Via Bark").font(.caption).foregroundStyle(.secondary)
                    }
                    Spacer(minLength: 8)
                    NoticeText(status).font(.subheadline)
                        .foregroundStyle(status == "On" ? Color.green : .secondary)
                }.padding(.vertical, 3)
            }
        } header: { Text("Notifications") }
        .onAppear { settings.select(account); Task { await settings.refresh() } }
        .onChange(of: account) { _, account in settings.select(account); Task { await settings.refresh() } }
    }
}

struct PhoneNotificationDetails: View {
    @Environment(WheelStore.self) private var store
    @Environment(\.scenePhase) private var scenePhase
    @Bindable var settings: PhoneNotificationSettingsModel
    @State private var editingAddress = false
    @State private var confirmingDisable = false
    private var account: NotificationAccount? { .current(store) }
    private var current: Bool { account != nil && settings.account == account }
    private var enabled: Bool? { current ? settings.enabled : nil }

    var body: some View {
        Form {
            Section {
                LabeledContent {
                    NoticeText(enabled.map { $0 ? "On" : "Off" } ?? (account == nil ? "Not connected" : "Unavailable"))
                        .foregroundStyle(enabled == true ? Color.green : .secondary)
                } label: { Label { Text("Bark") } icon: { Image(systemName: "bell.badge") } }
                if let account { LabeledContent { NoticeText("IB \(account.mode.capitalized)") } label: { Text("Account") } }
            } footer: {
                Text("Price alerts, executions and confirmed cancellations. Notifications continue when Wheel is closed while this account is connected on your backend.")
            }

            if account == nil {
                Section { Text("Connect to Paper or Live in Settings to manage notifications.").foregroundStyle(.secondary) }
            } else {
                if enabled == true && !editingAddress {
                    Section {
                        Button { Task { await settings.sendTest() } } label: { Label { Text("Send test notification") } icon: { Image(systemName: "paperplane") } }
                        Button { editingAddress = true } label: { Text("Change Bark address") }
                        Button(role: .destructive) { confirmingDisable = true } label: { Text("Turn off for this account") }
                    }.disabled(settings.busy || !current)
                } else if enabled == false || editingAddress {
                    Section {
                        SecureField(text: $settings.pushAddress) { Text("Bark push address") }
                            .textInputAutocapitalization(.never).autocorrectionDisabled().keyboardType(.URL)
                        Button { Task { await settings.save(); if settings.error == nil { editingAddress = false } } } label: {
                            Text(LocalizedStringKey(editingAddress ? "Save address" : "Enable Bark"))
                        }.disabled(settings.pushAddress.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                        if editingAddress { Button { editingAddress = false; settings.pushAddress = "" } label: { Text("Cancel") } }
                    } header: { Text("Bark address") }
                    footer: { Text("Open Bark, allow notifications, then paste its api.day.app push address here. Alert summaries are sent through Bark. Your address is stored privately on your backend.") }
                    .disabled(settings.busy || !current)
                }
                if settings.busy || settings.error != nil || settings.message != nil {
                    Section {
                        if settings.busy { ProgressView { Text("Updating…") } }
                        if let error = settings.error { NoticeText(error).foregroundStyle(.orange) }
                        else if let message = settings.message { NoticeText(message).foregroundStyle(.secondary) }
                    }.font(.footnote)
                }
            }
            Section {
                NavigationLink {
                    Form { DirectPushNotificationSettings() }.navigationTitle("Direct app notifications").navigationBarTitleDisplayMode(.inline)
                } label: { Text("Direct app notifications") }
            } header: { Text("Advanced") }
            footer: { Text("Bark is managed separately from direct Wheel notifications.") }
        }
        .navigationTitle("Notifications").navigationBarTitleDisplayMode(.inline)
        .refreshable { settings.select(account); await settings.refresh() }
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button { Task { settings.select(account); await settings.refresh() } } label: { Image(systemName: "arrow.clockwise") }
                    .accessibilityLabel(Text("Refresh notification status"))
                    .disabled(settings.busy || account == nil)
            }
        }
        .task(id: account) { settings.select(account); editingAddress = false; confirmingDisable = false; await settings.refresh() }
        .onChange(of: scenePhase) { _, phase in if phase == .active { Task { settings.select(account); await settings.refresh() } } }
        .confirmationDialog("Turn off Bark notifications?", isPresented: $confirmingDisable, titleVisibility: .visible) {
            Button(role: .destructive) { Task { await settings.disable() } } label: { Text("Turn off for this account") }
        } message: { Text("This stops new notifications for the selected account. A notification already in transit may still arrive.") }
    }
}
