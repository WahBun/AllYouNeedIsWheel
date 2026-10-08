import SwiftUI
import Charts

enum PerformanceColors {
    // Lavender in dark mode; deeper violet keeps thin lines legible on white.
    static let spx = Color(uiColor: UIColor { traits in
        traits.userInterfaceStyle == .dark
            ? UIColor(red: 190.0 / 255, green: 167.0 / 255, blue: 239.0 / 255, alpha: 1)
            : UIColor(red: 134.0 / 255, green: 100.0 / 255, blue: 190.0 / 255, alpha: 1)
    })
}

private struct PerformancePoint: Decodable, Identifiable {
    var date: String
    var portfolio: Double
    var spx: Double
    var nq100: Double
    var id: String { date }
    let day: Date
    private enum CodingKeys: String, CodingKey { case date, portfolio, spx, nq100 }
    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        date = try values.decode(String.self, forKey: .date)
        portfolio = try values.decode(Double.self, forKey: .portfolio)
        spx = try values.decode(Double.self, forKey: .spx)
        nq100 = try values.decode(Double.self, forKey: .nq100)
        guard let parsed = ISO8601DateFormatter().date(from: date + "T16:00:00Z") else {
            throw DecodingError.dataCorruptedError(forKey: .date, in: values, debugDescription: "Invalid trading date")
        }
        day = parsed
    }
}
private struct PerformanceHistory: Decodable {
    struct Latest: Decodable { let date: String; let nav: Double }
    let points: [PerformancePoint]
    let start: String
    let end: String
    let refreshing: Bool?
    let awaiting_report: Bool?
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

private struct ReturnSegment: Identifiable {
    let id: String
    let start: Date
    let end: Date
    let first: Double
    let last: Double
    var positive: Bool { first + last >= 0 }
}

private enum BenchmarkSelection: String, CaseIterable, Identifiable {
    case none = "Portfolio only"
    case spx = "SPX"
    case nq100 = "NDX"
    case both = "SPX + NDX"
    var id: String { rawValue }
    var showsSPX: Bool { self == .spx || self == .both }
    var showsNQ100: Bool { self == .nq100 || self == .both }
}

struct PerformanceView: View {
    @Environment(WheelStore.self) private var store
    @Environment(\.scenePhase) private var phase
    @Environment(\.customPalette) private var palette
    @Environment(\.colorScheme) private var scheme
    @State private var period = "YTD"
    @State private var benchmarks: BenchmarkSelection = .both
    @State private var history: PerformanceHistory?
    @State private var live: PerformanceLive?
    @State private var error: String?
    @State private var liveError: String?
    @State private var loading = false
    @State private var visible = false
    @State private var revision = 0
    private var active: Bool { visible && phase == .active && store.selectedTab == "portfolio" }
    private var context: String { "\(active)-\(store.demo)-\(store.address)-\(period)-\(revision)" }
    private var performanceLegend: some View {
        HStack(spacing: 6) {
            Text("● Portfolio").foregroundStyle(gain)
            if benchmarks.showsSPX { Text("● SPX").foregroundStyle(PerformanceColors.spx) }
            if benchmarks.showsNQ100 { Text("● NDX").foregroundStyle(.orange) }
        }
    }
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
    private func segments(from start: Date, _ first: Double, to end: Date, _ last: Double, id: String) -> [ReturnSegment] {
        if first * last < 0 {
            let crossing = start.addingTimeInterval(end.timeIntervalSince(start) * abs(first) / (abs(first) + abs(last)))
            return [ReturnSegment(id: id + "a", start: start, end: crossing, first: first, last: 0),
                    ReturnSegment(id: id + "b", start: crossing, end: end, first: 0, last: last)]
        }
        return [ReturnSegment(id: id, start: start, end: end, first: first, last: last)]
    }
    private var accountSegments: [ReturnSegment] {
        guard let points = history?.points else { return [] }
        return zip(points, points.dropFirst()).flatMap { a, b in
            segments(from: a.day, a.portfolio, to: b.day, b.portfolio, id: a.date)
        }
    }
    var body: some View {
        List {
            Section {
                Picker("Period", selection: $period) {
                    ForEach(["MTD", "YTD", "ALL"], id: \.self) { Text(LocalizedStringKey($0)).tag($0) }
                }.pickerStyle(.segmented)
                Picker("Compare with", selection: $benchmarks) {
                    ForEach(BenchmarkSelection.allCases) { option in
                        Text(LocalizedStringKey(option.rawValue)).tag(option)
                    }
                }.pickerStyle(.menu)
                if let history {
                    let value = estimate ?? history.points.last?.portfolio ?? 0
                    Text(String(format: "%+.2f%%", value))
                        .font(.system(size: 38, weight: .semibold, design: .rounded)).monospacedDigit()
                        .foregroundStyle(value >= 0 ? gain : loss)
                    Text(LocalizedStringKey(estimate == nil ? "Reported return" : "Intraday estimate")).font(.caption).foregroundStyle(.secondary)
                    Chart {
                        RuleMark(y: .value("Zero", 0)).foregroundStyle(.secondary.opacity(0.4)).lineStyle(StrokeStyle(lineWidth: 1))
                        if history.points.count == 1, let point = history.points.first {
                            PointMark(x: .value("Date", point.day), y: .value("Return", point.portfolio))
                                .foregroundStyle(gain)
                        }
                        ForEach(accountSegments) { segment in
                            LineMark(x: .value("Date", segment.start), y: .value("Return", segment.first), series: .value("Series", segment.id))
                                .foregroundStyle(segment.positive ? gain : loss).lineStyle(StrokeStyle(lineWidth: 2.5))
                            LineMark(x: .value("Date", segment.end), y: .value("Return", segment.last), series: .value("Series", segment.id))
                                .foregroundStyle(segment.positive ? gain : loss).lineStyle(StrokeStyle(lineWidth: 2.5))
                        }
                        ForEach(history.points) { point in
                            if benchmarks.showsSPX {
                            LineMark(x: .value("Date", point.day), y: .value("Return", point.spx), series: .value("Series", "SPX"))
                                .foregroundStyle(PerformanceColors.spx).lineStyle(StrokeStyle(lineWidth: 1.5))
                            }
                            if benchmarks.showsNQ100 {
                            LineMark(x: .value("Date", point.day), y: .value("Return", point.nq100), series: .value("Series", "NDX"))
                                .foregroundStyle(.orange).lineStyle(StrokeStyle(lineWidth: 1.5))
                            }
                        }
                        if let estimate, let last = history.points.last {
                            ForEach(segments(from: last.day, last.portfolio, to: Date(), estimate, id: "estimate")) { segment in
                                LineMark(x: .value("Date", segment.start), y: .value("Return", segment.first), series: .value("Series", segment.id))
                                    .foregroundStyle(segment.positive ? gain : loss).lineStyle(StrokeStyle(lineWidth: 2, dash: [4, 3]))
                                LineMark(x: .value("Date", segment.end), y: .value("Return", segment.last), series: .value("Series", segment.id))
                                    .foregroundStyle(segment.positive ? gain : loss).lineStyle(StrokeStyle(lineWidth: 2, dash: [4, 3]))
                            }
                        }

                    }
                    .chartXAxis {
                        if let first = history.points.first, let last = history.points.last {
                            AxisMarks(values: first.day == last.day ? [first.day] : [first.day, last.day]) { value in
                                AxisValueLabel(anchor: value.as(Date.self) == first.day ? .topLeading : .topTrailing) {
                                    if let date = value.as(Date.self) {
                                        let parts = (date == first.day ? first.date : last.date).split(separator: "-")
                                        Text(parts.count == 3 ? "\(parts[1])/\(parts[2])/\(parts[0])" : "")
                                            .font(.caption2).fontWeight(.medium).monospacedDigit()
                                    }
                                }
                            }
                        } else {
                            AxisMarks(values: .automatic) { _ in AxisValueLabel() }
                        }
                    }
                    .chartYAxis {
                        AxisMarks(position: .trailing, values: .automatic) { value in
                            AxisValueLabel {
                                if let percent = value.as(Double.self) {
                                    Text(percent.formatted(.number.precision(.fractionLength(0...2))) + "%")
                                        .monospacedDigit()
                                }
                            }
                        }
                    }
                    .chartOverlay { proxy in
                        PerformanceSelectionOverlay(points: history.points, proxy: proxy, gain: gain, loss: loss, benchmarks: benchmarks)
                            .id(period + benchmarks.rawValue)
                    }
                    .frame(height: 240)
                    performanceLegend.font(.caption)
                    if history.awaiting_report == true { Text("Awaiting the first daily report for this period").font(.caption).foregroundStyle(.secondary) }
                    if history.limited_history { Text("Limited history for this period").font(.caption).foregroundStyle(.orange) }
                    if history.stale || loading { Text("Cached history · refresh pending").font(.caption).foregroundStyle(.orange) }
                    if let warning = history.warning { NoticeText(warning).font(.caption).foregroundStyle(.orange) }
                }
                if loading { ProgressView() }
                if let error { NoticeText(error).font(.footnote).foregroundStyle(.orange) }
            }
            Section("Today") {
                LabeledContent("Daily P&L") {
                    let pnl = live?.fresh == true ? live?.daily_pnl : nil
                    Text(money(pnl)).monospacedDigit()
                        .foregroundStyle(pnl.map { $0 > 0 ? gain : ($0 < 0 ? loss : Color.secondary) } ?? Color.secondary)
                }
                Text("Account base currency · IBKR daily P&L").font(.caption).foregroundStyle(.secondary)
                if let liveError { NoticeText(liveError).font(.caption).foregroundStyle(.orange) }
            }
            Section {
                Button("Refresh") { revision += 1 }
                Text("History: compounded daily IBKR TWR. SPX and NDX: FRED daily price indices, excluding reinvested dividends. Intraday estimate uses daily P&L / last reported NAV; deposits, withdrawals and IB reset times may affect comparability. Final returns follow the next Flex report.")
                    .font(.footnote).foregroundStyle(.secondary)
            }
        }.navigationTitle("Performance")
            .onAppear { visible = true }.onDisappear { visible = false }
            .task(id: context) {
                guard active else { return }
                let requestedContext = context
                let cacheKey = store.address + "|" + period
                history = store.demo ? nil : store.performanceHistoryCache[cacheKey].flatMap { try? JSONDecoder().decode(PerformanceHistory.self, from: $0) }
                error = nil
                guard !store.demo else { error = "Performance requires a live backend with Flex history."; return }
                loading = true
                defer { if context == requestedContext { loading = false } }
                for _ in 0..<45 {
                    do {
                        let (data, status) = try await read("history", query: [URLQueryItem(name: "period", value: period)])
                        if status == 202 { try await Task.sleep(for: .seconds(2)); continue }
                        let value = try JSONDecoder().decode(PerformanceHistory.self, from: data)
                        try Task.checkCancellation()
                        guard context == requestedContext else { return }
                        store.performanceHistoryCache[cacheKey] = data; history = value
                        if value.refreshing == true { try await Task.sleep(for: .seconds(2)); continue }
                        return
                    } catch { if !Task.isCancelled, context == requestedContext { self.error = connectionMessage(error) }; return }
                }
                if context == requestedContext { error = "History is still generating. Try Refresh shortly." }
            }
            .task(id: "live-\(active)-\(store.demo)-\(store.address)") {
                live = nil; liveError = nil
                guard active, !store.demo else { return }
                let requestedAddress = store.address
                while !Task.isCancelled {
                    do {
                        let (data, _) = try await read("live")
                        let next = try JSONDecoder().decode(PerformanceLive.self, from: data)
                        try Task.checkCancellation()
                        guard active, !store.demo, store.address == requestedAddress else { return }
                        live = next; liveError = nil
                    } catch { if Task.isCancelled || !active || store.address != requestedAddress { return }; live = nil; liveError = connectionMessage(error) }
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

// Selection is local to this overlay: finger movement does not rebuild chart marks.
private struct PerformanceSelectionOverlay: View {
    let points: [PerformancePoint]
    let proxy: ChartProxy
    let gain: Color
    let loss: Color
    let benchmarks: BenchmarkSelection
    @State private var selectedIndex: Int?
    @State private var touch: CGPoint = .zero
    @State private var interactionRevision = 0

    private func select(_ location: CGPoint, plot: CGRect) {
        let x = min(max(location.x - plot.minX, 0), plot.width)
        guard let date: Date = proxy.value(atX: x), !points.isEmpty else { return }
        var lower = 0
        var upper = points.count
        while lower < upper {
            let middle = (lower + upper) / 2
            if points[middle].day < date { lower = middle + 1 } else { upper = middle }
        }
        let right = min(lower, points.count - 1)
        let left = max(right - 1, 0)
        let index = abs(points[left].day.timeIntervalSince(date)) < abs(points[right].day.timeIntervalSince(date)) ? left : right
        if selectedIndex != index { selectedIndex = index }
        touch = location
        interactionRevision &+= 1
    }
    var body: some View {
        GeometryReader { geometry in
            if let anchor = proxy.plotFrame {
                let plot = geometry[anchor]
                ZStack(alignment: .topLeading) {
                    Rectangle().fill(.clear).contentShape(Rectangle())
                        .gesture(DragGesture(minimumDistance: 0)
                            .onChanged { select($0.location, plot: plot) }
                            .onEnded { _ in interactionRevision &+= 1 })
                    if let index = selectedIndex, points.indices.contains(index) {
                        let point = points[index]
                        let x = plot.minX + (proxy.position(forX: point.day) ?? 0)
                        Path { path in
                            path.move(to: CGPoint(x: x, y: plot.minY))
                            path.addLine(to: CGPoint(x: x, y: plot.maxY))
                        }.stroke(.secondary, style: StrokeStyle(lineWidth: 1, dash: [3, 3])).allowsHitTesting(false)
                        marker(point.portfolio, color: point.portfolio >= 0 ? gain : loss, x: x, plot: plot)
                        if benchmarks.showsSPX {
                        marker(point.spx, color: PerformanceColors.spx, x: x, plot: plot)
                        }
                        if benchmarks.showsNQ100 {
                        marker(point.nq100, color: .orange, x: x, plot: plot)
                        }
                        let width = min(CGFloat(150), plot.width)
                        let preferredX = x + 16 + width <= plot.maxX ? x + 16 : x - width - 16
                        let left = max(plot.minX, min(preferredX, plot.maxX - width))
                        let top = max(plot.minY, min(touch.y - 120, plot.maxY - 108))
                        tooltip(point).frame(width: width).offset(x: left, y: top)
                    }
                }
                .allowsHitTesting(true)
                .transaction { $0.animation = nil }
            }
        }
        .task(id: interactionRevision) {
            guard selectedIndex != nil else { return }
            do {
                try await Task.sleep(for: .seconds(3))
                try Task.checkCancellation()
                selectedIndex = nil
            } catch { /* New input or leaving the chart cancels the pending hide. */ }
        }
    }
    private func marker(_ value: Double, color: Color, x: CGFloat, plot: CGRect) -> some View {
        Circle().fill(color).frame(width: 7, height: 7)
            .position(x: x, y: plot.minY + (proxy.position(forY: value) ?? 0))
            .allowsHitTesting(false)
    }
    private func tooltip(_ point: PerformancePoint) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(point.date).fontWeight(.semibold)
            tooltipRow("Portfolio", value: point.portfolio, color: point.portfolio >= 0 ? gain : loss)
            if benchmarks.showsSPX {
            tooltipRow("SPX", value: point.spx, color: PerformanceColors.spx)
            }
            if benchmarks.showsNQ100 {
            tooltipRow("NDX", value: point.nq100, color: .orange)
            }
        }
        .font(.caption).monospacedDigit().padding(10)
        .allowsHitTesting(false)
    }
    private func tooltipRow(_ title: String, value: Double, color: Color) -> some View {
        HStack {
            Text(LocalizedStringKey(title))
            Spacer()
            Text(String(format: "%+.2f%%", value)).fontWeight(.semibold)
        }.foregroundStyle(color)
    }
}
