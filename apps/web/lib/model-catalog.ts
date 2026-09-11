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

export type ModelAvailability = "live" | "pending" | "unavailable" | "unknown";

export type FlashAvailability = {
  state: ModelAvailability;
  model: GatewayCatalogModel | null;
  /** True only when the catalog itself reported the model as callable. */
  verified: boolean;
};

/**
 * Read availability straight off the catalog this deployment serves.
 *
 * Nothing here infers "live" from the model existing in the copy: a missing
 * catalog, a disabled Gateway, a pending price revision or a disabled provider
 * all resolve to a non-live state so the UI can never paint a green badge for a
 * model that cannot actually be called.
 */
export function flashAvailability(catalog: GatewayCatalog | null): FlashAvailability {
  if (!catalog || catalog.unavailable) return { state: "unknown", model: null, verified: false };
  const model = catalog.models.find((item) => item.id === FLASH_MODEL_ID) ?? null;
  if (!model) return { state: "unknown", model: null, verified: false };
  if (!catalog.gateway_enabled) return { state: "pending", model, verified: false };
  if (model.availability === "available") return { state: "live", model, verified: true };
  if (model.availability === "provider_disabled") return { state: "unavailable", model, verified: false };
  return { state: "pending", model, verified: false };
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
