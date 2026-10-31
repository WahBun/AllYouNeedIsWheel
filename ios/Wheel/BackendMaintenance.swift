import SwiftUI
import Observation

struct BackendMaintenanceStatus: Decodable {
    let backend: String
    let mode: String
    let gateway_connected: Bool
    let epoch: String
    let performance: PerformanceMaintenanceStatus
}

struct PerformanceMaintenanceStatus: Decodable {
    let configured: Bool
    let can_replace: Bool
    var source: String?
    var history_through: String?
    var history_available: Bool?
    var last_success: String?
    var refreshing: Bool?
    var error: String?
    var token_expires_on: String?
    var days_remaining: Int?
    var token_saved_at: String?
}

private struct FlexValidationStatus: Decodable {
    let id: String?
    let state: String
    var report_through: String?
    var error: String?
}

@MainActor @Observable
final class BackendMaintenanceModel {
    private(set) var account: NotificationAccount?
    private(set) var status: BackendMaintenanceStatus?
    private(set) var busy = false
    private(set) var validationID: String?
    private(set) var validationState: String?
    private(set) var reportThrough: String?
    private(set) var error: String?
    private(set) var message: String?
    var token = ""
    var recordsExpiry = false
    var expiry = Date.now.addingTimeInterval(86400)
    @ObservationIgnored private var revision = UUID()
    @ObservationIgnored private let session: URLSession

    init(session: URLSession = URLSession(configuration: .ephemeral, delegate: NoRedirect(), delegateQueue: nil)) {
        self.session = session
    }

    func select(_ account: NotificationAccount?) {
        guard self.account != account else { return }
        self.account = account; revision = UUID()
        status = nil; busy = false; error = nil; message = nil
        clearDraft()
    }

    func clearDraft() {
        token = ""; recordsExpiry = false
        validationID = nil; validationState = nil; reportThrough = nil
    }

    private func request(_ path: String, account: NotificationAccount, body: [String: Any]? = nil) async throws -> Data {
        guard let base = URL(string: account.address), base.scheme == "https", base.host != nil,
              base.user == nil, base.password == nil, base.query == nil, base.fragment == nil else {
            throw AppError.message("Use your private HTTPS backend address in Settings.")
        }
        var request = URLRequest(url: base.appendingPathComponent("api/maintenance/" + path), cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 15)
        request.httpMethod = body == nil ? "GET" : "POST"
        request.setValue("1", forHTTPHeaderField: "X-All-You-Need-Is-Wheel")
        request.setValue(account.epoch, forHTTPHeaderField: "X-Wheel-Account-Epoch")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let body { request.httpBody = try JSONSerialization.data(withJSONObject: body) }
        let (data, response) = try await session.data(for: request)
        let code = (response as? HTTPURLResponse)?.statusCode ?? 0
        guard [200, 202].contains(code) else {
            if code == 404 { throw AppError.message("This backend does not support maintenance yet. Deploy the matching update on Mini.") }
            let reply = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
            throw AppError.message(reply?["error"] as? String ?? "Maintenance is unavailable. Refresh before trying again.")
        }
        return data
    }

    func refresh() async {
        guard !busy, let account else { return }
        let requested = revision
        busy = true; error = nil
        defer { if requested == revision { busy = false } }
        do {
            let data = try await request("status", account: account)
            let value = try JSONDecoder().decode(BackendMaintenanceStatus.self, from: data)
            guard requested == revision else { return }
            guard value.epoch == account.epoch, value.mode == account.mode else {
                throw AppError.message("Account changed. Reconnect in Settings before continuing.")
            }
            status = value
            if let validationID { try await checkValidation(validationID, account: account, requested: requested) }
        } catch {
            guard requested == revision else { return }
            status = nil
            self.error = (error as? AppError)?.localizedDescription ?? "Backend is unreachable. Check Tailscale and Mini, then refresh."
        }
    }

