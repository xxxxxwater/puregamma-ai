import Observation
import SwiftUI
import UniformTypeIdentifiers

/// Whether the transcript on screen is following the live stream or being
/// restored from the server's event log after the stream dropped.
enum AgentConnectionState: Equatable { case live, recovering }

/// One user-initiated send. Its request id is reused only when this same
/// attempt is retried, so the server can recognise a resend (§8.1).
struct AgentSendAttempt: Equatable {
    let content: String
    let context: AgentRequestContext
    let requestID: String
    /// True once the server answered the send with a stream: from then on the
    /// turn exists server-side and a new question needs a new id.
    var accepted = false
}

@MainActor @Observable final class AgentViewModel {
    var conversations: LoadState<[AgentConversation]> = .idle; var messages: LoadState<[AgentMessage]> = .idle; var capabilities: LoadState<AgentCapabilities> = .idle
    var selectedConversation: AgentConversation?; var context = AgentRequestContext(); var prompt = ""; var runID: String?; var toolActivity: [String] = []; var isStreaming = false; var composerError: APIError?
    var connection: AgentConnectionState?
    /// A one-off notice (e.g. the conversation was deleted elsewhere).
    var notice: String?
    var permissionModes: [AgentPermissionMode] = []
    var permission: AgentPermissionMode = .workspaceWrite
    private(set) var pendingAttempt: AgentSendAttempt?
    private let repository: AgentRepository; private var streamTask: Task<Void, Never>?
    private var reducer = AgentStreamReducer(); private var cursor = AgentRunCursor()
    /// Seconds between event-log polls while restoring (tests shorten it).
    var replayPollInterval: Double = 2.5
    init(repository: AgentRepository) { self.repository = repository }

    var modelMenu: [AgentModelMenu.Entry] { if case .loaded(let access) = capabilities { AgentModelMenu.entries(access.models) } else { [] } }

    func load() async {
        conversations = .loading; capabilities = .loading
        async let rows: Result<[AgentConversation], Error> = agentResult { try await repository.conversations() }; async let access: Result<AgentCapabilities, Error> = agentResult { try await repository.capabilities() }
        async let workspace: Result<AgentWorkspaceCapabilitiesDTO, Error> = agentResult { try await repository.workspaceCapabilities() }
        switch await rows { case .success(let values): conversations = values.isEmpty ? .empty : .loaded(values); if selectedConversation == nil, let first = values.first { await open(first) }; case .failure(let e): conversations = .failed(e as? APIError ?? .transport(e.localizedDescription)) }
        switch await access { case .success(let value): capabilities = .loaded(value); context.model = AgentModelMenu.resolve(context.model, in: value.models); if !value.dataSources.contains("all") { context.dataSources = context.dataSources.filter(value.dataSources.contains) }; case .failure(let e): capabilities = .failed(e as? APIError ?? .transport(e.localizedDescription)) }
        // Only modes the server offers and this client knows; never full-access.
        if case .success(let value) = await workspace { permissionModes = AgentPermissionMode.selectable(from: value.permissionModes) }
    }
    func create() async { do { let value = try await repository.create(); selectedConversation = value; permission = .workspaceWrite; messages = .loaded([]); await refreshConversations() } catch { composerError = error as? APIError ?? .transport(error.localizedDescription) } }

