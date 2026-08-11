import Observation
import SwiftUI

@MainActor @Observable final class TodayViewModel {
    var market: LoadState<[MarketAsset]> = .idle; var reports: LoadState<[Report]> = .idle; var billing: LoadState<BillingSummary> = .idle
    private let repository: TodayRepository
    init(repository: TodayRepository) { self.repository = repository }
    func load() async {
        market = .loading; reports = .loading; billing = .loading
        async let a: Result<CachedRepositoryValue<[MarketAsset]>, Error> = asyncResult { try await repository.cachedMarket() }; async let b: Result<CachedRepositoryValue<[Report]>, Error> = asyncResult { try await repository.cachedReports() }; async let c: Result<BillingSummary, Error> = asyncResult { try await repository.subscription() }
        let (assets, reportRows, summary) = await (a, b, c)
        market = Self.cachedState(assets, isEmpty: { $0.isEmpty }); reports = Self.cachedState(reportRows, isEmpty: { $0.isEmpty }); billing = Self.state(summary, isEmpty: { _ in false })
    }
    private static func cachedState<T>(_ result: Result<CachedRepositoryValue<T>, Error>, isEmpty: (T) -> Bool) -> LoadState<T> { switch result { case .success(let result): if isEmpty(result.value) { return .empty }; return result.cachedAt.map { .stale(result.value, $0) } ?? .loaded(result.value); case .failure(let error): return .failed(error as? APIError ?? .transport(error.localizedDescription)) } }
    private static func state<T>(_ result: Result<T, Error>, isEmpty: (T) -> Bool) -> LoadState<T> { switch result { case .success(let value): if isEmpty(value) { return .empty }; return .loaded(value); case .failure(let error): return .failed(error as? APIError ?? .transport(error.localizedDescription)) } }
}

private func asyncResult<T>(_ operation: () async throws -> T) async -> Result<T, Error> { do { return .success(try await operation()) } catch { return .failure(error) } }

struct TodayView: View {
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @State private var model: TodayViewModel
    init(repository: TodayRepository) { _model = State(initialValue: TodayViewModel(repository: repository)) }
    var body: some View {
        ScrollView { LazyVStack(alignment: .leading, spacing: 22) {
            title; billing; PGSectionHeader(index: "01", title: "Markets", trailing: "REAL DATA"); market; PGSectionHeader(index: "02", title: "Latest research"); reports; RiskDisclosureView()
        }.padding(.horizontal, 16).padding(.bottom, 24) }
        .navigationTitle("Today").navigationBarTitleDisplayMode(.inline).refreshable { await model.load() }.task { if case .idle = model.market { await model.load() } }
    }
    private var title: some View { VStack(alignment: .leading, spacing: 6) { Text("DECISION SUPPORT / UTC INPUT").font(.caption2.monospaced()).foregroundStyle(PGTheme.accent); Text("What changed today?").font(.largeTitle.weight(.semibold)); Text("Beta, alpha and long-gamma context from connected sources.").foregroundStyle(.secondary) }.padding(.top, 8) }
    @ViewBuilder private var billing: some View { switch model.billing { case .loaded(let value): billingMetrics(value).padding(.vertical, 12).overlay(alignment: .top) { TerminalDivider() }.overlay(alignment: .bottom) { TerminalDivider() }; case .failed(let e): StateView(title: "Credits unavailable", detail: LocalizedStringKey(e.localizedDescription), symbol: "creditcard.trianglebadge.exclamationmark", retry: { Task { await model.load() } }); default: ProgressView().frame(maxWidth: .infinity) } }
    @ViewBuilder private func billingMetrics(_ value: BillingSummary) -> some View {
        // Three monospaced columns hard-truncate at Accessibility sizes; stack
        // vertically instead so each metric keeps its full width.
        if dynamicTypeSize.isAccessibilitySize {
            VStack(alignment: .leading, spacing: 14) { metric("PLAN", value.plan); metric("CREDITS", String(value.credits)); metric("STATUS", value.status.uppercased()) }
        } else {
            HStack { metric("PLAN", value.plan); metric("CREDITS", String(value.credits)); metric("STATUS", value.status.uppercased()) }
        }
    }
    private func metric(_ label: String, _ value: String) -> some View { VStack(alignment: .leading, spacing: 5) { Text(label).font(.caption2.monospaced()).foregroundStyle(.secondary); Text(value).font(.headline.monospaced()).lineLimit(1).minimumScaleFactor(0.7) }.frame(maxWidth: .infinity, alignment: .leading).accessibilityElement(children: .combine) }
    @ViewBuilder private var market: some View { switch model.market { case .loading, .idle: ProgressView("Loading live markets…").frame(maxWidth: .infinity, minHeight: 180); case .empty: StateView(title: "No market data", detail: "No authorized market feed is currently available.", symbol: "chart.line.downtrend.xyaxis", retry: { Task { await model.load() } }); case .failed(let e): StateView(title: LocalizedStringKey(e.presentation == .offline ? "Offline" : "Markets unavailable"), detail: LocalizedStringKey(e.localizedDescription), symbol: "wifi.exclamationmark", retry: { Task { await model.load() } }); case .loaded(let assets): marketRows(assets); case .stale(let assets, let cachedAt): VStack(alignment: .leading, spacing: 8) { StaleDataBanner(cachedAt: cachedAt); marketRows(assets) } } }
    @ViewBuilder private var reports: some View { switch model.reports { case .loading, .idle: ProgressView().frame(maxWidth: .infinity); case .empty: StateView(title: "No reports yet", detail: "A sourced report will appear after generation.", symbol: "doc"); case .failed(let e): StateView(title: "Research unavailable", detail: LocalizedStringKey(e.localizedDescription), symbol: "doc.badge.ellipsis", retry: { Task { await model.load() } }); case .loaded(let rows): reportRows(rows); case .stale(let rows, let cachedAt): VStack(alignment: .leading, spacing: 8) { StaleDataBanner(cachedAt: cachedAt); reportRows(rows) } } }
    private func marketRows(_ assets: [MarketAsset]) -> some View { VStack(spacing: 0) { ForEach(assets) { MarketRow(asset: $0); TerminalDivider() } } }
    private func reportRows(_ rows: [Report]) -> some View { VStack(spacing: 0) { ForEach(rows.prefix(3)) { ReportRow(report: $0); TerminalDivider() } } }
}

