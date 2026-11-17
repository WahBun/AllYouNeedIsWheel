import SwiftUI
import Observation

struct PerformanceAnalytics: Decodable {
    struct CommissionTotal: Decodable, Identifiable {
        let currency: String
        let total: Double?
        let missing: Int
        var id: String { currency }
    }
    struct Total: Decodable {
        let executions: Int
        let book_entries: Int?
        let realized_pnl: Double?
        let missing_pnl: Int
    }
    struct Day: Decodable, Identifiable {
        let date: String
        let executions: Int
        let book_entries: Int?
        let realized_pnl: Double?
        let missing_pnl: Int
        var id: String { date }
        var activityCount: Int { executions + (book_entries ?? 0) }
    }
    struct Contribution: Decodable, Identifiable {
        let ticker: String
        let executions: Int
        let book_entries: Int?
        let realized_pnl: Double?
        var id: String { ticker }
    }
    struct Execution: Decodable, Identifiable {
        let id: String
        let ticker: String
        let option_type: String
        let expiration: String?
        let strike: Double?
        let action: String
        let quantity: Double
        let avg_fill_price: Double
        let fill_time: String
        let currency: String
        let commission: Double?
        let commission_currency: String
        let realized_pnl: Double?
        let intent: String?
        let record_type: String?
        var contract: String {
            guard let expiration, let strike, option_type == "PUT" || option_type == "CALL" else { return ticker }
            return "\(ticker) · \(expiration.prefix(4))-\(expiration.dropFirst(4).prefix(2))-\(expiration.suffix(2)) · \(strike.formatted())\(option_type == "PUT" ? "P" : "C")"
        }
        var time: String {
            guard let stamp = ISO8601DateFormatter().date(from: fill_time) else { return "—" }
            let formatter = DateFormatter()
            formatter.timeZone = TimeZone(identifier: "America/New_York")
            formatter.dateFormat = "HH:mm:ss"
            return formatter.string(from: stamp)
        }
    }
    struct Bucket: Decodable, Identifiable {
        let period: String
        let executions: Int
        let book_entries: Int?
        let realized_pnl: Double?
        var displayAmount: Double? { executions + (book_entries ?? 0) == 0 ? nil : realized_pnl }
        var id: String { period }
    }
    struct Coverage: Decodable {
        let first: String
        let through: String
    }
    let scope: String?
    let year: String?
    let periods: [Bucket]?
    let coverage: [Coverage]?
    let account_opened: String?
    let period_commissions: [CommissionTotal]?
    let month: String
    let months: [String]
    let currency: String
    let currencies: [String]
    let days: [Day]
    let summary: Total
    let monthly_commissions: [CommissionTotal]?
    let daily_commissions: [CommissionTotal]?
    let contributions: [Contribution]
    let trades: [Execution]
    let trade_count: Int
    let next_offset: Int?
    let report_through: String?
    let report_version: String?
    let warning: String?
    let refreshing: Bool

    static func activityLabel(_ executions: Int, _ books: Int?, locale: Locale = Locale(identifier: "en")) -> String {
        let count = books ?? 0
        let fills = String(format: localizedLabel(executions == 1 ? "%lld execution" : "%lld executions", locale: locale), executions)
        return count == 0 ? fills : fills + " · " + String(format: localizedLabel(count == 1 ? "%lld book entry" : "%lld book entries", locale: locale), count)
    }
}

// Owns only report reads. No connection to TradingSession mutation or quote loops.
@MainActor @Observable final class PerformanceAnalyticsModel {
    private(set) var report: PerformanceAnalytics?
    private(set) var trades: [PerformanceAnalytics.Execution] = []
    private(set) var loading = false
    private(set) var error: String?
    private var requestID = UUID()
    private var loadedContext = ""

