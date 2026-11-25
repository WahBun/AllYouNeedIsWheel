import SwiftUI
import WatchConnectivity

@main
struct WheelWatch: App {
    @StateObject private var phone = WatchLink()
    var body: some Scene { WindowGroup { WatchDashboard().environmentObject(phone) } }
}

@MainActor
final class WatchLink: NSObject, ObservableObject, WCSessionDelegate {
    @Published private(set) var snapshot: WatchSnapshot?
    @Published private(set) var notice = "Connecting to iPhone…"
    @Published private(set) var reachability = 0
    @Published private(set) var theme = UserDefaults.standard.data(forKey: "wheel.watch.theme")
        .flatMap { try? JSONDecoder().decode(WatchTheme.self, from: $0) } ?? .initial
    @Published private(set) var directions: [String: Int] = [:]

    private func acceptTheme(_ raw: Any?) {
        guard let data = raw as? Data, let next = try? JSONDecoder().decode(WatchTheme.self, from: data),
              next != theme else { return }
        theme = next
        UserDefaults.standard.set(data, forKey: "wheel.watch.theme")
    }

    private var requestID = UUID()
    private var pages = WatchPageCache()

    override init() {
        super.init()
        WCSession.default.delegate = self
        WCSession.default.activate()
    }

    func clear() {
        pages = WatchPageCache()
        requestID = UUID()
        snapshot = nil
        directions = [:]
        notice = "Updating…"
    }

    func select(_ section: WatchSection, page: Int) {
        requestID = UUID()
        snapshot = pages.snapshot(for: section, page: page)
        directions = [:]
        notice = snapshot == nil ? "Updating…" : ""
    }

    func read(_ section: WatchSection, page: Int) async {
        let id = UUID()
        requestID = id
        let session = WCSession.default
        if session.activationState == .notActivated { session.activate() }
        guard session.activationState == .activated, session.isReachable else {
            notice = "iPhone unavailable"
            return
        }
        do {
            let reply: [String: Any] = try await withCheckedThrowingContinuation { continuation in
                session.sendMessage(["section": section.rawValue, "page": page],
                    replyHandler: { continuation.resume(returning: $0) },
                    errorHandler: { continuation.resume(throwing: $0) })
            }
            guard id == requestID, !Task.isCancelled else { return }
            if reply["error"] as? String == "account" {
                clear()
                notice = "Waiting for account verification on iPhone."
                return
            }
            guard let data = reply["data"] as? Data else { throw URLError(.badServerResponse) }
            let next = try JSONDecoder().decode(WatchSnapshot.self, from: data)
            acceptTheme(reply["theme"])
            directions = next.directions(since: snapshot)
            pages.store(next, section: section, page: page)
            snapshot = next
            notice = ""
        } catch {
            if id == requestID, !Task.isCancelled { notice = "Update unavailable" }
        }
    }

    nonisolated func session(_ session: WCSession, activationDidCompleteWith activationState: WCSessionActivationState, error: Error?) {
        Task { @MainActor in self.reachability += 1 }
    }
    nonisolated func sessionReachabilityDidChange(_ session: WCSession) {
        Task { @MainActor in self.reachability += 1 }
    }
    nonisolated func session(_ session: WCSession, didReceiveApplicationContext context: [String: Any]) {
        Task { @MainActor in
            self.acceptTheme(context["theme"])
            if self.snapshot?.mode != context["mode"] as? String || self.snapshot?.epoch != context["epoch"] as? String {
                self.clear()
                self.reachability += 1
            }
        }
    }
}

