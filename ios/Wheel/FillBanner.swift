import SwiftUI
import Observation

struct FillNotice: Identifiable {
    let id = UUID()
    var order: Order
    var demo = false
    var filled: Double { order.filledQuantity ?? 0 }
    var complete: Bool { order.ib_status?.lowercased() == "filled" || order.status.lowercased() == "executed" || (order.quantity.map { $0 > 0 && filled >= $0 } ?? false) }
    var quantityLabel: String { "\(filled.formatted())/\(order.quantity?.formatted() ?? "—")" }
    var contractLabel: String { "\(order.name) · \(order.fill_action ?? order.action ?? "—") · \(money(order.strike)) \(order.option_type ?? "")" }
    static func sample(_ filled: Double) -> FillNotice {
        FillNotice(order: Order(id: 0, ticker: "TSLL", action: "SELL", option_type: "PUT", strike: 9,
            expiration: "20261016", quantity: 2, status: filled == 2 ? "executed" : "processing",
            filled: filled, avg_fill_price: 0.48), demo: true)
    }
}

/// Monotonic quantities, keyed by both local and broker identities. No disappearance inference.
struct FillTracker {
    private var quantities: [String: Double] = [:]
    private var ready = false
    private var started: Date
    init(started: Date = Date()) { self.started = started }
    mutating func ingest(_ orders: [Order]) -> [FillNotice] {
        var notices: [FillNotice] = []
        for order in orders {
            let keys = ["id:\(order.id)"] + (order.perm_id.flatMap { $0 > 0 ? "perm:\($0)" : nil }.map { [$0] } ?? [])
            let previous = keys.compactMap { quantities[$0] }.max()
            let filled = order.filledQuantity ?? 0
            guard filled.isFinite, filled >= 0 else { continue }
            // Unseen historical rows must not announce late metadata enrichment.
            let parser = ISO8601DateFormatter()
            let stamp = order.fill_time.flatMap { value -> Date? in
                if let date = parser.date(from: value) { return date }
                parser.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
                return parser.date(from: value)
            }
            let recent = stamp.map { $0 >= started } ?? false
            if ready, filled > (previous ?? 0), previous != nil || recent {
                notices.append(FillNotice(order: order))
            }
            for key in keys { quantities[key] = max(previous ?? 0, filled) }
        }
        ready = true
        return notices
    }
}

@MainActor @Observable
final class FillPreview {
    var notice: FillNotice?
    var detail: FillNotice?
    private var queue: [FillNotice] = []
    private var task: Task<Void, Never>?
    func enqueue(_ notices: [FillNotice]) { queue.append(contentsOf: notices); advance() }
    func updateMetadata(_ orders: [Order]) {
        func updated(_ value: FillNotice) -> FillNotice {
            guard !value.demo, let latest = orders.first(where: {
                $0.id == value.order.id && $0.filledQuantity == value.order.filledQuantity
            }) else { return value }
            var copy = value; copy.order = latest; return copy
        }
        if let value = notice { notice = updated(value) }
        if let value = detail { detail = updated(value) }
        queue = queue.map(updated)
    }
    func advance() {
        if notice == nil, detail == nil, !queue.isEmpty { notice = queue.removeFirst() }
    }
    func dismiss(_ id: UUID) {
        if notice?.id == id { notice = nil; advance() }
    }
    func clear() { task?.cancel(); task = nil; notice = nil; detail = nil; queue = [] }
    func start() {
        clear()
        task = Task { [weak self] in
            do {
                try await Task.sleep(for: .seconds(3))
                self?.enqueue([.sample(1)])
                try await Task.sleep(for: .seconds(8))
                self?.enqueue([.sample(2)])
            } catch { }
        }
    }
}

struct FillBannerOverlay: ViewModifier {
    let preview: FillPreview
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    func body(content: Content) -> some View {
        @Bindable var preview = preview
        content.overlay(alignment: .top) {
            if let notice = preview.notice {
                HStack(alignment: .top, spacing: 12) {
                    Button {
                        preview.detail = notice
                        preview.dismiss(notice.id)
                    } label: {
                        HStack(alignment: .top, spacing: 12) {
                            Image(systemName: notice.complete ? "checkmark.circle.fill" : "circle.lefthalf.filled")
                                .font(.title2).foregroundStyle(.teal)
                            VStack(alignment: .leading, spacing: 5) {
                                HStack {
                                    Text(LocalizedStringKey(notice.complete ? "Order filled" : "Partially filled")).font(.headline)
                                    Spacer(minLength: 4)
                                    if notice.demo { Text("Demo").font(.caption2.bold()).foregroundStyle(.secondary) }
                                }
                                Text(notice.contractLabel).font(.subheadline.weight(.semibold))
                                Text("\(notice.order.expiration ?? "") · \(notice.quantityLabel)").font(.caption).foregroundStyle(.secondary)
                                HStack(spacing: 4) {
                                    Text("Average fill price")
                                    Text(verbatim: money(notice.order.fillPrice))
                                }.font(.caption).foregroundStyle(.secondary)
                                if notice.order.intent == "CLOSE" {
                                    HStack { Text("Realized P&L"); RealizedProfit(order: notice.order) }.font(.caption.weight(.semibold))
                                }
                            }
                        }.foregroundStyle(.primary).contentShape(Rectangle())
                    }.buttonStyle(.plain)
                    Button { preview.dismiss(notice.id) } label: {
                        Image(systemName: "xmark").font(.subheadline.weight(.semibold))
                            .foregroundStyle(.secondary).frame(width: 32, height: 32)
                    }.buttonStyle(.plain).accessibilityLabel("Dismiss notification")
                }
                .padding(16)
                .frame(maxWidth: 560)
                .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 22))
                .overlay(RoundedRectangle(cornerRadius: 22).stroke(.primary.opacity(0.08)))
                .shadow(color: .black.opacity(0.16), radius: 14, y: 6)
                .padding(.horizontal, 14).padding(.top, 8)
                .transition(reduceMotion ? .opacity : .move(edge: .top).combined(with: .opacity))
                .task(id: notice.id) {
                    do {
                        try await Task.sleep(for: .seconds(6))
                        preview.dismiss(notice.id)
                    } catch { }
                }
            }
        }
        .animation(reduceMotion ? nil : .spring(duration: 0.3), value: preview.notice?.id)
        .sensoryFeedback(.success, trigger: preview.notice?.id) { _, next in next != nil }
        .sheet(item: $preview.detail, onDismiss: { preview.advance() }) { notice in
            NavigationStack {
                Form {
                    Section {
                        Text(notice.contractLabel)
                        Text(notice.order.expiration ?? "")
                        LabeledContent("Status") { Text(LocalizedStringKey(notice.complete ? "Order filled" : "Partially filled")) }
                        LabeledContent("Filled quantity", value: notice.quantityLabel)
                        LabeledContent("Average fill price", value: money(notice.order.fillPrice))
                    }
                    if notice.demo { Text("Preview only. No order was submitted or changed.").foregroundStyle(.secondary) }
                    else {
                        LabeledContent("Last fill time", value: notice.order.fillTimeLabel)
                        LabeledContent("Commission", value: notice.order.commissionLabel)
                        if notice.order.intent == "CLOSE" { LabeledContent("Realized P&L") { RealizedProfit(order: notice.order) } }
                    }
                }
                .navigationTitle(LocalizedStringKey(notice.demo ? "Demo fill details" : notice.complete ? "Order filled" : "Partially filled"))
                .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { preview.detail = nil } } }
            }.presentationDetents([.medium, .large])
        }
    }
}
