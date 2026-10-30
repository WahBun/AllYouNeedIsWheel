import Foundation

/// Presentation order only; never changes the portfolio snapshot or contract identity.
enum OptionPositionOrder {
    private static func key(_ row: Position) -> (String, String, Int, Double, Int) {
        let expiry = (row.expiration ?? "").replacingOccurrences(of: "-", with: "")
        let right = (row.option_type ?? "").uppercased()
        let rank = ["P", "PUT"].contains(right) ? 0 : ["C", "CALL"].contains(right) ? 1 : 2
        return (row.symbol.uppercased(), expiry.isEmpty ? "99999999" : expiry, rank,
                row.strike.flatMap { $0.isFinite ? $0 : nil } ?? .infinity, row.con_id ?? Int.max)
    }
    static func sorted(_ rows: [Position]) -> [Position] {
        rows.enumerated().sorted { lhs, rhs in
            let a = key(lhs.element), b = key(rhs.element)
            return a == b ? lhs.offset < rhs.offset : a < b
        }.map(\.element)
    }
}