private struct WatchDashboard: View {
    @EnvironmentObject private var phone: WatchLink
    @Environment(\.scenePhase) private var phase
    @Environment(\.isLuminanceReduced) private var dimmed
    @AppStorage("wheel.watch.section") private var section: WatchSection = .quotes
    @State private var page = 0

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 5) {
                    HStack {
                        sectionButton("Quotes", .quotes)
                        sectionButton("Holdings", .holdings)
                    }
                    if !phone.notice.isEmpty {
                        Text(verbatim: phone.notice).font(.footnote).foregroundStyle(.secondary)
                    }
                    if let snapshot = phone.snapshot {
                        if section == .quotes {
                            ForEach(snapshot.quotes) { row in
                                VStack(alignment: .leading, spacing: 0) {
                                    HStack(alignment: .firstTextBaseline, spacing: 3) {
                                        SymbolText(symbol: row.symbol).font(.body.bold())
                                        if row.contract != row.symbol {
                                            Text(verbatim: row.contract.hasPrefix(row.symbol) ? String(row.contract.dropFirst(row.symbol.count)) : row.contract)
                                                .font(.caption2).foregroundStyle(.secondary)
                                        }
                                        Spacer(minLength: 2)
                                        Text(verbatim: row.price.map { $0.formatted(.number.precision(.fractionLength(2))) } ?? "—")
                                            .foregroundStyle(priceColor(row)).monospacedDigit()
                                    }
                                    if let note = quoteNote(row) {
                                        Text(verbatim: note).font(.caption2).foregroundStyle(.secondary)
                                    }
                                }
                                Divider()
                            }
                            if let oldest = snapshot.quotes.compactMap(\.sampledAt).min() {
                                Text("As of \(stamp(oldest))").font(.caption2).foregroundStyle(.secondary)
                            }
                        } else {
                            if snapshot.total == 0 { Text("No holdings") }
                            ForEach(snapshot.positions) { row in
                                VStack(alignment: .leading, spacing: 1) {
                                    HStack(alignment: .firstTextBaseline, spacing: 3) {
                                        SymbolText(symbol: row.symbol).font(.headline)
                                        if row.contract != row.symbol {
                                            Text(verbatim: row.contract.hasPrefix(row.symbol) ? String(row.contract.dropFirst(row.symbol.count)) : row.contract)
                                                .font(.caption2).fixedSize(horizontal: false, vertical: true)
                                        }
                                    }
                                    HStack {
                                        Text(verbatim: row.quantity.formatted())
                                            .accessibilityLabel("Quantity \(row.quantity.formatted())")
                                        Spacer()
                                        Text(verbatim: row.price.map { price in
                                            let style = FloatingPointFormatStyle<Double>.Currency(code: row.currency)
                                            return price.formatted(row.currency == "USD" ? style.presentation(.narrow) : style)
                                        } ?? "—")
                                    }.font(.caption).monospacedDigit().foregroundStyle(.secondary)
                                }
                                Divider()
                            }
                            if page > 0 { Button("Previous") { page -= 1 } }
                            if (page + 1) * 30 < snapshot.total { Button("Next") { page += 1 } }
                            Text("As of \(Date(timeIntervalSince1970: snapshot.sampledAt).formatted(date: .abbreviated, time: .shortened))")
                                .font(.caption2).foregroundStyle(.secondary)
                        }
                    }
                }
                .padding(.horizontal, 5)
            }
            .foregroundStyle(phone.theme.dark ? Color.white : .black)
            .background(phone.theme.dark ? Color.black : .white)
            .environment(\.colorScheme, phone.theme.dark ? .dark : .light)
            .navigationTitle(phone.snapshot?.mode.capitalized ?? "Wheel")
            .toolbarTitleDisplayMode(.inline)
            .onChange(of: section) { _, next in page = 0; phone.select(next, page: 0) }
            .onChange(of: page) { _, next in phone.select(section, page: next) }
            .task(id: "\(section.rawValue)-\(page)-\(phase)-\(dimmed)-\(phone.reachability)") {
                guard phase == .active, !dimmed else { return }
                while !Task.isCancelled {
                    await phone.read(section, page: page)
                    let waiting = section == .quotes && phone.snapshot?.quotes.contains { $0.price == nil } == true
                    do { try await Task.sleep(for: .seconds(waiting ? 6 : 15)) } catch { return }
                }
            }
        }
    }

    private func sectionButton(_ title: LocalizedStringKey, _ value: WatchSection) -> some View {
        Button { section = value } label: {
            Text(title).font(.footnote.bold())
                .foregroundStyle(section == value ? color(phone.theme.accent) : .secondary)
                .frame(maxWidth: .infinity, minHeight: 30)
                .background(Capsule().fill(color(phone.theme.accent).opacity(section == value ? 0.20 : 0.06)))
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(section == value ? .isSelected : [])
    }

    private func color(_ rgb: Int) -> Color {
        Color(red: Double((rgb >> 16) & 255) / 255, green: Double((rgb >> 8) & 255) / 255, blue: Double(rgb & 255) / 255)
    }

    private func priceColor(_ row: WatchQuote) -> Color {
        guard phone.notice.isEmpty, let value = phone.directions[row.symbol], value != 0 else {
            return phone.theme.dark ? .white : .black
        }
        return color(value > 0 ? phone.theme.gain : phone.theme.loss)
    }

    private func stamp(_ seconds: Double) -> String {
        let date = Date(timeIntervalSince1970: seconds)
        return date.formatted(date: Calendar.current.isDateInToday(date) ? .omitted : .abbreviated, time: .standard)
    }

    private func quoteNote(_ row: WatchQuote) -> String? {
        guard let time = row.sampledAt else { return "Awaiting quote" }
        let type = [2: "Frozen", 3: "Delayed", 4: "Delayed frozen"][row.dataType ?? 0]
        let stale = Date.now.timeIntervalSince1970 - time > 60
        let notes = [type, row.source == "close" ? "Close" : nil, stale ? "Stale · " + stamp(time) : nil].compactMap { $0 }
        return notes.isEmpty ? nil : notes.joined(separator: " · ")
    }
}
