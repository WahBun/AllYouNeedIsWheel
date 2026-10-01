import SwiftUI
import PhotosUI
import ImageIO

/// Matches AnalyticsStudio: absolute position market values grouped by symbol,
/// plus positive cash. These are exposure weights, not net liquidation weights.
struct HoldingsShareSlice: Identifiable {
    var name: String
    var value: Double
    var id: String { name }
    static func make(_ portfolio: Bootstrap?) -> [Self] {
        var values: [String: Double] = [:]
        for position in portfolio?.positions ?? [] where position.position != 0 {
            guard let value = position.market_value, value.isFinite else { continue }
            values[position.symbol.uppercased(), default: 0] += abs(value)
        }
        if let cash = portfolio?.summary.cash_balance, cash.isFinite, cash > 0 { values["Cash", default: 0] += cash }
        return values.filter { $0.value > 0 }.map { Self(name: $0.key, value: $0.value) }
            .sorted { $0.value == $1.value ? $0.name < $1.name : $0.value > $1.value }
    }
}

enum HoldingsShareBackground: String, CaseIterable, Identifiable {
    case wallStreet = "ShareBackdrop", space = "ShareSpace", gold = "ShareGold"
    case aurora = "ShareAurora", coast = "ShareCoast", city = "ShareCity", ink = "ShareInk"
    var id: String { rawValue }
    var title: String { switch self { case .wallStreet: "Wall Street"; case .space: "Deep Space"; case .gold: "Golden Peaks"; case .aurora: "Aurora"; case .coast: "Moonlit Coast"; case .city: "Neon City"; case .ink: "Ink Mountains" } }
}

struct HoldingsSharePreview: View {
    @Environment(\.dismiss) private var dismiss
    @State private var slices: [HoldingsShareSlice]
    init(portfolio: Bootstrap?) { _slices = State(initialValue: HoldingsShareSlice.make(portfolio)) }
    @State private var image: Image?
    @State private var photo: PhotosPickerItem?
    @State private var customImage: UIImage?
    @State private var customActive = false
    @State private var renderID = UUID()
    @State private var importError = false
    @State private var background: HoldingsShareBackground = .wallStreet
    @AppStorage("shareEnglishLettering") private var showLettering = true
    var body: some View {
        NavigationStack {
            ScrollView { VStack(spacing: 20) {
                if let image {
                    image.resizable().scaledToFit().clipShape(RoundedRectangle(cornerRadius: 18))
                    ScrollView(.horizontal, showsIndicators: false) { HStack(spacing: 12) {
                        ForEach(HoldingsShareBackground.allCases) { option in
                            Button { customActive = false; background = option; renderID = UUID() } label: {
                                VStack(spacing: 6) {
                                    Image(option.rawValue).resizable().scaledToFill().frame(width: 76, height: 76).clipped()
                                        .clipShape(RoundedRectangle(cornerRadius: 10))
                                        .overlay(RoundedRectangle(cornerRadius: 10).stroke(!customActive && background == option ? Color.accentColor : .clear, lineWidth: 3))
                                    Text(LocalizedStringKey(option.title)).font(.caption)
                                }
                            }.buttonStyle(.plain).accessibilityAddTraits(!customActive && background == option ? .isSelected : [])
                        }
                        if let customImage {
                            Button { customActive = true; renderID = UUID() } label: {
                                VStack(spacing: 6) {
                                    Image(uiImage: customImage).resizable().scaledToFill().frame(width: 76, height: 76).clipped()
                                        .clipShape(RoundedRectangle(cornerRadius: 10))
                                        .overlay(RoundedRectangle(cornerRadius: 10).stroke(customActive ? Color.accentColor : .clear, lineWidth: 3))
                                    Text("My background").font(.caption)
                                }
                            }.buttonStyle(.plain).accessibilityAddTraits(customActive ? .isSelected : [])
                        }
                    }.padding(4) }
                    Button { customActive = false; background = HoldingsShareBackground.allCases.filter { $0 != background }.randomElement() ?? .wallStreet; renderID = UUID() } label: {
                        Label("Random background", systemImage: "shuffle")
                    }.buttonStyle(.bordered)
                    PhotosPicker(selection: $photo, matching: .images) {
                        Label("Import background", systemImage: "photo.badge.plus")
                    }.buttonStyle(.bordered)
                    Toggle("English lettering", isOn: $showLettering)
                        .tint(.cyan)
                        .onChange(of: showLettering) { renderID = UUID() }
                    ShareLink(item: image, preview: SharePreview("Holdings", image: image)) {
                        Label("Share image", systemImage: "square.and.arrow.up").frame(maxWidth: .infinity)
                    }.buttonStyle(.borderedProminent)
                } else { ProgressView() }
                Text("Weights use absolute position values plus positive cash. Account details and amounts are hidden.")
                    .font(.footnote).foregroundStyle(.secondary)
                Spacer(minLength: 0)
            }.padding() }.navigationTitle("Share holdings").navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
                .task(id: renderID) {
                    let renderer = ImageRenderer(content: HoldingsShareArtwork(slices: slices, background: background, customImage: customActive ? customImage : nil, showLettering: showLettering).frame(width: 1080, height: 1080))
                    renderer.scale = 1
                    if let rendered = renderer.uiImage { image = Image(uiImage: rendered) }
                }
                .task {
                    if let data = try? Data(contentsOf: ShareBackgroundImport.fileURL) {
                        customImage = ShareBackgroundImport.decode(data)
                    }
                }
                .task(id: photo) {
                    guard let photo else { return }
                    do {
                        guard let data = try await photo.loadTransferable(type: Data.self),
                              let imported = ShareBackgroundImport.decode(data),
                              let saved = imported.jpegData(compressionQuality: 0.9) else {
                            importError = true; return
                        }
                        try Task.checkCancellation()
                        try FileManager.default.createDirectory(at: ShareBackgroundImport.fileURL.deletingLastPathComponent(), withIntermediateDirectories: true)
                        try saved.write(to: ShareBackgroundImport.fileURL, options: .atomic)
                        customImage = imported
                        customActive = true
                        renderID = UUID()
                    } catch is CancellationError { } catch { importError = true }
                }
                .alert("Unable to import image", isPresented: $importError) {
                    Button("OK", role: .cancel) { }
                } message: { Text("Choose another photo and try again.") }
        }
    }
}

