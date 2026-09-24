import test from 'node:test'
import assert from 'node:assert/strict'
import * as policy from '../plugins/wallet-auth/src/policy.ts'
import {
  AUTH_SERVICE_UNAVAILABLE,
  DEFAULT_CHAIN_ID,
  NONCE_BYTES,
  NONCE_HEX_LENGTH,
  NONCE_KEY_PREFIX,
  NONCE_TTL_SECONDS,
  PLACEHOLDER_EMAIL_DOMAIN,
  RATE_LIMITED,
  RATE_LIMIT_KEY_PREFIX,
  RATE_LIMIT_LIMIT,
  RATE_LIMIT_WINDOW_SECONDS,
  SIGNER_RECOVERY_UNAVAILABLE,
  SIWE_STATEMENT,
  UNSUPPORTED_WALLET,
  WALLET_NONCE_EXPIRED,
  WALLET_SIGNATURE_INVALID,
  WALLET_SIGNATURE_MISMATCH,
  buildSiweMessage,
  compareRecoveredSigner,
  evaluateRateLimit,
  normalizeChainId,
  normalizeWalletAddress,
  normalizeWalletProvider,
  nonceStoreKey,
  parseSiteOrigin,
  rateLimitApplies,
  rateLimitClient,
  rateLimitFingerprint,
  rateLimitKey,
  toChecksumAddress,
  walletSignupIdentity,
} from '../plugins/wallet-auth/src/policy.ts'
import { SiweWalletAuthProvider } from '../plugins/wallet-auth/src/index.ts'

const ADDRESS = '0x1111111111111111111111111111111111111111'
/** The exact statement sentence of the classic `_build_message`. */
const CLASSIC_STATEMENT = 'Sign in to PureGamma AI with your wallet. This request will not trigger a blockchain transaction or cost any gas fees.'

/** The provider only needs the two Context members it actually uses. */
function fakeContext(services = {}) {
  return { reflect: { provide() {} }, get: name => services[name] }
}

function provider(config = {}, runtime = {}) {
  return new SiweWalletAuthProvider(fakeContext(), config, runtime)
}

/** A nonce store double; every method can be made to throw like an unreachable Redis. */
function fakeStore({ count = 1, stored = null, fail = null } = {}) {
  const puts = []
  const increments = []
  return {
    puts,
    increments,
    async put(key, message, ttlSeconds) {
      if (fail === 'put') throw new Error('redis unavailable')
      puts.push({ key, message, ttlSeconds })
    },
    async take(key) {
      if (fail === 'take') throw new Error('redis unavailable')
      if (stored !== null) return stored
      const put = puts.find(entry => entry.key === key)
      return put === undefined ? null : put.message
    },
    async increment(key, windowSeconds) {
      if (fail === 'increment') throw new Error('redis unavailable')
      increments.push({ key, windowSeconds })
      return count
    },
  }
}

const signature = '0x' + 'ab'.repeat(65)
const messageFor = (nonce, address = ADDRESS) => buildSiweMessage({
  host: 'puregamma.ai',
  origin: 'https://puregamma.ai',
  address,
  chainId: 1,
  nonce,
  issuedAt: '2026-09-21T00:00:00.000Z',
})

// ------------------------------------------------------------------ addresses

test('an address is 0x plus exactly 40 hex characters, lowercased and never coerced', () => {
  // The classic lowercases before matching, so a checksummed address and even an
  // uppercase 0X prefix are normalized rather than refused; a mixed-case body is
  // lowercased, never passed through.
  const accepted = [
    [ADDRESS, ADDRESS],
    ['0X1111111111111111111111111111111111111111', ADDRESS],
    ['0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed', '0x5aaeb6053f3e94c9b9a09f33669435e7ef1beaed'],
    ['  0xAbCdEf0123456789AbCdEf0123456789AbCdEf01  ', '0xabcdef0123456789abcdef0123456789abcdef01'],
  ]
  for (const [value, expected] of accepted) {
    const result = normalizeWalletAddress(value)
    assert.equal(result.ok, true, value)
    assert.equal(result.value, expected, value)
    assert.match(result.value, /^0x[0-9a-f]{40}$/)
  }

  const refused = [
    '0x111111111111111111111111111111111111111',    // 39 hex characters
    '0x11111111111111111111111111111111111111111',  // 41 hex characters
    '1111111111111111111111111111111111111111',     // missing 0x
    '0x11111111111111111111111111111111111111g1',   // non-hex
    '0x11111111111111111111111111111111111111 1',   // interior whitespace
    '0x',
    '',
    '   ',
    null,
    undefined,
  ]
  for (const value of refused) {
    const result = normalizeWalletAddress(value)
    assert.equal(result.ok, false, String(value))
    assert.equal(result.code, 'INVALID_WALLET_ADDRESS', String(value))
    // A refusal never carries an address-shaped payload.
    assert.equal('value' in result, false, String(value))
  }
})

