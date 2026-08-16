import Observation
import SwiftUI

@MainActor @Observable final class AccountViewModel {
    var billing: LoadState<BillingSummary> = .idle; var push: LoadState<DailyPushPreference> = .idle; var saving = false; var deleting = false; var error: APIError?
    private let repository: AccountRepository
    init(repository: AccountRepository) { self.repository = repository }
    func load() async { billing = .loading; push = .loading; async let b: Void = loadBilling(); async let p: Void = loadPush(); _ = await (b, p) }
    private func loadBilling() async { do { billing = .loaded(try await repository.subscription()) } catch { billing = .failed(error as? APIError ?? .transport(error.localizedDescription)) } }
    private func loadPush() async { do { push = .loaded(try await repository.pushPreference()) } catch { push = .failed(error as? APIError ?? .transport(error.localizedDescription)) } }
    func save(_ value: DailyPushPreference) async { saving = true; defer { saving = false }; do { push = .loaded(try await repository.updatePush(value)) } catch { self.error = error as? APIError ?? .transport(error.localizedDescription) } }
    func deleteAccount(confirmation: String) async -> Bool { deleting = true; defer { deleting = false }; do { try await repository.deleteAccount(confirmation: confirmation); return true } catch { self.error = error as? APIError ?? .transport(error.localizedDescription); return false } }
}

struct AccountView: View {
    @Environment(AppState.self) private var app; @State private var model: AccountViewModel; @State private var showDeleteAccount = false; @State private var deleteConfirmation = ""
    init(repository: AccountRepository) { _model = State(initialValue: AccountViewModel(repository: repository)) }
    var body: some View { Form { identity; billing; push; preferences; about; privacy; advancedFeatures; security; Section { Button("Sign out", role: .destructive) { Task { await app.logout() } }; Button("Delete account", role: .destructive) { deleteConfirmation = ""; showDeleteAccount = true }.disabled(model.deleting) } }.navigationTitle("Account").navigationBarTitleDisplayMode(.inline).task { await model.load() }.refreshable { await model.load() }.alert("Account", isPresented: Binding(get: { model.error != nil }, set: { if !$0 { model.error = nil } })) { Button("OK") {} } message: { Text(model.error?.localizedDescription ?? "") } .alert("Permanently delete account?", isPresented: $showDeleteAccount) { TextField("Confirm your email", text: $deleteConfirmation).textInputAutocapitalization(.never).keyboardType(.emailAddress); Button("Delete account", role: .destructive) { Task { if await model.deleteAccount(confirmation: deleteConfirmation) { app.completeAccountDeletion() } } }; Button("Cancel", role: .cancel) {} } message: { Text("This removes your PureGamma account and associated data. Enter the account email to confirm. Billing or records that must be retained by law may be handled separately.") } }
    private var about: some View { Section("About") { LabeledContent("Version", value: appVersion) } }
    private var appVersion: String {
        let info = Bundle.main.infoDictionary ?? [:]
        let version = info["CFBundleShortVersionString"] as? String ?? "—"
        let build = info["CFBundleVersion"] as? String ?? "—"
        return "\(version) (\(build))"
    }
    @ViewBuilder private var identity: some View { if case .authenticated(let user) = app.session { Section { HStack(spacing: 14) { AsyncImage(url: user.avatarURL) { image in image.resizable().scaledToFill() } placeholder: { Image(systemName: "person.crop.circle.fill").resizable().foregroundStyle(.secondary) }.frame(width: 48, height: 48).clipShape(Circle()); VStack(alignment: .leading) { Text(user.name).font(.headline); Text(user.email).font(.caption).foregroundStyle(.secondary) } }.accessibilityElement(children: .combine) } } }
    @ViewBuilder private var billing: some View { Section("Plan & Credits") { switch model.billing { case .loaded(let value), .stale(let value, _): LabeledContent("Plan", value: MembershipTier.label(value.membershipTier, plan: value.plan)); LabeledContent("Credits", value: String(value.credits)); LabeledContent("Billing status", value: value.status); if value.status == "past_due" { Label("Account capabilities are restricted by the server until billing is resolved.", systemImage: "exclamationmark.triangle").foregroundStyle(PGTheme.warning) }; Text("Purchases and upgrades are unavailable in this build pending App Store compliance review. Existing subscribers may manage billing through approved account-management channels.").font(.caption).foregroundStyle(.secondary); case .failed(let e): StateView(title: "Billing unavailable", detail: LocalizedStringKey(e.localizedDescription), symbol: "creditcard.trianglebadge.exclamationmark", retry: { Task { await model.load() } }); default: ProgressView() } } }
    @ViewBuilder private var push: some View {
        Section("Daily push") {
            switch model.push {
            case .loaded(let value), .stale(let value, _):
                Toggle("Daily research brief", isOn: Binding(
                    get: { value.enabled && value.channel == "push" },
                    set: { enabled in Task { await updatePush(value, enabled: enabled) } }
                ))
                .disabled(model.saving)
                LabeledContent("Channel", value: value.channel == "push" ? "iOS push" : value.channel)
                LabeledContent("Local time", value: value.localTime)
                LabeledContent("Time zone", value: value.timezone)
                if let next = value.nextDelivery { LabeledContent("Next delivery", value: PGFormat.dateTime(next)) }
                if value.enabled {
                    Section {
                        Toggle("Portfolio", isOn: contentBinding(value, \.includePortfolio))
                        Toggle("Markets", isOn: contentBinding(value, \.includeMarket))
                        Toggle("Signals", isOn: contentBinding(value, \.includeSignals))
                        Toggle("Risk", isOn: contentBinding(value, \.includeRisk))
                        Toggle("Sentiment", isOn: contentBinding(value, \.includeSentiment))
                    } header: { Text("Include in brief") } footer: { Text("Choose what appears in your daily research brief.") }
                }
                if app.pushDeliveryAvailable == false {
                    Label("APNs delivery is not configured on the server.", systemImage: "exclamationmark.triangle")
                        .font(.caption)
                        .foregroundStyle(PGTheme.warning)
                }
                if let error = app.pushRegistrationError {
                    Text(error).font(.caption).foregroundStyle(PGTheme.negative)
                }
            case .failed(let e):
                StateView(title: e.presentation == .permissionDenied ? "Push not included" : "Push settings unavailable", detail: LocalizedStringKey(e.localizedDescription), symbol: "bell.slash", retry: { Task { await model.load() } })
            default:
                ProgressView()
            }
        }
    }