    func load(base: String, epoch: String?, month: String = "", currency: String = "",
              scope: String = "month", year: String = "", day: String? = nil, offset: Int = 0, refresh: Bool = false,
              session: URLSession = .shared) async {
        let token = UUID(); requestID = token
        loading = true; error = nil
        let context = "\(base)|\(epoch ?? "")|\(scope)|\(year)|\(month)|\(currency)|\(day ?? "")"
        if context != loadedContext { report = nil; trades = []; loadedContext = context }
        defer { if requestID == token { loading = false } }
        for attempt in 0..<15 {
            do {
                var query = [URLQueryItem(name: "offset", value: String(offset))]
                query.append(URLQueryItem(name: "scope", value: scope))
                if !year.isEmpty { query.append(URLQueryItem(name: "year", value: year)) }
                if !month.isEmpty { query.append(URLQueryItem(name: "month", value: month)) }
                if !currency.isEmpty { query.append(URLQueryItem(name: "currency", value: currency)) }
                if let day { query.append(URLQueryItem(name: "day", value: day)) }
                if refresh && attempt == 0 { query.append(URLQueryItem(name: "refresh", value: "1")) }
                let (data, status) = try await PerformanceRequest.read(base: base, path: "analytics", query: query, session: session, epoch: epoch)
                try Task.checkCancellation()
                guard requestID == token else { return }
                if status == 202 { try await Task.sleep(for: .seconds(2)); continue }
                let next = try JSONDecoder().decode(PerformanceAnalytics.self, from: data)
                guard (next.scope ?? "month") == scope else {
                    error = "Update the Wheel backend to view this period."
                    return
                }
                if offset > 0 && next.report_version != report?.report_version {
                    error = "The report changed. Refresh to load the updated executions."
                    return
                }
                report = next
                if offset == 0 { trades = next.trades }
                else {
                    let known = Set(trades.map(\.id))
                    trades += next.trades.filter { !known.contains($0.id) }
                }
                if !next.refreshing || offset > 0 { return }
                try await Task.sleep(for: .seconds(2))
            } catch {
                guard requestID == token, !Task.isCancelled else { return }
                self.error = connectionMessage(error)
                return
            }
        }
        error = "Report refresh is still pending. Try Refresh shortly."
    }
}

enum AnalyticsCalendar {
    static var calendar: Calendar {
        var value = Calendar(identifier: .gregorian)
        value.timeZone = TimeZone(secondsFromGMT: 0)!
        return value
    }
    static func slots(month: String) -> [String?] {
        let parts = month.split(separator: "-").compactMap { Int($0) }
        guard parts.count == 2, let first = calendar.date(from: DateComponents(year: parts[0], month: parts[1], day: 1)),
              let days = calendar.range(of: .day, in: .month, for: first) else { return [] }
        // Monday is column zero. A month starting on a weekend begins at the following Monday.
        let firstColumn = (calendar.component(.weekday, from: first) + 5) % 7
        let leadingBlanks = firstColumn < 5 ? firstColumn : 0
        let weekdays = days.filter { (firstColumn + $0 - 1) % 7 < 5 }
        return Array(repeating: nil, count: leadingBlanks) + weekdays.map { String(format: "%@-%02d", month, $0) }
    }
    static func displayedPnL(for day: PerformanceAnalytics.Day?) -> Double? {
        if day?.activityCount == 0, day?.realized_pnl == 0 {
            return nil
        }
        return day?.realized_pnl
    }
    static func monthNames(_ locale: Locale) -> [String] {
        var calendar = Calendar(identifier: .gregorian)
        calendar.locale = locale
        return calendar.shortStandaloneMonthSymbols
    }
    static func weekdays(locale: Locale) -> [String] {
        let formatter = DateFormatter(); formatter.locale = locale
        return Array(formatter.shortStandaloneWeekdaySymbols.dropFirst().prefix(5))
    }
    static func amount(_ number: Double?, currency: String) -> String {
        guard let number else { return "—" }
        return number.formatted(.currency(code: currency))
    }
}

struct PerformanceAnalyticsView: View {
    @Environment(WheelStore.self) private var store
    var body: some View {
        Group {
            if store.demo {
                ContentUnavailableView("Report analytics", systemImage: "calendar", description: Text("Connect to your account to review completed Flex reports."))
            } else {
                PerformanceAnalyticsScreen(base: store.address, epoch: store.trading.accountEpoch)
                    .id("\(store.address)|\(store.trading.accountEpoch ?? "")")
            }
        }.navigationTitle("Trade review")
    }
}

enum ReviewPeriod: Hashable {
    case month(String)
    case year(String)
    case all