struct HoldingsShareArtwork: View {
    let slices: [HoldingsShareSlice]
    var background: HoldingsShareBackground = .wallStreet
    var customImage: UIImage?
    var showLettering = true
    private let colors: [Color] = [.cyan, .mint, .purple, .orange, .red, .green, .teal, .blue]
    var body: some View {
        GeometryReader { geometry in
            let size = geometry.size.width
            let radius = size * 0.42
            let center = CGPoint(x: size / 2, y: size * 0.49)
            ZStack {
                (customImage.map { Image(uiImage: $0) } ?? Image(background.rawValue)).resizable().scaledToFill().frame(width: size, height: size).clipped()
                if showLettering {
                    ShareEditorialLettering()
                        .allowsHitTesting(false)
                        .accessibilityHidden(true)
                }
                Canvas { context, _ in
                    let total = slices.reduce(0) { $0 + $1.value }
                    var start = -Double.pi / 2
                    for (index, slice) in slices.enumerated() {
                        let fraction = slice.value / total
                        let end = start + fraction * 2 * .pi
                        let color = colors[index % colors.count]
                        var wedge = Path()
                        wedge.move(to: center)
                        wedge.addArc(center: center, radius: radius, startAngle: .radians(start), endAngle: .radians(end), clockwise: false)
                        wedge.closeSubpath()
                        context.fill(wedge, with: .radialGradient(Gradient(colors: [color.opacity(0.01), color.opacity(0.13)]), center: center, startRadius: 0, endRadius: radius))
                        var edge = Path()
                        edge.addArc(center: center, radius: radius, startAngle: .radians(start), endAngle: .radians(end), clockwise: false)
                        context.drawLayer { aura in
                            aura.addFilter(.blur(radius: radius * 0.045))
                            aura.stroke(edge, with: .color(color.opacity(0.9)), lineWidth: radius * 0.055)
                        }
                        context.drawLayer { glow in
                            glow.addFilter(.shadow(color: color, radius: 18))
                            glow.stroke(edge, with: .color(color), lineWidth: 5)
                        }
                        var divider = Path()
                        divider.move(to: CGPoint(x: center.x + cos(start) * radius * 0.3, y: center.y + sin(start) * radius * 0.3))
                        divider.addLine(to: CGPoint(x: center.x + cos(start) * radius, y: center.y + sin(start) * radius))
                        context.drawLayer { glow in
                            glow.addFilter(.shadow(color: color, radius: 12))
                            glow.stroke(divider, with: .color(color.opacity(0.8)), lineWidth: 5)
                        }
                        var inner = Path()
                        inner.addArc(center: center, radius: radius * 0.3, startAngle: .radians(start), endAngle: .radians(end), clockwise: false)
                        context.drawLayer { glow in
                            glow.addFilter(.shadow(color: color, radius: 15))
                            glow.stroke(inner, with: .color(color), lineWidth: 4)
                        }
                        context.stroke(divider, with: .color(.white.opacity(0.85)), lineWidth: 2)
                        if fraction >= 0.025 {
                            let middle = (start + end) / 2
                            let point = CGPoint(x: center.x + cos(middle) * radius * 0.68, y: center.y + sin(middle) * radius * 0.68)
                            let fontSize = radius * (fraction < 0.09 ? 0.09 : 0.13)
                            context.draw(Text(String(format: "%.1f%%", fraction * 100)).font(.system(size: fontSize, weight: .black)).foregroundStyle(.white), at: CGPoint(x: point.x, y: point.y - fontSize * 0.3))
                            context.draw(Text(slice.name).font(.system(size: fontSize * 0.48, weight: .bold)).foregroundStyle(.white), at: CGPoint(x: point.x, y: point.y + fontSize * 0.55))
                        }
                        start = end
                    }
                }
                Image("ShareCenter").resizable().scaledToFill().frame(width: radius * 0.55, height: radius * 0.55)
                    .clipShape(Circle()).overlay(Circle().stroke(.white.opacity(0.8), lineWidth: 3))
                    .position(center)
                if slices.isEmpty { Text("No portfolio").font(.title).foregroundStyle(.white).position(x: center.x, y: size * 0.8) }
            }
        }
    }
}

