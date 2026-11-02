import SwiftUI

struct CandidatePickerContext: Identifiable {
    let symbol: String
    var pin: PinnedOpportunity? = nil
    var id: String { pin?.id ?? symbol }
}

struct CandidateContractPicker: View {
    let symbol: String
    let type: String
    var initial: PinnedOpportunity? = nil
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
                        Picker("Strike", selection: $strike) {
                            ForEach(strikes, id: \.self) { value in
                                Text(money(value)).tag(Optional(value))
                            }
                        }.pickerStyle(.navigationLink)
                    } else if error == nil { ProgressView("Loading contracts…") }
                    if let error {
                        NoticeText(error)
                        Button("Retry") { retry += 1 }
                    }
                }
            }
            .navigationTitle(initial == nil ? "Add contract" : "Change contract")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button(initial == nil ? "Add" : "Save") { if let strike { choose(expiration, strike) } }
                        .disabled(loadedExpiration != expiration || strike.map { !strikes.contains($0) } != false)
                }
            }
        }
        .task(id: retry) {
            do {
                error = nil
                if dates.isEmpty {
                    let values = try await store.opportunities.expirationChoices(symbol, store: store)
                    try Task.checkCancellation()
                    dates = values.compactMap { $0["value"] as? String }
                    guard let first = dates.first else { throw AppError.message("No expiration available.") }
                    let preferred = initial?.expiration ?? primary?.quote?.expiration ?? ""
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
                let target = initial?.strike ?? primary?.quote?.strike ?? primary?.stockPrice ?? values[0]
                strikes = values
                strike = values.min { abs($0 - target) < abs($1 - target) }
                loadedExpiration = date
            } catch { if !Task.isCancelled { self.error = connectionMessage(error) } }
        }
    }
}