test('the message address line is checksummed exactly as eth_utils checksums it', () => {
  // Expected values produced with eth_utils.to_checksum_address, the call the
  // classic handler makes inside _build_message.
  const vectors = [
    ['0x5aaeb6053f3e94c9b9a09f33669435e7ef1beaed', '0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed'],
    ['0xfb6916095ca1df60bb79ce92ce3ea74c37c5d359', '0xfB6916095ca1df60bB79Ce92cE3Ea74c37c5d359'],
    ['0xdbf03b407c01e7cd3cbea99509d93f8dddc8c6fb', '0xdbF03B407c01E7cD3CBea99509d93f8DDDC8C6FB'],
    ['0xd1220a0cf47c7b9be7a2e6ba89f429762e7b9adb', '0xD1220A0cf47c7B9Be7A2E6BA89F429762e7b9aDb'],
    ['0x52908400098527886e0f7030069857d2e4169ee7', '0x52908400098527886E0F7030069857D2E4169EE7'],
    ['0x8617e340b3d01fa5f11f306f4090fd50e238070d', '0x8617E340B3D01FA5F11F306F4090FD50E238070D'],
    ['0xde709f2102306220921060314715629080e2fb77', '0xde709f2102306220921060314715629080e2fb77'],
    ['0x27b1fdb04752bbc536007a920d24acb045561c26', '0x27b1fdb04752bbc536007a920d24acb045561c26'],
  ]
  for (const [input, expected] of vectors) {
    assert.equal(toChecksumAddress(input), expected, input)
    assert.equal(messageFor('0123456789abcdef', input).split('\n')[1], expected, input)
  }
  // An address that is not 0x+40 hex is passed through unchanged, mirroring the
  // classic try/except around to_checksum_address.
  assert.equal(toChecksumAddress('not-an-address'), 'not-an-address')
})

// -------------------------------------------------------------------- wallets

test('only metamask, zerion and injected are accepted; anything else is UNSUPPORTED_WALLET', () => {
  for (const wallet of ['metamask', 'zerion', 'injected']) {
    assert.deepEqual(normalizeWalletProvider(wallet), { ok: true, value: wallet })
    assert.deepEqual(normalizeWalletProvider(wallet.toUpperCase()), { ok: true, value: wallet })
  }
  // An omitted label means the classic pydantic default.
  for (const empty of ['', '   ', null, undefined]) {
    assert.deepEqual(normalizeWalletProvider(empty), { ok: true, value: 'injected' })
  }
  // The classic strips before the membership test, so surrounding whitespace is
  // normalized; the label itself must still be an exact member.
  assert.deepEqual(normalizeWalletProvider(' metamask '), { ok: true, value: 'metamask' })
  for (const wallet of ['coinbase', 'walletconnect', 'phantom', 'met amask', 'injected!', 'metamaskx']) {
    const result = normalizeWalletProvider(wallet)
    assert.equal(result.ok, false, wallet)
    assert.equal(result.code, UNSUPPORTED_WALLET, wallet)
    assert.equal('value' in result, false, wallet)
  }
})

