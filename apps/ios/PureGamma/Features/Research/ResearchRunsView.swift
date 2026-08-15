import Observation
import SwiftUI

// MARK: - 列表 ViewModel

@MainActor @Observable final class ResearchRunsViewModel {
    var runs: LoadState<[ResearchRun]> = .idle
    var error: APIError?
    let repository: ResearchRunsRepository
    let capabilities: MobileCapabilities

    init(repository: ResearchRunsRepository, capabilities: MobileCapabilities) {
        self.repository = repository
        self.capabilities = capabilities
    }

    var isAvailable: Bool { capabilities.serverContractAvailable && capabilities.harnessResearchEnabled }

    func load() async {
        runs = .loading
        do {
            let result = try await repository.runs()
            runs = result.value.isEmpty ? .empty : result.cachedAt.map { .stale(result.value, $0) } ?? .loaded(result.value)
        } catch {
            runs = .failed(error.mobileAPIError)
        }
    }

    func cancel(_ id: String) async {
        do { try await replaceRun(id, with: repository.cancel(id)) } catch { self.error = error.mobileAPIError }
    }
    func retry(_ id: String) async {
        do { try await replaceRun(id, with: repository.retry(id)) } catch { self.error = error.mobileAPIError }
    }
    private func replaceRun(_ id: String, with request: ResearchRun) async throws {
        if case .loaded(var rows) = runs, let index = rows.firstIndex(where: { $0.id == id }) {
            rows[index] = request; runs = .loaded(rows)
        }
    }
}

// MARK: - 列表

struct ResearchRunsView: View {
    @Environment(AppState.self) private var app
    @State private var model: ResearchRunsViewModel
    @State private var showStart = false
    @State private var showError = false

    init(repository: ResearchRunsRepository, capabilities: MobileCapabilities) {
        _model = State(initialValue: ResearchRunsViewModel(repository: repository, capabilities: capabilities))
    }

    var body: some View {
        Group {
            if !model.isAvailable {
                unavailable
            } else {
                content
            }
        }
        .navigationTitle("Research runs").navigationBarTitleDisplayMode(.inline)
        .task { await model.load() }
        .refreshable { await model.load() }
        .sheet(isPresented: $showStart) {
            ResearchStartView(repository: model.repository, capabilities: model.capabilities) { runID in
                app.pendingResearchRunID = runID
            }
        }
        .alert("Research run", isPresented: Binding(get: { model.error != nil }, set: { if !$0 { model.error = nil } })) { Button("OK") {} } message: { Text(model.error?.localizedDescription ?? "") }
    }

    private var unavailable: some View {
        VStack(spacing: 12) {
            StateView(
                title: "Harness research unavailable",
                detail: LocalizedStringKey(capabilityMessage),
                symbol: "lock.doc"
            )
        }
    }

    private var capabilityMessage: String {
        if !model.capabilities.serverContractAvailable { return String(localized: "The backend has not exposed this feature yet. It will appear here once enabled.") }
        if !model.capabilities.harnessResearchEnabled { return String(localized: "Harness research is disabled for your account or plan.") }
        return model.capabilities.maintenanceMessage ?? String(localized: "Feature not available yet")
    }

    @ViewBuilder private var content: some View {
        switch model.runs {
        case .loading, .idle:
            ProgressView("Loading research runs…").frame(maxWidth: .infinity, maxHeight: .infinity)
        case .empty:
            StateView(title: "No research runs", detail: "Start a harness research task and its progress will appear here.", symbol: "doc.text.magnifyingglass")
        case .failed(let error):
            StateView(title: "Research runs unavailable", detail: LocalizedStringKey(error.localizedDescription), symbol: "doc.badge.ellipsis", retry: { Task { await model.load() } })
        case .loaded(let rows):
            runList(rows, cachedAt: nil)
        case .stale(let rows, let cachedAt):
            VStack(spacing: 8) { StaleDataBanner(cachedAt: cachedAt).padding(.horizontal); runList(rows, cachedAt: cachedAt) }
        }
    }

    private func runList(_ rows: [ResearchRun], cachedAt: Date?) -> some View {
        VStack(spacing: 0) {
            Button { showStart = true } label: {
                HStack { Label("Start research", systemImage: "sparkles"); Spacer(); Image(systemName: "arrow.right") }
                    .font(.footnote).padding(.horizontal, 12).padding(.vertical, 8)
            }
            .buttonStyle(.bordered).tint(PGTheme.accent)
            .disabled(!model.capabilities.userCanStartResearch)
            .padding(.horizontal).padding(.vertical, 6)
            List(rows) { run in
                NavigationLink { ResearchRunDetailView(repository: model.repository, runID: run.id, capabilities: model.capabilities) } label: { ResearchRunRow(run: run) }
            }
            .listStyle(.plain)
        }
    }
}