    /// Show a conversation from the server's record and reattach to the run it
    /// is still producing, if any (§8.6/§8.7).
    func open(_ value: AgentConversation) async {
        detach()
        selectedConversation = value; messages = .loading; notice = nil
        do {
            let snapshot = try await repository.snapshot(value.id)
            selectedConversation = snapshot.conversation
            permission = snapshot.conversation.permissionMode.flatMap(AgentPermissionMode.init(rawValue:)) ?? .workspaceWrite
            messages = snapshot.messages.isEmpty ? .empty : .loaded(snapshot.messages)
            if let active = snapshot.activeRunID { observe(conversationID: value.id, runID: active) }
        } catch let error as APIError {
            if !handleConversationGone(error, id: value.id) { messages = .failed(error) }
        } catch { messages = .failed(.transport(error.localizedDescription)) }
    }
    func rename(_ title: String) async { guard let id = selectedConversation?.id else { return }; do { selectedConversation = try await repository.update(id, title: title); await refreshConversations() } catch { report(error, conversationID: id) } }
    func archive() async { guard let id = selectedConversation?.id else { return }; do { _ = try await repository.update(id, archived: true); selectedConversation = nil; messages = .empty; await refreshConversations() } catch { report(error, conversationID: id) } }
    func delete() async { guard let id = selectedConversation?.id else { return }; do { try await repository.delete(id); selectedConversation = nil; messages = .empty; await refreshConversations() } catch { report(error, conversationID: id) } }
    func setPermission(_ mode: AgentPermissionMode) async {
        guard mode != permission else { return }
        guard let id = selectedConversation?.id else { permission = mode; return }
        let previous = permission; permission = mode
        do { selectedConversation = try await repository.setPermission(id, mode: mode) }
        catch { permission = previous; report(error, conversationID: id) }
    }
    private func refreshConversations() async { do { let rows = try await repository.conversations(); conversations = rows.isEmpty ? .empty : .loaded(rows) } catch { conversations = .failed(error as? APIError ?? .transport(error.localizedDescription)) } }
    private func report(_ error: Error, conversationID: String) {
        let apiError = error as? APIError ?? .transport(error.localizedDescription)
        if !handleConversationGone(apiError, id: conversationID) { composerError = apiError }
    }

    /// A deleted conversation is a 404 with a plain-text detail (§8.4): drop it
    /// locally and say so, instead of showing a generic failure.
    @discardableResult func handleConversationGone(_ error: APIError, id: String) -> Bool {
        guard case .rejected(let detail) = error, detail.status == 404, detail.code == nil else { return false }
        if case .loaded(let rows) = conversations { let kept = rows.filter { $0.id != id }; conversations = kept.isEmpty ? .empty : .loaded(kept) }
        if selectedConversation?.id == id { detach(); selectedConversation = nil; messages = .empty; pendingAttempt = nil }
        composerError = nil
        notice = String(localized: "This conversation was deleted.")
        return true
    }

    func send(locale: String) async {
        let content = prompt.trimmingCharacters(in: .whitespacesAndNewlines); guard !content.isEmpty, !isStreaming else { return }
        if case .loaded(let access) = capabilities { context.model = AgentModelMenu.resolve(context.model, in: access.models) }
        pendingAttempt = AgentSendAttempt(content: content, context: context, requestID: ClientRequestID.make())
        prompt = ""
        await submit(locale: locale)
    }
    /// Retry the last attempt. Before the server accepted it, the same request
    /// id is reused, so a send that did arrive is attached to, never charged twice.
    func retry(locale: String) async {
        guard var attempt = pendingAttempt, !isStreaming else { return }
        if attempt.accepted { attempt = AgentSendAttempt(content: attempt.content, context: attempt.context, requestID: ClientRequestID.make()) }
        pendingAttempt = attempt
        await submit(locale: locale)
    }
    private func submit(locale: String) async {
        guard let attempt = pendingAttempt else { return }
        if selectedConversation == nil { await create() }; guard let conversation = selectedConversation else { return }
        var rows: [AgentMessage] = { if case .loaded(let values) = messages { values } else { [] } }()
        let now = Date(); let localUserID = "local-" + attempt.requestID
        rows.append(.init(id: localUserID, conversationID: conversation.id, role: "user", content: attempt.content, status: "completed", model: nil, sources: [], createdAt: now, errorMessage: nil))
        let assistantID = "local-assistant-" + attempt.requestID; rows.append(.init(id: assistantID, conversationID: conversation.id, role: "assistant", content: "", status: "streaming", model: attempt.context.model, sources: [], createdAt: now, errorMessage: nil)); messages = .loaded(rows)
        isStreaming = true; composerError = nil; notice = nil; toolActivity = []; reducer = AgentStreamReducer(); cursor = AgentRunCursor(); connection = .live
        streamTask = Task {
            let stream: AsyncThrowingStream<AgentStreamFrame, Error>
            do {
                stream = try await repository.stream(conversationID: conversation.id, prompt: attempt.content, locale: locale, context: attempt.context, clientRequestID: attempt.requestID)
            } catch {
                await sendRefused(error as? APIError ?? .transport(error.localizedDescription), conversationID: conversation.id, localIDs: [localUserID, assistantID])
                return
            }
            pendingAttempt?.accepted = true
            var ended = false
            do {
                for try await frame in stream where cursor.admit(frame) {
                    apply(frame.event, assistantID: assistantID)
                    if frame.event.isTerminal { ended = true }
                }
            } catch {
                if Task.isCancelled { return }
            }
            if Task.isCancelled { return }
            // The body ended before a terminal frame: the run's outcome is the
            // server's to tell, not a failure to report.
            if !ended { await recover(conversationID: conversation.id) }
            await reload(conversationID: conversation.id)
            finishStreaming()
        }
    }

