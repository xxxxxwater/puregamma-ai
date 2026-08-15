import Observation
import SwiftUI
import UniformTypeIdentifiers

@MainActor @Observable final class AgentViewModel {
    var conversations: LoadState<[AgentConversation]> = .idle; var messages: LoadState<[AgentMessage]> = .idle; var capabilities: LoadState<AgentCapabilities> = .idle
    var selectedConversation: AgentConversation?; var context = AgentRequestContext(); var prompt = ""; var runID: String?; var toolActivity: [String] = []; var isStreaming = false; var composerError: APIError?
    private let repository: AgentRepository; private var streamTask: Task<Void, Never>?
    private var retryContent = ""; private var retryContext = AgentRequestContext(); private var reducer = AgentStreamReducer()
    init(repository: AgentRepository) { self.repository = repository }

    func load() async {
        conversations = .loading; capabilities = .loading
        async let rows: Result<[AgentConversation], Error> = agentResult { try await repository.conversations() }; async let access: Result<AgentCapabilities, Error> = agentResult { try await repository.capabilities() }
        switch await rows { case .success(let values): conversations = values.isEmpty ? .empty : .loaded(values); if selectedConversation == nil, let first = values.first { await open(first) }; case .failure(let e): conversations = .failed(e as? APIError ?? .transport(e.localizedDescription)) }
        switch await access { case .success(let value): capabilities = .loaded(value); if !value.models.contains(where: { $0.id == context.model && $0.available }) { context.model = "default" }; if !value.dataSources.contains("all") { context.dataSources = context.dataSources.filter(value.dataSources.contains) }; case .failure(let e): capabilities = .failed(e as? APIError ?? .transport(e.localizedDescription)) }
    }
    func create() async { do { let value = try await repository.create(); selectedConversation = value; messages = .loaded([]); await refreshConversations() } catch { composerError = error as? APIError ?? .transport(error.localizedDescription) } }
    func open(_ value: AgentConversation) async { selectedConversation = value; messages = .loading; do { let (_, rows) = try await repository.conversation(value.id); messages = rows.isEmpty ? .empty : .loaded(rows) } catch { messages = .failed(error as? APIError ?? .transport(error.localizedDescription)) } }
    func rename(_ title: String) async { guard let id = selectedConversation?.id else { return }; do { selectedConversation = try await repository.update(id, title: title); await refreshConversations() } catch { composerError = error as? APIError ?? .transport(error.localizedDescription) } }
    func archive() async { guard let id = selectedConversation?.id else { return }; do { _ = try await repository.update(id, archived: true); selectedConversation = nil; messages = .empty; await refreshConversations() } catch { composerError = error as? APIError ?? .transport(error.localizedDescription) } }
    func delete() async { guard let id = selectedConversation?.id else { return }; do { try await repository.delete(id); selectedConversation = nil; messages = .empty; await refreshConversations() } catch { composerError = error as? APIError ?? .transport(error.localizedDescription) } }
    private func refreshConversations() async { do { let rows = try await repository.conversations(); conversations = rows.isEmpty ? .empty : .loaded(rows) } catch { conversations = .failed(error as? APIError ?? .transport(error.localizedDescription)) } }