    static var currentMonth: String {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "America/New_York")!
        let parts = calendar.dateComponents([.year, .month], from: Date())
        return String(format: "%04d-%02d", parts.year!, parts.month!)
    }
    var scope: String {
        switch self { case .month: "month"; case .year: "year"; case .all: "all" }
    }
    var month: String { if case let .month(value) = self { value } else { "" } }
    var year: String { if case let .year(value) = self { value } else { "" } }
    var title: String {
        switch self { case .month: "Month"; case .year: "Year"; case .all: "All time" }
    }
    var gridTitle: String {
        switch self { case .month: "P&L calendar"; case .year: "Monthly P&L"; case .all: "Yearly P&L" }
    }
    var feeTitle: String {
        switch self { case .month: "Monthly commissions"; case .year: "Annual commissions"; case .all: "Total commissions" }
    }
}

struct PerformanceAnalyticsScreen: View {
    let base: String
    let epoch: String?
    @Environment(\.scenePhase) private var phase
    @Environment(\.locale) private var locale
    @State private var model = PerformanceAnalyticsModel()
    @State var period: ReviewPeriod = .month(ReviewPeriod.currentMonth)
    @State private var parents: [ReviewPeriod] = []
    @State private var currency = ""
    @State private var revision = 0
    @State private var pendingRefresh = false
    @State private var visible = false
    @State private var selectedDate: String?
    private var currentReport: PerformanceAnalytics? {
        guard let report = model.report, (report.scope ?? "month") == period.scope,
              (period.month.isEmpty || period.month == report.month),
              (period.year.isEmpty || period.year == report.year),
              (currency.isEmpty || currency == report.currency) else { return nil }
        return report
    }
    private var context: String { "\(visible)-\(phase == .active)-\(period)-\(currency)-\(revision)" }

    var body: some View {
        List {
            Section {
                periodPicker
                if let report = currentReport {
                    if report.currencies.count > 1 {
                        Picker("Currency", selection: Binding(get: { currency.isEmpty ? report.currency : currency }, set: { currency = $0 })) {
                            ForEach(report.currencies, id: \.self) { Text(verbatim: $0).tag($0) }
                        }
                    }
                    VStack(alignment: .leading, spacing: 5) {
                        HStack(spacing: 4) {
                            Text("Realized P&L")
                            PerformanceInfoButton(topic: .pnl)
                        }.font(.subheadline).foregroundStyle(.secondary)
                        AnalyticsAmount(value: report.report_through == nil ? nil : report.summary.realized_pnl, currency: report.currency)
                            .font(.largeTitle.bold()).minimumScaleFactor(0.6).lineLimit(1)
                        Text(verbatim: "\(PerformanceAnalytics.activityLabel(report.summary.executions, report.summary.book_entries, locale: locale)) · \(report.currency)")
                            .font(.caption).foregroundStyle(.secondary)
                    }.padding(.vertical, 4)
                    AnalyticsReportNote(report: report)
                }
            }
            if let report = currentReport {
                let monthly = period.scope == "month"
                AnalyticsCommissionsSection(title: period.feeTitle,
                                             totals: monthly ? report.monthly_commissions : report.period_commissions, periodSummary: !monthly)
                Section {
                    Group {
                        if monthly {
                            AnalyticsCalendarGrid(report: report) { selectedDate = $0 }
                        } else {
                            AnalyticsPeriodGrid(report: report, period: period) { child in
                                parents.append(period)
                                period = child
                                currency = report.currency
                            }
                        }
                    }.listRowInsets(EdgeInsets(top: 12, leading: 8, bottom: 12, trailing: 8))
                } header: {
                    HStack(spacing: 4) {
                        Text(LocalizedStringKey(period.gridTitle))
                        if monthly { PerformanceInfoButton(topic: .calendar) }
                        if !parents.isEmpty {
                            Spacer()
                            Button("Back") { if let parent = parents.popLast() { period = parent } }
                        }
                    }.textCase(nil)
                }
                Section {
                    if report.contributions.isEmpty { Text("No executions in this report period.").foregroundStyle(.secondary) }
                    ForEach(report.contributions) { row in
                        HStack {
                            VStack(alignment: .leading, spacing: 4) {
                                Text(verbatim: row.ticker).fontWeight(.semibold)
                                Text(verbatim: PerformanceAnalytics.activityLabel(row.executions, row.book_entries, locale: locale)).font(.caption).foregroundStyle(.secondary)
                            }
                            Spacer(minLength: 8)
                            AnalyticsAmount(value: row.realized_pnl, currency: report.currency).lineLimit(1).minimumScaleFactor(0.7)
                        }.padding(.vertical, 3)
                    }
                } header: {
                    HStack(spacing: 4) { Text("Symbol contributions"); PerformanceInfoButton(topic: .contributions, forLongerPeriod: !monthly) }.textCase(nil)
                }
            }
            if model.loading { Section { ProgressView("Loading report…") } }
            if let error = model.error { Section { NoticeText(error).foregroundStyle(.orange) } }
            Section { Button("Refresh") { pendingRefresh = true; revision += 1 }.disabled(model.loading) }
        }
        .navigationDestination(item: $selectedDate) { date in
            if let report = currentReport {
                PerformanceExecutionView(base: base, epoch: epoch, month: report.month, currency: report.currency, day: date)
            }
        }
        .onAppear { visible = true }.onDisappear { visible = false }
        .task(id: context) {
            guard visible, phase == .active else { return }
            let refresh = pendingRefresh
            pendingRefresh = false
            await model.load(base: base, epoch: epoch, month: period.month, currency: currency,
                             scope: period.scope, year: period.year, refresh: refresh)
        }
    }

