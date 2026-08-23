import { api } from "@/lib/api";
import type { FrontendPluginManifest } from "../contracts";

/**
 * Fetches the FastAPI-managed plugin manifest (GET /api/frontend/plugins).
 * FastAPI decides WHO may load WHAT; the browser only resolves ids through
 * the compiled builtin whitelist, never server-provided URLs or code.
 */
export function fetchFrontendPlugins(): Promise<FrontendPluginManifest> {
  return api<FrontendPluginManifest>("/api/frontend/plugins", {
    fallback: { plugins: [], unavailable: true },
  });
}
