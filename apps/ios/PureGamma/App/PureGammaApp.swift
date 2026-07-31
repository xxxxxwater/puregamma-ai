import SwiftUI

@main
struct PureGammaApp: App {
    @UIApplicationDelegateAdaptor(PushAppDelegate.self) private var appDelegate
    @State private var appState = AppState.live()

    var body: some Scene {
        WindowGroup {
            AppRootView()
                .environment(appState)
                .environment(\.locale, appState.locale)
                .preferredColorScheme(appState.preferredColorScheme)
                .task { await appState.restoreSession() }
                .onOpenURL { appState.authentication.handleCallbackURL($0) }
                .onReceive(NotificationCenter.default.publisher(for: .pureGammaPushToken)) { notification in
                    guard let token = notification.object as? String else { return }
                    Task { await appState.registerPushDevice(token) }
                }
                .onReceive(NotificationCenter.default.publisher(for: .pureGammaPushRegistrationFailed)) { notification in
                    appState.pushRegistrationError = notification.object as? String
                }
                .onReceive(NotificationCenter.default.publisher(for: .pureGammaPushOpened)) { notification in
                    appState.handlePushRoute(notification.object as? [AnyHashable: Any] ?? [:])
                }
        }
    }
}