    func send(locale: String) async {
        let content = prompt.trimmingCharacters(in: .whitespacesAndNewlines); guard !content.isEmpty, !isStreaming else { return }
        retryContent = content; retryContext = context
        prompt = ""
        await submit(content: content, requestContext: context, locale: locale)
    }
    func retry(locale: String) async {
        guard !retryContent.isEmpty, !isStreaming else { return }
        await submit(content: retryContent, requestContext: retryContext, locale: locale)
    }
    private func submit(content: String, requestContext: AgentRequestContext, locale: String) async {
        if selectedConversation == nil { await create() }; guard let conversation = selectedConversation else { return }
        var rows: [AgentMessage] = { if case .loaded(let values) = messages { values } else { [] } }()
        let now = Date(); rows.append(.init(id: UUID().uuidString, conversationID: conversation.id, role: "user", content: content, status: "completed", model: nil, sources: [], createdAt: now, errorMessage: nil))
        let assistantID = UUID().uuidString; rows.append(.init(id: assistantID, conversationID: conversation.id, role: "assistant", content: "", status: "streaming", model: requestContext.model, sources: [], createdAt: now, errorMessage: nil)); messages = .loaded(rows); isStreaming = true; composerError = nil; toolActivity = []; reducer = AgentStreamReducer()
        streamTask = Task { do {
            let stream = try await repository.stream(conversationID: conversation.id, prompt: content, locale: locale, context: requestContext)
            for try await event in stream { apply(event, assistantID: assistantID) }
            if isStreaming { await recoverConversation() }
        } catch let error as APIError { if error != .canceled { composerError = error }; await recoverConversation() }
        catch { composerError = .transport(error.localizedDescription); await recoverConversation() }
        }
    }
    private func apply(_ event: AgentSSEEvent, assistantID: String) {
        var effect: AgentStreamReducer.Effect = .none
        if case .loaded(var rows) = messages, let index = rows.firstIndex(where: { $0.id == assistantID }) {
            effect = reducer.apply(event, to: &rows[index])
            messages = .loaded(rows)
        } else {
            // The stream can outlive the visible message (e.g. user switched
            // conversations); state transitions must still run.
            var discard = AgentMessage(id: assistantID, conversationID: selectedConversation?.id ?? "", role: "assistant", content: "", status: "streaming", model: nil, sources: [], createdAt: Date(), errorMessage: nil)
            effect = reducer.apply(event, to: &discard)
        }
        runID = reducer.runID; toolActivity = reducer.toolActivity; isStreaming = reducer.isStreaming
        switch effect {
        case .completed: retryContent = ""
        case .failed(let message): composerError = .unavailable(message)
        default: break
        }
    }
    func cancel() async { streamTask?.cancel(); if let runID { try? await repository.cancel(runID: runID) }; await recoverConversation() }
    private func recoverConversation() async {
        isStreaming = false; runID = nil
        guard let conversation = selectedConversation, needsServerReconciliation else { return }
        try? await Task.sleep(for: .milliseconds(250))
        await open(conversation)
    }
    /// A successfully completed stream is already authoritative locally; only
    /// reload when the run ended without a terminal state (dropped connection,
    /// failed or canceled run) so server truth replaces the partial content.
    private var needsServerReconciliation: Bool {
        guard case .loaded(let rows) = messages, let last = rows.last else { return true }
        return last.status == "streaming" || last.status == "failed" || last.status == "canceled"
    }
    func addAttachment(_ url: URL) {
        let fileSize = (try? url.resourceValues(forKeys: [.fileSizeKey]))?.fileSize
        guard context.attachments.count < 5,
              let fileSize,
              fileSize <= 20_000,
              context.attachments.reduce(0, { $0 + $1.content.utf8.count }) + fileSize <= 50_000,
              let data = try? Data(contentsOf: url),
              let text = String(data: data, encoding: .utf8) else {
            composerError = .server(status: 400, message: String(localized: "Attachments must be UTF-8 text, no larger than 20 KB each or 50 KB total.")); return
        }
        context.attachments.append(.init(name: url.lastPathComponent, content: text, mime: UTType(filenameExtension: url.pathExtension)?.preferredMIMEType ?? "text/plain"))
    }
}

private func agentResult<T>(_ operation: () async throws -> T) async -> Result<T, Error> { do { return .success(try await operation()) } catch { return .failure(error) } }