test('the chain id defaults to 1 and a non-positive or fractional id is refused', () => {
  assert.deepEqual(normalizeChainId(undefined), { ok: true, value: DEFAULT_CHAIN_ID })
  assert.deepEqual(normalizeChainId(null), { ok: true, value: 1 })
  assert.deepEqual(normalizeChainId(137), { ok: true, value: 137 })
  for (const value of [0, -1, 1.5, Number.NaN, Number.POSITIVE_INFINITY]) {
    const result = normalizeChainId(value)
    assert.equal(result.ok, false, String(value))
    assert.equal(result.code, 'INVALID_CHAIN_ID', String(value))
  }
})

// ------------------------------------------------------------------- messages

test('the built message is the classic EIP-4361 layout, in order', () => {
  const nonce = '0123456789abcdef'
  const issuedAt = '2026-09-21T00:00:00.000Z'
  const message = messageFor(nonce)
  const lines = message.split('\n')
  assert.equal(lines.length, 10)
  assert.equal(lines[0], 'puregamma.ai wants you to sign in with your Ethereum account:')
  assert.equal(lines[1], ADDRESS)
  assert.equal(lines[2], '')
  assert.equal(lines[3], CLASSIC_STATEMENT)
  assert.equal(SIWE_STATEMENT, CLASSIC_STATEMENT)
  assert.equal(lines[4], '')
  assert.equal(lines[5], 'URI: https://puregamma.ai')
  assert.equal(lines[6], 'Version: 1')
  assert.equal(lines[7], 'Chain ID: 1')
  assert.equal(lines[8], `Nonce: ${nonce}`)
  assert.equal(lines[9], `Issued At: ${issuedAt}`)
  assert.equal(message.endsWith('\n'), false)

  // Field ORDER, not merely presence.
  const order = ['wants you to sign in', '\n' + ADDRESS, 'URI:', 'Version:', 'Chain ID:', 'Nonce:', 'Issued At:']
    .map(field => message.indexOf(field))
  assert.deepEqual([...order].sort((left, right) => left - right), order)
  assert.ok(order.every(index => index >= 0))
  for (const required of ['puregamma.ai', ADDRESS, 'Chain ID: 1', nonce, issuedAt]) {
    assert.ok(message.includes(required), required)
  }
})

test('a different nonce produces a different message', () => {
  const first = messageFor('0123456789abcdef')
  const second = messageFor('fedcba9876543210')
  assert.notEqual(first, second)
  assert.equal(second.split('\n')[8], 'Nonce: fedcba9876543210')
  // Deterministic for identical inputs, so only the nonce is what varies.
  assert.equal(messageFor('0123456789abcdef'), first)
})

// -------------------------------------------------------------- nonce policy

test('the nonce is 16 hex characters (8 random bytes) with a 300 second TTL', () => {
  assert.equal(NONCE_TTL_SECONDS, 300)
  assert.equal(NONCE_BYTES, 8)
  assert.equal(NONCE_HEX_LENGTH, 16)
  assert.equal(nonceStoreKey(ADDRESS), `${NONCE_KEY_PREFIX}${ADDRESS}`)
  assert.equal(nonceStoreKey(ADDRESS), `pg:auth:wallet:${ADDRESS}`)
})

test('the issued nonce is single-use, server-side, and never echoed by the client', async () => {
  const store = fakeStore()
  const auth = provider({ siteUrl: 'puregamma.ai' }, { nonceStore: store })
  const issued = await auth.nonce({ address: ADDRESS })
  assert.equal(issued.ok, true)
  assert.match(issued.value.nonce, /^[0-9a-f]{16}$/)
  assert.equal(issued.value.expiresInSeconds, 300)
  assert.equal(store.puts.length, 1)
  assert.equal(store.puts[0].key, `pg:auth:wallet:${ADDRESS}`)
  assert.equal(store.puts[0].ttlSeconds, 300)
  // The stored value is the FULL message, and the client is handed exactly it.
  assert.equal(store.puts[0].message, issued.value.message)
  assert.ok(issued.value.message.includes(`Nonce: ${issued.value.nonce}`))

  // A second issue is a fresh random nonce, not a reuse.
  const again = await auth.nonce({ address: ADDRESS })
  assert.notEqual(again.value.nonce, issued.value.nonce)
})

