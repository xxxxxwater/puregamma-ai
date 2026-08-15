import Observation
import SwiftUI

// MARK: - 列表

@MainActor @Observable final class TradingSafetyViewModel {
    var mandates: LoadState<[TradingMandate]> = .idle
    var error: APIError?
    let repository: TradingMandatesRepository
    let capabilities: MobileCapabilities

    init(repository: TradingMandatesRepository, capabilities: MobileCapabilities) {
        self.repository = repository
        self.capabilities = capabilities
    }

    var isAvailable: Bool { capabilities.serverContractAvailable && capabilities.autoTradingEnabled && capabilities.userCanViewTradingMandates }

    func load() async {
        mandates = .loading
        do { let rows = try await repository.mandates(); mandates = rows.isEmpty ? .empty : .loaded(rows) } catch let error as APIError { mandates = .failed(error) } catch { mandates = .failed(.transport(error.localizedDescription)) }
    }
}

struct TradingSafetyView: View {
    @State private var model: TradingSafetyViewModel

    init(repository: TradingMandatesRepository, capabilities: MobileCapabilities) {
        _model = State(initialValue: TradingSafetyViewModel(repository: repository, capabilities: capabilities))
    }

    var body: some View {
        Group {
            if !model.isAvailable { unavailable } else { content }
        }
        .navigationTitle("Trading safety").navigationBarTitleDisplayMode(.inline)
        .task { await model.load() }
        .refreshable { await model.load() }
        .alert("Trading", isPresented: Binding(get: { model.error != nil }, set: { if !$0 { model.error = nil } })) { Button("OK") {} } message: { Text(model.error?.localizedDescription ?? "") }
    }

    private var unavailable: some View {
        StateView(
            title: "Auto trading unavailable",
            detail: LocalizedStringKey(!model.capabilities.serverContractAvailable
                ? "The backend has not exposed this feature yet. It will appear here once enabled."
                : "Auto-trading mandates are disabled for your account. LIVE trading is never available in this app."),
            symbol: "lock.shield"
        )
    }

    @ViewBuilder private var content: some View {
        VStack(spacing: 0) {
            liveDisabledBanner
            switch model.mandates {
            case .loading, .idle: ProgressView("Loading mandates…").frame(maxWidth: .infinity, maxHeight: .infinity)
            case .empty: StateView(title: "No mandates", detail: "No auto-trading mandates exist for your account.", symbol: "doc.plaintext")
            case .failed(let error): StateView(title: "Mandates unavailable", detail: LocalizedStringKey(error.localizedDescription), symbol: "exclamationmark.shield", retry: { Task { await model.load() } })
            case .loaded(let rows), .stale(let rows, _):
                List(rows) { mandate in
                    NavigationLink { MandateDetailView(repository: model.repository, mandate: mandate, capabilities: model.capabilities) } label: { TradingMandateRow(mandate: mandate) }
                }
                .listStyle(.plain)
            }
        }
    }

    /// LIVE 在任何配置下都不可操作：这里只展示状态，不渲染任何启动/启用按钮。
    private var liveDisabledBanner: some View {
        HStack(spacing: 10) {
            Image(systemName: "lock.fill").foregroundStyle(PGTheme.warning)
            VStack(alignment: .leading, spacing: 2) {
                Text("LIVE trading is permanently disabled in this app").font(.caption).bold()
                Text("No orders can be placed from mobile. All trading goes through the server Trading Control Plane.").font(.caption2).foregroundStyle(.secondary)
            }
            Spacer()
        }
        .padding(12)
        .background(RoundedRectangle(cornerRadius: 10).fill(PGTheme.secondaryBackground))
        .padding(.horizontal)
        .accessibilityElement(children: .combine)
    }
}