/// A shared, resolution-independent lettering layer for built-in and imported backdrops.
/// All built-in backgrounds are clean; the same toggle governs every background.
private struct ShareEditorialLettering: View {
    var body: some View {
        Canvas { context, canvas in
            let size = canvas.width
            func label(_ text: String, x: CGFloat, y: CGFloat, font: CGFloat = 0.012,
                       tracking: CGFloat = 0.003, anchor: UnitPoint = .topLeading) {
                let lettering = Text(verbatim: text)
                    .font(.system(size: size * font, weight: .medium))
                    .tracking(size * tracking)
                    .foregroundStyle(.white.opacity(0.7))
                context.drawLayer { layer in
                    layer.addFilter(.shadow(color: .black.opacity(0.9), radius: size * 0.003))
                    layer.draw(lettering, at: CGPoint(x: size * x, y: size * y), anchor: anchor)
                }
            }
            label("U.S. STOCKS", x: 0.03, y: 0.025, font: 0.017, tracking: 0.007)
            for (index, word) in ["INVEST", "TRADE", "COMPOUND"].enumerated() {
                label(word, x: 0.03, y: 0.064 + CGFloat(index) * 0.02)
            }
            for (index, word) in ["DISCIPLINE", "EXECUTION", "FREEDOM"].enumerated() {
                label(word, x: 0.974, y: 0.064 + CGFloat(index) * 0.029, anchor: .topTrailing)
            }
            label("NO RISK.", x: 0.03, y: 0.846, font: 0.015, tracking: 0.006)
            label("NO STORY.", x: 0.03, y: 0.878, font: 0.015, tracking: 0.006)
            for (index, word) in ["PRICE ACTION", "PATIENCE", "DISCIPLINE", "BETTER TRADER"].enumerated() {
                label(word, x: 0.84, y: 0.818 + CGFloat(index) * 0.027, font: 0.011, tracking: 0.002)
            }
            label("SMALL STEPS BIG RESULTS", x: 0.5, y: 0.955, font: 0.012,
                  tracking: 0.007, anchor: .top)
            let script = Text(verbatim: "Trade\nYour Plan")
                .font(.custom("SnellRoundhand", size: size * 0.023))
                .foregroundStyle(.white.opacity(0.55))
            context.draw(script, at: CGPoint(x: size * 0.95, y: size * 0.47))
            var rules = Path()
            for y in [0.134, 0.915] {
                rules.move(to: CGPoint(x: size * 0.03, y: size * y))
                rules.addLine(to: CGPoint(x: size * 0.068, y: size * y))
            }
            context.stroke(rules, with: .color(.yellow.opacity(0.65)), lineWidth: size * 0.002)
        }
    }
}

/// Decode directly to export resolution to avoid retaining a full camera image.
enum ShareBackgroundImport {
    static var fileURL: URL {
        URL.applicationSupportDirectory.appending(path: "HoldingsShare/background.jpg")
    }
    static func decode(_ data: Data) -> UIImage? {
        guard let source = CGImageSourceCreateWithData(data as CFData, nil),
              let thumbnail = CGImageSourceCreateThumbnailAtIndex(source, 0, [
                kCGImageSourceCreateThumbnailFromImageAlways: true,
                kCGImageSourceCreateThumbnailWithTransform: true,
                kCGImageSourceThumbnailMaxPixelSize: 1600
              ] as CFDictionary) else { return nil }
        return UIImage(cgImage: thumbnail)
    }
}