struct AgentView: View {
    @Environment(AppState.self) private var app
    @Environment(\.scenePhase) private var scenePhase
    @Environment(\.locale) private var locale
    @State private var model: AgentViewModel; @State private var showConversations = false; @State private var showContext = false; @State private var importer = false; @State private var rename = false; @State private var newTitle = ""; @State private var showResearchStart = false
    init(repository: AgentRepository) { _model = State(initialValue: AgentViewModel(repository: repository)) }
    var body: some View {
        VStack(spacing: 0) { statusStrip; messageList; if let error = model.composerError { errorStrip(error) }; composer }
            .navigationTitle(model.selectedConversation?.title ?? String(localized: "Agent")).navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .topBarLeading) { Button { showConversations = true } label: { Image(systemName: "sidebar.left") }.accessibilityLabel("Conversations") }; ToolbarItemGroup(placement: .topBarTrailing) { Button { showResearchStart = true } label: { Image(systemName: "flask") }.accessibilityLabel("Start research"); Button { showContext = true } label: { Image(systemName: "slider.horizontal.3") }.accessibilityLabel("Agent context") ; Menu { Button("Rename") { newTitle = model.selectedConversation?.title ?? ""; rename = true }; Button("Archive", systemImage: "archivebox") { Task { await model.archive() } }; Button("Delete", systemImage: "trash", role: .destructive) { Task { await model.delete() } } } label: { Image(systemName: "ellipsis") } } }
            .task { await model.load() }.sheet(isPresented: $showConversations) { conversationsSheet }.sheet(isPresented: $showContext) { AgentContextView(model: model, importer: $importer) }
            .sheet(isPresented: $showResearchStart) { ResearchStartView(repository: app.repositories.researchRuns, capabilities: app.mobileCapabilities) { runID in app.selectedTab = .research; app.pendingResearchRunID = runID } }
            .fileImporter(isPresented: $importer, allowedContentTypes: [.plainText, .commaSeparatedText, .json]) { result in if case .success(let url) = result { let access = url.startAccessingSecurityScopedResource(); model.addAttachment(url); if access { url.stopAccessingSecurityScopedResource() } } }
            .alert("Rename conversation", isPresented: $rename) { TextField("Title", text: $newTitle); Button("Save") { Task { await model.rename(newTitle) } }; Button("Cancel", role: .cancel) {} }
            .onChange(of: scenePhase) { _, phase in
                if phase == .background, model.isStreaming { Task { await model.cancel() } }
                if phase == .active, let conversation = model.selectedConversation, !model.isStreaming { Task { await model.open(conversation) } }
            }
    }
    private var statusStrip: some View { HStack { Circle().fill(model.isStreaming ? PGTheme.warning : PGTheme.positive).frame(width: 7, height: 7); Text(model.isStreaming ? "RUNNING" : "READY").font(.caption2.monospaced()); if case .loaded(let access) = model.capabilities { Text("\(access.credits) CREDITS · \(access.remaining) RUNS").font(.caption2.monospaced()).foregroundStyle(.secondary) }; Spacer(); if model.isStreaming { Button("Stop") { Task { await model.cancel() } }.font(.caption).foregroundStyle(PGTheme.negative) } }.padding(.horizontal, 16).frame(height: 34).background(RoundedRectangle(cornerRadius: 10, style: .continuous).fill(PGTheme.secondaryBackground)) }
    @ViewBuilder private var messageList: some View { switch model.messages { case .loading, .idle: ProgressView("Loading conversation…").frame(maxWidth: .infinity, maxHeight: .infinity); case .empty: StateView(title: "Start a research thread", detail: "Ask about markets, portfolio risk, sources, or long-gamma research.", symbol: "sparkles"); case .failed(let e): StateView(title: "Conversation unavailable", detail: LocalizedStringKey(e.localizedDescription), symbol: "exclamationmark.bubble", retry: { if let row = model.selectedConversation { Task { await model.open(row) } } }); case .loaded(let rows), .stale(let rows, _): ScrollView { LazyVStack(spacing: 22) { ForEach(rows) { AgentMessageView(message: $0) }; ForEach(model.toolActivity, id: \.self) { Label($0, systemImage: "wrench.and.screwdriver").font(.caption.monospaced()).foregroundStyle(.secondary).frame(maxWidth: .infinity, alignment: .leading) } }.padding(16) }.defaultScrollAnchor(.bottom) } }
    private func errorStrip(_ error: APIError) -> some View {
        let showsRetry = showsRetry(for: error)
        return HStack { Image(systemName: "exclamationmark.triangle"); Text(error.localizedDescription).lineLimit(2); Spacer(); if showsRetry { Button("Retry") { Task { await model.retry(locale: locale.language.languageCode?.identifier ?? "en") } } } }
            .font(.caption).padding(10).foregroundStyle(error.presentation == .permissionDenied ? PGTheme.warning : PGTheme.negative).background(RoundedRectangle(cornerRadius: 10, style: .continuous).fill(PGTheme.secondaryBackground))
    }
    private func showsRetry(for error: APIError) -> Bool {
        // Permission/payment failures cannot be fixed by re-submitting the same prompt.
        switch error { case .forbidden, .paymentRequired: false; default: true }
    }
    private var composer: some View { VStack(spacing: 8) { if !model.context.attachments.isEmpty { ScrollView(.horizontal) { HStack { ForEach(model.context.attachments) { file in Text(file.name).font(.caption).padding(6).background(RoundedRectangle(cornerRadius: 8, style: .continuous).fill(PGTheme.tertiaryBackground)) } } } }; HStack(alignment: .bottom) { Button { importer = true } label: { Image(systemName: "paperclip") }.accessibilityLabel("Attach text file"); TextField("Ask with sources…", text: $model.prompt, axis: .vertical).lineLimit(1...6).textFieldStyle(.plain).padding(10).background(RoundedRectangle(cornerRadius: 10, style: .continuous).fill(PGTheme.secondaryBackground)); Button { Task { await model.send(locale: locale.language.languageCode?.identifier ?? "en") } } label: { Image(systemName: "arrow.up").frame(width: 34, height: 34).background(Circle().fill(PGTheme.accent)).foregroundStyle(PGTheme.onAccent) }.disabled(model.prompt.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || model.isStreaming).accessibilityLabel("Send") }; Text("Research only · Responses may use Credits").font(.caption2).foregroundStyle(.secondary) }.padding(12).overlay(alignment: .top) { TerminalDivider() } }
    private var conversationsSheet: some View { NavigationStack { Group { switch model.conversations { case .loaded(let rows), .stale(let rows, _): List(rows) { row in Button { Task { await model.open(row); showConversations = false } } label: { VStack(alignment: .leading) { Text(row.title); Text(PGFormat.dateTime(row.updatedAt)).font(.caption).foregroundStyle(.secondary) } } }; case .empty: StateView(title: "No conversations", detail: "Create your first research thread.", symbol: "bubble.left"); case .failed(let e): StateView(title: "Unable to load", detail: LocalizedStringKey(e.localizedDescription), symbol: "wifi.exclamationmark", retry: { Task { await model.load() } }); default: ProgressView() } }.navigationTitle("Conversations").toolbar { ToolbarItem(placement: .topBarLeading) { Button("Done") { showConversations = false } }; ToolbarItem(placement: .topBarTrailing) { Button { Task { await model.create(); showConversations = false } } label: { Image(systemName: "plus") } } } } }
}

