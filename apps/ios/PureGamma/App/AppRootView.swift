import SwiftUI

struct AppRootView: View {
    @Environment(AppState.self) private var app
    var body: some View {
        switch app.session {
        case .restoring: ProgressView("Restoring session…").frame(maxWidth: .infinity, maxHeight: .infinity)
        case .signedOut: LoginView()
        case .authenticated:
            @Bindable var state = app
            TabView(selection: $state.selectedTab) {
                NavigationStack { TodayView(repository: app.repositories.today) }
                    .tabItem { Label("Today", systemImage: "chart.line.uptrend.xyaxis") }
                    .tag(AppTab.today)
                NavigationStack { AgentView(repository: app.repositories.agent) }
                    .tabItem { Label("Agent", systemImage: "sparkles") }
                    .tag(AppTab.agent)
                NavigationStack { ResearchView(repository: app.repositories.research) }
                    .tabItem { Label("Research", systemImage: "doc.text.magnifyingglass") }
                    .tag(AppTab.research)
                NavigationStack { PortfolioView(repository: app.repositories.portfolio) }
                    .tabItem { Label("Portfolio", systemImage: "chart.pie") }
                    .tag(AppTab.portfolio)
                NavigationStack { AccountView(repository: app.repositories.account) }
                    .tabItem { Label("Account", systemImage: "person.crop.circle") }
                    .tag(AppTab.account)
            }.tint(PGTheme.accent)
        }
    }
}
