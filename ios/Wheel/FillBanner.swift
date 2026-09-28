import SwiftUI
import Observation

struct FillNotice: Identifiable {
    let id = UUID()
    let filled: Int
    var complete: Bool { filled == 2 }
}

@MainActor @Observable
final class FillPreview {
    var notice: FillNotice?
    var detail: FillNotice?
    private var task: Task<Void, Never>?
    func dismiss(_ id: UUID) {
        if notice?.id == id { notice = nil }
    }
    func clear() { task?.cancel(); task = nil; notice = nil; detail = nil }
    func start() {
        clear()
        task = Task { [weak self] in
            do {
                try await Task.sleep(for: .seconds(3))
                self?.notice = FillNotice(filled: 1)
                try await Task.sleep(for: .seconds(8))
                self?.notice = FillNotice(filled: 2)
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
                                    Text("Demo").font(.caption2.bold()).foregroundStyle(.secondary)
                                }
                                Text("TSLL · SELL · $9 PUT").font(.subheadline.weight(.semibold))
                                Text("20261016 · \(notice.filled)/2").font(.caption).foregroundStyle(.secondary)
                                HStack(spacing: 4) {
                                    Text("Average fill price")
                                    Text(verbatim: "$0.48")
                                }.font(.caption).foregroundStyle(.secondary)
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
        .sheet(item: $preview.detail) { notice in
            NavigationStack {
                Form {
                    Section("Demo fill details") {
                        Text("TSLL · SELL · 20261016 · $9 PUT")
                        LabeledContent("Status") { Text(LocalizedStringKey(notice.complete ? "Order filled" : "Partially filled")) }
                        LabeledContent("Filled quantity", value: "\(notice.filled)/2")
                        LabeledContent("Average fill price", value: "$0.48")
                    }
                    Text("Preview only. No order was submitted or changed.").foregroundStyle(.secondary)
                }
                .navigationTitle("Demo fill details")
                .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { preview.detail = nil } } }
            }.presentationDetents([.medium, .large])
        }
    }
}