struct AgentMessageView: View {
    let message: AgentMessage
    var body: some View { VStack(alignment: .leading, spacing: 10) { Text(message.role == "user" ? "YOU" : "PΓ / AGENT").font(.caption2.monospaced()).foregroundStyle(message.role == "user" ? .secondary : PGTheme.accent); Text(message.content.isEmpty && message.status == "streaming" ? "…" : message.content).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading); if let error = message.errorMessage { Text(error).font(.caption).foregroundStyle(PGTheme.negative) }; if !message.sources.isEmpty { TerminalDivider(); ForEach(message.sources.sorted(by: { $0.citationIndex < $1.citationIndex })) { source in Link(destination: source.url ?? URL(string: "about:blank")!) { HStack(alignment: .top) { Text("[\(source.citationIndex)]").font(.caption.monospaced()).foregroundStyle(PGTheme.accent); VStack(alignment: .leading, spacing: 3) { Text(source.title).font(.caption).foregroundStyle(.primary); Text("\(source.provider) · \(PGFormat.dateTime(source.publishedAt ?? source.sourceTimestamp ?? source.fetchedAt))").font(.caption2).foregroundStyle(.secondary) } } }.disabled(source.url == nil) } } }.frame(maxWidth: .infinity, alignment: .leading).padding(message.role == "user" ? 12 : 0).background { if message.role == "user" { RoundedRectangle(cornerRadius: 12, style: .continuous).fill(PGTheme.secondaryBackground) } }.accessibilityElement(children: .contain) }
}