test('a client-supplied message is never the one that gets signed', async () => {
  const storedMessage = messageFor('aaaaaaaabbbbbbbb')
  const seen = []
  const store = fakeStore({ stored: storedMessage })
  const auth = provider({ siteUrl: 'puregamma.ai' }, {
    nonceStore: store,
    signerRecovery: { recover: async (message) => { seen.push(message); return ADDRESS } },
  })
  const result = await auth.verify({
    address: ADDRESS,
    signature,
    wallet: 'metamask',
    // Not part of the contract; an attacker-supplied message must be ignored.
    message: 'evil.example wants you to sign in with your Ethereum account:',
  })
  assert.equal(result.ok, true)
  assert.deepEqual(seen, [storedMessage])
  // The policy layer offers no path that consumes a caller-supplied message either:
  // compareRecoveredSigner only ever sees an already-recovered signer.
  assert.equal(compareRecoveredSigner.length, 2)
  assert.equal(Object.hasOwn(policy, 'authorizeWalletSignature'), false)
})

// -------------------------------------------------------------- rate limiting

test('the rate-limit key is sha256(client:address:action) under the classic prefix', () => {
  // Digests produced with python3 hashlib.sha256, the classic implementation.
  assert.equal(
    rateLimitFingerprint('203.0.113.7', ADDRESS, 'nonce'),
    '5d94babf8dd04effa1bdabba2b416989849db51db43efd530b77d3a880268fd4',
  )
  assert.equal(
    rateLimitFingerprint('203.0.113.7', ADDRESS, 'verify'),
    'e767fe495d088be62ac1d58baabd48ce48862e041191a37a89b8390233e42b1c',
  )
  assert.equal(
    rateLimitKey('203.0.113.7', ADDRESS, 'verify'),
    `${RATE_LIMIT_KEY_PREFIX}e767fe495d088be62ac1d58baabd48ce48862e041191a37a89b8390233e42b1c`,
  )
  assert.match(rateLimitKey('203.0.113.7', ADDRESS, 'nonce'), /^pg:auth:wallet:rl:[0-9a-f]{64}$/)
})

test('the client is resolved like the classic request headers', () => {
  assert.equal(rateLimitClient({ realIp: '203.0.113.7', forwardedFor: '198.51.100.1' }), '203.0.113.7')
  assert.equal(rateLimitClient({ forwardedFor: '198.51.100.1, 10.0.0.1' }), '198.51.100.1')
  assert.equal(rateLimitClient({ forwardedFor: '198.51.100.1,10.0.0.1' }), '198.51.100.1')
  assert.equal(rateLimitClient({ realIp: '', forwardedFor: '198.51.100.1' }), '198.51.100.1')
  assert.equal(rateLimitClient({ peer: '10.0.0.9' }), '10.0.0.9')
  assert.equal(rateLimitClient({}), 'unknown')
  assert.equal(rateLimitClient(undefined), 'unknown')
})

test('the limit boundary is exactly at the limit, and limit+1 is refused', () => {
  assert.equal(RATE_LIMIT_LIMIT, 10)
  assert.equal(RATE_LIMIT_WINDOW_SECONDS, 600)
  assert.equal(evaluateRateLimit(RATE_LIMIT_LIMIT, RATE_LIMIT_LIMIT).ok, true)
  assert.deepEqual(evaluateRateLimit(10, 10), { ok: true, value: { count: 10, limit: 10, remaining: 0 } })
  assert.equal(evaluateRateLimit(1, 10).ok, true)
  assert.equal(evaluateRateLimit(0, 10).ok, true)

  const denied = evaluateRateLimit(RATE_LIMIT_LIMIT + 1, RATE_LIMIT_LIMIT)
  assert.equal(denied.ok, false)
  assert.equal(denied.code, RATE_LIMITED)
  assert.equal(denied.retryAfterSeconds, RATE_LIMIT_WINDOW_SECONDS)
  assert.equal('value' in denied, false)

  // A counter we cannot trust, or a misconfigured limit, denies rather than opens.
  for (const deniedByCount of [Number.NaN, -1, 1.5, Number.POSITIVE_INFINITY]) {
    const result = evaluateRateLimit(deniedByCount, 10)
    assert.equal(result.ok, false, String(deniedByCount))
    assert.equal(result.code, AUTH_SERVICE_UNAVAILABLE, String(deniedByCount))
  }
  for (const badLimit of [0, -5, 2.5]) {
    const result = evaluateRateLimit(1, badLimit)
    assert.equal(result.ok, false, String(badLimit))
    assert.equal(result.code, AUTH_SERVICE_UNAVAILABLE, String(badLimit))
  }
})