struct ResearchRunRow: View {
    let run: ResearchRun
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(run.name).font(.headline).lineLimit(2)
                Spacer()
                ResearchStateBadge(state: run.state)
            }
            HStack(spacing: 14) {
                Label("\(run.evidenceCount)", systemImage: "doc.richtext").font(.caption)
                Label("\(run.citationCount)", systemImage: "quote.opening").font(.caption)
                if run.isDegraded || run.effectiveVerification == .degraded { Label("Degraded", systemImage: "exclamationmark.triangle").font(.caption).foregroundStyle(PGTheme.warning) }
                Spacer()
                Text(PGFormat.dateTime(run.updatedAt)).font(.caption2).foregroundStyle(.secondary)
            }
            if let error = run.errorMessage { Text(error).font(.caption).foregroundStyle(PGTheme.negative).lineLimit(2) }
        }
        .padding(.vertical, 6)
        .accessibilityElement(children: .combine)
    }
}

struct ResearchStateBadge: View {
    let state: ResearchRunState
    private var color: Color {
        switch state {
        case .completed: PGTheme.positive
        case .degraded: PGTheme.warning
        case .failed, .canceled, .timedOut: PGTheme.negative
        case .running, .validating: PGTheme.accent
        default: .secondary
        }
    }
    var body: some View {
        Text(state.rawValue.uppercased())
            .font(.caption2.monospaced())
            .foregroundStyle(color)
            .padding(.horizontal, 8).padding(.vertical, 3)
            .overlay(RoundedRectangle(cornerRadius: 6).stroke(color.opacity(0.6)))
            .accessibilityLabel("Status \(state.rawValue)")
    }
}

// MARK: - 详情 ViewModel（SSE + 断线恢复 + 最终状态以服务端为准）

@MainActor @Observable final class ResearchRunDetailViewModel {
    var run: LoadState<ResearchRun> = .idle
    var evidence: LoadState<[ResearchEvidence]> = .idle
    var liveStage: String?
    var liveProgress: Int?
    var liveEvidenceCount: Int?
    var error: APIError?
    let repository: ResearchRunsRepository
    let capabilities: MobileCapabilities
    private var watchTask: Task<Void, Never>?

    init(repository: ResearchRunsRepository, capabilities: MobileCapabilities) {
        self.repository = repository
        self.capabilities = capabilities
    }

    func load(_ id: String) async {
        if case .idle = run { run = .loading }
        do { run = .loaded(try await repository.run(id)) } catch { run = .failed(error.mobileAPIError) }
        if case .idle = evidence { await loadEvidence(id) }
        watch(id: id)
    }

    /// 视图离开/后台时必须停止事件流；SSE 只负责进度，最终一致性永远以 GET 为准。
    func stop() {
        watchTask?.cancel()
        watchTask = nil
    }

    /// 回到前台：重新查服务端最终状态后再订阅。
    func resume(_ id: String) async {
        do { run = .loaded(try await repository.run(id)) } catch { /* 保留现有展示，不做覆盖 */ }
        watch(id: id)
    }

    private func loadEvidence(_ id: String) async {
        evidence = .loading
        do { let rows = try await repository.evidence(id); evidence = rows.isEmpty ? .empty : .loaded(rows) } catch { evidence = .failed(error.mobileAPIError) }
    }

    /// 订阅事件流：断线重连（有限次数+退避）；重连失败转轮询；
    /// SSE 异常绝不影响任务状态判定，任务失败只能来自服务端查询。
    private func watch(id: String) {
        watchTask?.cancel()
        watchTask = Task {
            var streamAttempts = 0
            var pollCount = 0
            while !Task.isCancelled {
                if streamAttempts < 3 {
                    streamAttempts += 1
                    let sawTerminal = await consumeStream(id: id)
                    if sawTerminal { break }
                    try? await Task.sleep(for: .seconds(2))
                    continue
                }
                // 断线/重连失败：以服务端最终状态为准；活跃则继续低频轮询（受视图生命周期控制）。
                if let updated = try? await repository.run(id) { run = .loaded(updated) }
                if case .loaded(let value) = run, value.state.isTerminal { break }
                pollCount += 1
                try? await Task.sleep(for: .seconds(pollCount < 6 ? 10 : 30))
            }
        }
    }

