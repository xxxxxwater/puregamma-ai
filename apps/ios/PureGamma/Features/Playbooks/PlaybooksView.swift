import Observation
import SwiftUI

@MainActor @Observable final class PlaybooksViewModel {
    var state: LoadState<[Playbook]> = .idle
    var generating = false
    var message: String?
    private let repository: ResearchRepository
    init(repository: ResearchRepository) { self.repository = repository }
    func load() async {
        if case .loaded = state { return }
        state = .loading
        do { let result = try await repository.playbooks(); state = result.playbooks.isEmpty ? .empty : .loaded(result.playbooks) }
        catch { state = .failed(error as? APIError ?? .transport(error.localizedDescription)) }
    }
    func generate() async {
        generating = true; defer { generating = false }
        do { let rows = try await repository.generatePlaybook(); state = rows.isEmpty ? .empty : .loaded(rows); message = String(localized: "Playbook generated.") }
        catch APIError.paymentRequired { message = String(localized: "Not enough credits to generate a playbook.") }
        catch { message = error.localizedDescription }
    }
}

struct PlaybooksView: View {
    @State private var model: PlaybooksViewModel
    init(repository: ResearchRepository) { _model = State(initialValue: PlaybooksViewModel(repository: repository)) }
    var body: some View {
        VStack(spacing: 0) {
            HStack { Text("STRATEGY PLAYBOOKS").font(.caption2.monospaced()).foregroundStyle(PGTheme.accent); Spacer(); Button { Task { await model.generate() } } label: { Label("Generate", systemImage: "sparkles").font(.caption).padding(.horizontal, 10).padding(.vertical, 6) }.buttonStyle(.bordered).disabled(model.generating) }
                .padding(.horizontal).padding(.vertical, 8)
            if model.generating { ProgressView("Generating playbook…").frame(maxHeight: .infinity) }
            else {
                switch model.state {
                case .loading, .idle: ProgressView("Loading playbooks…").frame(maxHeight: .infinity)
                case .empty: StateView(title: "No playbooks", detail: "Generate a playbook to see strategy setups.", symbol: "figure.strengthtraining.traditional")
                case .failed(let error): StateView(title: "Playbooks unavailable", detail: LocalizedStringKey(error.localizedDescription), symbol: "exclamationmark.triangle", retry: { Task { await model.load() } })
                case .loaded(let rows), .stale(let rows, _): List(rows) { PlaybookRow(playbook: $0) }.listStyle(.plain).refreshable { Task { await model.load() } }
                }
            }
        }
        .navigationTitle("Playbooks")
        .navigationBarTitleDisplayMode(.inline)
        .task { await model.load() }
        .alert("Playbook", isPresented: Binding(get: { model.message != nil }, set: { if !$0 { model.message = nil } })) { Button("OK") {} } message: { Text(model.message ?? "") }
    }
}

struct PlaybookRow: View {
    let playbook: Playbook
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(playbook.strategyName).font(.headline)
                Spacer()
                Text(playbook.asset).font(.caption.monospaced()).padding(.horizontal, 6).padding(.vertical, 2).background(RoundedRectangle(cornerRadius: 4, style: .continuous).fill(PGTheme.secondaryBackground))
            }
            Text(playbook.thesis).font(.subheadline).foregroundStyle(.secondary)
            HStack(spacing: 10) {
                Label("\(playbook.confidence.formatted(.number.precision(.fractionLength(0))))%", systemImage: "checkmark.seal").font(.caption)
                Label("RISK \(playbook.riskScore)", systemImage: "shield").font(.caption2.monospaced())
                Spacer()
                Text(playbook.timeframe).font(.caption2.monospaced())
            }
            DisclosureGroup("Setup") {
                VStack(alignment: .leading, spacing: 6) {
                    setupRow("Trigger", playbook.trigger)
                    setupRow("Entry", playbook.entryCondition)
                    setupRow("Exit", playbook.exitCondition)
                    setupRow("Invalidation", playbook.invalidation)
                    setupRow("Expected payoff", playbook.expectedPayoff)
                }.font(.caption)
            }.font(.caption).tint(PGTheme.accent)
        }
        .padding(.vertical, 6)
        .accessibilityElement(children: .contain)
    }
}
private func setupRow(_ label: String, _ value: String) -> some View {
    HStack(alignment: .top) { Text(label.uppercased()).font(.caption2.monospaced()).foregroundStyle(.secondary).frame(width: 110, alignment: .leading); Text(value).frame(maxWidth: .infinity, alignment: .leading) }
}