    func validate() async {
        guard !busy, let account, status?.performance.can_replace == true, validationID == nil else { return }
        let requested = revision
        busy = true; error = nil; message = nil
        defer { if requested == revision { busy = false } }
        do {
            var body: [String: Any] = ["token": token.trimmingCharacters(in: .whitespacesAndNewlines)]
            if recordsExpiry {
                let formatter = DateFormatter(); formatter.locale = Locale(identifier: "en_US_POSIX")
                formatter.dateFormat = "yyyy-MM-dd"
                body["expires_on"] = formatter.string(from: expiry)
            }
            let data = try await request("flex/validate", account: account, body: body)
            let result = try JSONDecoder().decode(FlexValidationStatus.self, from: data)
            guard requested == revision else { return }
            guard let id = result.id, result.state == "validating", id.count == 32,
                  id.allSatisfy({ $0.isHexDigit }) else { throw AppError.message("Validation could not be confirmed. Refresh before trying again.") }
            token = ""; validationID = id; validationState = "validating"
            // Poll reads only. A timeout never retries a credential write.
            for _ in 0..<90 {
                try await Task.sleep(for: .seconds(2))
                guard requested == revision else { return }
                try await checkValidation(id, account: account, requested: requested)
                if validationState != "validating" { return }
            }
            message = "Validation is still running. Refresh to check its result."
        } catch {
            guard requested == revision else { return }
            self.error = (error as? AppError)?.localizedDescription ?? "Validation response unavailable. Nothing is saved until you tap Save validated token."
        }
    }

    private func checkValidation(_ id: String, account: NotificationAccount, requested: UUID) async throws {
        let data = try await request("flex/validation/" + id, account: account)
        let result = try JSONDecoder().decode(FlexValidationStatus.self, from: data)
        guard requested == revision else { return }
        guard result.id == id, ["validating", "ready", "failed", "saved"].contains(result.state) else {
            throw AppError.message("Validation status is unavailable. Refresh before continuing.")
        }
        validationState = result.state; reportThrough = result.report_through
        if result.state == "failed" { error = result.error ?? "Token validation failed." }
        if result.state == "saved" { message = "Token saved on Mini. No restart is needed."; clearDraft() }
    }

    func save() async {
        guard !busy, let account, let validationID, validationState == "ready" else { return }
        let requested = revision
        busy = true; error = nil; message = nil
        do {
            let data = try await request("flex/save", account: account, body: ["id": validationID])
            let result = try JSONDecoder().decode(FlexValidationStatus.self, from: data)
            guard requested == revision else { return }
            guard result.state == "saved" else { throw AppError.message("Saving could not be confirmed. Refresh to check its result.") }
            clearDraft(); message = "Token saved on Mini. No restart is needed."
        } catch {
            guard requested == revision else { return }
            // Disable Save after an uncertain response; reconcile using GET first.
            validationState = "unknown"
            self.error = (error as? AppError)?.localizedDescription ?? "Save response unavailable. Refresh to check whether Mini saved the token."
        }
        guard requested == revision else { return }
        busy = false
        if validationState == nil { await refresh() }
    }
}

struct BackendMaintenanceSections: View {
    @Bindable var model: BackendMaintenanceModel
    @Binding var editing: Bool
    @Binding var expanded: Bool