    private var periodPicker: some View {
        let current = ReviewPeriod.currentMonth
        let months = Set((model.report?.months ?? []) + [current, period.month]).filter { !$0.isEmpty }.sorted(by: >)
        let years = Set(months.map { String($0.prefix(4)) } + [period.year]).filter { !$0.isEmpty }.sorted(by: >)
        let month = period.month.isEmpty ? (months.first { $0.hasPrefix(period.year) } ?? current) : period.month
        let year = period.year.isEmpty ? String(month.prefix(4)) : period.year
        return HStack {
            Menu {
                Button("Month") { select(.month(month)) }
                Button("Year") { select(.year(year)) }
                Button("All time") { select(.all) }
            } label: {
                HStack(spacing: 5) { Text(LocalizedStringKey(period.title)); Image(systemName: "chevron.down").font(.caption2) }
            }.accessibilityIdentifier("review-scope")
            Spacer()
            if period != .all {
                Picker("Selected period", selection: Binding(get: { period.month.isEmpty ? year : month },
                                                            set: { select(period.month.isEmpty ? .year($0) : .month($0)) })) {
                    ForEach(period.month.isEmpty ? years : months, id: \.self) { Text(verbatim: $0).tag($0) }
                }.labelsHidden().pickerStyle(.menu).accessibilityIdentifier("review-period")
            }
        }
    }

    private func select(_ next: ReviewPeriod) {
        guard next != period else { return }
        parents.removeAll()
        period = next
    }

}

struct AnalyticsReportNote: View {
    let report: PerformanceAnalytics
    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            if let ranges = report.coverage, report.scope != "month", report.scope != nil {
                ForEach(ranges, id: \.first) { range in Text("Reported \(range.first) – \(range.through)") }
                if ranges.isEmpty { Text("No report coverage for this period") }
                if let opened = report.account_opened { Text("Account opened \(opened)") }
            } else if let through = report.report_through { Text("Flex report through \(through)") }
            else { Text("No report coverage for this month") }
            if report.summary.missing_pnl > 0 { Text("Some executions have no reported realized P&L. Totals remain unavailable until the report is complete.").foregroundStyle(.orange) }
            if report.refreshing { Text("Report refresh pending").foregroundStyle(.orange) }
            if let warning = report.warning { NoticeText(warning).foregroundStyle(.orange) }
        }.font(.caption).foregroundStyle(.secondary)
    }
}