    private func sendRefused(_ error: APIError, conversationID: String, localIDs: Set<String>) async {
        if case .loaded(let rows) = messages { let kept = rows.filter { !localIDs.contains($0.id) }; messages = kept.isEmpty ? .empty : .loaded(kept) }
        switch AgentSendFailure.classify(error) {
        case .duplicate(let runID, let status):
            // The server already has this attempt: follow that run, do not resend.
            pendingAttempt = nil
            if !AgentRunStatus.isTerminal(status ?? "") { connection = .recovering; await follow(runID: runID) }
            await reload(conversationID: conversationID)
        case .conversationGone:
            handleConversationGone(error, id: conversationID)
        case .retryable(let error):
            if error != .canceled { composerError = error }
        case .final(let error):
            composerError = error
            pendingAttempt = nil
            if error.code == "AGENT_MODEL_INVALID" { context.model = "default" }
        }
        finishStreaming()
    }

    /// The live stream died mid-run: follow the run's event log (§8.7 rule 2).
    private func recover(conversationID: String) async {
        connection = .recovering
        var runID = cursor.runID
        if runID == nil, let snapshot = try? await repository.snapshot(conversationID) { runID = snapshot.activeRunID }
        if let runID { await follow(runID: runID) }
    }

    private func follow(runID: String) async {
        self.runID = runID
        let follower = AgentRunFollower(fetch: { [repository] id, after in try await repository.runEvents(runID: id, after: after) }, pollInterval: replayPollInterval)
        var cursor = self.cursor
        _ = await follower.follow(runID: runID, cursor: &cursor) { frame in
            if case .toolStarted(let tool) = frame.event { toolActivity.append("RUNNING · \(tool)") }
            if case .toolCompleted(let tool) = frame.event { toolActivity.removeAll { $0 == "RUNNING · \(tool)" }; toolActivity.append("DONE · \(tool)") }
        }
        self.cursor = cursor
    }

    /// Reattach to a run the server is still producing (reopened conversation,
    /// back from background). Observation only: nothing is resent or canceled.
    private func observe(conversationID: String, runID: String) {
        isStreaming = true; connection = .recovering; self.runID = runID; cursor = AgentRunCursor(runID: runID)
        streamTask = Task {
            await follow(runID: runID)
            if Task.isCancelled { return }
            await reload(conversationID: conversationID)
            finishStreaming()
        }
    }

    /// The server's record replaces the streamed view (§8.7 rule 3).
    private func reload(conversationID: String) async {
        guard selectedConversation?.id == conversationID else { return }
        do {
            let snapshot = try await repository.snapshot(conversationID)
            messages = snapshot.messages.isEmpty ? .empty : .loaded(snapshot.messages)
            if case .loaded(let rows) = messages, let last = rows.last, last.role == "assistant", last.status == "completed" { pendingAttempt = nil }
        } catch let error as APIError { handleConversationGone(error, id: conversationID) }
        catch {}
    }

