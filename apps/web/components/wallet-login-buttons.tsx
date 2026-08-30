"use client";

import { useState } from "react";
import { Loader2, Wallet } from "lucide-react";
import type { Locale } from "@/i18n/routing";
import { t } from "@/lib/translations";
import { getWalletNonce, verifyWallet, extractApiError } from "@/lib/api";

type Eip1193Provider = {
  isMetaMask?: boolean;
  isZerion?: boolean;
  providers?: Eip1193Provider[];
  request: (args: { method: string; params?: unknown[] }) => Promise<unknown>;
};

function injectedEthereum(): Eip1193Provider | undefined {
  if (typeof window === "undefined") return undefined;
  return window.ethereum as Eip1193Provider | undefined;
}

function injectedProviders(): Eip1193Provider[] {
  const root = injectedEthereum();
  if (!root) return [];
  return Array.isArray(root.providers) && root.providers.length ? root.providers : [root];
}

function pickProvider(kind: "metamask" | "zerion"): Eip1193Provider | null {
  const providers = injectedProviders();
  if (kind === "metamask") return providers.find((p) => p.isMetaMask) ?? null;
  return providers.find((p) => p.isZerion) ?? null;
}

/**
 * MetaMask / Zerion wallet sign-in buttons (SIWE / EIP-4361 personal_sign —
 * gas-free, no contract call). An unknown address creates the account, so the
 * same button serves both sign-up and sign-in.
 */
export function WalletLoginButtons({ locale, onError }: { locale: Locale; onError: (message: string) => void }) {
  const [busy, setBusy] = useState<"" | "metamask" | "zerion">("");

  const signIn = async (kind: "metamask" | "zerion") => {
    if (busy) return;
    onError("");
    const provider = pickProvider(kind);
    if (!provider) {
      onError(t(locale, kind === "metamask" ? "common.auth.walletNoMetaMask" : "common.auth.walletNoZerion"));
      return;
    }
    setBusy(kind);
    try {
      const accounts = (await provider.request({ method: "eth_requestAccounts" })) as string[];
      const address = (accounts?.[0] || "").toLowerCase();
      if (!address) throw new Error("no_account");
      let chainId = 1;
      try {
        chainId = parseInt(String(await provider.request({ method: "eth_chainId" })), 16) || 1;
      } catch {
        /* default to mainnet id in the message */
      }
      const { message } = await getWalletNonce(address, chainId);
      const signature = (await provider.request({
        method: "personal_sign",
        params: [message, address],
      })) as string;
      await verifyWallet(address, signature, kind);
      const returnTo = new URLSearchParams(window.location.search).get("returnTo");
      window.location.href = returnTo?.startsWith("/") && !returnTo.startsWith("//") ? returnTo : `/${locale}/chat`;
    } catch (err) {
      const apiError = extractApiError(err);
      const code = (err as { code?: number } | null)?.code;
      if (code === 4001) {
        onError(t(locale, "common.auth.walletRejected"));
      } else if (apiError.code === "WALLET_NONCE_EXPIRED") {
        onError(t(locale, "common.auth.walletNonceExpired"));
      } else if (apiError.code === "WALLET_SIGNATURE_MISMATCH" || apiError.code === "WALLET_SIGNATURE_INVALID") {
        onError(t(locale, "common.auth.walletSignatureInvalid"));
      } else if (apiError.status === 429) {
        onError(t(locale, "common.auth.walletRateLimited"));
      } else {
        onError(t(locale, "common.auth.walletSignFailed"));
      }
    } finally {
      setBusy("");
    }
  };

  return (
    <div className="grid grid-cols-2 gap-3">
      <button
        type="button"
        disabled={Boolean(busy)}
        onClick={() => void signIn("metamask")}
        className="inline-flex items-center justify-center gap-2 border border-border-pg bg-bg-panel-muted px-4 py-2.5 text-sm font-semibold text-text-pg transition hover:border-border-pg-strong disabled:cursor-not-allowed disabled:opacity-50 rounded-lg"
      >
        {busy === "metamask" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Wallet className="h-4 w-4" />}
        MetaMask
      </button>
      <button
        type="button"
        disabled={Boolean(busy)}
        onClick={() => void signIn("zerion")}
        className="inline-flex items-center justify-center gap-2 border border-border-pg bg-bg-panel-muted px-4 py-2.5 text-sm font-semibold text-text-pg transition hover:border-border-pg-strong disabled:cursor-not-allowed disabled:opacity-50 rounded-lg"
      >
        {busy === "zerion" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Wallet className="h-4 w-4" />}
        Zerion
      </button>
    </div>
  );
}
