import Observation
import SwiftUI

@MainActor @Observable final class PortfolioViewModel {
    enum Range: String, CaseIterable, Identifiable { case day = "1D", week = "1W", month = "1M", all = "ALL"; var id: String { rawValue } }
    var portfolio: LoadState<Portfolio> = .idle; var autopilot: LoadState<Autopilot> = .idle; var range: Range = .month; var busy = ""; var error: APIError?; var walletAddress = ""
    private let repository: PortfolioRepository
    private let ibkrOAuth = IBKROAuthCoordinator()
    init(repository: PortfolioRepository) { self.repository = repository }
    func load() async { portfolio = .loading; autopilot = .loading; async let p = loadPortfolio(); async let a = loadAutopilot(); _ = await (p, a) }
    private func loadPortfolio() async { do { let result = try await repository.cachedSnapshot(); portfolio = result.value.connected ? result.cachedAt.map { .stale(result.value, $0) } ?? .loaded(result.value) : .empty } catch { portfolio = .failed(error as? APIError ?? .transport(error.localizedDescription)) } }
    private func loadAutopilot() async { do { autopilot = .loaded(try await repository.autopilot()) } catch { autopilot = .failed(error as? APIError ?? .transport(error.localizedDescription)) } }
    func connectPlaid() async { busy = "plaid"; defer { busy = "" }; do { let token = try await repository.plaidLinkToken(); let result = try await PlaidLinkCoordinator.open(token: token); portfolio = .loaded(try await repository.exchangePlaid(publicToken: result.publicToken, institution: result.institution)); await loadAutopilot() } catch let e as APIError where e == .canceled {} catch { self.error = error as? APIError ?? .transport(error.localizedDescription) } }
    func connectHyperliquid() async { busy = "hyperliquid"; defer { busy = "" }; do { portfolio = .loaded(try await repository.connectHyperliquid(address: walletAddress)); walletAddress = ""; await loadAutopilot() } catch { self.error = error as? APIError ?? .transport(error.localizedDescription) } }
    func connectIBKR() async { busy = "ibkr"; defer { busy = "" }; do { portfolio = .loaded(try await ibkrOAuth.connect(repository: repository)); await loadAutopilot() } catch let error as APIError where error == .canceled {} catch { self.error = error as? APIError ?? .transport(error.localizedDescription) } }
    func sync(_ id: String) async { busy = id; defer { busy = "" }; do { portfolio = .loaded(try await repository.sync(id)) } catch { self.error = error as? APIError ?? .transport(error.localizedDescription) } }
    func disconnect(_ id: String) async { busy = id; defer { busy = "" }; do { let value = try await repository.disconnect(id); portfolio = value.connected ? .loaded(value) : .empty; await loadAutopilot() } catch { self.error = error as? APIError ?? .transport(error.localizedDescription) } }
    func runReview() async { busy = "review"; defer { busy = "" }; do { autopilot = .loaded(try await repository.runAutopilot()) } catch { self.error = error as? APIError ?? .transport(error.localizedDescription) } }
    func filtered(_ points: [NAVPoint]) -> [NAVPoint] { let days: TimeInterval? = switch range { case .day: 1; case .week: 7; case .month: 30; case .all: nil }; guard let days else { return points }; let cutoff = Date().addingTimeInterval(-days * 86_400); return points.filter { $0.date >= cutoff } }
}

struct PortfolioView: View {
    @State private var model: PortfolioViewModel
    init(repository: PortfolioRepository) { _model = State(initialValue: PortfolioViewModel(repository: repository)) }
    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 22) {
                PortfolioSummary(model: model)
                PGSectionHeader(index: "02", title: "Connections")
                PortfolioConnections(model: model)
                PGSectionHeader(index: "03", title: "Autopilot review", trailing: "RESEARCH ONLY")
                AutopilotReview(model: model)
                RiskDisclosureView()
            }
            .padding(16)
        }
        .navigationTitle("Portfolio")
        .navigationBarTitleDisplayMode(.inline)
        .task { await model.load() }
        .refreshable { await model.load() }
        .alert("Portfolio", isPresented: Binding(
            get: { model.error != nil },
            set: { if !$0 { model.error = nil } }
        )) {
            Button("OK") { }
        } message: {
            Text(model.error?.localizedDescription ?? "")
        }
    }
}

private struct PortfolioSummary: View {
    @Bindable var model: PortfolioViewModel