test('the rate limit applies in production only, and denies when the counter is unreachable', async () => {
  assert.equal(rateLimitApplies('production'), true)
  assert.equal(rateLimitApplies(' PRODUCTION '), true)
  for (const environment of ['development', 'staging', 'Production!', '', null, undefined]) {
    assert.equal(rateLimitApplies(environment), false, String(environment))
  }

  const skipped = fakeStore()
  const development = provider({ siteUrl: 'puregamma.ai', appEnvironment: 'development' }, { nonceStore: skipped })
  assert.equal((await development.nonce({ address: ADDRESS })).ok, true)
  assert.equal(skipped.increments.length, 0, 'the classic skips the limiter outside production')

  const productionStore = fakeStore({ count: 11 })
  const production = provider({ siteUrl: 'puregamma.ai', appEnvironment: 'production' }, { nonceStore: productionStore })
  const limited = await production.nonce({ address: ADDRESS, client: { realIp: '203.0.113.7' } })
  assert.equal(limited.ok, false)
  assert.equal(limited.code, RATE_LIMITED)
  assert.equal(limited.retryAfterSeconds, 600)
  assert.equal(productionStore.increments.length, 1)
  assert.equal(productionStore.increments[0].windowSeconds, 600)
  assert.equal(productionStore.increments[0].key, rateLimitKey('203.0.113.7', ADDRESS, 'nonce'))
  assert.equal(productionStore.puts.length, 0, 'a limited caller never gets a nonce')

  const atLimit = provider({ siteUrl: 'puregamma.ai', appEnvironment: 'production' }, { nonceStore: fakeStore({ count: 10 }) })
  assert.equal((await atLimit.nonce({ address: ADDRESS })).ok, true)

  const broken = provider({ siteUrl: 'puregamma.ai', appEnvironment: 'production' }, { nonceStore: fakeStore({ fail: 'increment' }) })
  const unavailable = await broken.nonce({ address: ADDRESS })
  assert.equal(unavailable.ok, false)
  assert.equal(unavailable.code, AUTH_SERVICE_UNAVAILABLE)
})

// ------------------------------------------------------------------- sign-up

test('the placeholder mailbox is minted only by the wallet sign-up path', () => {
  const identity = walletSignupIdentity(ADDRESS.toUpperCase().replace('0X', '0x'))
  assert.equal(identity.ok, true)
  assert.equal(identity.value.address, ADDRESS)
  assert.equal(identity.value.email, `${ADDRESS}@${PLACEHOLDER_EMAIL_DOMAIN}`)
  assert.equal(identity.value.email, `${ADDRESS}@wallet.puregamma.local`)
  assert.equal(identity.value.displayName, '0x1111...1111')
  // The classic User/UserIdentity provider fields.
  assert.equal(identity.value.authProvider, 'wallet')
  assert.equal(identity.value.identityProvider, 'evm_wallet')

  // Nothing else in the sign-in flow fabricates a mailbox.
  assert.equal(messageFor('0123456789abcdef').includes(PLACEHOLDER_EMAIL_DOMAIN), false)
  assert.equal(nonceStoreKey(ADDRESS).includes(PLACEHOLDER_EMAIL_DOMAIN), false)
  assert.equal(rateLimitKey('203.0.113.7', ADDRESS, 'verify').includes(PLACEHOLDER_EMAIL_DOMAIN), false)

  // And an address that is not an address cannot mint one.
  for (const value of ['0xnope', '', null, undefined]) {
    const refused = walletSignupIdentity(value)
    assert.equal(refused.ok, false, String(value))
    assert.equal(refused.code, 'INVALID_WALLET_ADDRESS', String(value))
    assert.equal('value' in refused, false, String(value))
  }
})

// ------------------------------------------------------------ site origin