enum PerformanceHelpTopic: String {
    case performance = "Performance"
    case commissions = "Commissions"
    case pnl = "Realized P&L"
    case calendar = "P&L calendar"
    case contributions = "Symbol contributions"
    case dailyPnl = "Daily P&L"
    case history = "Performance history"
    var explanation: String {
        switch self {
        case .performance:
            PerformanceHelpTopic.dailyPnl.explanation + "\n\n" + PerformanceHelpTopic.history.explanation
        case .commissions:
            "Total trading commissions reported by IBKR for this account and the selected month or day, across all instruments and trade currencies. The P&L currency filter does not change these totals.\n\nAmounts use the commission currency; currencies are not converted or combined. Positive values are costs; credits reduce the total. Missing amounts appear as a dash, not zero. Dates follow the report's trade date.\n\nRealized P&L already includes commissions; these totals are not deducted again. Market data subscriptions and other account charges are separate and are not included. These totals do not establish eligibility for a subscription fee waiver."
        case .dailyPnl:
            "Account base currency · IBKR daily P&L.\n\nDaily %: estimate using last reported NAV."
        case .history:
            "History: compounded daily IBKR TWR. SPX and NDX: IBKR daily closes with retained FRED history as fallback, excluding reinvested dividends.\n\nIntraday estimate uses daily P&L / last reported NAV; deposits, withdrawals and IB reset times may affect comparability. Final returns follow the next Flex report."
        case .pnl:
            "Reported realized P&L, not live account P&L. Commissions are already included; opening premium is not realized profit.\n\nTotals include reported executions and recognized assignment, exercise and expiration book entries. These entries are counted separately from exchange executions.\n\nTotals cover reported dates only. Earlier history appears when available in a Flex report.\n\nCurrencies are shown separately; no FX conversion is applied."
        case .calendar:
            "Tap a reported day to review executions and book entries.\n\nDates follow the IBKR trade date. Overnight futures and FX executions may occur on the previous evening."
        case .contributions:
            "Ranked by absolute realized P&L for the selected month and currency.\n\nStock and option executions share their underlying symbol. This is not total portfolio return."
        }
    }
}

struct AnalyticsCommissionsSection: View {
    let title: String
    let totals: [PerformanceAnalytics.CommissionTotal]?
    var periodSummary = false
    var body: some View {
        Section {
            if let totals {
                if totals.isEmpty { Text("No commissions reported").foregroundStyle(.secondary) }
                ForEach(totals) { row in
                    LabeledContent {
                        Text(verbatim: AnalyticsCalendar.amount(row.total, currency: row.currency))
                            .monospacedDigit().foregroundStyle(.secondary)
                    } label: {
                        if row.currency.isEmpty { Text("Unspecified currency") } else { Text(verbatim: row.currency) }
                    }
                    if row.missing > 0 { Text("Some commission amounts are missing.").font(.caption).foregroundStyle(.secondary) }
                }
            } else { Text("—").foregroundStyle(.secondary) }
        } header: {
            HStack(spacing: 4) { Text(LocalizedStringKey(title)); PerformanceInfoButton(topic: .commissions, forLongerPeriod: periodSummary) }.textCase(nil)
        }
    }
}

struct PerformanceInfoButton: View {
    let topic: PerformanceHelpTopic
    var forLongerPeriod = false
    @State private var presented = false
    @Environment(\.locale) private var locale
    var body: some View {
        Button { presented = true } label: {
            Image(systemName: "info.circle").frame(width: 32, height: 32).contentShape(Rectangle())
        }.buttonStyle(.plain).foregroundStyle(.secondary)
            .accessibilityLabel(Text("About \(localizedLabel(topic.rawValue, locale: locale))"))
            .sheet(isPresented: $presented) {
                NavigationStack {
                    Form {
                        if topic == .performance {
                            Section { NoticeText(PerformanceHelpTopic.dailyPnl.explanation) } header: { Text("Daily P&L") }
                            Section { NoticeText(PerformanceHelpTopic.history.explanation) } header: { Text("Performance history") }
                        } else if forLongerPeriod && topic == .commissions {
                            Text("Account trading commissions for the reported dates in this period, grouped by fee currency. Credits reduce costs. Commissions are already included in realized P&L.")
                        } else if forLongerPeriod && topic == .contributions {
                            Text("Symbols are ranked by absolute realized P&L for the selected period and currency. Stock and option activity share their underlying symbol.")
                        } else { NoticeText(topic.explanation) }
                    }
                        .navigationTitle(LocalizedStringKey(topic.rawValue)).navigationBarTitleDisplayMode(.inline)
                        .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { presented = false } } }
                }.presentationDetents([.medium, .large])
            }
    }
}