    private func finishStreaming() { isStreaming = false; runID = nil; connection = nil; streamTask = nil }

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
        runID = reducer.runID ?? runID; toolActivity = reducer.toolActivity
        switch effect {
        case .completed: pendingAttempt = nil
        case .failed(let message): composerError = .unavailable(message)
        default: break
        }
    }

    /// Explicit user stop: the only path that cancels a run.
    func cancel() async {
        let target = runID ?? cursor.runID
        streamTask?.cancel(); streamTask = nil
        if let target { try? await repository.cancel(runID: target) }
        if let id = selectedConversation?.id { await reload(conversationID: id) }
        finishStreaming()
    }

    /// Stop observing without canceling (view left, app backgrounded).
    func detach() {
        streamTask?.cancel(); streamTask = nil
        if isStreaming { finishStreaming() }
    }

    /// Back in the foreground: re-read the server's record and reattach.
    func resume() async {
        guard !isStreaming, let conversation = selectedConversation else { return }
        await open(conversation)
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
        VStack(spacing: 0) { statusStrip; if model.connection == .recovering { recoveringStrip }; if let notice = model.notice { noticeStrip(notice) }; messageList; if let error = model.composerError { errorStrip(error) }; composer }
            .navigationTitle(model.selectedConversation?.title ?? String(localized: "Agent")).navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .topBarLeading) { Button { showConversations = true } label: { Image(systemName: "sidebar.left") }.accessibilityLabel("Conversations") }; ToolbarItemGroup(placement: .topBarTrailing) { Button { showResearchStart = true } label: { Image(systemName: "flask") }.accessibilityLabel("Start research"); Button { showContext = true } label: { Image(systemName: "slider.horizontal.3") }.accessibilityLabel("Agent context") ; Menu { Button("Rename") { newTitle = model.selectedConversation?.title ?? ""; rename = true }; Button("Archive", systemImage: "archivebox") { Task { await model.archive() } }; Button("Delete", systemImage: "trash", role: .destructive) { Task { await model.delete() } } } label: { Image(systemName: "ellipsis") } } }
            .task { await model.load() }.sheet(isPresented: $showConversations) { conversationsSheet }.sheet(isPresented: $showContext) { AgentContextView(model: model, importer: $importer) }
            .sheet(isPresented: $showResearchStart) { ResearchStartView(repository: app.repositories.researchRuns, capabilities: app.mobileCapabilities) { runID in app.selectedTab = .research; app.pendingResearchRunID = runID } }
            .fileImporter(isPresented: $importer, allowedContentTypes: [.plainText, .commaSeparatedText, .json]) { result in if case .success(let url) = result { let access = url.startAccessingSecurityScopedResource(); model.addAttachment(url); if access { url.stopAccessingSecurityScopedResource() } } }
            .alert("Rename conversation", isPresented: $rename) { TextField("Title", text: $newTitle); Button("Save") { Task { await model.rename(newTitle) } }; Button("Cancel", role: .cancel) {} }
            .onChange(of: scenePhase) { _, phase in
                // Leaving the app stops observing; it never cancels the run.
                // Only the Stop button cancels (§8.7 rule 5).
                if phase == .background { model.detach() }
                if phase == .active { Task { await model.resume() } }
            }
    }
    private var statusStrip: some View { HStack { Circle().fill(model.isStreaming ? PGTheme.warning : PGTheme.positive).frame(width: 7, height: 7); Text(model.isStreaming ? "RUNNING" : "READY").font(.caption2.monospaced()); if case .loaded(let access) = model.capabilities { Text("\(access.credits) CREDITS · \(access.remaining) RUNS").font(.caption2.monospaced()).foregroundStyle(.secondary) }; Spacer(); if model.isStreaming { Button("Stop") { Task { await model.cancel() } }.font(.caption).foregroundStyle(PGTheme.negative) } }.padding(.horizontal, 16).frame(height: 34).background(RoundedRectangle(cornerRadius: 10, style: .continuous).fill(PGTheme.secondaryBackground)) }
    @ViewBuilder private var messageList: some View { switch model.messages { case .loading, .idle: ProgressView("Loading conversation…").frame(maxWidth: .infinity, maxHeight: .infinity); case .empty: StateView(title: "Start a research thread", detail: "Ask about markets, portfolio risk, sources, or long-gamma research.", symbol: "sparkles"); case .failed(let e): StateView(title: "Conversation unavailable", detail: LocalizedStringKey(e.localizedDescription), symbol: "exclamationmark.bubble", retry: { if let row = model.selectedConversation { Task { await model.open(row) } } }); case .loaded(let rows), .stale(let rows, _): ScrollView { LazyVStack(spacing: 22) { ForEach(rows) { AgentMessageView(message: $0) }; ForEach(model.toolActivity, id: \.self) { Label($0, systemImage: "wrench.and.screwdriver").font(.caption.monospaced()).foregroundStyle(.secondary).frame(maxWidth: .infinity, alignment: .leading) } }.padding(16) }.defaultScrollAnchor(.bottom) } }
    private var recoveringStrip: some View {
        Label("Connection interrupted. Restoring from the server's record — nothing has been marked failed.", systemImage: "wifi.exclamationmark")
            .font(.caption).foregroundStyle(PGTheme.warning).frame(maxWidth: .infinity, alignment: .leading).padding(10)
            .accessibilityIdentifier("agent.recovering")
    }
    private func noticeStrip(_ text: String) -> some View {
        HStack { Image(systemName: "info.circle"); Text(text).lineLimit(2); Spacer(); Button("Dismiss") { model.notice = nil } }
            .font(.caption).padding(10).foregroundStyle(.secondary).background(RoundedRectangle(cornerRadius: 10, style: .continuous).fill(PGTheme.secondaryBackground))
    }
    private func errorStrip(_ error: APIError) -> some View {
        let showsRetry = model.pendingAttempt != nil && showsRetry(for: error)
        return HStack { Image(systemName: "exclamationmark.triangle"); Text(error.localizedDescription).lineLimit(2); Spacer(); if showsRetry { Button("Retry") { Task { await model.retry(locale: locale.language.languageCode?.identifier ?? "en") } } } }
            .font(.caption).padding(10).foregroundStyle(error.presentation == .permissionDenied ? PGTheme.warning : PGTheme.negative).background(RoundedRectangle(cornerRadius: 10, style: .continuous).fill(PGTheme.secondaryBackground))
    }
    private func showsRetry(for error: APIError) -> Bool {
        // Only failures a resend can fix offer Retry; it reuses the attempt's request id.
        if case .retryable = AgentSendFailure.classify(error) { return true }
        return false
    }
    private var composer: some View { VStack(spacing: 8) { if !model.context.attachments.isEmpty { ScrollView(.horizontal) { HStack { ForEach(model.context.attachments) { file in Text(file.name).font(.caption).padding(6).background(RoundedRectangle(cornerRadius: 8, style: .continuous).fill(PGTheme.tertiaryBackground)) } } } }; HStack(alignment: .bottom) { Button { importer = true } label: { Image(systemName: "paperclip") }.accessibilityLabel("Attach text file"); TextField("Ask with sources…", text: $model.prompt, axis: .vertical).lineLimit(1...6).textFieldStyle(.plain).padding(10).background(RoundedRectangle(cornerRadius: 10, style: .continuous).fill(PGTheme.secondaryBackground)); Button { Task { await model.send(locale: locale.language.languageCode?.identifier ?? "en") } } label: { Image(systemName: "arrow.up").frame(width: 34, height: 34).background(Circle().fill(PGTheme.accent)).foregroundStyle(PGTheme.onAccent) }.disabled(model.prompt.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || model.isStreaming).accessibilityLabel("Send") }; Text("Research only · Responses may use Credits").font(.caption2).foregroundStyle(.secondary) }.padding(12).overlay(alignment: .top) { TerminalDivider() } }
    private var conversationsSheet: some View { NavigationStack { Group { switch model.conversations { case .loaded(let rows), .stale(let rows, _): List(rows) { row in Button { Task { await model.open(row); showConversations = false } } label: { VStack(alignment: .leading) { Text(row.title); Text(PGFormat.dateTime(row.updatedAt)).font(.caption).foregroundStyle(.secondary) } } }; case .empty: StateView(title: "No conversations", detail: "Create your first research thread.", symbol: "bubble.left"); case .failed(let e): StateView(title: "Unable to load", detail: LocalizedStringKey(e.localizedDescription), symbol: "wifi.exclamationmark", retry: { Task { await model.load() } }); default: ProgressView() } }.navigationTitle("Conversations").toolbar { ToolbarItem(placement: .topBarLeading) { Button("Done") { showConversations = false } }; ToolbarItem(placement: .topBarTrailing) { Button { Task { await model.create(); showConversations = false } } label: { Image(systemName: "plus") } } } } }
}

