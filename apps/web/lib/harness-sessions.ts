/**
 * Entry to the DSH Session front door (the multi-tenant session broker).
 *
 * Off unless NEXT_PUBLIC_DSH_SESSIONS_URL is set at build time. The value is
 * the broker's public URL, normally a dedicated subdomain such as
 * https://harness.puregamma.ai/ (see
 * docs/architecture/upgrade-20261029/dsh-ingress-isolation.md). Sessions live
 * in DSH; this app only links there and keeps no Session state of its own.
 */
export function harnessSessionsUrl(raw: string | undefined = process.env.NEXT_PUBLIC_DSH_SESSIONS_URL): string | null {
  const value = raw?.trim();
  if (!value) return null;
  try {
    const url = new URL(value);
    const loopback = url.hostname === "127.0.0.1" || url.hostname === "localhost";
    if (url.protocol !== "https:" && !(url.protocol === "http:" && loopback)) return null;
    if (url.username || url.password) return null;
    return url.href;
  } catch {
    return null;
  }
}