struct AnalyticsAmount: View {
    let value: Double?
    let currency: String
    @Environment(\.customPalette) private var palette
    @Environment(\.colorScheme) private var scheme
    var color: Color {
        guard let value, value != 0 else { return .secondary }
        return palette.color(value > 0 ? "gain" : "loss", scheme: scheme, fallback: value > 0 ? FinancialColors.gain : FinancialColors.loss)
    }
    var body: some View {
        Text(verbatim: AnalyticsCalendar.amount(value, currency: currency)).foregroundStyle(color).monospacedDigit()
    }
}

struct AnalyticsPeriodGrid: View {
    let report: PerformanceAnalytics
    let period: ReviewPeriod
    let onSelect: (ReviewPeriod) -> Void
    @Environment(\.customPalette) private var palette
    @Environment(\.colorScheme) private var scheme
    @Environment(\.locale) private var locale

    var body: some View {
        let annual = period.scope == "year"
        let buckets = Dictionary(uniqueKeysWithValues: (report.periods ?? []).map { ($0.period, $0) })
        let keys = annual ? (1...12).map { String(format: "%@-%02d", period.year, $0) } : buckets.keys.sorted(by: >)
        let names = AnalyticsCalendar.monthNames(locale)
        LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 5), count: annual ? 3 : 2), spacing: 5) {
            ForEach(keys, id: \.self) { key in
                let amount = buckets[key]?.displayAmount
                let value = amount ?? 0
                let color: Color = value == 0 ? .secondary : palette.color(value > 0 ? "gain" : "loss", scheme: scheme,
                                                                           fallback: value > 0 ? FinancialColors.gain : FinancialColors.loss)
                let label = annual ? names[(Int(key.suffix(2)) ?? 1) - 1] : key
                Button { onSelect(annual ? .month(key) : .year(key)) } label: {
                    VStack(spacing: 5) {
                        Text(verbatim: label).font(.caption.weight(.medium))
                        Text(verbatim: amount?.formatted(.number.notation(.compactName).precision(.fractionLength(0...1))) ?? "—")
                            .font(.caption.weight(.semibold)).monospacedDigit()
                    }.frame(maxWidth: .infinity, minHeight: 47)
                        .background(color.opacity(buckets[key] == nil ? 0.04 : 0.13), in: RoundedRectangle(cornerRadius: 6))
                        .foregroundStyle(color).contentShape(Rectangle())
                }.buttonStyle(.plain).disabled(buckets[key] == nil)
                    .accessibilityLabel("\(key), \(AnalyticsCalendar.amount(amount, currency: report.currency))")
                    .accessibilityIdentifier("analytics-period-\(key)")
            }
        }
    }
}

struct AnalyticsCalendarGrid: View {
    @Environment(\.locale) private var locale
    let report: PerformanceAnalytics
    let onSelect: (String) -> Void
    @Environment(\.customPalette) private var palette
    @Environment(\.colorScheme) private var scheme
    var body: some View {
        let slots = AnalyticsCalendar.slots(month: report.month)
        let weekdays = AnalyticsCalendar.weekdays(locale: locale)
        let byDate = Dictionary(uniqueKeysWithValues: report.days.map { ($0.date, $0) })
        VStack(spacing: 6) {
            HStack(spacing: 2) {
                ForEach(Array(weekdays.enumerated()), id: \.offset) { _, title in
                    Text(verbatim: title).font(.caption2).foregroundStyle(.secondary).frame(maxWidth: .infinity)
                }
            }
            LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 2), count: weekdays.count), spacing: 5) {
                ForEach(slots.indices, id: \.self) { index in
                    if let date = slots[index] {
                        let day = byDate[date]
                        let pnl = AnalyticsCalendar.displayedPnL(for: day)
                        Button { onSelect(date) } label: {
                            VStack(spacing: 5) {
                                Text(verbatim: String(Int(date.suffix(2)) ?? 0)).font(.caption.weight(.medium)).lineLimit(1).minimumScaleFactor(0.7)
                                Text(verbatim: pnl.map { $0.formatted(.number.notation(.compactName).precision(.fractionLength(0...1))) } ?? "—")
                                    .font(.system(size: 10, weight: .semibold)).lineLimit(1).minimumScaleFactor(0.6)
                            }
                            .frame(maxWidth: .infinity, minHeight: 47)
                            .background(tone(day).opacity(day?.activityCount == 0 ? 0.04 : 0.13), in: RoundedRectangle(cornerRadius: 6))
                            .foregroundStyle(tone(day))
                            .contentShape(Rectangle())
                        }.buttonStyle(.plain).disabled(day == nil)
                        .accessibilityIdentifier("analytics-day-\(date)")
                        .accessibilityLabel("\(date), \(AnalyticsCalendar.amount(pnl, currency: report.currency)), \(PerformanceAnalytics.activityLabel(day?.executions ?? 0, day?.book_entries, locale: locale))")
                    } else { Color.clear.frame(height: 47) }
                }
            }
        }
    }
    private func tone(_ day: PerformanceAnalytics.Day?) -> Color {
        guard let value = day?.realized_pnl, value != 0 else { return .secondary }
        return palette.color(value > 0 ? "gain" : "loss", scheme: scheme, fallback: value > 0 ? FinancialColors.gain : FinancialColors.loss)
    }
}