struct AgentContextView: View {
    @Bindable var model: AgentViewModel; @Binding var importer: Bool; @Environment(\.dismiss) private var dismiss
    let sourceOptions = ["market", "rss", "fintwit", "x-twitter", "bloomberg", "portfolio", "options"]
    var body: some View { NavigationStack { Form { Section("Model") { if case .loaded(let access) = model.capabilities { Picker("Model", selection: $model.context.model) { ForEach(access.models) { row in Text(row.available ? row.name : "\(row.name) · \(row.reason ?? "Unavailable")").tag(row.id).disabled(!row.available) } } } else { ProgressView() } }; Section("Data sources") { ForEach(availableSources, id: \.self) { item in Toggle(item, isOn: selection(item, in: $model.context.dataSources)) } }; Section("Skills") { ForEach(availableSkills, id: \.self) { item in Toggle(item, isOn: selection(item, in: $model.context.skills)) } }; Section("Custom prompt") { TextField("Additional research instructions", text: $model.context.customPrompt, axis: .vertical).lineLimit(3...8) }; Section("Attachments") { Button("Attach TXT, MD, CSV or JSON") { importer = true }; Text("Maximum 5 files, 20 KB each, 50 KB total.").font(.caption).foregroundStyle(.secondary) } }.navigationTitle("Agent context").toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } } } }
    private var availableSkills: [String] { guard case .loaded(let access) = model.capabilities else { return ["market_research", "news_research", "portfolio_review", "options_analysis", "source_check", "deep_research"] }; return access.skills.isEmpty ? ["market_research", "news_research", "portfolio_review", "options_analysis", "source_check", "deep_research"] : access.skills }
    private var availableSources: [String] { guard case .loaded(let access) = model.capabilities else { return [] }; return access.dataSources.contains("all") ? sourceOptions : sourceOptions.filter(access.dataSources.contains) }
    private func selection(_ value: String, in values: Binding<[String]>) -> Binding<Bool> { Binding(get: { values.wrappedValue.contains(value) }, set: { enabled in if enabled { if !values.wrappedValue.contains(value) { values.wrappedValue.append(value) } } else { values.wrappedValue.removeAll { $0 == value } } }) }
}

/// Pure state machine for Agent SSE events. Unit-testable without a network.
struct AgentStreamReducer {
    enum Effect: Equatable, Sendable { case none, completed, failed(String), canceled }

    var runID: String?
    var toolActivity: [String] = []
    var isStreaming = true

    mutating func apply(_ event: AgentSSEEvent, to message: inout AgentMessage) -> Effect {
        switch event {
        case .runStarted(let id): runID = id; return .none
        case .delta(let delta): message.content += delta; return .none
        case .toolStarted(let tool): toolActivity.append("RUNNING · \(tool)"); return .none
        case .toolCompleted(let tool):
            toolActivity.removeAll { $0 == "RUNNING · \(tool)" || $0 == "DONE · \(tool)" }
            toolActivity.append("DONE · \(tool)")
            return .none
        case .citation(let source):
            if !message.sources.contains(source) { message.sources.append(source) }
            return .none
        case .completed: message.status = "completed"; isStreaming = false; runID = nil; return .completed
        case .failed(let text): message.status = "failed"; message.errorMessage = text; isStreaming = false; runID = nil; return .failed(text)
        case .canceled: message.status = "canceled"; isStreaming = false; runID = nil; return .canceled
        }
    }
}
