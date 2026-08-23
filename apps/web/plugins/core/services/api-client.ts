import {
  API_URL,
  api,
  getMarketSnapshot,
  getPortfolioPositions,
  getPortfolioSnapshot,
  getSignals,
  syncPortfolioAccount,
} from "@/lib/api";

/**
 * ctx.api — the single API entry point available to plugins.
 *
 * Converges the existing apps/web/lib/api.ts surface: plugins call through
 * this service instead of importing fetch helpers directly, so the runtime
 * can later add tenant/locale headers, auth-expiry handling and
 * observability in one place. FastAPI remains the only trusted boundary.
 */
export class ApiClientService {
  /** Fallback-backed fetch (never throws on network/auth errors). */
  get = api;

  get baseUrl(): string {
    return API_URL;
  }

  portfolio = {
    snapshot: getPortfolioSnapshot,
    positions: getPortfolioPositions,
    refreshAccount: syncPortfolioAccount,
  };

  market = {
    snapshot: getMarketSnapshot,
  };

  signals = {
    list: getSignals,
  };
}