struct AgentMessageView: View {
    let message: AgentMessage
    /// Terminal states other than success, as the server recorded them.
    static func endedCaption(_ status: String) -> String? {
        switch status {
        case "canceled": String(localized: "Stopped. Partial answer shown.")
        case "interrupted": String(localized: "Interrupted before it finished. Partial answer shown.")
        default: nil
        }
    }
    var body: some View { VStack(alignment: .leading, spacing: 10) { Text(message.role == "user" ? "YOU" : "PΓ / AGENT").font(.caption2.monospaced()).foregroundStyle(message.role == "user" ? .secondary : PGTheme.accent); Text(message.content.isEmpty && message.status == "streaming" ? "…" : message.content).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading); if let ended = AgentMessageView.endedCaption(message.status) { Text(ended).font(.caption).foregroundStyle(.secondary) }; if let error = message.errorMessage { Text(error).font(.caption).foregroundStyle(PGTheme.negative) }; if !message.sources.isEmpty { TerminalDivider(); ForEach(message.sources.sorted(by: { $0.citationIndex < $1.citationIndex })) { source in Link(destination: source.url ?? URL(string: "about:blank")!) { HStack(alignment: .top) { Text("[\(source.citationIndex)]").font(.caption.monospaced()).foregroundStyle(PGTheme.accent); VStack(alignment: .leading, spacing: 3) { Text(source.title).font(.caption).foregroundStyle(.primary); Text("\(source.provider) · \(PGFormat.dateTime(source.publishedAt ?? source.sourceTimestamp ?? source.fetchedAt))").font(.caption2).foregroundStyle(.secondary) } } }.disabled(source.url == nil) } } }.frame(maxWidth: .infinity, alignment: .leading).padding(message.role == "user" ? 12 : 0).background { if message.role == "user" { RoundedRectangle(cornerRadius: 12, style: .continuous).fill(PGTheme.secondaryBackground) } }.accessibilityElement(children: .contain) }
}

