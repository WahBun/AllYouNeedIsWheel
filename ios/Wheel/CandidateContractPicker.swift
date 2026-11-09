import SwiftUI

struct CandidatePickerContext: Identifiable {
    let symbol: String
    var pin: PinnedOpportunity? = nil
    var editingPrimary = false
    var id: String { pin?.id ?? (editingPrimary ? symbol + ":primary" : symbol) }
}

struct CandidateContractPicker: View {
    let symbol: String
    let type: String
    var initial: PinnedOpportunity? = nil
    var editingPrimary = false
    let choose: (String, Double) -> Void
    @Environment(WheelStore.self) private var store
    @Environment(\.dismiss) private var dismiss
    @State private var dates: [String] = []
    @State private var expiration = ""
    @State private var strikes: [Double] = []
    @State private var loadedExpiration = ""
    @State private var strike: Double?
    @State private var error: String?
    @State private var retry = 0

    private var primary: OpportunityRow? { store.opportunities.rows[store.opportunities.key(symbol, type)] }

    private var editedPreference: OpportunityPreference? {
        editingPrimary ? store.opportunities.preferences[store.opportunities.key(symbol, type)] : nil
    }

    var body: some View {
        NavigationStack {
            Form {
                Section(symbol) {
                    if !dates.isEmpty {
                        Picker("Expiration", selection: $expiration) {
                            ForEach(dates, id: \.self) { Text(ContractLabel.expiry($0)).tag($0) }
                        }
                    }
                    if loadedExpiration == expiration, !strikes.isEmpty {
                        NavigationLink {
                            CandidateStrikeList(strikes: strikes, selection: $strike, stockPrice: primary?.stockPrice)
                        } label: {
                            LabeledContent("Strike", value: money(strike))
                        }
                    } else if error == nil { ProgressView("Loading contracts…") }
                    if let error {
                        NoticeText(error)
                        Button("Retry") { retry += 1 }
                    }
                }
            }
            .navigationTitle(initial != nil || editingPrimary ? "Change contract" : "Add contract")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button(initial != nil || editingPrimary ? "Save" : "Add") { if let strike { choose(expiration, strike) } }
                        .disabled(loadedExpiration != expiration || strike.map { !strikes.contains($0) } != false)
                }
            }
        }
        .task {
            guard !store.demo, primary?.stockQuoteIsFresh(at: .now, batchFailed: store.opportunities.priceError != nil) != true else { return }
            _ = await store.opportunities.refreshPrices([symbol], type: type, store: store)
        }
        .task(id: retry) {
            do {
                error = nil
                if dates.isEmpty {
                    let values = try await store.opportunities.expirationChoices(symbol, store: store)
                    try Task.checkCancellation()
                    dates = values.compactMap { $0["value"] as? String }
                    guard let first = dates.first else { throw AppError.message("No expiration available.") }
                    let preferred = initial?.expiration ?? primary?.quote?.expiration ?? editedPreference?.expiration ?? ""
                    expiration = dates.contains(preferred) ? preferred : first
                }
            } catch { if !Task.isCancelled { self.error = connectionMessage(error) } }
        }
        .task(id: "\(expiration)-\(retry)") {
            guard !expiration.isEmpty else { return }
            let date = expiration
            strikes = []; loadedExpiration = ""; strike = nil; error = nil
            do {
                let values = try await store.opportunities.availableStrikes(symbol, type: type, expiration: date, store: store)
                try Task.checkCancellation()
                guard !values.isEmpty else { throw AppError.message("No strikes available.") }
                let target = initial?.strike ?? primary?.quote?.strike ?? editedPreference?.strike ?? primary?.stockPrice ?? values[0]
                strikes = values
                strike = values.min { abs($0 - target) < abs($1 - target) }
                loadedExpiration = date
            } catch { if !Task.isCancelled { self.error = connectionMessage(error) } }
        }
    }
}

struct CandidateStrikeList: View {
    let strikes: [Double]
    @Binding var selection: Double?
    let stockPrice: Double?
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        ScrollViewReader { proxy in
            List(strikes, id: \.self) { value in
                Button {
                    selection = value
                    dismiss()
                } label: {
                    HStack {
                        Text(money(value)).foregroundStyle(.primary)
                        Spacer()
                        if selection == value { Image(systemName: "checkmark").accessibilityHidden(true) }
                    }
                    .contentShape(Rectangle())
                }
                .accessibilityAddTraits(selection == value ? .isSelected : [])
                .id(value)
            }
            .navigationTitle("Strike")
            .task {
                // Position once per visit. Later quote ticks must not move a list being browsed.
                let price = stockPrice.flatMap { $0.isFinite && $0 > 0 ? $0 : nil }
                guard let target = price ?? selection else { return }
                // Prefer the rounded dollar when listed. On a sparse chain, stay closest to the quote.
                let rounded = price?.rounded()
                guard let nearest = rounded.flatMap({ strikes.contains($0) ? $0 : nil })
                    ?? strikes.min(by: { abs($0 - target) < abs($1 - target) }) else { return }
                await Task.yield()
                guard !Task.isCancelled else { return }
                proxy.scrollTo(nearest, anchor: .center)
            }
        }
    }
}
