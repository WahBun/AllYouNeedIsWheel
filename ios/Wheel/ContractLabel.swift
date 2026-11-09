import Foundation

/// Keep the display label separate from the underlying symbol and broker contract ID.
enum ContractLabel {
    private static let occ = try! NSRegularExpression(pattern: #"^([A-Z0-9.]{1,6})\s*([0-9]{6})([CP])([0-9]{8})$"#)
    private static let human = try! NSRegularExpression(pattern: #"^(.+?)\s+([0-9]{8}|[0-9]{4}-[0-9]{2}-[0-9]{2})\s+([0-9]+(?:[.,][0-9]+)*)\s+(CALL|PUT|C|P)$"#, options: .caseInsensitive)
    private static func groups(_ pattern: NSRegularExpression, _ raw: String) -> [String]? {
        guard let match = pattern.firstMatch(in: raw, range: NSRange(raw.startIndex..., in: raw)) else { return nil }
        return (1..<match.numberOfRanges).map { String(raw[Range(match.range(at: $0), in: raw)!]) }
    }
    private static func option(_ symbol: String, _ expiry: String, _ strike: Double?, _ right: String) -> String? {
        let digits = expiry.replacingOccurrences(of: "-", with: "")
        guard !symbol.isEmpty, digits.count == 8, digits.allSatisfy(\.isNumber),
              let year = Int(digits.prefix(4)), let month = Int(digits.dropFirst(4).prefix(2)), let day = Int(digits.suffix(2)),
              let strike, strike.isFinite, strike > 0,
              let code = rightCode(right) else { return nil }
        var calendar = Calendar(identifier: .gregorian); calendar.timeZone = TimeZone(secondsFromGMT: 0)!
        guard let date = calendar.date(from: DateComponents(year: year, month: month, day: day)),
              calendar.component(.year, from: date) == year, calendar.component(.month, from: date) == month,
              calendar.component(.day, from: date) == day else { return nil }
        let number = String(format: "%.8f", locale: Locale(identifier: "en_US_POSIX"), strike)
            .replacingOccurrences(of: #"\.?0+$"#, with: "", options: .regularExpression)
        return "\(symbol) · \(digits.dropFirst(4).prefix(2))/\(digits.suffix(2))/\(digits.dropFirst(2).prefix(2)) · \(number)\(code)"
    }
    static func expiry(_ value: String) -> String {
        guard value.count == 8, value.allSatisfy(\.isNumber) else { return value }
        return "\(value.dropFirst(4).prefix(2))/\(value.suffix(2))/\(value.dropFirst(2).prefix(2))"
    }
    struct OptionName {
        let root: String
        let expiration: String
        let strike: Double
        let right: String

        let label: String

        init?(root: String, expiration: String, strike: Double, right: String) {
            guard let label = option(root, expiration, strike, right) else { return nil }
            self.root = root
            self.expiration = expiration
            self.strike = strike
            self.right = right
            self.label = label
        }
        func matches(expiration: String?, strike: Double?, right: String?) -> Bool {
            guard let strike, let right else { return false }
            return self.expiration == expiration?.replacingOccurrences(of: "-", with: "") &&
                abs(self.strike - strike) < 0.0000001 && self.right == rightCode(right)
        }
    }

    static func rightCode(_ right: String) -> String? {
        ["CALL": "C", "PUT": "P", "C": "C", "P": "P"][right.uppercased()]
    }
    private static func occName(_ raw: String) -> OptionName? {
        guard let v = groups(occ, raw), let value = Double(v[3]) else { return nil }
        return OptionName(root: v[0], expiration: "20" + v[1], strike: value / 1000, right: v[2])
    }
    static func optionName(_ raw: String) -> OptionName? {
        if let name = occName(raw) { return name }
        guard let v = groups(human, raw), let right = rightCode(v[3]) else { return nil }
        // Older recent-chart records appended the terms to the complete OCC symbol.
        if let name = occName(v[0]) {
            let groupedStrike = name.strike.formatted(.number.locale(Locale(identifier: "en_US")))
            let strike = v[2] == groupedStrike || v[2] == name.strike.formatted() ? name.strike : Double(v[2])
            return name.matches(expiration: v[1], strike: strike, right: right) ? name : nil
        }
        guard !v[0].contains(where: { $0.isWhitespace }), let strike = Double(v[2]) else { return nil }
        return OptionName(root: v[0], expiration: v[1].replacingOccurrences(of: "-", with: ""), strike: strike, right: right)
    }
    static func compact(_ raw: String) -> String { optionName(raw)?.label ?? raw }
    static func label(symbol: String, expiration: String?, strike: Double?, right: String?, raw: String = "", type: String = "OPT") -> String {
        let fallback = raw.isEmpty ? symbol : raw
        guard type == "OPT" else { return fallback }
        if let name = optionName(fallback), symbol.isEmpty || symbol == fallback || name.root.hasPrefix(symbol) {
            if let expiration, let strike, let right,
               !name.matches(expiration: expiration, strike: strike, right: right) { return fallback }
            return name.label
        }
        return option(symbol, expiration ?? "", strike, right ?? "") ?? fallback
    }
    static func details(expiration: String?, strike: Double?, right: String?) -> String {
        if let value = option("_", expiration ?? "", strike, right ?? "") { return String(value.dropFirst(4)) }
        return [expiration ?? "", strike.map { String($0) } ?? "", right ?? ""].filter { !$0.isEmpty }.joined(separator: " · ")
    }
}

extension Order {
    var contractLabel: String {
        if displaySymbol == name, name.range(of: #"[0-9]{6}[CP][0-9]{8}$"#, options: .regularExpression) != nil { return name }
        return ContractLabel.label(symbol: displaySymbol, expiration: expiration, strike: strike, right: option_type,
                            raw: name, type: ["CALL", "PUT", "C", "P"].contains((option_type ?? "").uppercased()) ? "OPT" : "OTHER")
    }
    var contractDetails: String { ContractLabel.details(expiration: expiration, strike: strike, right: option_type) }
}