struct AgentContextView: View {
    @Bindable var model: AgentViewModel; @Binding var importer: Bool; @Environment(\.dismiss) private var dismiss
    let sourceOptions = ["market", "rss", "fintwit", "x-twitter", "bloomberg", "portfolio", "options"]
    var body: some View { NavigationStack { Form { Section("Model") { if case .loaded = model.capabilities { Picker("Model", selection: $model.context.model) { ForEach(model.modelMenu) { row in Text(row.selectable ? row.name : "\(row.name) · \(row.note ?? "")").tag(row.id).disabled(!row.selectable) } } } else { ProgressView() } }; if !model.permissionModes.isEmpty { Section("Permissions") { Picker("Agent may", selection: Binding(get: { model.permission }, set: { mode in Task { await model.setPermission(mode) } })) { ForEach(model.permissionModes) { Text($0.title).tag($0) } }.disabled(model.isStreaming) } }; Section("Data sources") { ForEach(availableSources, id: \.self) { item in Toggle(item, isOn: selection(item, in: $model.context.dataSources)) } }; Section("Skills") { ForEach(availableSkills, id: \.self) { item in Toggle(item, isOn: selection(item, in: $model.context.skills)) } }; Section("Custom prompt") { TextField("Additional research instructions", text: $model.context.customPrompt, axis: .vertical).lineLimit(3...8) }; Section("Attachments") { Button("Attach TXT, MD, CSV or JSON") { importer = true }; Text("Maximum 5 files, 20 KB each, 50 KB total.").font(.caption).foregroundStyle(.secondary) } }.navigationTitle("Agent context").toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } } } }
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
        case .approvalRequired(let tool): toolActivity.append("APPROVAL · \(tool)"); return .none
        case .planReady, .evidenceReady, .ignored: return .none
        }
    }
}