    var body: some View {
        switch model.portfolio {
        case .loading, .idle:
            ProgressView("Loading real portfolio…")
                .frame(maxWidth: .infinity, minHeight: 260)
        case .empty:
            StateView(
                title: "No portfolio connected",
                detail: "Connect a read-only account. PureGamma never requests trading or withdrawal permission.",
                symbol: "link.badge.plus"
            )
        case .failed(let error):
            StateView(
                title: error.presentation == .offline ? "Offline" : "Portfolio unavailable",
                detail: LocalizedStringKey(error.localizedDescription),
                symbol: "wifi.exclamationmark",
                retry: { Task { await model.load() } }
            )
        case .loaded(let portfolio):
            loaded(portfolio, cachedAt: nil)
        case .stale(let portfolio, let cachedAt):
            loaded(portfolio, cachedAt: cachedAt)
        }
    }

    private func loaded(_ portfolio: Portfolio, cachedAt: Date?) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            if let cachedAt { StaleDataBanner(cachedAt: cachedAt) }
            HStack {
                VStack(alignment: .leading) {
                    Text("PORTFOLIO NAV").font(.caption2.monospaced()).foregroundStyle(.secondary)
                    Text(PGFormat.money(portfolio.nav))
                        .font(.system(.largeTitle, design: .rounded).weight(.semibold))
                        .contentTransition(.numericText())
                        .lineLimit(1)
                        .minimumScaleFactor(0.5)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                Spacer()
                Text(portfolio.stale ? "STALE" : "CURRENT")
                    .font(.caption.monospaced())
                    .foregroundStyle(portfolio.stale ? PGTheme.warning : PGTheme.positive)
            }
            Text("Available \(PGFormat.money(portfolio.availableCash)) · As of \(PGFormat.dateTime(portfolio.asOf))")
                .font(.caption)
                .foregroundStyle(.secondary)
            RangePicker(model: model)
            let points = model.filtered(portfolio.history)
            if points.count > 1 {
                NAVChart(points: points)
            } else {
                StateView(
                    title: "Not enough history",
                    detail: "The real NAV curve appears after at least two account snapshots.",
                    symbol: "chart.xyaxis.line"
                )
            }
        }
        .accessibilityElement(children: .contain)
    }
}

private struct RangePicker: View {
    @Bindable var model: PortfolioViewModel
    var body: some View {
        HStack(spacing: 4) {
            ForEach(PortfolioViewModel.Range.allCases) { range in
                Button(range.rawValue) { model.range = range }
                    .buttonStyle(.bordered)
                    .tint(model.range == range ? PGTheme.accent : .secondary)
            }
        }
    }
}

private struct PortfolioConnections: View {
    @Bindable var model: PortfolioViewModel

    var body: some View {
        VStack(spacing: 12) {
            connectionRows
            Button { Task { await model.connectPlaid() } } label: {
                Label(model.busy == "plaid" ? "Opening Plaid…" : "Connect Plaid Investments", systemImage: "building.columns")
            }
            .buttonStyle(.bordered)
            .disabled(model.busy != "")
            Button { Task { await model.connectIBKR() } } label: {
                Label(model.busy == "ibkr" ? "Opening IBKR…" : "Connect Interactive Brokers", systemImage: "safari")
            }
            .buttonStyle(.bordered)
            .disabled(model.busy != "")
            HStack {
                TextField("Hyperliquid public 0x address", text: $model.walletAddress)
                    .textInputAutocapitalization(.never)
                    .font(.caption.monospaced())
                    .padding(9)
                    .background(PGTheme.secondaryBackground)
                Button("Connect") { Task { await model.connectHyperliquid() } }
                    .disabled(model.walletAddress.isEmpty || model.busy != "")
            }
        }
    }

    @ViewBuilder private var connectionRows: some View {
        switch model.portfolio {
        case .loaded(let value), .stale(let value, _):
            ForEach(value.connections) { connection in
                ConnectionRow(connection: connection, model: model)
                TerminalDivider()
            }
        default:
            EmptyView()
        }
    }
}

private struct ConnectionRow: View {
    let connection: PortfolioConnection
    @Bindable var model: PortfolioViewModel

    var body: some View {
        HStack {
            VStack(alignment: .leading) {
                Text(connection.name).font(.headline)
                Text("\(connection.provider.uppercased()) · \(PGFormat.dateTime(connection.lastSync))")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                if let error = connection.error {
                    Text(error).font(.caption2).foregroundStyle(PGTheme.negative)
                }
            }
            Spacer()
            Text(connection.status)
                .font(.caption2.monospaced())
                .foregroundStyle(connection.status == "CONNECTED" ? PGTheme.positive : PGTheme.warning)
            Menu {
                Button("Sync") { Task { await model.sync(connection.id) } }
                Button("Disconnect", role: .destructive) { Task { await model.disconnect(connection.id) } }
            } label: {
                if model.busy == connection.id { ProgressView() } else { Image(systemName: "ellipsis.circle") }
            }
        }
        .padding(.vertical, 8)
    }
}