struct TradingMandateRow: View {
    let mandate: TradingMandate
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(mandate.name).font(.headline).lineLimit(2)
                Spacer()
                TradingEnvironmentBadge(environment: mandate.environment)
            }
            HStack(spacing: 12) {
                Label(mandate.paused ? "Paused" : "Running", systemImage: mandate.paused ? "pause.circle" : "play.circle").font(.caption)
                if let reason = mandate.riskBlockReason { Label("Risk block: \(reason)", systemImage: "exclamationmark.triangle").font(.caption).foregroundStyle(PGTheme.warning) }
                Spacer()
                Text(PGFormat.dateTime(mandate.updatedAt)).font(.caption2).foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 6)
        .accessibilityElement(children: .combine)
    }
}

struct TradingEnvironmentBadge: View {
    let environment: TradingEnvironment
    private var label: String {
        switch environment {
        case .off: "OFF"
        case .paper: "PAPER"
        case .shadow: "SHADOW"
        case .liveDisabled: "LIVE_DISABLED"
        case .unavailable: "—"
        }
    }
    private var color: Color {
        switch environment {
        case .paper, .shadow: PGTheme.accent
        case .liveDisabled: PGTheme.negative
        case .off: .secondary
        case .unavailable: .secondary
        }
    }
    var body: some View {
        Text(label).font(.caption2.monospaced()).foregroundStyle(color).padding(.horizontal, 8).padding(.vertical, 3)
            .overlay(RoundedRectangle(cornerRadius: 6).stroke(color.opacity(0.6)))
            .accessibilityLabel("Trading environment \(label)")
    }
}

// MARK: - 详情

@MainActor @Observable final class MandateDetailViewModel {
    var status: LoadState<MandateStatus> = .idle
    var risk: LoadState<MandateRiskLimits> = .idle
    var error: APIError?
    let repository: TradingMandatesRepository
    let capabilities: MobileCapabilities

    init(repository: TradingMandatesRepository, capabilities: MobileCapabilities) {
        self.repository = repository
        self.capabilities = capabilities
    }

    func load(_ id: String) async {
        status = .loading; risk = .loading
        async let s: Void = loadStatus(id)
        async let r: Void = loadRisk(id)
        _ = await (s, r)
    }
    private func loadStatus(_ id: String) async {
        do { status = .loaded(try await repository.status(id)) } catch { status = .failed(error.mobileAPIError) }
    }
    private func loadRisk(_ id: String) async {
        do { risk = .loaded(try await repository.risk(id)) } catch { risk = .failed(error.mobileAPIError) }
    }

    /// 操作后必须以服务端状态为准：重新 GET status，不依据本地 paused 认定成功。
    func pause(_ id: String) async {
        do {
            _ = try await repository.pause(id)
            await loadStatus(id)
        } catch { self.error = error.mobileAPIError }
    }
    func resume(_ id: String) async {
        do {
            _ = try await repository.resume(id)
            await loadStatus(id)
        } catch { self.error = error.mobileAPIError }
    }
}

struct MandateDetailView: View {
    @State private var model: MandateDetailViewModel
    let mandate: TradingMandate
    let capabilities: MobileCapabilities

