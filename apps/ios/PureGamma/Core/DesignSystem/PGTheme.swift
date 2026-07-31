import SwiftUI

enum PGTheme {
    static let accent = Color(red: 0.76, green: 0.93, blue: 0.42)
    static let positive = Color(red: 0.35, green: 0.79, blue: 0.58)
    static let negative = Color(red: 0.93, green: 0.38, blue: 0.39)
    static let warning = Color(red: 0.92, green: 0.69, blue: 0.28)
    static let separator = Color.primary.opacity(0.12)
    static let secondaryBackground = Color(uiColor: .secondarySystemBackground)
    static let tertiaryBackground = Color(uiColor: .tertiarySystemBackground)
    static func change(_ value: Decimal?) -> Color { guard let value else { return .secondary }; return value >= 0 ? positive : negative }
}

struct PGSectionHeader: View {
    let index: String; let title: LocalizedStringKey; var trailing: String? = nil
    var body: some View { HStack(alignment: .firstTextBaseline) { Text(index).font(.caption2.monospaced()).foregroundStyle(PGTheme.accent); Text(title).font(.headline); Spacer(); if let trailing { Text(trailing).font(.caption.monospaced()).foregroundStyle(.secondary) } }.accessibilityElement(children: .combine) }
}

struct RiskDisclosureView: View {
    var body: some View { Text("Research only. Not investment advice. AI-generated content may be inaccurate. Users bear all risks of using this service.").font(.caption2).foregroundStyle(.secondary).padding(.vertical, 8).accessibilityLabel("Risk disclosure. Research only. Not investment advice.") }
}

struct StateView: View {
    let title: LocalizedStringKey; let detail: LocalizedStringKey; let symbol: String; var retry: (() -> Void)?
    var body: some View { ContentUnavailableView { Label(title, systemImage: symbol) } description: { Text(detail) } actions: { if let retry { Button("Retry", action: retry).buttonStyle(.bordered) } }.frame(maxWidth: .infinity, minHeight: 220).accessibilityElement(children: .contain) }
}

struct StaleBanner: View {
    let date: Date
    var body: some View { Label("Data may be stale · \(PGFormat.dateTime(date))", systemImage: "clock.badge.exclamationmark").font(.caption).foregroundStyle(PGTheme.warning).frame(maxWidth: .infinity, alignment: .leading).padding(10).background(PGTheme.warning.opacity(0.1)) }
}

struct TerminalDivider: View { var body: some View { Rectangle().fill(PGTheme.separator).frame(height: 1) } }
