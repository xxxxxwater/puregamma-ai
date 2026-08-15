export type SessionUserState = {
  id?: string;
  email?: string;
  name?: string;
  avatar_url?: string | null;
  auth_provider?: string;
  plan?: string;
  membership_tier?: string;
  credit_balance?: number;
};

export const USER_STATE_EVENT = "puregamma:user-state";

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function storedUser(): SessionUserState | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem("pg_user");
    return raw ? JSON.parse(raw) as SessionUserState : null;
  } catch {
    return null;
  }
}

export function publishUserState(update: SessionUserState, replace = false): void {
  if (typeof window === "undefined") return;
  const next = replace ? update : { ...(storedUser() || {}), ...update };
  try {
    window.localStorage.setItem("pg_user", JSON.stringify(next));
  } catch {
    // A blocked storage backend must not prevent live UI updates.
  }
  window.dispatchEvent(new CustomEvent<SessionUserState>(USER_STATE_EVENT, { detail: next }));
}

export function publishCreditBalance(balance: number): void {
  if (!Number.isFinite(balance) || balance < 0) return;
  publishUserState({ credit_balance: balance });
}

export function syncUserStateFromPayload(payload: unknown): void {
  if (typeof window === "undefined" || !isRecord(payload)) return;
  if (isRecord(payload.user)) {
    publishUserState(payload.user as SessionUserState, true);
    return;
  }

  const quota = isRecord(payload.quota) ? payload.quota : null;
  const capabilities = isRecord(payload.capabilities) ? payload.capabilities : null;
  const balance = payload.credit_balance ?? quota?.credit_balance ?? capabilities?.credit_balance;
  const update: SessionUserState = {};
  if (typeof balance === "number") update.credit_balance = balance;
  if (typeof payload.plan === "string" && payload.plan) update.plan = payload.plan;
  if (Object.keys(update).length) publishUserState(update);
}