    /// 消费一轮事件流。返回是否到达终止状态。任何流错误都被吞掉并触发服务端对账。
    private func consumeStream(id: String) async -> Bool {
        do {
            let stream = try await repository.events(id)
            var terminal = false
            for try await event in stream {
                apply(event)
                switch event {
                case .stateChanged(let state) where state.isTerminal: terminal = true
                case .completed, .failed, .canceled: terminal = true
                default: break
                }
                if terminal { break }
            }
            return terminal
        } catch {
            return false
        }
    }

    private func apply(_ event: ResearchRunEvent) {
        switch event {
        case .stateChanged(let state):
            if case .loaded(var value) = run { value.state = state; run = .loaded(value) }
        case .progress(let stage, let percent): liveStage = stage; liveProgress = percent
        case .evidenceAdded(let count): liveEvidenceCount = count
        case .completed(let verified, let degraded):
            if case .loaded(var value) = run {
                value.verification = verified ? .verified : .partial
                value.isDegraded = degraded || value.isDegraded
                run = .loaded(value)
            }
        case .failed(let message):
            if case .loaded(var value) = run { value.state = .failed; value.errorMessage = message; run = .loaded(value) }
        case .canceled:
            if case .loaded(var value) = run { value.state = .canceled; run = .loaded(value) }
        case .unknown: break
        }
    }

    func cancel(_ id: String) async {
        do { run = .loaded(try await repository.cancel(id)) } catch { self.error = error.mobileAPIError }
    }
    func retry(_ id: String) async {
        do { run = .loaded(try await repository.retry(id)) } catch { self.error = error.mobileAPIError }
    }
}

// MARK: - 详情