private struct AutopilotReview: View {
    @Bindable var model: PortfolioViewModel

    var body: some View {
        switch model.autopilot {
        case .loading, .idle:
            ProgressView()
        case .failed(let error):
            StateView(
                title: "Autopilot unavailable",
                detail: LocalizedStringKey(error.localizedDescription),
                symbol: "exclamationmark.shield",
                retry: { Task { await model.load() } }
            )
        case .empty:
            EmptyView()
        case .loaded(let value), .stale(let value, _):
            loaded(value)
        }
    }

    private func loaded(_ value: Autopilot) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Synchronizes accounts, reviews concentration and freshness, and watches long-gamma opportunities. It never places orders or rebalances.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
            HStack {
                Text(value.enabled ? "ENABLED" : "DISABLED")
                    .font(.caption.monospaced())
                    .foregroundStyle(value.enabled ? PGTheme.positive : .secondary)
                Spacer()
                Button("Run review") { Task { await model.runReview() } }
                    .buttonStyle(.bordered)
                    .disabled(value.accountCount == 0 || model.busy != "")
            }
            if value.findings.isEmpty {
                Text(value.accountCount == 0 ? "Connect a real account to enable reviews." : "No completed review findings.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                ForEach(Array(value.findings.enumerated()), id: \.offset) { _, finding in
                    FindingRow(finding: finding)
                }
            }
        }
    }
}

private struct FindingRow: View {
    let finding: AutopilotFinding
    var body: some View {
        Label(finding.title, systemImage: finding.severity == "high" ? "exclamationmark.triangle" : "info.circle")
            .font(.caption)
            .foregroundStyle(finding.severity == "high" ? PGTheme.negative : PGTheme.warning)
    }
}

struct NAVChart: View {
    let points: [NAVPoint]
    @State private var selected: Int?

    var body: some View {
        GeometryReader { geometry in
            chart
                .contentShape(Rectangle())
                .gesture(dragGesture(width: geometry.size.width))
                .overlay(alignment: .topLeading) { tooltip }
        }
        .frame(height: 230)
        .accessibilityElement()
        .accessibilityLabel("Portfolio NAV history chart")
        .accessibilityValue(accessibilitySummary)
    }

    private var values: [Double] {
        points.map { NSDecimalNumber(decimal: $0.value).doubleValue }
    }

    private var chart: some View {
        let chartValues = values
        return Canvas { context, size in
            guard points.count > 1,
                  let minValue = chartValues.min(),
                  let maxValue = chartValues.max() else { return }
            let span = Swift.max(maxValue - minValue, 0.01)
            func position(_ index: Int) -> CGPoint {
                CGPoint(
                    x: size.width * CGFloat(index) / CGFloat(points.count - 1),
                    y: size.height - size.height * CGFloat((chartValues[index] - minValue) / span)
                )
            }
            var path = Path()
            path.move(to: position(0))
            for index in 1..<points.count { path.addLine(to: position(index)) }
            let isPositive = (chartValues.last ?? 0) >= (chartValues.first ?? 0)
            context.stroke(path, with: .color(isPositive ? PGTheme.positive : PGTheme.negative), lineWidth: 2)
            if let selected {
                let point = position(selected)
                var crosshair = Path()
                crosshair.move(to: CGPoint(x: point.x, y: 0))
                crosshair.addLine(to: CGPoint(x: point.x, y: size.height))
                context.stroke(crosshair, with: .color(.secondary.opacity(0.5)), style: StrokeStyle(lineWidth: 1, dash: [3]))
                context.fill(Path(ellipseIn: CGRect(x: point.x - 4, y: point.y - 4, width: 8, height: 8)), with: .color(.primary))
            }
        }
    }

    private func dragGesture(width: CGFloat) -> some Gesture {
        DragGesture(minimumDistance: 0)
            .onChanged { value in
                guard points.count > 1 else { return }
                let ratio = value.location.x / Swift.max(width, 1)
                selected = Swift.min(points.count - 1, Swift.max(0, Int(round(ratio * CGFloat(points.count - 1)))))
            }
            // The last selection is kept after release so the value can be
            // read without keeping a finger on the screen.
    }

    @ViewBuilder private var tooltip: some View {
        if let selected {
            Text("\(PGFormat.money(points[selected].value)) · \(PGFormat.dateTime(points[selected].date))")
                .font(.caption.monospacedDigit())
                .padding(6)
                .background(.thinMaterial)
        }
    }

    private var accessibilitySummary: String {
        if let selected {
            return "\(PGFormat.money(points[selected].value)) at \(PGFormat.dateTime(points[selected].date))"
        }
        return "\(points.count) real data points"
    }
}
