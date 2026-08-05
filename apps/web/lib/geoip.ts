interface CacheEntry {
  country: string | null;
  expires: number;
}

const geoCache = new Map<string, CacheEntry>();
const CACHE_TTL = 60 * 60 * 1000;
const LOOKUP_TIMEOUT = 2000;

function extractClientIP(headers: Headers): string | null {
  const forwarded = headers.get("x-forwarded-for");
  if (forwarded) {
    const first = forwarded.split(",")[0]?.trim();
    if (first) return first;
  }
  return headers.get("x-real-ip");
}

async function lookupCountry(ip: string): Promise<string | null> {
  const cached = geoCache.get(ip);
  if (cached && cached.expires > Date.now()) {
    return cached.country;
  }

  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), LOOKUP_TIMEOUT);
    const res = await fetch(
      `http://ip-api.com/json/${encodeURIComponent(ip)}?fields=countryCode`,
      { signal: controller.signal }
    );
    clearTimeout(timeout);

    if (!res.ok) {
      geoCache.set(ip, { country: null, expires: Date.now() + CACHE_TTL });
      return null;
    }

    const data = await res.json();
    const country = data.countryCode || null;
    geoCache.set(ip, { country, expires: Date.now() + CACHE_TTL });
    return country;
  } catch {
    geoCache.set(ip, { country: null, expires: Date.now() + CACHE_TTL });
    return null;
  }
}

function isPrivateIP(ip: string): boolean {
  if (ip === "127.0.0.1" || ip === "::1" || ip === "0.0.0.0") return true;
  if (ip.startsWith("10.") || ip.startsWith("192.168.")) return true;
  if (/^172\.(1[6-9]|2\d|3[01])\./.test(ip)) return true;
  return false;
}

export async function isChinaIP(headers: Headers): Promise<boolean> {
  const ip = extractClientIP(headers);
  if (!ip || isPrivateIP(ip)) return false;
  return (await lookupCountry(ip)) === "CN";
}