    private func updatePush(_ value: DailyPushPreference, enabled: Bool) async {
        var copy = value
        if enabled {
            guard await app.requestPushAuthorization() else {
                model.error = .forbidden(String(localized: "Notifications are disabled. Enable them in iOS Settings and retry."))
                return
            }
            copy.channel = "push"
            copy.timezone = TimeZone.current.identifier
            copy.locale = app.locale.language.languageCode?.identifier ?? "en"
        }
        copy.enabled = enabled
        await model.save(copy)
    }
    private func contentBinding(_ value: DailyPushPreference, _ keyPath: WritableKeyPath<DailyPushPreference, Bool>) -> Binding<Bool> {
        Binding(get: { value[keyPath: keyPath] }, set: { newValue in
            var copy = value
            copy[keyPath: keyPath] = newValue
            Task { await model.save(copy) }
        })
    }
    private var preferences: some View {
        Section("Language & appearance") {
            Picker("Language", selection: Binding(
                get: { app.language.rawValue },
                set: { app.setLanguage(AppLanguage(rawValue: $0) ?? .system) }
            )) {
                ForEach(AppLanguage.allCases) { value in
                    Text(value.title).tag(value.rawValue)
                }
            }
            Picker("Appearance", selection: Binding(
                get: { app.appearance.rawValue },
                set: { app.setAppearance(AppAppearance(rawValue: $0) ?? .system) }
            )) {
                ForEach(AppAppearance.allCases) { value in
                    Text(value.title).tag(value.rawValue)
                }
            }
        }
    }
    private var privacy: some View { Section("Privacy & legal") { if let url = AppLinks.privacyPolicy { Link("Privacy policy", destination: url) }; if let url = AppLinks.terms { Link("Terms of service", destination: url) }; if let url = AppLinks.support { Link("Contact support", destination: url) } } }
    private var advancedFeatures: some View {
        Section("Research & safety") {
            NavigationLink { MemoryControlsView(repository: app.repositories.memory, capabilities: app.mobileCapabilities) } label: { Label("Memory controls", systemImage: "brain.head.profile") }
            NavigationLink { TradingSafetyView(repository: app.repositories.tradingMandates, capabilities: app.mobileCapabilities) } label: { Label("Trading safety", systemImage: "lock.shield") }
            if !app.mobileCapabilities.serverContractAvailable {
                Text("Harness research, memory and trading mandates appear here once the server exposes them.").font(.caption).foregroundStyle(.secondary)
            } else if let message = app.mobileCapabilities.maintenanceMessage {
                Text(message).font(.caption).foregroundStyle(PGTheme.warning)
            }
        }
    }
    private var security: some View { Section("Security boundary") { Label("Read-only research client", systemImage: "lock.shield").foregroundStyle(PGTheme.positive); Text("No LIVE orders, transfers, withdrawals, private keys, seed phrases or wallet signing. Stripe, LLM, Plaid, IBKR and exchange secrets remain server-side.").font(.caption).foregroundStyle(.secondary) } }
}
