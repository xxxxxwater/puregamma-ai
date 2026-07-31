import Observation
import SwiftUI

@MainActor @Observable final class ResearchViewModel {
    enum Section: String, CaseIterable, Identifiable { case reports = "Reports", options = "Long Gamma"; var id: String { rawValue } }
    var section: Section = .reports; var reports: LoadState<[Report]> = .idle; var options: LoadState<[OptionCandidate]> = .idle; var currency = "BTC"; var optionStatus = ""; var fetchedAt: Date?
    private let repository: ResearchRepository
    init(repository: ResearchRepository) { self.repository = repository }
    func loadReports() async { reports = .loading; do { let result = try await repository.cachedReports(); reports = result.value.isEmpty ? .empty : result.cachedAt.map { .stale(result.value, $0) } ?? .loaded(result.value) } catch { reports = .failed(error as? APIError ?? .transport(error.localizedDescription)) } }
    func loadOptions() async { options = .loading; do { let result = try await repository.longGamma(currency: currency); optionStatus = result.0; fetchedAt = result.1; options = result.2.isEmpty ? .empty : .loaded(result.2); if let error = result.3, result.2.isEmpty { options = .failed(.unavailable(error)) } } catch { options = .failed(error as? APIError ?? .transport(error.localizedDescription)) } }
}

struct ResearchView: View {
    @State private var model: ResearchViewModel
    init(repository: ResearchRepository) { _model = State(initialValue: ResearchViewModel(repository: repository)) }
    var body: some View {
        VStack(spacing: 0) {
            Picker("Research section", selection: $model.section) { ForEach(ResearchViewModel.Section.allCases) { Text(LocalizedStringKey($0.rawValue)).tag($0) } }.pickerStyle(.segmented).padding()
            if model.section == .reports { reports } else { options }
        }.navigationTitle("Research").navigationBarTitleDisplayMode(.inline).task { await model.loadReports() }.onChange(of: model.section) { _, value in if value == .options, case .idle = model.options { Task { await model.loadOptions() } } }
    }
    @ViewBuilder private var reports: some View { switch model.reports { case .loading, .idle: ProgressView("Loading reports…").frame(maxHeight: .infinity); case .empty: StateView(title: "No reports", detail: "No real research report has been generated yet.", symbol: "doc.text"); case .failed(let e): StateView(title: "Reports unavailable", detail: LocalizedStringKey(e.localizedDescription), symbol: "doc.badge.ellipsis", retry: { Task { await model.loadReports() } }); case .loaded(let rows): reportList(rows); case .stale(let rows, let cachedAt): VStack(spacing: 8) { StaleDataBanner(cachedAt: cachedAt).padding(.horizontal); reportList(rows) } } }
    private func reportList(_ rows: [Report]) -> some View { List(rows) { row in NavigationLink { ReportDetailView(report: row) } label: { ReportRow(report: row) } }.listStyle(.plain) }
    @ViewBuilder private var options: some View { VStack(spacing: 0) { HStack { Picker("Underlying", selection: $model.currency) { Text("BTC").tag("BTC"); Text("ETH").tag("ETH") }.pickerStyle(.segmented).frame(width: 150); Spacer(); Text("\(model.optionStatus) · \(PGFormat.dateTime(model.fetchedAt))").font(.caption2.monospaced()).foregroundStyle(model.optionStatus == "HEALTHY" ? PGTheme.positive : PGTheme.warning) }.padding(.horizontal).onChange(of: model.currency) { _, _ in Task { await model.loadOptions() } }; Group { switch model.options { case .loading, .idle: ProgressView("Loading Deribit public data…").frame(maxWidth: .infinity, maxHeight: .infinity); case .empty: StateView(title: "No candidates", detail: "The connected Deribit public feed returned no qualifying long-gamma candidates.", symbol: "waveform.path.ecg"); case .failed(let e): StateView(title: "Options data unavailable", detail: LocalizedStringKey(e.localizedDescription), symbol: "exclamationmark.arrow.triangle.2.circlepath", retry: { Task { await model.loadOptions() } }); case .loaded(let rows), .stale(let rows, _): List(rows) { OptionRow(candidate: $0) }.listStyle(.plain) } } } }
}
struct ReportDetailView: View { let report: Report; var body: some View { ScrollView { VStack(alignment: .leading, spacing: 16) { Text(report.type.uppercased()).font(.caption.monospaced()).foregroundStyle(PGTheme.accent); Text(report.title).font(.largeTitle.bold()); Text(PGFormat.dateTime(report.createdAt)).font(.caption).foregroundStyle(.secondary); TerminalDivider(); Text(report.markdown).textSelection(.enabled); RiskDisclosureView() }.padding() }.navigationBarTitleDisplayMode(.inline) } }
struct OptionRow: View {
    let candidate: OptionCandidate
    private var score: String {
        candidate.score.map { "SCORE \(NSDecimalNumber(decimal: $0).stringValue)" } ?? "—"
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 9) {
            HStack {
                Text(candidate.instrument).font(.headline.monospaced())
                Spacer()
                Text(verbatim: score).font(.caption2.monospaced()).foregroundStyle(PGTheme.accent)
            }
            HStack {
                optionMetric("STRIKE", PGFormat.money(candidate.strike))
                optionMetric("IV", candidate.markIV?.description ?? "—")
                optionMetric("GAMMA", candidate.gamma?.description ?? "—")
                optionMetric("THETA", candidate.theta?.description ?? "—")
            }
            Text("Expiry \(PGFormat.dateTime(candidate.expiry))").font(.caption).foregroundStyle(.secondary)
            ForEach(candidate.rationale, id: \.self) { Text("• \($0)").font(.caption) }
            Text("Research only · execution disabled").font(.caption2.monospaced()).foregroundStyle(PGTheme.warning)
        }
        .padding(.vertical, 8)
        .accessibilityElement(children: .combine)
    }
}
private func optionMetric(_ label: String, _ value: String) -> some View { VStack(alignment: .leading, spacing: 3) { Text(label).font(.caption2.monospaced()).foregroundStyle(.secondary); Text(value).font(.caption.monospacedDigit()) }.frame(maxWidth: .infinity, alignment: .leading) }