    init(repository: TradingMandatesRepository, mandate: TradingMandate, capabilities: MobileCapabilities) {
        self.mandate = mandate
        self.capabilities = capabilities
        _model = State(initialValue: MandateDetailViewModel(repository: repository, capabilities: capabilities))
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                header
                statusSection
                riskSection
                TerminalDivider()
                safetyNotice
            }
            .padding()
        }
        .navigationTitle("Mandate").navigationBarTitleDisplayMode(.inline)
        .task { await model.load(mandate.id) }
        .alert("Trading", isPresented: Binding(get: { model.error != nil }, set: { if !$0 { model.error = nil } })) { Button("OK") {} } message: { Text(model.error?.localizedDescription ?? "") }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text(mandate.name).font(.title2.bold())
                Spacer()
                TradingEnvironmentBadge(environment: mandate.environment)
            }
            Text(mandate.strategyName).font(.caption.monospaced()).foregroundStyle(PGTheme.accent)
            LabeledContent("Created", value: PGFormat.dateTime(mandate.createdAt))
            LabeledContent("Last run", value: PGFormat.dateTime(mandate.lastRunAt))
            if let status = mandate.lastRunStatus { LabeledContent("Last run status", value: status) }
            if let reason = mandate.riskBlockReason {
                Label("Risk blocked: \(reason)", systemImage: "exclamationmark.triangle.fill").font(.subheadline).foregroundStyle(PGTheme.warning)
            }
        }
    }

    @ViewBuilder private var statusSection: some View {
        PGSectionHeader(index: "01", title: "Status")
        switch model.status {
        case .loading, .idle: ProgressView()
        case .empty: StateView(title: "Status unavailable", detail: "The server returned no status for this mandate yet.", symbol: "questionmark.circle", retry: { Task { await model.load(mandate.id) } })
        case .failed(let error): StateView(title: "Status unavailable", detail: LocalizedStringKey(error.localizedDescription), symbol: "exclamationmark.shield", retry: { Task { await model.load(mandate.id) } })
        case .loaded(let status), .stale(let status, _):
            VStack(alignment: .leading, spacing: 10) {
                TradingEnvironmentBadge(environment: status.environment)
                LabeledContent("Running", value: status.running ? "Yes" : "No")
                LabeledContent("Paused", value: status.paused ? "Yes" : "No")
                LabeledContent("Blocked by risk", value: status.blockedByRisk ? "Yes" : "No")
                if let reason = status.blockReason { LabeledContent("Block reason", value: reason) }
                actions(environment: status.environment, paused: status.paused)
            }
        }
    }

    /// 动作策略：仅 PAPER/SHADOW + 服务端能力允许时渲染按钮；LIVE 永不渲染。
    @ViewBuilder private func actions(environment: TradingEnvironment, paused: Bool) -> some View {
        if environment.isLive {
            Label("LIVE is disabled and cannot be started from this app.", systemImage: "lock.fill").font(.caption).foregroundStyle(PGTheme.negative)
        } else if MandateActionPolicy.pauseAllowed(environment: environment, paused: paused, capabilities: capabilities) {
            Button { Task { await model.pause(mandate.id) } } label: { Label("Pause mandate", systemImage: "pause.circle").frame(maxWidth: .infinity) }.buttonStyle(.bordered)
        } else if MandateActionPolicy.resumeAllowed(environment: environment, paused: paused, capabilities: capabilities) {
            Button { Task { await model.resume(mandate.id) } } label: { Label("Resume mandate", systemImage: "play.circle").frame(maxWidth: .infinity) }.buttonStyle(.bordered).tint(PGTheme.accent)
        }
    }

    @ViewBuilder private var riskSection: some View {
        PGSectionHeader(index: "02", title: "Risk limits")
        switch model.risk {
        case .loading, .idle: ProgressView()
        case .empty: StateView(title: "Risk limits unavailable", detail: "The server returned no risk limits for this mandate yet.", symbol: "questionmark.circle", retry: { Task { await model.load(mandate.id) } })
        case .failed(let error): StateView(title: "Risk limits unavailable", detail: LocalizedStringKey(error.localizedDescription), symbol: "gauge.with.dots.needle.33percent", retry: { Task { await model.load(mandate.id) } })
        case .loaded(let limits), .stale(let limits, _):
            VStack(alignment: .leading, spacing: 10) {
                LabeledContent("Max notional", value: limits.maxNotional.map { PGFormat.money($0) } ?? "—")
                LabeledContent("Daily loss limit", value: limits.dailyLossLimit.map { PGFormat.money($0) } ?? "—")
                LabeledContent("Max leverage", value: limits.maxLeverage.map { "\($0)×" } ?? "—")
                LabeledContent("Max position size", value: limits.maxPositionSizePct.map { "\($0)%" } ?? "—")
            }
        }
    }

    private var safetyNotice: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Read-only control surface").font(.caption).bold()
            Text("This screen only displays mandate state and risk limits. Orders are never placed from mobile, risk limits cannot be changed here, and all pause/resume actions are re-verified by the server Trading Control Plane.").font(.caption2).foregroundStyle(.secondary)
            RiskDisclosureView()
        }
    }
}