    var body: some View {
        Group {
            Section {
                row("Backend", model.busy && model.status == nil ? "Checking…" : model.status == nil ? "Unavailable" : "Reachable")
                if let status = model.status {
                    row("Gateway", status.gateway_connected ? "Connected" : "Disconnected")
                }
            }
            if let performance = model.status?.performance {
                Section {
                    DisclosureGroup(isExpanded: $expanded) {
                        if performance.configured {
                            row("History through", performance.history_through ?? "Unavailable")
                            row("Last refresh", displayDate(performance.last_success))
                            row("Token expiry", performance.token_expires_on ?? "Not recorded")
                            if let remaining = performance.days_remaining, remaining <= 30 {
                                Text(verbatim: remaining < 0 ? "Recorded expiry has passed." : "Recorded expiry is in \(remaining) days.")
                                    .foregroundStyle(.orange)
                            }
                            if performance.refreshing == true { Text(verbatim: "Performance refresh is running.").foregroundStyle(.secondary) }
                            if let error = performance.error { Text(verbatim: error).foregroundStyle(.orange) }
                            if performance.last_success == nil {
                                Text(verbatim: "Refresh time is available after the first successful refresh following a backend restart.")
                                    .font(.footnote).foregroundStyle(.secondary)
                            }
                        } else {
                            Text(verbatim: "Performance data is not configured for this account.").foregroundStyle(.secondary)
                        }
                        if performance.can_replace && !editing {
                            Button { editing = true } label: { Text(verbatim: "Replace Flex token") }
                        }
                    } label: {
                        HStack {
                            Text(verbatim: "Performance data")
                            Spacer(minLength: 8)
                            Text(verbatim: performance.days_remaining.map { $0 <= 30 ? "Check expiry" : "Ready" } ?? (performance.configured ? "Configured" : "Not configured"))
                                .foregroundStyle(performance.days_remaining.map { $0 <= 30 } == true ? Color.orange : .secondary)
                        }
                    }
                }
            }
            if editing, model.status?.performance.can_replace == true {
                Section {
                    if model.validationID == nil {
                        SecureField("Flex token", text: $model.token)
                            .textInputAutocapitalization(.never).autocorrectionDisabled()
                            .privacySensitive()
                        Toggle(isOn: $model.recordsExpiry) { Text(verbatim: "Record expiry date") }
                        if model.recordsExpiry {
                            DatePicker(selection: $model.expiry, in: Date.now..., displayedComponents: .date) { Text(verbatim: "Expires on") }
                        }
                        Button { Task { await model.validate() } } label: { Text(verbatim: "Validate token") }
                            .disabled(model.token.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    } else if model.validationState == "ready" {
                        Label { Text(verbatim: "Report and account verified") } icon: { Image(systemName: "checkmark.circle") }.foregroundStyle(.green)
                        row("Report through", model.reportThrough ?? "—")
                        Button { Task { await model.save(); if model.validationID == nil { editing = false } } } label: { Text(verbatim: "Save validated token") }
                    } else {
                        Text(verbatim: model.validationState == "validating" ? "Waiting for IB to generate the report…" : "Refresh to check validation, or cancel to start again.")
                    }
                    Button(role: .cancel) { model.clearDraft(); editing = false } label: { Text(verbatim: "Cancel") }
                } header: { Text(verbatim: "Replace token") } footer: {
                    Text(verbatim: "Paste a new token from IB. Validate first, then save privately on Mini. Record the expiry shown by IB. Update other apps that share this token too.")
                }
                .id("tokenEditor")
                .disabled(model.busy)
            }
            if model.account == nil {
                Section { Text(verbatim: "Connect to Paper or Live in Settings to view backend status.").foregroundStyle(.secondary) }
            }
            if model.busy || model.error != nil || model.message != nil {
                Section {
                    if model.busy { ProgressView { Text(verbatim: "Checking…") } }
                    if let error = model.error { Text(verbatim: error).foregroundStyle(.orange) }
                    if let message = model.message { Text(verbatim: message).foregroundStyle(.secondary) }
                }
            }
        }
        .environment(\.locale, Locale(identifier: "en"))
    }

    private func row(_ label: String, _ value: String) -> some View {
        LabeledContent { Text(verbatim: value).multilineTextAlignment(.trailing) } label: { Text(verbatim: label) }
    }

    private func displayDate(_ raw: String?) -> String {
        guard let raw else { return "Unavailable" }
        let formatter = ISO8601DateFormatter(); formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        guard let date = formatter.date(from: raw) ?? ISO8601DateFormatter().date(from: raw) else { return "Unavailable" }
        let display = DateFormatter(); display.locale = Locale(identifier: "en_US_POSIX")
        display.dateFormat = "yyyy-MM-dd HH:mm"
        return display.string(from: date)
    }
}