struct ResearchRunDetailView: View {
    @Environment(\.scenePhase) private var scenePhase
    @State private var model: ResearchRunDetailViewModel
    let runID: String
    let capabilities: MobileCapabilities
    init(repository: ResearchRunsRepository, runID: String, capabilities: MobileCapabilities) {
        self.runID = runID
        self.capabilities = capabilities
        _model = State(initialValue: ResearchRunDetailViewModel(repository: repository, capabilities: capabilities))
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                switch model.run {
                case .loading, .idle: ProgressView("Loading run…").frame(maxWidth: .infinity, minHeight: 160)
                case .empty: StateView(title: "Run unavailable", detail: "The server returned no data for this run yet.", symbol: "doc.questionmark", retry: { Task { await model.load(runID) } })
                case .failed(let error): StateView(title: "Run unavailable", detail: LocalizedStringKey(error.localizedDescription), symbol: "exclamationmark.triangle", retry: { Task { await model.load(runID) } })
                case .loaded(let run), .stale(let run, _):
                    header(run)
                    verificationBanner(run)
                    progressSection(run)
                    TerminalDivider()
                    details(run)
                    TerminalDivider()
                    timeline(run)
                    TerminalDivider()
                    evidenceSection
                    actions(run)
                    disclaimer(run)
                }
            }
            .padding()
        }
        .navigationTitle("Research run").navigationBarTitleDisplayMode(.inline)
        .task { await model.load(runID) }
        .onDisappear { model.stop() }
        .onChange(of: scenePhase) { _, phase in
            if phase == .background { model.stop() }
            if phase == .active { Task { await model.resume(runID) } }
        }
        .alert("Research run", isPresented: Binding(get: { model.error != nil }, set: { if !$0 { model.error = nil } })) { Button("OK") {} } message: { Text(model.error?.localizedDescription ?? "") }
    }

    private func header(_ run: ResearchRun) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(run.name).font(.title2.bold())
            HStack { ResearchStateBadge(state: run.state); if run.isDegraded { Text("DEGRADED").font(.caption2.monospaced()).foregroundStyle(PGTheme.warning) } }
            HStack(spacing: 14) {
                Label("Started", systemImage: "clock").font(.caption)
                Text(PGFormat.dateTime(run.createdAt)).font(.caption).foregroundStyle(.secondary)
                Label("Updated", systemImage: "arrow.clockwise").font(.caption)
                Text(PGFormat.dateTime(run.updatedAt)).font(.caption).foregroundStyle(.secondary)
            }
        }
    }

    private func verificationBanner(_ run: ResearchRun) -> some View {
        let verification = run.effectiveVerification
        let (symbol, color, text): (String, Color, LocalizedStringKey) = switch verification {
        case .verified: ("checkmark.seal.fill", PGTheme.positive, "Verified result")
        case .partial: ("checkmark.seal", PGTheme.accent, "Partial result — some evidence could not be verified")
        case .degraded: ("exclamationmark.triangle.fill", PGTheme.warning, "Degraded result — treat conclusions with extra caution")
        case .failed: ("xmark.octagon.fill", PGTheme.negative, "Failed result")
        case .incomplete: ("hourglass", .secondary, "Result not complete yet — awaiting final server state")
        }
        return Label(text, systemImage: symbol).font(.subheadline).foregroundStyle(color).padding(12).frame(maxWidth: .infinity, alignment: .leading).background(RoundedRectangle(cornerRadius: 10).fill(PGTheme.secondaryBackground)).accessibilityElement(children: .combine)
    }

    private func progressSection(_ run: ResearchRun) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            if run.state.isActive {
                if let stage = model.liveStage { Label("Stage: \(stage)", systemImage: "gearshape.2").font(.caption) }
                if let percent = model.liveProgress { ProgressView(value: Double(percent), total: 100).tint(PGTheme.accent); Text("\(percent)%").font(.caption2.monospaced()).foregroundStyle(.secondary) }
            }
            if let error = run.errorMessage { Label(error, systemImage: "exclamationmark.circle").font(.caption).foregroundStyle(PGTheme.negative) }
        }
    }

    private func details(_ run: ResearchRun) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            PGSectionHeader(index: "01", title: "Run details")
            LabeledContent("Credits used", value: "\(run.creditsUsed?.description ?? "—")\(run.creditsEstimate.map { " / est \($0)" } ?? "")")
            LabeledContent("Data scope", value: run.dataSources.isEmpty ? "—" : run.dataSources.joined(separator: ", "))
            LabeledContent("Evidence", value: "\(model.liveEvidenceCount ?? run.evidenceCount)")
            LabeledContent("Citations", value: String(run.citationCount))
            if let summary = run.summary { Text(summary).font(.subheadline).textSelection(.enabled) }
        }
    }

    private func timeline(_ run: ResearchRun) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            PGSectionHeader(index: "02", title: "Timeline")
            if run.transitions.isEmpty {
                Text("Server timeline not available yet.").font(.caption).foregroundStyle(.secondary)
            } else {
                ForEach(run.transitions) { transition in
                    HStack(spacing: 10) {
                        ResearchStateBadge(state: transition.state)
                        Spacer()
                        Text(PGFormat.dateTime(transition.at)).font(.caption2).foregroundStyle(.secondary)
                    }
                }
            }
        }
    }

    @ViewBuilder private var evidenceSection: some View {
        PGSectionHeader(index: "03", title: "Evidence & citations")
        switch model.evidence {
        case .loading, .idle: ProgressView().frame(maxWidth: .infinity, minHeight: 60)
        case .empty: Text("No evidence recorded yet.").font(.caption).foregroundStyle(.secondary)
        case .failed(let error): StateView(title: "Evidence unavailable", detail: LocalizedStringKey(error.localizedDescription), symbol: "doc.questionmark", retry: { Task { await model.load(runID) } })
        case .loaded(let rows), .stale(let rows, _):
            ForEach(rows) { evidence in
                NavigationLink { ResearchEvidenceView(evidence: evidence) } label: { ResearchEvidenceRow(evidence: evidence) }
                    .buttonStyle(.plain)
            }
        }
    }

    @ViewBuilder private func actions(_ run: ResearchRun) -> some View {
        if run.state.isActive && model.capabilities.userCanStartResearch {
            Button(role: .destructive) { Task { await model.cancel(runID) } } label: { Label("Cancel run", systemImage: "stop.circle").frame(maxWidth: .infinity) }.buttonStyle(.bordered)
        }
        if run.state.isRetryable && model.capabilities.harnessRetryEnabled {
            Button { Task { await model.retry(runID) } } label: { Label("Retry run", systemImage: "arrow.clockwise").frame(maxWidth: .infinity) }.buttonStyle(.bordered).tint(PGTheme.accent)
        }
    }

    private func disclaimer(_ run: ResearchRun) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(run.disclaimer ?? String(localized: "Research conclusions require human verification and are not factual assertions or investment advice."))
                .font(.caption2).foregroundStyle(.secondary)
            RiskDisclosureView()
        }
    }
}

