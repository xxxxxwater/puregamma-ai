import type { GatewayCatalog, GatewayCatalogModel } from "@/lib/api";

/**
 * Catalog-derived model facts, shared by server and client components.
 *
 * This module is deliberately framework-neutral: it uses no hooks, no React and
 * no `"use client"` directive, so a Server Component can call `flashAvailability`
 * directly. Exporting it from a client component instead would turn it into a
 * client-reference proxy on the server, which throws when invoked during a
 * static render.
 */

/** Canonical public id of DeepSeek V4.1 Flash in the Gateway catalog. */
export const FLASH_MODEL_ID = "deepseek-flash";

/** Compatibility id DeepSeek still serves from the same upstream model. */
export const FLASH_ALIAS_ID = "deepseek-v4-flash";

/**
 * Catalog state, kept deliberately distinct from runtime health.
 *
 * These four states answer "what does the published catalog say?" — the only
 * question the public endpoint can answer. They are NOT a health check:
 *
 *   - `available`    the catalog serves it with an approved, active price and
 *                    an enabled provider. This is a *published and priced*
 *                    fact, not proof that the upstream is healthy right now.
 *   - `pending`      the catalog has the model but pricing review or provider
 *                    enablement has not completed. Not billable yet.
 *   - `unavailable`  the provider is disabled: do not offer it.
 *   - `unknown`      the catalog could not be read, so nothing is claimed.
 *
 * Runtime health is a separate concern with a separate owner: the provider
 * health check and request outcome live behind the authenticated Gateway
 * dashboard (`GET /gateway/dashboard`, `POST /admin/gateway/providers/
 * healthcheck`) and the agent capability endpoint. A page that only reads the
 * public catalog must not present its state as a health guarantee, which is why
 * the UI labels this "published with an approved price".
 */
export type ModelCatalogState = "available" | "pending" | "unavailable" | "unknown";

export type FlashAvailability = {
  state: ModelCatalogState;
  /** UI-facing state: `available` here means published and priced, not healthy. */
  uiState: "published" | "pending" | "unavailable" | "unverified";
  model: GatewayCatalogModel | null;
  /** True only when the catalog itself reported the model as published+priced. */
  verified: boolean;
};

/**
 * Read catalog state straight off the catalog this deployment serves.
 *
 * Nothing here infers availability from the model existing in copy: a missing
 * catalog, a disabled Gateway, a pending price revision or a disabled provider
 * all resolve to a non-available state so the UI can never paint a green badge
 * for a model that cannot actually be called.
 */
export function flashAvailability(catalog: GatewayCatalog | null): FlashAvailability {
  const none: FlashAvailability = { state: "unknown", uiState: "unverified", model: null, verified: false };
  if (!catalog || catalog.unavailable) return none;
  const model = catalog.models.find((item) => item.id === FLASH_MODEL_ID) ?? null;
  if (!model) return none;
  if (!catalog.gateway_enabled) return { state: "pending", uiState: "pending", model, verified: false };
  if (model.availability === "available") return { state: "available", uiState: "published", model, verified: true };
  if (model.availability === "provider_disabled") return { state: "unavailable", uiState: "unavailable", model, verified: false };
  return { state: "pending", uiState: "pending", model, verified: false };
}

/**
 * The platform's default model as the deployment declares it.
 *
 * The request sent to the Agent API keeps the `default` sentinel — that is the
 * routing contract and this function never changes it. This resolves the
 * *label* for that sentinel from the catalog, so the UI does not hardcode a
 * model name that the backend could change.
 *
 * `metadata.platform_default: "true"` is the authoritative declaration. Until
 * the backend publishes it, `FLASH_MODEL_ID` is the documented fallback.
 */
export function platformDefaultModel(catalog: GatewayCatalog | null): GatewayCatalogModel | null {
  const models = catalog?.models ?? [];
  const declared = models.find((model) => String(model.metadata?.platform_default ?? "").toLowerCase() === "true");
  if (declared) return declared;
  return models.find((model) => model.id === FLASH_MODEL_ID) ?? null;
}

/** Display name for the resolved default model, or null when nothing is known. */
export function platformDefaultModelName(catalog: GatewayCatalog | null): string | null {
  return platformDefaultModel(catalog)?.display_name ?? null;
}

/** Compact a token count for display, returning null when the catalog omits it. */
export function compactTokens(value: unknown): string | null {
  const numeric = Number(value || 0);
  if (!Number.isFinite(numeric) || numeric <= 0) return null;
  if (numeric >= 1_000_000) return `${Number((numeric / 1_000_000).toFixed(1))}M`;
  if (numeric >= 1_000) return `${Number((numeric / 1_000).toFixed(1))}K`;
  return String(numeric);
}

/** Human label for a catalog availability value. */
export function catalogAvailabilityLabel(
  model: GatewayCatalogModel,
  catalog: GatewayCatalog | null,
  zh: boolean,
): string {
  if (!catalog?.gateway_enabled) return zh ? "网关待启用" : "Gateway disabled";
  return {
    available: zh ? "已上线" : "Live",
    pending_approval: zh ? "待价格审批" : "Price pending approval",
    provider_disabled: zh ? "渠道已停用" : "Provider disabled",
    setup_required: zh ? "配置中" : "Setup required",
  }[model.availability];
}

/** Provider label that never depends on curated copy. */
export function catalogProviderLabel(model: GatewayCatalogModel | undefined, id: string): string {
  if (model?.provider_display_name) return model.provider_display_name;
  if (id.startsWith("deepseek")) return "DeepSeek";
  if (id.startsWith("kimi")) return "Moonshot AI";
  if (id.startsWith("glm")) return "Zhipu AI";
  return "";
}
