import Charts
import Observation
import SwiftUI

@MainActor @Observable final class BacktestViewModel {
    var runs: LoadState<[BacktestRun]> = .idle
    var detail: LoadState<BacktestRun> = .idle
    var symbols: [String] = []
    var running = false
    var message: String?
    var selectedRunID: String?
    var name = "Momentum BTC"; var signal = "momentum"; var asset = "BTC"; var windowDays = 30
    private let repository: ResearchRepository
    init(repository: ResearchRepository) { self.repository = repository }
    func load() async {
        if case .loaded = runs { return }
        runs = .loading
        do {
            let statusInfo = try await repository.backtestStatus()
            let rows = try await repository.backtestRuns()
            symbols = statusInfo.symbols
            if !statusInfo.symbols.contains(asset) { asset = statusInfo.symbols.first ?? "BTC" }
            runs = rows.isEmpty ? .empty : .loaded(rows)
        } catch { runs = .failed(error as? APIError ?? .transport(error.localizedDescription)) }
    }
    func run() async {
        running = true; defer { running = false }
        let spec = BacktestSpecDTO(name: name.isEmpty ? "Strategy" : name, mode: "daily", signal: signal, assets: [asset], fastWindow: 12, slowWindow: 26, rebalanceDays: 5, longShort: false, maxPosition: 1.0, feeBps: 10.0)
        do {
            let run = try await repository.runBacktest(spec: spec, windowDays: windowDays)
            selectedRunID = run.id
            await refreshRuns()
            await openDetail(run.id)
        } catch APIError.paymentRequired { message = String(localized: "Not enough credits for a backtest run.") }
        catch { message = error.localizedDescription }
    }
    func refreshRuns() async { do { let rows = try await repository.backtestRuns(); runs = rows.isEmpty ? .empty : .loaded(rows) } catch {} }
    func openDetail(_ id: String) async {
        detail = .loading
        do { detail = .loaded(try await repository.backtestRun(id)) } catch { detail = .failed(error as? APIError ?? .transport(error.localizedDescription)) }
    }
}

struct BacktestView: View {
    @State private var model: BacktestViewModel
    @Environment(\.locale) private var locale
    init(repository: ResearchRepository) { _model = State(initialValue: BacktestViewModel(repository: repository)) }
    var body: some View {
        List {
            Section("New backtest") {
                TextField("Strategy name", text: $model.name)
                Picker("Signal", selection: $model.signal) {
                    Text("Momentum").tag("momentum"); Text("Mean reversion").tag("mean_reversion"); Text("Breakout").tag("breakout"); Text("Relative strength").tag("relative_strength")
                }
                Picker("Asset", selection: $model.asset) { ForEach(model.symbols, id: \.self) { Text($0).tag($0) } }
                Picker("Window", selection: $model.windowDays) { Text("7 days").tag(7); Text("14 days").tag(14); Text("30 days").tag(30) }
                Button { Task { await model.run() } } label: { Label("Run backtest", systemImage: "play.fill").frame(maxWidth: .infinity) }.buttonStyle(.borderedProminent).tint(PGTheme.accent).foregroundStyle(PGTheme.onAccent).disabled(model.running || model.symbols.isEmpty)
                Text("Research only · 50 credits per run · daily candles").font(.caption2).foregroundStyle(.secondary)
            }
            Section("History") {
                switch model.runs {
                case .loading, .idle: ProgressView().frame(maxWidth: .infinity)
                case .empty: Text("No backtest runs yet.").foregroundStyle(.secondary)
                case .failed(let error): Label(error.localizedDescription, systemImage: "exclamationmark.triangle").font(.footnote).foregroundStyle(PGTheme.negative)
                case .loaded(let rows), .stale(let rows, _): ForEach(rows) { row in NavigationLink { BacktestDetailView(runID: row.id, model: model) } label: { BacktestRow(run: row) } }
                }
            }
        }
        .navigationTitle("Backtest Lab")
        .navigationBarTitleDisplayMode(.inline)
        .task { await model.load() }
        .refreshable { await model.refreshRuns() }
        .alert("Backtest", isPresented: Binding(get: { model.message != nil }, set: { if !$0 { model.message = nil } })) { Button("OK") {} } message: { Text(model.message ?? "") }
    }
}