struct ResearchEvidenceRow: View {
    let evidence: ResearchEvidence
    var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            HStack {
                Text("[\(evidence.citationIndex)] \(evidence.provider.uppercased())").font(.caption.monospaced()).foregroundStyle(PGTheme.accent)
                Spacer()
                if evidence.isVerified {
                    Label("Verified", systemImage: "checkmark.seal").font(.caption2).foregroundStyle(PGTheme.positive)
                } else {
                    Label("Unverified", systemImage: "questionmark.diamond").font(.caption2).foregroundStyle(PGTheme.warning)
                }
            }
            Text(evidence.title).font(.subheadline).lineLimit(3)
            if let excerpt = evidence.excerpt { Text(excerpt).font(.caption).foregroundStyle(.secondary).lineLimit(4) }
            if let note = evidence.verificationNote { Text(note).font(.caption2).foregroundStyle(PGTheme.warning) }
        }
        .padding(.vertical, 6)
        .accessibilityElement(children: .combine)
    }
}

struct ResearchEvidenceView: View {
    let evidence: ResearchEvidence
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                PGSectionHeader(index: String(evidence.citationIndex), title: LocalizedStringKey(evidence.title))
                Label(evidence.isVerified ? "Verified by server evidence pipeline" : "Unverified — included as raw source", systemImage: evidence.isVerified ? "checkmark.seal" : "questionmark.diamond")
                    .font(.caption).foregroundStyle(evidence.isVerified ? PGTheme.positive : PGTheme.warning)
                LabeledContent("Provider", value: evidence.provider)
                LabeledContent("Scope", value: evidence.sourceScope ?? "—")
                LabeledContent("Fetched", value: PGFormat.dateTime(evidence.fetchedAt))
                if let excerpt = evidence.excerpt { TerminalDivider(); Text(excerpt).font(.body).textSelection(.enabled) }
                if let url = evidence.url { Link("Open source", destination: url).font(.footnote) }
                TerminalDivider()
                Text("Evidence is displayed for verification purposes. Conclusions remain unverified unless the server marks them verified.").font(.caption2).foregroundStyle(.secondary)
            }
            .padding()
        }
        .navigationTitle("Evidence").navigationBarTitleDisplayMode(.inline)
    }
}

// MARK: - 启动研究（Agent 与 Runs 列表共用）

struct ResearchStartView: View {
    @Environment(\.dismiss) private var dismiss
    @Environment(\.locale) private var locale
    let repository: ResearchRunsRepository
    let capabilities: MobileCapabilities
    var onCreated: (String) -> Void

    @State private var name = ""
    @State private var prompt = ""
    @State private var dataSources: Set<String> = ["market"]
    @State private var submitting = false
    @State private var error: APIError?
    @State private var createdRunID: String?

    private static let availableSources = ["market", "news", "research"]

    var body: some View {
        NavigationStack {
            Form {
                Section("Research task") {
                    TextField("Task name", text: $name)
                    TextField("What should the harness investigate?", text: $prompt, axis: .vertical).lineLimit(3...8)
                }
                Section("Data scope") {
                    ForEach(Self.availableSources, id: \.self) { source in
                        Toggle(source, isOn: Binding(get: { dataSources.contains(source) }, set: { selected in if selected { dataSources.insert(source) } else { dataSources.remove(source) } })).tint(PGTheme.accent)
                    }
                }
                Section {
                    Button { Task { await submit() } } label: { HStack { Spacer(); if submitting { ProgressView() } else { Text("Start research") }; Spacer() } }
                        .disabled(!canSubmit)
                } footer: {
                    Text("The server runs the harness, charges credits, and keeps the task alive even after you close the app. You will be notified when it finishes.")
                }
                if let createdRunID {
                    Section {
                        Button { dismiss(); onCreated(createdRunID) } label: { Label("View run", systemImage: "arrow.right.circle").foregroundStyle(PGTheme.accent) }
                    }
                }
            }
            .navigationTitle("Start research").navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } } }
            .alert("Research run", isPresented: Binding(get: { error != nil }, set: { if !$0 { error = nil } })) { Button("OK") {} } message: { Text(error?.localizedDescription ?? "") }
        }
    }

    private var canSubmit: Bool {
        !submitting && capabilities.userCanStartResearch && !name.trimmingCharacters(in: .whitespaces).isEmpty && !prompt.trimmingCharacters(in: .whitespaces).isEmpty && !dataSources.isEmpty
    }

    private func submit() async {
        submitting = true; defer { submitting = false }
        do {
            let run = try await repository.create(name: name, prompt: prompt, dataSources: Array(dataSources).sorted())
            createdRunID = run.id
        } catch { self.error = error.mobileAPIError }
    }
}
