import Observation
import SwiftUI

@MainActor @Observable final class SignalsViewModel {
    var state: LoadState<[Signal]> = .idle
    var direction = "all"
    private let repository: ResearchRepository
    init(repository: ResearchRepository) { self.repository = repository }
    func load() async {
        state = .loading
        do { let rows = try await repository.signals(); state = rows.isEmpty ? .empty : .loaded(rows) }
        catch { state = .failed(error as? APIError ?? .transport(error.localizedDescription)) }
    }
    var filtered: [Signal] { guard case .loaded(let rows) = state else { return [] }; return direction == "all" ? rows : rows.filter { $0.direction == direction } }
}

struct SignalsView: View {
    @State private var model: SignalsViewModel
    init(repository: ResearchRepository) { _model = State(initialValue: SignalsViewModel(repository: repository)) }
    var body: some View {
        VStack(spacing: 0) {
            HStack { Picker("Direction", selection: $model.direction) { Text("ALL").tag("all"); Text("LONG").tag("long"); Text("SHORT").tag("short"); Text("MONITOR").tag("monitor") }.pickerStyle(.segmented); Spacer() }.padding(.horizontal).padding(.top, 8)
            switch model.state {
            case .loading, .idle: ProgressView("Scanning market signals…").frame(maxHeight: .infinity)
            case .empty: StateView(title: "No signals", detail: "No research signals are available right now.", symbol: "waveform.path")
            case .failed(let error): StateView(title: "Signals unavailable", detail: LocalizedStringKey(error.localizedDescription), symbol: "exclamationmark.triangle", retry: { Task { await model.load() } })
            case .loaded, .stale: List(model.filtered) { SignalRow(signal: $0) }.listStyle(.plain).refreshable { await model.load() }
            }
        }
        .navigationTitle("Signals")
        .navigationBarTitleDisplayMode(.inline)
        .task { if case .idle = model.state { await model.load() } }
    }
}

struct SignalRow: View {
    let signal: Signal
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(signal.asset).font(.headline.monospaced())
                Text(signal.signalType.uppercased()).font(.caption2.monospaced()).padding(.horizontal, 6).padding(.vertical, 2).background(RoundedRectangle(cornerRadius: 4, style: .continuous).fill(PGTheme.secondaryBackground))
                Spacer()
                directionBadge
                Text("\((signal.confidence ?? 0).formatted(.number.precision(.fractionLength(0))))%").font(.caption.monospacedDigit())
            }
            if let thesis = signal.thesis, !thesis.isEmpty { Text(thesis).font(.subheadline) }
            HStack(spacing: 12) {
                if let catalyst = signal.catalyst, !catalyst.isEmpty { Label(catalyst, systemImage: "bolt").font(.caption).foregroundStyle(.secondary) }
                if let timeframe = signal.timeframe, !timeframe.isEmpty { Text("TF \(timeframe)").font(.caption2.monospaced()).foregroundStyle(.secondary) }
                Spacer()
                if let invalidation = signal.invalidation, !invalidation.isEmpty { Text("INVALIDATION \(invalidation)").font(.caption2.monospaced()).foregroundStyle(PGTheme.warning).lineLimit(1) }
            }
        }
        .padding(.vertical, 6)
        .accessibilityElement(children: .combine)
    }
    private var directionBadge: some View {
        let isLong = signal.direction == "long"
        return Text(signal.direction.uppercased()).font(.caption2.monospaced()).foregroundStyle(isLong ? PGTheme.positive : PGTheme.negative)
    }
}
