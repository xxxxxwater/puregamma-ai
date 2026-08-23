import { publishUserState, USER_STATE_EVENT, type SessionUserState } from "@/lib/user-state";

/**
 * ctx.session — login state and user profile for plugins, backed by the
 * existing puregamma:user-state event bus. Login/logout/credit changes
 * already flow through publishUserState; plugins subscribe instead of
 * polling localStorage.
 */
export class SessionService {
  current(): SessionUserState | null {
    if (typeof window === "undefined") return null;
    try {
      const raw = window.localStorage.getItem("pg_user");
      return raw ? (JSON.parse(raw) as SessionUserState) : null;
    } catch {
      return null;
    }
  }

  subscribe(listener: (state: SessionUserState) => void): () => void {
    const handler = (event: Event) => {
      const detail = (event as CustomEvent<SessionUserState>).detail;
      if (detail) listener(detail);
    };
    window.addEventListener(USER_STATE_EVENT, handler);
    return () => window.removeEventListener(USER_STATE_EVENT, handler);
  }

  update(patch: SessionUserState, replace = false): void {
    publishUserState(patch, replace);
  }
}
