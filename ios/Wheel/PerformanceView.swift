import SwiftUI
import Charts

private struct PerformancePoint: Decodable, Identifiable {
    var date: String
    var portfolio: Double
    var spx: Double
    var nq100: Double
    var id: String { date }
    var day: Date { ISO8601DateFormatter().date(from: date + "T16:00:00Z") ?? .distantPast }
}
private struct PerformanceHistory: Decodable {
    struct Latest: Decodable { let date: String; let nav: Double }
    let points: [PerformancePoint]
    let start: String
    let end: String
    let limited_history: Bool
    let stale: Bool
    let warning: String?
    let latest: Latest?
}
private struct PerformanceLive: Decodable {
    let daily_pnl: Double?
    let fresh: Bool
    let received_at: String?
}

struct PerformanceView: View {
    @Environment(WheelStore.self) private var store
    @Environment(\.scenePhase) private var phase
    @Environment(\.customPalette) private var palette
    @Environment(\.colorScheme) private var scheme
    @State private var period = "YTD"
    @State private var history: PerformanceHistory?
    @State private var live: PerformanceLive?
    @State private var error: String?
    @State private var liveError: String?
    @State private var loading = false
    @State private var visible = false
    @State private var revision = 0
    private var active: Bool { visible && phase == .active && store.selectedTab == "portfolio" }
    private var context: String { "\(active)-\(store.demo)-\(store.address)-\(period)-\(revision)" }
    private var gain: Color { palette.color("gain", scheme: scheme, fallback: FinancialColors.gain) }
    private var loss: Color { palette.color("loss", scheme: scheme, fallback: FinancialColors.loss) }
    // Daily P&L / previous reported NAV is provisional, not an official intraday TWR.
    private var estimate: Double? {
        guard live?.fresh == true, let pnl = live?.daily_pnl, pnl.isFinite,
              let history, let latest = history.latest, latest.nav > 0,
              latest.date == history.end, let last = history.points.last else { return nil }
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "America/New_York")!
        let today = calendar.startOfDay(for: Date())
        let clock = calendar.dateComponents([.hour, .minute], from: Date())
        let minute = (clock.hour ?? 0) * 60 + (clock.minute ?? 0)
        guard (570..<960).contains(minute) else { return nil }
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let components = latest.date.split(separator: "-").compactMap { Int($0) }
        guard components.count == 3, let previous = calendar.date(from: DateComponents(year: components[0], month: components[1], day: components[2])),
              let days = calendar.dateComponents([.day], from: previous, to: today).day,
              (1...4).contains(days), !calendar.isDateInWeekend(today),
              let stamp = live?.received_at.flatMap({ formatter.date(from: $0) ?? ISO8601DateFormatter().date(from: $0) }),
              calendar.isDate(stamp, inSameDayAs: today) else { return nil }
        return ((1 + last.portfolio / 100) * (1 + pnl / latest.nav) - 1) * 100
    }
    var body: some View {
        List {
            Section {
                Picker("Period", selection: $period) {
                    ForEach(["MTD", "YTD", "ALL"], id: \.self) { Text($0).tag($0) }
                }.pickerStyle(.segmented)
                if let history {
                    let value = estimate ?? history.points.last?.portfolio ?? 0
                    Text(String(format: "%+.2f%%", value))
                        .font(.system(size: 38, weight: .semibold, design: .rounded)).monospacedDigit()
                        .foregroundStyle(value >= 0 ? gain : loss)
                    Text(estimate == nil ? "Reported return" : "Intraday estimate").font(.caption).foregroundStyle(.secondary)
                    Chart {
                        RuleMark(y: .value("Zero", 0)).foregroundStyle(.secondary.opacity(0.4)).lineStyle(StrokeStyle(dash: [3, 3]))
                        ForEach(history.points) { point in
                            LineMark(x: .value("Date", point.day), y: .value("Return", point.portfolio), series: .value("Series", "Portfolio"))
                                .foregroundStyle(gain).lineStyle(StrokeStyle(lineWidth: 2.5))
                            LineMark(x: .value("Date", point.day), y: .value("Return", point.spx), series: .value("Series", "SPX"))
                                .foregroundStyle(.blue).lineStyle(StrokeStyle(lineWidth: 1.5))
                            LineMark(x: .value("Date", point.day), y: .value("Return", point.nq100), series: .value("Series", "Nasdaq-100"))
                                .foregroundStyle(.purple).lineStyle(StrokeStyle(lineWidth: 1.5))
                        }
                        if let estimate, let last = history.points.last {
                            ForEach([last.day, Date()], id: \.self) { day in
                                LineMark(x: .value("Date", day), y: .value("Return", day == last.day ? last.portfolio : estimate), series: .value("Series", "Estimate"))
                                    .foregroundStyle(gain).lineStyle(StrokeStyle(lineWidth: 2, dash: [4, 3]))
                            }
                        }
                    }.frame(height: 240)
                    HStack { Text("● Portfolio").foregroundStyle(gain); Text("● SPX").foregroundStyle(.blue); Text("● Nasdaq-100").foregroundStyle(.purple) }.font(.caption)
                    Text("\(history.start) → \(history.end)").font(.caption).foregroundStyle(.secondary)
                    if history.limited_history { Text("Limited history for this period").font(.caption).foregroundStyle(.orange) }
                    if history.stale { Text("Cached history · refresh pending").font(.caption).foregroundStyle(.orange) }
                    if let warning = history.warning { Text(warning).font(.caption).foregroundStyle(.orange) }
                }
                if loading { ProgressView() }
                if let error { Text(error).font(.footnote).foregroundStyle(.orange) }
            }
            Section("Today") {
                LabeledContent("Daily P&L", value: live?.fresh == true ? money(live?.daily_pnl) : "—")
                Text("Account base currency · IBKR daily P&L").font(.caption).foregroundStyle(.secondary)
                if let liveError { Text(liveError).font(.caption).foregroundStyle(.orange) }
            }
            Section {
                Text("History: compounded daily IBKR TWR. SPX and Nasdaq-100: FRED daily price indices, excluding reinvested dividends. Intraday estimate uses daily P&L / last reported NAV; deposits, withdrawals and IB reset times may affect comparability. Final returns follow the next Flex report.")
                    .font(.footnote).foregroundStyle(.secondary)
                Button("Refresh") { revision += 1 }
            }
        }.navigationTitle("Performance")
            .onAppear { visible = true }.onDisappear { visible = false }
            .task(id: context) {
                guard active else { return }
                history = nil; live = nil; error = nil; liveError = nil
                guard !store.demo else { error = "Performance requires a live backend with Flex history."; return }
                loading = true
                defer { loading = false }
                for _ in 0..<45 {
                    do {
                        let (data, status) = try await read("history", query: [URLQueryItem(name: "period", value: period)])
                        if status == 202 { try await Task.sleep(for: .seconds(2)); continue }
                        let value = try JSONDecoder().decode(PerformanceHistory.self, from: data)
                        try Task.checkCancellation(); history = value; return
                    } catch { if !Task.isCancelled { self.error = error.localizedDescription }; return }
                }
                error = "History is still generating. Try Refresh shortly."
            }
            .task(id: "live-\(active)-\(store.demo)-\(store.address)") {
                guard active, !store.demo else { return }
                while !Task.isCancelled {
                    do {
                        let (data, _) = try await read("live")
                        let next = try JSONDecoder().decode(PerformanceLive.self, from: data)
                        try Task.checkCancellation(); live = next; liveError = nil
                    } catch { if Task.isCancelled { return }; live = nil; liveError = error.localizedDescription }
                    do { try await Task.sleep(for: .seconds(5)) } catch { return }
                }
            }
    }
    private func read(_ path: String, query: [URLQueryItem] = []) async throws -> (Data, Int) {
        guard var url = URLComponents(string: store.address.trimmingCharacters(in: .whitespacesAndNewlines)), url.scheme == "https", url.host != nil,
              url.user == nil, url.password == nil, url.query == nil, url.fragment == nil else { throw AppError.message("Invalid backend address.") }
        url.path = url.path.trimmingCharacters(in: CharacterSet(charactersIn: "/")) + "/api/performance/" + path
        if !url.path.hasPrefix("/") { url.path = "/" + url.path }
        url.queryItems = query.isEmpty ? nil : query
        let (data, response) = try await URLSession.shared.data(for: URLRequest(url: url.url!, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 15))
        guard let http = response as? HTTPURLResponse else { throw AppError.message("Invalid response.") }
        guard (200...202).contains(http.statusCode) else {
            let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
            throw AppError.message(payload?["error"] as? String ?? "Performance endpoint unavailable.")
        }
        return (data, http.statusCode)
    }
}