struct PerformanceExecutionView: View {
    let base: String
    let epoch: String?
    let month: String
    let currency: String
    let day: String
    @Environment(\.scenePhase) private var phase
    @Environment(\.locale) private var locale
    @State private var model = PerformanceAnalyticsModel()
    @State private var offset = 0
    @State private var revision = 0
    var body: some View {
        List {
            if let report = model.report {
                Section {
                    if let total = report.days.first(where: { $0.date == day }) {
                        LabeledContent("Realized P&L") { AnalyticsAmount(value: total.realized_pnl, currency: currency) }
                        LabeledContent("Executions", value: String(total.executions))
                        if let books = total.book_entries, books > 0 { LabeledContent("Book entries", value: String(books)) }
                    }
                    Text("IBKR Flex · trade date · times in New York").font(.caption).foregroundStyle(.secondary)
                    if let warning = report.warning { NoticeText(warning).foregroundStyle(.orange) }
                }
                AnalyticsCommissionsSection(title: "Daily commissions", totals: report.daily_commissions)
                if report.trade_count == 0 { Text("No activity for this date and currency.").foregroundStyle(.secondary) }
                ForEach(model.trades) { trade in
                    Section {
                        VStack(alignment: .leading, spacing: 6) {
                            Text(verbatim: trade.contract).fontWeight(.semibold).fixedSize(horizontal: false, vertical: true)
                            if let kind = trade.record_type, kind != "Execution" {
                                Text("\(localizedLabel(kind, locale: locale)) · Book entry").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                            }
                            Text(verbatim: "\(localizedLabel(trade.action, locale: locale)) \(trade.quantity.formatted()) @ \(trade.avg_fill_price.formatted(.number.precision(.fractionLength(0...6)))) \(trade.currency)")
                            Text(verbatim: "\(trade.time) ET · \(localizedLabel(trade.intent ?? "Execution", locale: locale))").font(.caption).foregroundStyle(.secondary)
                        }
                        LabeledContent("Realized P&L") { AnalyticsAmount(value: trade.realized_pnl, currency: trade.currency) }
                        LabeledContent("Commission", value: AnalyticsCalendar.amount(trade.commission, currency: trade.commission_currency))
                    }
                }
                if let next = report.next_offset {
                    Button("Load more activity") { offset = next }.disabled(model.loading || model.error != nil)
                }
            }
            if model.loading { ProgressView("Loading activity…") }
            if let error = model.error { NoticeText(error).foregroundStyle(.orange) }
            Button("Refresh") { offset = 0; revision += 1 }.disabled(model.loading)
        }.navigationTitle(day).navigationBarTitleDisplayMode(.inline)
            .task(id: "\(phase == .active)-\(offset)-\(revision)") {
                guard phase == .active else { return }
                await model.load(base: base, epoch: epoch, month: month, currency: currency, day: day, offset: offset, refresh: revision > 0 && offset == 0)
            }
    }
}
