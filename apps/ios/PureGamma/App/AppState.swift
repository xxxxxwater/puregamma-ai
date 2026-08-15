import Foundation
import Observation
import SwiftUI
import UIKit
import UserNotifications

@MainActor @Observable
final class AppState {
    enum SessionState: Equatable { case restoring, signedOut, authenticated(User), offline }

    var session: SessionState = .restoring
    var selectedTab: AppTab = .today
    var language: AppLanguage
    var appearance: AppAppearance
    var pushAuthorization: UNAuthorizationStatus = .notDetermined
    var pushDeliveryAvailable: Bool?
    var pushRegistrationError: String?
    /// 服务端能力发现结果。所有新功能入口以此为准；拉取失败时视为全部不可用。
    var mobileCapabilities: MobileCapabilities = .unavailable
    /// 待打开的研究任务 ID（Agent"启动研究"或推送深链写入，Research Tab 消费）。
    var pendingResearchRunID: String?
    private var currentPushToken: String?
    let authentication: AuthenticationService
    let repositories: RepositoryContainer

    var locale: Locale {
        switch language {
        case .system: Locale.current
        case .chinese: Locale(identifier: "zh-Hans")
        case .english: Locale(identifier: "en")
        }
    }
    var preferredColorScheme: ColorScheme? { appearance.colorScheme }

    init(authentication: AuthenticationService, repositories: RepositoryContainer) {
        self.authentication = authentication
        self.repositories = repositories
        language = AppLanguage(rawValue: UserDefaults.standard.string(forKey: "app.language") ?? "system") ?? .system
        appearance = AppAppearance(rawValue: UserDefaults.standard.string(forKey: "app.appearance") ?? "system") ?? .system
    }

    static func live() -> AppState {
        let keychain = KeychainTokenStore()
        let client = APIClient(configuration: .current, tokenStore: keychain)
        let auth = AuthenticationService(client: client, tokenStore: keychain)
        let state = AppState(authentication: auth, repositories: RepositoryContainer(client: client))
        client.onUnauthorized = { @MainActor [weak auth, weak state] in
            auth?.clearLocalSession()
            state?.session = .signedOut
            state?.selectedTab = .today
            if let repositories = state?.repositories { Task { await repositories.clearCaches() } }
        }
        return state
    }

    func restoreSession() async {
        guard authentication.hasToken else { session = .signedOut; return }
        do {
            session = .authenticated(try await authentication.currentUser())
            await loadMobileCapabilities()
            await resumePushRegistration()
        } catch let error as APIError {
            // Only a rejected token ends the session. Transport/server errors
            // (cold start without connectivity, transient 5xx) must preserve
            // the stored session and offer an offline-retry path instead of
            // silently logging the user out.
            switch error {
            case .unauthorized:
                authentication.clearLocalSession()
                await repositories.clearCaches()
                session = .signedOut
            default:
                session = .offline
            }
        } catch {
            authentication.clearLocalSession()
            await repositories.clearCaches()
            session = .signedOut
        }
    }

    func completeLogin(_ user: User) {
        session = .authenticated(user)
        Task {
            await loadMobileCapabilities()
            await resumePushRegistration()
        }
    }
    func logout() async {
        if let currentPushToken { try? await repositories.account.unregisterPushDevice(token: currentPushToken) }
        await authentication.logout(); await repositories.clearCaches(); currentPushToken = nil
        mobileCapabilities = .unavailable; pendingResearchRunID = nil
        session = .signedOut
    }
    func completeAccountDeletion() {
        if let currentPushToken { Task { try? await repositories.account.unregisterPushDevice(token: currentPushToken) } }
        authentication.clearLocalSession(); selectedTab = .today; currentPushToken = nil
        mobileCapabilities = .unavailable; pendingResearchRunID = nil
        session = .signedOut; Task { await repositories.clearCaches() }
    }

    func setLanguage(_ value: AppLanguage) {
        language = value; UserDefaults.standard.set(value.rawValue, forKey: "app.language")
    }
    func setAppearance(_ value: AppAppearance) {
        appearance = value; UserDefaults.standard.set(value.rawValue, forKey: "app.appearance")
    }

    func requestPushAuthorization() async -> Bool {
        do {
            let granted = try await UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .badge, .sound])
            await refreshPushAuthorization()
            if granted { UIApplication.shared.registerForRemoteNotifications() }
            return granted
        } catch {
            pushRegistrationError = error.localizedDescription
            return false
        }
    }

    func refreshPushAuthorization() async {
        pushAuthorization = await UNUserNotificationCenter.current().notificationSettings().authorizationStatus
    }

    func resumePushRegistration() async {
        await refreshPushAuthorization()
        if pushAuthorization == .authorized || pushAuthorization == .provisional || pushAuthorization == .ephemeral {
            UIApplication.shared.registerForRemoteNotifications()
        }
    }

    func registerPushDevice(_ token: String) async {
        currentPushToken = token
        guard case .authenticated = session else { return }
        do {
            pushDeliveryAvailable = try await repositories.account.registerPushDevice(token: token)
            pushRegistrationError = pushDeliveryAvailable == false ? String(localized: "Push delivery is not configured on the server.") : nil
        } catch {
            pushRegistrationError = error.localizedDescription
        }
    }

    func handlePushRoute(_ payload: [AnyHashable: Any]) {
        switch payload["route"] as? String {
        case "agent": selectedTab = .agent
        case "portfolio": selectedTab = .portfolio
        case "account": selectedTab = .account
        case "research", "report": selectedTab = .research
        case "research_run":
            // 点击通知后先按 run_id 查服务端最终状态，再打开详情（详情页会再次查询）。
            selectedTab = .research
            pendingResearchRunID = payload["run_id"] as? String ?? payload["runId"] as? String
        default: selectedTab = .today
        }
    }

    /// 拉取服务端能力。失败/未实现时全部按不可用处理；不做本地"可用"缓存。
    func loadMobileCapabilities() async {
        do {
            mobileCapabilities = try await repositories.mobileCapabilities.capabilities()
        } catch {
            mobileCapabilities = .unavailable
        }
    }
}

enum AppTab: Hashable { case today, agent, research, portfolio, account }
enum AppLanguage: String, CaseIterable, Identifiable {
    case system, chinese, english
    var id: String { rawValue }
    var title: LocalizedStringKey { switch self { case .system: "System"; case .chinese: "简体中文"; case .english: "English" } }
}
enum AppAppearance: String, CaseIterable, Identifiable {
    case system, light, dark
    var id: String { rawValue }
    var colorScheme: ColorScheme? { switch self { case .system: nil; case .light: .light; case .dark: .dark } }
    var title: LocalizedStringKey { switch self { case .system: "System"; case .light: "Light"; case .dark: "Dark" } }
}