struct StaleDataBanner: View {
    let cachedAt: Date
    var body: some View { Label("Offline · showing server data saved \(PGFormat.dateTime(cachedAt))", systemImage: "clock.badge.exclamationmark").font(.caption).foregroundStyle(PGTheme.warning).accessibilityLabel(String(localized: "Stale data saved \(PGFormat.dateTime(cachedAt))")) }
}

struct MarketRow: View {
    let asset: MarketAsset
    private var coin: String { asset.symbol.uppercased().replacingOccurrences(of: "-USDC", with: "").replacingOccurrences(of: "USDC", with: "").replacingOccurrences(of: "DLY", with: "").trimmingCharacters(in: .whitespaces) }
    private var iconName: String? {
        switch coin {
        case "BTC": "coin_btc"; case "ETH": "coin_eth"; case "HYPE": "coin_hype"; case "ZEC": "coin_zec"; case "SOL": "coin_sol"; case "CASHCAT": "coin_cashcat"; case "ONDO": "coin_ondo"; default: nil
        }
    }
    var body: some View { HStack(spacing: 14) { icon; VStack(alignment: .leading, spacing: 4) { HStack { Text(asset.symbol).font(.headline.monospaced()); Text(asset.isRealtime ? "LIVE" : "DLY").font(.caption2.monospaced()).foregroundStyle(asset.isRealtime ? PGTheme.positive : PGTheme.warning) }; Text(asset.source).font(.caption2).foregroundStyle(.secondary).lineLimit(1) }.frame(maxWidth: .infinity, alignment: .leading); VStack(alignment: .trailing, spacing: 4) { Text(PGFormat.money(asset.price)).font(.headline.monospacedDigit()); Text(PGFormat.percent(asset.change24H)).font(.caption.monospacedDigit()).foregroundStyle(PGTheme.change(asset.change24H)) }; Text(asset.riskScore.map { "R\(NSDecimalNumber(decimal: $0).intValue)" } ?? "R—").font(.caption.monospaced()).frame(width: 34) }.padding(.vertical, 13).accessibilityElement(children: .combine).accessibilityLabel(String(localized: "\(asset.symbol), \(PGFormat.money(asset.price)), change \(PGFormat.percent(asset.change24H)), source \(asset.source)")) }
    @ViewBuilder private var icon: some View {
        if let iconName {
            Image(iconName).resizable().scaledToFill().frame(width: 22, height: 22).clipShape(Circle()).accessibilityHidden(true)
        } else {
            ZStack { Circle().fill(Color(.secondarySystemBackground)); Text(String(coin.prefix(1))).font(.caption2.bold()).foregroundStyle(.secondary) }.frame(width: 22, height: 22).accessibilityHidden(true)
        }
    }
}
struct ReportRow: View { let report: Report; var body: some View { VStack(alignment: .leading, spacing: 7) { HStack { Text(report.type.uppercased()).font(.caption2.monospaced()).foregroundStyle(PGTheme.accent); Spacer(); Text(PGFormat.dateTime(report.createdAt)).font(.caption2).foregroundStyle(.secondary) }; Text(report.title).font(.headline); Text(report.markdown.replacingOccurrences(of: "#", with: "")).font(.subheadline).foregroundStyle(.secondary).lineLimit(3) }.padding(.vertical, 14).accessibilityElement(children: .combine) } }
