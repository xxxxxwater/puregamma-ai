/**
 * ctx.telemetry — structured event sink. Phase 1 logs to the dev console
 * only; the service boundary exists so plugins never touch window or a
 * beacon endpoint directly. A production sink (metrics endpoint) plugs
 * in here without changing any plugin.
 */
export class TelemetryService {
  track(event: string, properties: Record<string, unknown> = {}): void {
    if (typeof window === "undefined") return;
    if (process.env.NODE_ENV === "development") {
      // eslint-disable-next-line no-console
      console.debug(`[plugins:telemetry] ${event}`, properties);
    }
  }
}
