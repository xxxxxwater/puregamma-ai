import type {
  PureGammaBacktestArtifactFile, PureGammaBacktestArtifactView, PureGammaBacktestMetric, PureGammaBacktestRunSummary, PureGammaBacktestRunsView,
  PureGammaResearchArtifact, PureGammaResearchArtifactsView, PureGammaResearchEvidence, PureGammaResearchRunSummary, PureGammaResearchRunView,
  PureGammaResearchRunsView,
} from './types.ts'

/**
 * Pure projections from compatibility payloads to the browser views of the
 * research/backtest resource tabs. Only named fields cross to the browser —
 * never server paths, download URLs, tokens or unknown keys — and a missing
 * value stays `undefined` instead of becoming a zero or an empty string.
 */

type Payload = Record<string, unknown>
interface Document { observedAt: string; source: string; payload: Payload }

export const RESEARCH_TERMINAL_STATUSES: ReadonlySet<string> = new Set(['completed', 'degraded', 'failed', 'canceled', 'timed_out'])
export const MAX_ARTIFACT_MARKDOWN = 20000
const MAX_TEXT = 4000
const MAX_ROWS = 50

function record(value: unknown): Payload | undefined { return typeof value === 'object' && value !== null && !Array.isArray(value) ? value as Payload : undefined }
function text(source: Payload | undefined, key: string, max = MAX_TEXT): string | undefined {
  const value = source?.[key]
  if (typeof value !== 'string') return undefined
  const trimmed = value.trim()
  return trimmed ? trimmed.slice(0, max) : undefined
}
function finite(source: Payload | undefined, key: string): number | undefined { const value = source?.[key]; return typeof value === 'number' && Number.isFinite(value) ? value : undefined }
function bool(source: Payload | undefined, key: string): boolean | undefined { const value = source?.[key]; return typeof value === 'boolean' ? value : undefined }
function rows(source: Payload | undefined, key: string): Payload[] { const value = source?.[key]; return Array.isArray(value) ? value.map(record).filter((item): item is Payload => item !== undefined).slice(0, MAX_ROWS) : [] }
function strings(source: Payload | undefined, key: string): string[] | undefined { const value = source?.[key]; return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string').slice(0, MAX_ROWS) : undefined }
function httpUrl(value: string | undefined): string | undefined {
  if (value === undefined) return undefined
  try {
    const url = new URL(value)
    // Citation links only; credentials embedded in a URL are never forwarded.
    return (url.protocol === 'https:' || url.protocol === 'http:') && !url.username && !url.password ? url.toString() : undefined
  } catch {
    return undefined
  }
}

export function unavailableView<T extends { available: boolean; observedAt: string; source: string; reason?: string }>(source: string, reason: string, extra: Omit<T, 'available' | 'observedAt' | 'source' | 'reason'>): T {
  return { available: false, observedAt: new Date().toISOString(), source, reason, ...extra } as T
}

export function researchRunSummary(raw: unknown): PureGammaResearchRunSummary | undefined {
  const run = record(raw)
  const id = text(run, 'id', 160)
  if (id === undefined) return undefined
  return {
    id,
    name: text(run, 'name', 200),
    status: text(run, 'status', 40),
    verification: text(run, 'verification', 40),
    createdAt: text(run, 'created_at', 64),
    updatedAt: text(run, 'updated_at', 64),
    evidenceCount: finite(run, 'evidence_count'),
    citationCount: finite(run, 'citation_count'),
    creditsUsed: finite(run, 'credits_used'),
    degraded: bool(run, 'is_degraded'),
    errorMessage: text(run, 'error_message'),
    summary: text(run, 'summary'),
    disclaimer: text(run, 'disclaimer'),
    dataSources: strings(run, 'data_sources'),
  }
}

export function researchRunView(document: Document): PureGammaResearchRunView {
  const run = researchRunSummary(document.payload.run)
  if (run === undefined) return unavailableView<PureGammaResearchRunView>(document.source, 'research run payload has no run', {})
  return { available: true, observedAt: document.observedAt, source: document.source, terminal: run.status !== undefined && RESEARCH_TERMINAL_STATUSES.has(run.status), run }
}

export function researchRunsView(document: Document): PureGammaResearchRunsView {
  return {
    available: true, observedAt: document.observedAt, source: document.source,
    total: finite(document.payload, 'total'),
    runs: rows(document.payload, 'runs').map(researchRunSummary).filter((item): item is PureGammaResearchRunSummary => item !== undefined),
  }
}

function researchArtifact(raw: Payload): PureGammaResearchArtifact | undefined {
  const id = text(raw, 'id', 160)
  if (id === undefined) return undefined
  const markdown = typeof raw.markdown === 'string' && raw.markdown.trim() ? raw.markdown : undefined
  return {
    id, type: text(raw, 'type', 60), title: text(raw, 'title', 200), status: text(raw, 'status', 40), createdAt: text(raw, 'created_at', 64),
    ...(markdown === undefined ? {} : { markdown: markdown.slice(0, MAX_ARTIFACT_MARKDOWN), markdownTruncated: markdown.length > MAX_ARTIFACT_MARKDOWN }),
  }
}

function researchEvidence(raw: Payload): PureGammaResearchEvidence {
  return {
    id: text(raw, 'id', 160) ?? text(raw, 'evidence_id', 160),
    title: text(raw, 'title', 300) ?? text(raw, 'headline', 300),
    source: text(raw, 'source', 120) ?? text(raw, 'provider', 120),
    url: httpUrl(text(raw, 'url', 2000) ?? text(raw, 'source_url', 2000)),
    publishedAt: text(raw, 'published_at', 64) ?? text(raw, 'as_of', 64),
    snippet: text(raw, 'snippet', 600) ?? text(raw, 'summary', 600),
  }
}

/** Artifacts are required; evidence is best-effort and its failure is said, not hidden as "none". */
export function researchArtifactsView(runId: string, artifacts: Document, evidence: Document | undefined): PureGammaResearchArtifactsView {
  return {
    available: true, observedAt: artifacts.observedAt, source: artifacts.source, runId,
    artifacts: rows(artifacts.payload, 'artifacts').map(researchArtifact).filter((item): item is PureGammaResearchArtifact => item !== undefined),
    evidenceAvailable: evidence !== undefined,
    evidence: evidence === undefined ? [] : rows(evidence.payload, 'evidence').map(researchEvidence),
  }
}

export function backtestRunSummary(raw: unknown): PureGammaBacktestRunSummary | undefined {
  const run = record(raw)
  const id = text(run, 'id', 160)
  if (id === undefined) return undefined
  return {
    id, status: text(run, 'status', 40), engine: text(run, 'engine', 60), strategyName: text(run, 'strategy_name', 200), asset: text(run, 'asset', 40),
    createdAt: text(run, 'created_at', 64), completedAt: text(run, 'completed_at', 64),
  }
}

function backtestMetrics(run: Payload | undefined): PureGammaBacktestMetric[] {
  const performance = record(run?.performance) ?? record(record(run?.result)?.metrics)
  if (performance === undefined) return []
  return Object.entries(performance)
    .filter((entry): entry is [string, number] => typeof entry[1] === 'number' && Number.isFinite(entry[1]))
    .slice(0, MAX_ROWS)
    .map(([name, value]) => ({ name: name.slice(0, 80), value }))
}

function backtestArtifactFile(raw: Payload): PureGammaBacktestArtifactFile | undefined {
  const id = text(raw, 'id', 160)
  if (id === undefined) return undefined
  // `relative_path` is a server storage path and stays on the Host.
  return { id, artifactType: text(raw, 'artifact_type', 60), format: text(raw, 'format', 20), sizeBytes: finite(raw, 'size_bytes'), checksum: text(raw, 'checksum', 128), createdAt: text(raw, 'created_at', 64) }
}

export function backtestArtifactView(document: Document): PureGammaBacktestArtifactView {
  const run = record(document.payload.run)
  const summary = backtestRunSummary(run)
  if (summary === undefined) return unavailableView<PureGammaBacktestArtifactView>(document.source, 'backtest payload has no run', { metrics: [], artifacts: [] })
  const window = record(run?.window)
  return {
    available: true, observedAt: document.observedAt, source: document.source,
    run: { ...summary, windowStart: text(window, 'start', 64), windowEnd: text(window, 'end', 64), errorMessage: text(record(run?.error), 'message'), isLegacy: bool(run, 'is_legacy') },
    metrics: backtestMetrics(run),
    artifacts: rows(run, 'artifacts').map(backtestArtifactFile).filter((item): item is PureGammaBacktestArtifactFile => item !== undefined),
  }
}

export function backtestRunsView(document: Document): PureGammaBacktestRunsView {
  return {
    available: true, observedAt: document.observedAt, source: document.source,
    total: finite(document.payload, 'total'),
    runs: rows(document.payload, 'runs').map(backtestRunSummary).filter((item): item is PureGammaBacktestRunSummary => item !== undefined),
  }
}
