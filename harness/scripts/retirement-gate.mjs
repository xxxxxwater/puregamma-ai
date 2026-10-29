/**
 * Pure validation behind scripts/retirement-check.mjs, split out so the rules
 * are unit-tested (scripts/retirement-check.test.mjs).
 *
 * `retired` holds per-route certificates and is the ONLY thing that permits a
 * legacy file to disappear. `candidates` records evidence progress toward a
 * certificate — gate by gate, with who supplies what is missing — and never
 * authorizes anything: a candidate's legacy file must still exist, and a
 * surface cannot be both a candidate and retired.
 */

export const CERTIFICATE_FIELDS = ['replacementPlugin', 'identityBinding', 'readWritePermissions', 'observableStates', 'bilingualUi', 'lifecycleCleanup', 'streamAndBinaryParity', 'e2eArtifactUrl', 'rollbackProcedure', 'reviewedBy', 'verifiedAt']

/** The per-capability migration gate of docs/architecture/HARNESS_CORE_V2.md, plus the certificate's deployment/review facts. */
export const CANDIDATE_GATES = [
  'serviceDefinition', 'providerHealth', 'dependencyInjection', 'lifecycleOwnedResources', 'toolGating', 'pluginUi',
  'pluginOwnedJobs', 'restartReconnect', 'observability', 'invariants', 'parityTests',
  'e2eArtifact', 'deploymentImage', 'humanReview',
]
export const GATE_STATUS = ['met', 'partial', 'missing']

export function ledgerRows(text, prefix, errors) {
  const entries = [...text.matchAll(/\{\s*surface:\s*'([^']+)'\s*,\s*(?:owner|target):\s*'([^']+)'/g)]
    .map(([, surface, owner]) => ({ surface, owner }))
    .filter(({ surface }) => surface.startsWith(prefix))
  const seen = new Set()
  for (const entry of entries) {
    if (seen.has(entry.surface)) errors.push(`duplicate migration owner: ${entry.surface}`)
    seen.add(entry.surface)
  }
  return entries
}

const text = (value, min = 8) => typeof value === 'string' && value.trim().length >= min

/**
 * @param {{ webMap: string, apiMap: string, certificate: unknown, exists: (surface: string) => boolean }} input
 * @returns {{ errors: string[], web: number, api: number, present: number, retired: number, candidates: { surface: string, met: number, total: number }[] }}
 */
export function validateRetirement({ webMap, apiMap, certificate, exists }) {
  const errors = []
  if (!certificate || typeof certificate !== 'object' || certificate.schemaVersion !== 1 || !certificate.retired || typeof certificate.retired !== 'object' || Array.isArray(certificate.retired)) {
    throw new Error('retirement-evidence.json must contain schemaVersion=1 and a retired object')
  }
  const web = ledgerRows(webMap, 'apps/web/app/', errors)
  const api = ledgerRows(apiMap, 'apps/api/routers/', errors)
  // Ledger rows must NOT disappear as pages retire: history is the anti-omission baseline.
  if (web.length < 83) errors.push(`web migration ledger shrank below 83 baseline entries: ${web.length}`)
  if (api.length < 38) errors.push(`API router migration ledger shrank below 38 baseline entries: ${api.length}`)
  const all = [...web, ...api]
  const owners = new Map(all.map(row => [row.surface, row.owner]))

  for (const [surface, evidence] of Object.entries(certificate.retired)) {
    if (!owners.has(surface)) errors.push(`retirement certificate has no preserved migration owner: ${surface}`)
    if (typeof evidence !== 'object' || evidence === null || Array.isArray(evidence)) {
      errors.push(`retirement certificate must be an object: ${surface}`)
      continue
    }
    if (evidence.owner !== owners.get(surface)) errors.push(`retirement owner mismatch: ${surface}`)
    for (const field of CERTIFICATE_FIELDS) {
      if (!text(evidence[field])) errors.push(`retirement evidence ${surface} missing ${field}`)
    }
    if (!/^[0-9a-f]{40}$/.test(String(evidence.integratedCommit ?? ''))) errors.push(`retirement evidence ${surface} missing exact integrated commit SHA`)
    if (!/^sha256:[0-9a-f]{64}$/.test(String(evidence.imageDigest ?? ''))) errors.push(`retirement evidence ${surface} missing immutable deployment image digest`)
    if (!/^https:\/\//.test(String(evidence.e2eArtifactUrl ?? ''))) errors.push(`retirement evidence ${surface} missing HTTPS E2E artifact URL`)
    if (!Number.isFinite(Date.parse(String(evidence.verifiedAt ?? '')))) errors.push(`retirement evidence ${surface} invalid verification timestamp`)
  }

  const candidates = []
  const candidateMap = certificate.candidates ?? {}
  if (typeof candidateMap !== 'object' || candidateMap === null || Array.isArray(candidateMap)) {
    errors.push('retirement-evidence.json candidates must be an object')
  } else {
    for (const [surface, candidate] of Object.entries(candidateMap)) {
      if (!owners.has(surface)) errors.push(`retirement candidate has no preserved migration owner: ${surface}`)
      if (Object.hasOwn(certificate.retired, surface)) errors.push(`surface is both a retirement candidate and retired: ${surface}`)
      if (!exists(surface)) errors.push(`retirement candidate is not a certificate; its legacy file must still exist: ${surface}`)
      if (typeof candidate !== 'object' || candidate === null || Array.isArray(candidate)) {
        errors.push(`retirement candidate must be an object: ${surface}`)
        continue
      }
      if (candidate.owner !== owners.get(surface)) errors.push(`retirement candidate owner mismatch: ${surface}`)
      const gates = candidate.gates
      if (typeof gates !== 'object' || gates === null || Array.isArray(gates)) {
        errors.push(`retirement candidate ${surface} must list gates`)
        continue
      }
      for (const gate of CANDIDATE_GATES) {
        const entry = gates[gate]
        if (!entry || typeof entry !== 'object') { errors.push(`retirement candidate ${surface} does not account for gate ${gate}`); continue }
        if (!GATE_STATUS.includes(entry.status)) errors.push(`retirement candidate ${surface} gate ${gate} has invalid status ${entry.status}`)
        // Met or partial needs evidence; anything not met names who supplies the rest.
        if (entry.status !== 'missing' && !text(entry.evidence)) errors.push(`retirement candidate ${surface} gate ${gate} is ${entry.status} without evidence`)
        if (entry.status !== 'met' && !text(entry.next, 4)) errors.push(`retirement candidate ${surface} gate ${gate} is ${entry.status} without a next step/owner`)
      }
      for (const gate of Object.keys(gates)) if (!CANDIDATE_GATES.includes(gate)) errors.push(`retirement candidate ${surface} names unknown gate ${gate}`)
      const met = CANDIDATE_GATES.filter(gate => gates[gate]?.status === 'met').length
      candidates.push({ surface, met, total: CANDIDATE_GATES.length })
    }
  }

  let present = 0
  let retired = 0
  for (const { surface } of all) {
    if (exists(surface)) {
      present++
    } else {
      retired++
      if (!Object.hasOwn(certificate.retired, surface)) errors.push(`legacy route deleted without verified retirement certificate: ${surface}`)
    }
  }
  return { errors, web: web.length, api: api.length, present, retired, candidates }
}