struct BacktestRow: View {
    let run: BacktestRun
    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                Text(run.strategyName.isEmpty ? run.asset : "\(run.strategyName) · \(run.asset)").font(.headline)
                Text("\(run.mode) · \(PGFormat.dateTime(run.createdAt))").font(.caption2.monospaced()).foregroundStyle(.secondary)
            }
            Spacer()
            VStack(alignment: .trailing, spacing: 4) {
                statusBadge
                if let total = run.metrics["total_return"] { Text(PGFormat.percent(total)).font(.caption.monospacedDigit()) }
            }
        }
        .padding(.vertical, 4)
    }
    private var statusBadge: some View {
        let color = run.status == "completed" ? PGTheme.positive : (run.status == "failed" ? PGTheme.negative : PGTheme.warning)
        return Text(run.status.uppercased()).font(.caption2.monospaced()).foregroundStyle(color)
    }
}

struct BacktestDetailView: View {
    let runID: String
    @Bindable var model: BacktestViewModel
    var body: some View {
        Group {
            switch model.detail {
            case .loading, .idle: ProgressView("Loading run…").frame(maxWidth: .infinity, maxHeight: .infinity)
            case .failed(let error): StateView(title: "Run unavailable", detail: LocalizedStringKey(error.localizedDescription), symbol: "exclamationmark.triangle", retry: { Task { await model.openDetail(runID) } })
            case .loaded(let run): content(run)
            case .stale(let run, _): content(run)
            case .empty: StateView(title: "No data", detail: "The run returned no data.", symbol: "chart.line.downtrend.xyaxis")
            }
        }
        .navigationTitle("Backtest")
        .navigationBarTitleDisplayMode(.inline)
        .task { if case .idle = model.detail { await model.openDetail(runID) } }
    }
    @ViewBuilder private func content(_ run: BacktestRun) -> some View {
        if run.status == "running" || run.status == "queued" {
            VStack(spacing: 12) { ProgressView(); Text("Run is \(run.status)…").font(.caption).foregroundStyle(.secondary); Button("Refresh") { Task { await model.openDetail(runID) } }.buttonStyle(.bordered) }.frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if run.status == "failed" {
            StateView(title: "Run failed", detail: LocalizedStringKey(run.error["message"] ?? "Unknown error"), symbol: "xmark.octagon")
        } else {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    HStack(spacing: 12) {
                        metric("TOTAL", PGFormat.percent(run.metrics["total_return"]))
                        metric("SHARPE", (run.metrics["sharpe"] ?? 0).formatted(.number.precision(.fractionLength(2))))
                        metric("MAX DD", PGFormat.percent(run.metrics["max_drawdown"]))
                        metric("WIN", (run.metrics["win_rate"] ?? 0).formatted(.percent.precision(.fractionLength(0))))
                    }
                    if !run.equityCurve.isEmpty {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("EQUITY CURVE").font(.caption2.monospaced()).foregroundStyle(PGTheme.accent)
                            Chart(run.equityCurve) { point in LineMark(x: .value("Day", point.index), y: .value("Equity", point.value)).foregroundStyle(PGTheme.accent) }.frame(height: 180)
                        }
                    }
                    if !run.trades.isEmpty {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("TRADES · \(run.trades.count)").font(.caption2.monospaced()).foregroundStyle(PGTheme.accent)
                            ForEach(Array(run.trades.prefix(30).enumerated()), id: \.offset) { _, trade in
                                HStack { Text(trade.asset).font(.caption.monospaced()); Text(trade.side.uppercased()).font(.caption2.monospaced()).foregroundStyle(trade.side == "buy" ? PGTheme.positive : PGTheme.negative); Spacer(); Text("QTY \(trade.quantity?.description ?? "—")").font(.caption2.monospaced()); Text("P&L \(PGFormat.money(trade.pnl))").font(.caption2.monospaced()) }
                            }
                        }
                    }
                    HStack { Text("\(run.asset) · \(run.mode) · \(run.spec["signal"] ?? "")").font(.caption2.monospaced()).foregroundStyle(.secondary); Spacer(); Text("\(run.creditsSpent ?? 0) CREDITS").font(.caption2.monospaced()).foregroundStyle(.secondary) }
                }.padding()
            }
        }
    }
    private func metric(_ label: String, _ value: String) -> some View { VStack(alignment: .leading, spacing: 3) { Text(label).font(.caption2.monospaced()).foregroundStyle(.secondary); Text(value).font(.headline.monospacedDigit()) }.frame(maxWidth: .infinity, alignment: .leading) }
}