test('the message host comes from SITE_URL, and an unconfigured host refuses', () => {
  assert.deepEqual(parseSiteOrigin('puregamma.ai'), { ok: true, value: { host: 'puregamma.ai', origin: 'https://puregamma.ai' } })
  assert.deepEqual(
    parseSiteOrigin('https://puregamma.ai/'),
    { ok: true, value: { host: 'puregamma.ai', origin: 'https://puregamma.ai' } },
  )
  assert.deepEqual(
    parseSiteOrigin('http://localhost:3000'),
    { ok: true, value: { host: 'localhost:3000', origin: 'http://localhost:3000' } },
  )
  for (const value of ['', '   ', null, undefined, 'http://', 'not a url']) {
    const result = parseSiteOrigin(value)
    assert.equal(result.ok, false, String(value))
    assert.equal(result.code, AUTH_SERVICE_UNAVAILABLE, String(value))
  }
})

// ------------------------------------------------------- signer comparison

test('the recovered signer is compared lowercased, and every failure is explicit', () => {
  assert.deepEqual(compareRecoveredSigner(ADDRESS, ADDRESS.toUpperCase().replace('0X', '0x')), { ok: true, value: ADDRESS })
  assert.deepEqual(compareRecoveredSigner(ADDRESS.toUpperCase().replace('0X', '0x'), ADDRESS), { ok: true, value: ADDRESS })

  const mismatch = compareRecoveredSigner(ADDRESS, '0x2222222222222222222222222222222222222222')
  assert.equal(mismatch.ok, false)
  assert.equal(mismatch.code, WALLET_SIGNATURE_MISMATCH)
  assert.equal('value' in mismatch, false)

  // "recovery produced nothing" is never a match.
  for (const recovered of [null, undefined, '', '   ', 'not-an-address']) {
    const result = compareRecoveredSigner(ADDRESS, recovered)
    assert.equal(result.ok, false, String(recovered))
    assert.equal(result.code, WALLET_SIGNATURE_INVALID, String(recovered))
    assert.equal('value' in result, false, String(recovered))
  }

  const claimed = compareRecoveredSigner('nope', ADDRESS)
  assert.equal(claimed.ok, false)
  assert.equal(claimed.code, 'INVALID_WALLET_ADDRESS')
})

// ------------------------------------------------------------- fail closed

