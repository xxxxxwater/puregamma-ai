import Observation
import SwiftUI

@MainActor @Observable final class MemoryControlsViewModel {
    var settings: LoadState<MemorySettings> = .idle
    var items: LoadState<[MemoryItem]> = .idle
    var proposals: LoadState<[MemoryProposal]> = .idle
    var scope: MemoryScope = .shortTerm
    var saving = false
    var error: APIError?
    var infoMessage: String?
    var lastExportURL: URL?
    let repository: MemoryRepository
    let capabilities: MobileCapabilities

    init(repository: MemoryRepository, capabilities: MobileCapabilities) {
        self.repository = repository
        self.capabilities = capabilities
    }

    var isAvailable: Bool { capabilities.serverContractAvailable && capabilities.memoryServiceEnabled && capabilities.userCanManageMemory }

    func load() async {
        settings = .loading; items = .loading; proposals = .loading
        async let a: Void = loadSettings()
        async let b: Void = loadItems()
        async let c: Void = loadProposals()
        _ = await (a, b, c)
    }
    private func loadSettings() async {
        do { settings = .loaded(try await repository.settings()) } catch { settings = .failed(error.mobileAPIError) }
    }
    private func loadItems() async {
        do { let rows = try await repository.items(scope: scope); items = rows.isEmpty ? .empty : .loaded(rows) } catch { items = .failed(error.mobileAPIError) }
    }
    private func loadProposals() async {
        do { let rows = try await repository.proposals(); proposals = rows.isEmpty ? .empty : .loaded(rows) } catch { proposals = .failed(error.mobileAPIError) }
    }

    func save(_ patch: MemorySettingsPatchDTO) async {
        saving = true; defer { saving = false }
        do { settings = .loaded(try await repository.updateSettings(patch)) } catch { self.error = error.mobileAPIError }
    }
    func toggle(_ keyPath: WritableKeyPath<MemorySettings, Bool>, to value: Bool, consentGranted: Bool) async {
        guard case .loaded(let current) = settings else { return }
        // 服务端要求同意时，本地先更新，再由服务器最终确认；服务器 403 CONSENT_REQUIRED 会回落。
        let patch = MemorySettingsPatchDTO(
            shortTermEnabled: keyPath == \.shortTermEnabled ? value : nil,
            midTermEnabled: keyPath == \.midTermEnabled ? value : nil,
            conversationSummaryEnabled: keyPath == \.conversationSummaryEnabled ? value : nil,
            researchMemoryEnabled: keyPath == \.researchMemoryEnabled ? value : nil,
            portfolioMemoryEnabled: keyPath == \.portfolioMemoryEnabled ? value : nil,
            consentGranted: consentGranted || !current.consentRequired
        )
        await save(patch)
    }

    func approve(_ proposal: MemoryProposal) async {
        do {
            _ = try await repository.approveProposal(proposal.id)
            if case .loaded(var rows) = proposals, let index = rows.firstIndex(where: { $0.id == proposal.id }) {
                rows.remove(at: index)
                proposals = rows.isEmpty ? .empty : .loaded(rows)
            }
            await reloadItems()
        } catch { self.error = error.mobileAPIError }
    }
    func reject(_ proposal: MemoryProposal) async {
        do {
            _ = try await repository.rejectProposal(proposal.id)
            if case .loaded(var rows) = proposals, let index = rows.firstIndex(where: { $0.id == proposal.id }) {
                rows.remove(at: index)
                proposals = rows.isEmpty ? .empty : .loaded(rows)
            }
        } catch { self.error = error.mobileAPIError }
    }

    /// 乐观删除：先保留原列表快照；服务端确认失败时回滚 UI 并明确提示。
    func delete(_ item: MemoryItem) async {
        guard case .loaded(let snapshot) = items else { return }
        var rows = snapshot
        rows.removeAll { $0.id == item.id }
        items = rows.isEmpty ? .empty : .loaded(rows)
        do {
            try await repository.deleteItem(item.id)
            await loadItems() // 服务端确认为准，重新拉取
        } catch {
            items = snapshot.isEmpty ? .empty : .loaded(snapshot) // 失败回滚
            self.error = error.mobileAPIError
        }
    }

    /// 清空：不做乐观清空，必须等服务端确认成功后再刷新并提示完成。
    func clearAll() async {
        do {
            let removed = try await repository.clear(scope: "all")
            await loadItems()
            infoMessage = String(localized: "Memory cleared (\(removed) item(s)).")
        } catch { self.error = error.mobileAPIError }
    }

    func reloadScope() async {
        items = .loading
        await loadItems()
    }

    func export() async {
        do { lastExportURL = try await repository.export().url } catch { self.error = error.mobileAPIError }
    }

