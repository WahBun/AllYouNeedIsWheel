import SwiftUI
import UserNotifications
import Observation

final class WheelNotificationDelegate: NSObject, UIApplicationDelegate, UNUserNotificationCenterDelegate {
    func application(_ application: UIApplication, didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil) -> Bool {
        UNUserNotificationCenter.current().delegate = self
        return true
    }
    func application(_ application: UIApplication, didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {
        let token = deviceToken.map { String(format: "%02x", $0) }.joined()
        Task { @MainActor in await WheelPush.shared.received(token) }
    }
    func application(_ application: UIApplication, didFailToRegisterForRemoteNotificationsWithError error: Error) {
        Task { @MainActor in WheelPush.shared.status = "Push registration failed. Enable Push Notifications signing and try again." }
    }
    func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification,
                                withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void) {
        // Native trading feedback already handles order sounds. Remote notifications
        // still show a banner for orders outside the currently visible chart.
        let kind = notification.request.content.userInfo["wheel_kind"] as? String
        completionHandler(kind == "price" ? [.banner, .sound, .list] : [.banner, .list])
    }
}

@MainActor @Observable
final class WheelPush {
    static let shared = WheelPush()
    var status = "Enable notifications for this account."
    var busy = false
    var enabled = false
    @ObservationIgnored private var token: String?
    @ObservationIgnored private var address = ""
    @ObservationIgnored private var mode = ""
    @ObservationIgnored private var epoch = ""
    @ObservationIgnored private var registered = ""
    @ObservationIgnored private let session = URLSession(configuration: .ephemeral, delegate: NoRedirect(), delegateQueue: nil)
    private var preferenceKey: String { "wheel.push.enabled:" + address + ":" + mode }
    private var identity: String {
        if let value = UserDefaults.standard.string(forKey: "wheel.push.installation") { return value }
        let value = UUID().uuidString; UserDefaults.standard.set(value, forKey: "wheel.push.installation"); return value
    }
    private var context: String { address + ":" + mode + ":" + epoch }
    private var environment: String {
        Bundle.main.object(forInfoDictionaryKey: "WheelAPNSEnvironment") as? String == "production" ? "production" : "sandbox"
    }
    func refresh(address: String, mode: String, epoch: String?) async {
        self.address = address; self.mode = mode; self.epoch = epoch ?? ""
        enabled = UserDefaults.standard.bool(forKey: preferenceKey)
        guard enabled, ["paper", "live"].contains(mode), !self.epoch.isEmpty else { return }
        let settings = await UNUserNotificationCenter.current().notificationSettings()
        guard settings.authorizationStatus == .authorized || settings.authorizationStatus == .provisional else {
            status = "Notifications are disabled in iPhone Settings."; return
        }
        // Ask APNs for the current token each launch; persisted tokens are not authoritative.
        UIApplication.shared.registerForRemoteNotifications()
        if token != nil { await enroll() }
    }
    func enable() async {
        guard !busy, !epoch.isEmpty, ["paper", "live"].contains(mode) else { return }
        busy = true; defer { busy = false }
        let requested = context
        do {
            let granted = try await UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge])
            guard requested == context else { return }
            guard granted else { status = "Allow notifications in iPhone Settings to receive alerts."; return }
            enabled = true; UserDefaults.standard.set(true, forKey: preferenceKey)
            registered = ""; status = "Registering this iPhone…"
            UIApplication.shared.registerForRemoteNotifications()
            if token != nil { await enroll() }
        } catch { status = "Notification permission could not be requested. Try again." }
    }
    func received(_ token: String) async { self.token = token; await enroll() }
    private func enroll() async {
        guard enabled, !epoch.isEmpty, let token else { return }
        let requested = context, signature = context + ":" + token
        guard registered != signature else { return }
        do {
            let reply = try await send(["id": identity, "token": token, "environment": environment, "enabled": true])
            guard requested == context else { return }
            registered = signature
            status = reply["push_configured"] as? Bool == true ? "Enabled for IB \(mode.capitalized)." : "iPhone registered. APNs setup on Mini is pending."
        } catch { if requested == context { status = error.localizedDescription } }
    }
    func disable() async {
        guard !busy else { return }; busy = true; defer { busy = false }
        let requested = context
        do {
            _ = try await send(["id": identity, "enabled": false])
            guard requested == context else { return }
            enabled = false; registered = ""; UserDefaults.standard.set(false, forKey: preferenceKey)
            status = "Notifications disabled for this account."
        } catch { if requested == context { status = error.localizedDescription } }
    }
    private func send(_ body: [String: Any]) async throws -> [String: Any] {
        guard let base = URL(string: address), base.scheme == "https", base.host != nil, !epoch.isEmpty else {
            throw AppError.message("Connect and verify your private backend first.")
        }
        var request = URLRequest(url: base.appendingPathComponent("api/notifications/devices"), cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 12)
        request.httpMethod = "POST"
        request.setValue("1", forHTTPHeaderField: "X-All-You-Need-Is-Wheel")
        request.setValue(epoch, forHTTPHeaderField: "X-Wheel-Account-Epoch")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: body)
        let (data, response) = try await session.data(for: request)
        let reply = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] ?? [:]
        guard (response as? HTTPURLResponse)?.statusCode == 200 else {
            throw AppError.message(reply["error"] as? String ?? "Notification registration failed. Try again.")
        }
        return reply
    }
}

struct DirectPushNotificationSettings: View {
    @Environment(WheelStore.self) private var store
    private var push: WheelPush { .shared }
    var body: some View {
        Section {
            Text(verbatim: "Price alerts, executions and confirmed cancellations.").font(.footnote)
            Button { Task { await push.enable() } } label: {
                Text(verbatim: push.enabled ? "Retry notification registration" : "Enable iPhone notifications")
            }.disabled(push.busy || store.demo || store.trading.accountEpoch == nil)
            if push.enabled {
                Button { Task { await push.disable() } } label: { Text(verbatim: "Disable for this account") }.disabled(push.busy)
            }
            Text(verbatim: push.status).font(.footnote).foregroundStyle(.secondary)
        } header: { Text(verbatim: "Direct app notifications") }
        footer: { Text(verbatim: "Optional. Requires Push Notifications signing and server setup. Bark works independently.") }
    }
}
