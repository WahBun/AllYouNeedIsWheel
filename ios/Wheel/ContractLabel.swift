import Foundation

/// Presentation only. Never feed a formatted name back into contract resolution.
enum ContractLabel {
    private static let occ = try! NSRegularExpression(pattern: #"^([A-Z0-9.]{1,6})\s*([0-9]{6})([CP])([0-9]{8})$"#)
    private static let human = try! NSRegularExpression(pattern: #"^(\S+)\s+([0-9]{8}|[0-9]{4}-[0-9]{2}-[0-9]{2})\s+([0-9]+(?:\.[0-9]+)?)\s+(CALL|PUT|C|P)$"#, options: .caseInsensitive)
    private static func groups(_ pattern: NSRegularExpression, _ raw: String) -> [String]? {
        guard let match = pattern.firstMatch(in: raw, range: NSRange(raw.startIndex..., in: raw)) else { return nil }
        return (1..<match.numberOfRanges).map { String(raw[Range(match.range(at: $0), in: raw)!]) }
    }
    private static func option(_ symbol: String, _ expiry: String, _ strike: Double?, _ right: String) -> String? {
        let digits = expiry.replacingOccurrences(of: "-", with: "")
        guard !symbol.isEmpty, digits.count == 8, digits.allSatisfy(\.isNumber),
              let year = Int(digits.prefix(4)), let month = Int(digits.dropFirst(4).prefix(2)), let day = Int(digits.suffix(2)),
              let strike, strike.isFinite, strike > 0,
              let code = ["CALL":"C", "PUT":"P", "C":"C", "P":"P"][right.uppercased()] else { return nil }
        var calendar = Calendar(identifier: .gregorian); calendar.timeZone = TimeZone(secondsFromGMT: 0)!
        guard let date = calendar.date(from: DateComponents(year: year, month: month, day: day)),
              calendar.component(.year, from: date) == year, calendar.component(.month, from: date) == month,
              calendar.component(.day, from: date) == day else { return nil }
        let number = String(format: "%.8f", locale: Locale(identifier: "en_US_POSIX"), strike)
            .replacingOccurrences(of: #"\.?0+$"#, with: "", options: .regularExpression)
        return "\(symbol) · \(digits.dropFirst(4).prefix(2))/\(digits.suffix(2))/\(digits.dropFirst(2).prefix(2)) · \(number)\(code)"
    }
    static func compact(_ raw: String) -> String {
        if let v = groups(occ, raw), let value = Double(v[3]) {
            return option(v[0], "20" + v[1], value / 1000, v[2]) ?? raw
        }
        if let v = groups(human, raw) { return option(v[0], v[1], Double(v[2]), v[3]) ?? raw }
        return raw
    }
    static func label(symbol: String, expiration: String?, strike: Double?, right: String?, raw: String = "", type: String = "OPT") -> String {
        let fallback = raw.isEmpty ? symbol : raw
        guard type == "OPT" else { return fallback }
        if let v = groups(occ, raw), v[0].hasPrefix(symbol),
           let value = Double(v[3]), let strike, abs(value / 1000 - strike) < 0.0000001,
           (expiration ?? "").replacingOccurrences(of: "-", with: "").suffix(6) == v[1],
           v[2] == ["CALL":"C", "PUT":"P", "C":"C", "P":"P"][(right ?? "").uppercased()] { return compact(raw) }
        return option(symbol, expiration ?? "", strike, right ?? "") ?? compact(fallback)
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