    private func reloadItems() async {
        do { let rows = try await repository.items(scope: scope); items = rows.isEmpty ? .empty : .loaded(rows) } catch { /* 保留现有展示，不做覆盖 */ }
    }
}

struct MemoryControlsView: View {
    @State private var model: MemoryControlsViewModel
    @State private var consentGranted = false
    @State private var pendingToggle: WritableKeyPath<MemorySettings, Bool>?
    @State private var pendingValue = false
    @State private var showConsent = false
    @State private var showClearConfirmation = false
    @State private var showExportSheet = false

    init(repository: MemoryRepository, capabilities: MobileCapabilities) {
        _model = State(initialValue: MemoryControlsViewModel(repository: repository, capabilities: capabilities))
    }

    var body: some View {
        Group {
            if !model.isAvailable { unavailable } else { content }
        }
        .navigationTitle("Memory controls").navigationBarTitleDisplayMode(.inline)
        .task { await model.load() }
        .refreshable { await model.load() }
        .alert("Memory", isPresented: Binding(get: { model.error != nil }, set: { if !$0 { model.error = nil } })) { Button("OK") {} } message: { Text(model.error?.localizedDescription ?? "") }
        .alert("Memory", isPresented: Binding(get: { model.infoMessage != nil }, set: { if !$0 { model.infoMessage = nil } })) { Button("OK") {} } message: { Text(model.infoMessage ?? "") }
        .confirmationDialog("Memory consent", isPresented: $showConsent, titleVisibility: .visible) {
            Button("Allow and save") {
                consentGranted = true
                if let keyPath = pendingToggle { Task { await model.toggle(keyPath, to: pendingValue, consentGranted: true) } }
            }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("Saving this memory setting requires your explicit consent. Memories are saved for you, can be reviewed one by one, deleted, or exported at any time.")
        }
        .confirmationDialog("Clear all memory?", isPresented: $showClearConfirmation, titleVisibility: .visible) {
            Button("Delete all saved memories", role: .destructive) { Task { await model.clearAll() } }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("This permanently removes your saved short-term and mid-term memories from the server. This cannot be undone.")
        }
        .sheet(isPresented: $showExportSheet) {
            NavigationStack {
                List {
                    Section("Export") {
                        if let url = model.lastExportURL {
                            ShareLink(item: url) { Label("Share exported memory file", systemImage: "square.and.arrow.up") }
                        } else {
                            Button { Task { await model.export() } } label: { Label("Prepare export file", systemImage: "arrow.down.doc") }
                        }
                    }
                    Section { Text("Export is generated by the server and contains only your own memories.").font(.caption).foregroundStyle(.secondary) }
                }
                .navigationTitle("Export memory").navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Done") { showExportSheet = false } } }
            }
        }
    }

    private var unavailable: some View {
        VStack {
            StateView(
                title: "Memory service unavailable",
                detail: LocalizedStringKey(!model.capabilities.serverContractAvailable
                    ? "The backend has not exposed this feature yet. It will appear here once enabled."
                    : "Memory service is disabled for your account or plan."),
                symbol: "lock.doc"
            )
        }
    }

    @ViewBuilder private var content: some View {
        switch model.settings {
        case .loading, .idle: ProgressView("Loading memory settings…").frame(maxWidth: .infinity, maxHeight: .infinity)
        case .empty: settingsContent(.allOff)
        case .failed(let error):
            StateView(title: "Memory settings unavailable", detail: LocalizedStringKey(error.localizedDescription), symbol: "brain.head.profile", retry: { Task { await model.load() } })
        case .loaded(let settings), .stale(let settings, _):
            settingsContent(settings)
        }
    }