test('every unavailable state refuses instead of producing a success-shaped result', async () => {
  const refusals = []
  const record = result => { refusals.push(result); return result }

  // No nonce store and no recovery installed at all.
  const bare = provider({ siteUrl: 'puregamma.ai' })
  record(await bare.nonce({ address: ADDRESS }))
  record(await bare.verify({ address: ADDRESS, signature, wallet: 'metamask' }))

  // A store, but no signer recovery: an unverifiable signature is never accepted.
  const noRecovery = provider({ siteUrl: 'puregamma.ai' }, { nonceStore: fakeStore({ stored: messageFor('0123456789abcdef') }) })
  const unrecoverable = record(await noRecovery.verify({ address: ADDRESS, signature, wallet: 'metamask' }))
  assert.equal(unrecoverable.code, SIGNER_RECOVERY_UNAVAILABLE)

  // An unconfigured site URL refuses to issue a message even with a store.
  record(await provider({ siteUrl: '' }, { nonceStore: fakeStore() }).nonce({ address: ADDRESS }))

  // The store rejecting a write or a read is an outage, not a pass.
  record(await provider({ siteUrl: 'puregamma.ai' }, { nonceStore: fakeStore({ fail: 'put' }) }).nonce({ address: ADDRESS }))
  record(await provider({ siteUrl: 'puregamma.ai' }, { nonceStore: fakeStore({ fail: 'take' }) }).verify({ address: ADDRESS, signature }))

  // Recovery throwing, and a recovered signer that is not the claimed address.
  const throwing = provider({ siteUrl: 'puregamma.ai' }, {
    nonceStore: fakeStore({ stored: messageFor('0123456789abcdef') }),
    signerRecovery: { recover: async () => { throw new Error('bad signature') } },
  })
  const invalid = record(await throwing.verify({ address: ADDRESS, signature }))
  assert.equal(invalid.code, WALLET_SIGNATURE_INVALID)

  const mismatching = provider({ siteUrl: 'puregamma.ai' }, {
    nonceStore: fakeStore({ stored: messageFor('0123456789abcdef') }),
    signerRecovery: { recover: async () => '0x2222222222222222222222222222222222222222' },
  })
  const mismatch = record(await mismatching.verify({ address: ADDRESS, signature }))
  assert.equal(mismatch.code, WALLET_SIGNATURE_MISMATCH)

  // An absent (already consumed or expired) stored message is 401-shaped.
  const expired = record(await provider({ siteUrl: 'puregamma.ai' }, {
    nonceStore: fakeStore(),
    signerRecovery: { recover: async () => ADDRESS },
  }).verify({ address: ADDRESS, signature }))
  assert.equal(expired.code, WALLET_NONCE_EXPIRED)

  // Address/provider/signature refusals.
  record(await bare.verify({ address: '0xnope', signature }))
  record(await provider({ siteUrl: 'puregamma.ai' }, { nonceStore: fakeStore({ stored: messageFor('0123456789abcdef') }) })
    .verify({ address: ADDRESS, signature, wallet: 'coinbase' }))
  record(await provider({ siteUrl: 'puregamma.ai' }, { nonceStore: fakeStore({ stored: messageFor('0123456789abcdef') }) })
    .verify({ address: ADDRESS, signature: '0xshort' }))

  assert.equal(refusals.length, 12, 'every recorded refusal above must be a refusal')
  for (const result of refusals) {
    assert.equal(result.ok, false)
    assert.equal(typeof result.code, 'string')
    assert.ok(result.reason.length > 0)
    // No refusal ever carries a success payload.
    assert.equal('value' in result, false)
    assert.equal('message' in result, false)
    assert.equal('nonce' in result, false)
  }
  // The pure module exposes no recovery-shaped function that could be mistaken
  // for an authorization decision.
  assert.equal(Object.hasOwn(policy, 'authorizeWalletSignature'), false)
  assert.equal(Object.hasOwn(policy, 'recoverSigner'), false)
})

test('a stored message is consumed single-use, before recovery', async () => {
  const store = fakeStore({ stored: messageFor('0123456789abcdef') })
  const auth = provider({ siteUrl: 'puregamma.ai' }, {
    nonceStore: store,
    signerRecovery: { recover: async request => { throw new Error('bad signature') } },
  })
  const first = await auth.verify({ address: ADDRESS, signature })
  assert.equal(first.ok, false)
  assert.equal(first.code, WALLET_SIGNATURE_INVALID)

  // The store double above keeps serving the same value, so prove single-use
  // through a store that actually forgets, like a Redis GETDEL.
  const forgetful = { value: messageFor('0123456789abcdef'), puts: [], increments: [] }
  const singleUseStore = {
    async put() {},
    async take() { const current = forgetful.value; forgetful.value = null; return current },
    async increment() { return 1 },
  }
  const single = provider({ siteUrl: 'puregamma.ai' }, {
    nonceStore: singleUseStore,
    signerRecovery: { recover: async () => ADDRESS },
  })
  assert.equal((await single.verify({ address: ADDRESS, signature })).ok, true)
  const replay = await single.verify({ address: ADDRESS, signature })
  assert.equal(replay.ok, false)
  assert.equal(replay.code, WALLET_NONCE_EXPIRED)
})

test('a verified signature returns the normalized address and the wallet label', async () => {
  const store = fakeStore({ stored: messageFor('0123456789abcdef') })
  const auth = provider({ siteUrl: 'puregamma.ai' }, {
    nonceStore: store,
    signerRecovery: { recover: async () => ADDRESS.toUpperCase().replace('0X', '0x') },
  })
  const verified = await auth.verify({ address: ADDRESS, signature, wallet: 'MetaMask' })
  assert.deepEqual(verified, { ok: true, value: { address: ADDRESS, wallet: 'metamask' } })
  // The identity layer derives the first-sign-in identity from the same policy.
  assert.deepEqual(auth.signupIdentity(ADDRESS.toUpperCase().replace('0X', '0x')).value.email, `${ADDRESS}@${PLACEHOLDER_EMAIL_DOMAIN}`)
})