    private func settingsContent(_ settings: MemorySettings) -> some View {
        Form {
            Section {
                toggleRow("Short-term memory", systemImage: "clock.arrow.circlepath", value: settings.shortTermEnabled, keyPath: \.shortTermEnabled, settings: settings)
                toggleRow("Mid-term memory", systemImage: "archivebox", value: settings.midTermEnabled, keyPath: \.midTermEnabled, settings: settings)
                toggleRow("Conversation summaries", systemImage: "bubble.left.and.text.bubble.right", value: settings.conversationSummaryEnabled, keyPath: \.conversationSummaryEnabled, settings: settings)
                toggleRow("Research memory", systemImage: "doc.text.magnifyingglass", value: settings.researchMemoryEnabled, keyPath: \.researchMemoryEnabled, settings: settings)
                toggleRow("Portfolio memory", systemImage: "chart.pie", value: settings.portfolioMemoryEnabled, keyPath: \.portfolioMemoryEnabled, settings: settings)
            } header: {
                Text("Memory switches")
            } footer: {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Memories are isolated per user. Trading decisions never read memories without server-side policy checks.")
                    if settings.consentRequired && !consentGranted {
                        Text("Consent required: saving new memories needs your confirmation each session.").foregroundStyle(PGTheme.warning)
                    }
                    Text("Never stored: private keys, API secrets, card details, tokens, account credentials, unconfirmed trade intent, unverified harness inferences, and auto-trade orders.").foregroundStyle(.secondary)
                }
            }

            Section("Saved memories (\(model.scope.rawValue))") {
                Picker("Scope", selection: $model.scope) {
                    Text("Short-term").tag(MemoryScope.shortTerm)
                    Text("Mid-term").tag(MemoryScope.midTerm)
                }
                .pickerStyle(.segmented)
                .onChange(of: model.scope) { _, _ in Task { await model.reloadScope() } }
                itemsSection
                Button(role: .destructive) { showClearConfirmation = true } label: { Label("Clear all memory…", systemImage: "trash") }
                Button { showExportSheet = true } label: { Label("Export my memory", systemImage: "square.and.arrow.up") }
            }

            Section("Proposals awaiting consent") { proposalsSection }

            Section("Memory status") {
                let state = MemoryState.state(settings: settings, consentGranted: consentGranted)
                LabeledContent("State", value: String(describing: state))
                LabeledContent("Retention", value: "\(settings.retentionDays) days")
                LabeledContent("Ownership", value: "user-isolated")
            }
        }
        .scrollContentBackground(.hidden).background(PGTheme.secondaryBackground)
    }

    private func toggleRow(_ title: LocalizedStringKey, systemImage: String, value: Bool, keyPath: WritableKeyPath<MemorySettings, Bool>, settings: MemorySettings) -> some View {
        Toggle(isOn: Binding(
            get: { value },
            set: { newValue in
                if settings.consentRequired && !consentGranted && newValue {
                    pendingToggle = keyPath; pendingValue = newValue; showConsent = true
                } else {
                    Task { await model.toggle(keyPath, to: newValue, consentGranted: consentGranted) }
                }
            }
        )) {
            Label(title, systemImage: systemImage)
        }
        .tint(PGTheme.accent)
        .disabled(model.saving)
        .accessibilityHint(settings.consentRequired && !consentGranted ? "Requires consent confirmation" : "")
    }

    @ViewBuilder private var itemsSection: some View {
        switch model.items {
        case .loading, .idle: ProgressView()
        case .empty: Text("No saved memories in this scope.").font(.caption).foregroundStyle(.secondary)
        case .failed(let error): StateView(title: "Memories unavailable", detail: LocalizedStringKey(error.localizedDescription), symbol: "brain.head.profile", retry: { Task { await model.load() } })
        case .loaded(let rows), .stale(let rows, _):
            ForEach(rows) { item in
                HStack(alignment: .top) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(item.contentPreview).font(.subheadline).lineLimit(3)
                        Text("\(item.kind) · \(MemoryItemLifecycleText(item.lifecycle)) · \(PGFormat.dateTime(item.createdAt))").font(.caption2).foregroundStyle(.secondary)
                    }
                    Spacer()
                    Button(role: .destructive) { Task { await model.delete(item) } } label: { Image(systemName: "trash") }
                        .buttonStyle(.borderless)
                        .accessibilityLabel("Delete memory \(item.id)")
                }
            }
        }
    }

    @ViewBuilder private var proposalsSection: some View {
        switch model.proposals {
        case .loading, .idle: ProgressView()
        case .empty: Text("No proposals awaiting your review.").font(.caption).foregroundStyle(.secondary)
        case .failed: Text("Proposals unavailable. Pull to refresh.").font(.caption).foregroundStyle(.secondary)
        case .loaded(let rows), .stale(let rows, _):
            ForEach(rows) { proposal in
                VStack(alignment: .leading, spacing: 8) {
                    Text(proposal.contentPreview).font(.subheadline).lineLimit(3)
                    Text("\(proposal.scope.rawValue) · \(proposal.source) · expires \(PGFormat.dateTime(proposal.expiresAt))").font(.caption2).foregroundStyle(.secondary)
                    HStack {
                        Button("Approve") { Task { await model.approve(proposal) } }.buttonStyle(.bordered).tint(PGTheme.positive).controlSize(.small)
                        Button("Reject") { Task { await model.reject(proposal) } }.buttonStyle(.bordered).controlSize(.small)
                    }
                }
                .padding(.vertical, 4)
            }
        }
    }
}

private func MemoryItemLifecycleText(_ lifecycle: MemoryItemLifecycle) -> String {
    switch lifecycle {
    case .saved: String(localized: "saved")
    case .pending: String(localized: "pending approval")
    case .rejected: String(localized: "rejected")
    case .expired: String(localized: "expired")
    case .deleted: String(localized: "deleted")
    }
}
