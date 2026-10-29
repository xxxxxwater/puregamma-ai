import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { randomBytes } from 'node:crypto'
import { lstatSync, mkdirSync, mkdtempSync, readFileSync, readlinkSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import process from 'node:process'
import test from 'node:test'
import { createBroker, directoryUsage, dockerArgs, hostPaths, loadConfig, readOnlyPaths, systemdProperties, userKey, validateConfig } from '../packages/session-broker/src/index.ts'
import { brokerConfig, call, secret, startFakeApi } from './fixtures/broker-harness.mjs'

// Host launchers: `direct` (default, unchanged), `systemd` (transient user
// unit) and `docker` (one container per Host).
//
// The pure tests pin every isolation flag. The live tests start the fake DSH
// Host (scripts/fixtures/fake-dsh-host.mjs) under each launcher and ask it,
// from inside, what it can see and do: other users' directories, cgroup and
// rlimit values, writes outside its own directory, oversized files. They are
// skipped when the launcher is unavailable (no systemd user manager; docker
// needs PG_BROKER_DOCKER_IMAGE, an image that can run the mounted host Node).
// session-broker.integration.mjs repeats the systemd/docker runs on real DSH.

const harness = process.cwd()
const root = mkdtempSync(path.join(tmpdir(), 'pg-launchers-'))
const SECRET = secret()
const api = await startFakeApi({ secret: SECRET })
test.after(async () => {
  await api.close()
  rmSync(root, { recursive: true, force: true })
})
const base = (overrides = {}) => brokerConfig({ api, root, harness, secret: SECRET, profileDir: path.join(harness, 'profile'), ...overrides })
const request = config => ({ userKey: userKey('user-a'), paths: hostPaths(config.hostsRoot, 'user-a'), env: { HOME: '/h', PUREGAMMA_LEGACY_API_TOKEN_FILE: '/t', SECRET_VALUE_SHOULD_NOT_APPEAR: 'sk-live-123' }, dshArgs: ['puregamma', '--port', '0', '--no-open'] })

test('defaults: direct launcher, limits derived from the heap cap, strict validation', () => {
  const config = loadConfig({})
  assert.equal(config.launcher, 'direct')
  assert.deepEqual(config.hostLimits, { memoryMb: 1536, cpuPercent: 100, tasksMax: 256, nofile: 4096, fileSizeMb: 256 })
  assert.equal(config.diskQuotaMb, 1024)
  assert.ok(config.sandboxHide.includes('/data'))
  const ok = { ...base(), launcher: 'systemd' }
  assert.deepEqual(validateConfig(ok), [])
  const errors = config => validateConfig({ ...base(), ...config }).join('\n')
  assert.match(errors({ launcher: 'invalid' }), /HOST_LAUNCHER/)
  assert.match(errors({ launcher: 'docker' }), /DOCKER_IMAGE/)
  assert.match(errors({ launcher: 'docker', dockerImage: 'x', dockerUser: 'root' }), /DOCKER_USER/)
  assert.match(errors({ launcher: 'systemd', hostLimits: { ...ok.hostLimits, memoryMb: 1000 } }), /MEMORY_MB/)
  assert.match(errors({ launcher: 'systemd', sandboxHide: ['/'] }), /SANDBOX_HIDE/)
  assert.match(errors({ instance: 'Bad Name' }), /INSTANCE/)
  assert.equal(loadConfig({ PUREGAMMA_DSH_HOST_LAUNCHER: 'bogus' }).launcher, 'invalid')
})

test('systemd: every limit and sandbox property, own directory writable, secrets never on the command line', () => {
  const config = { ...base(), launcher: 'systemd', hostLimits: { memoryMb: 768, cpuPercent: 50, tasksMax: 64, nofile: 1024, fileSizeMb: 8 } }
  const props = systemdProperties(config, request(config))
  for (const expected of ['MemoryMax=768M', 'MemorySwapMax=0', 'CPUQuota=50%', 'TasksMax=64', 'LimitNOFILE=1024', `LimitFSIZE=${8 * 1024 * 1024}`, 'LimitCORE=0',
    'NoNewPrivileges=yes', 'PrivateUsers=yes', 'PrivatePIDs=yes', 'PrivateTmp=yes', 'ProtectSystem=strict', 'ProtectHome=tmpfs', 'RestrictNamespaces=yes',
    'RestrictSUIDSGID=yes', 'SystemCallFilter=@system-service', 'SystemCallArchitectures=native', 'UMask=0077']) {
    assert.ok(props.includes(expected), expected)
  }
  assert.ok(props.includes(`TemporaryFileSystem=${config.hostsRoot}:ro`) || !existsDir(config.hostsRoot), 'other users hidden')
  const writable = props.filter(prop => /^(BindPaths|ReadWritePaths)=/.test(prop)).map(prop => prop.split('=')[1])
  assert.deepEqual([...new Set(writable)], [hostPaths(config.hostsRoot, 'user-a').dir])
  const ro = readOnlyPaths(config)
  assert.ok(ro.every(dir => !dir.startsWith(config.hostsRoot)), 'no user directory is mounted read-only either')
  assert.ok(!props.some(prop => /IPAddress/.test(prop)), 'user managers ignore IP ACLs; never pretend to set them')
})

test('docker: read-only root, no capabilities, limits, loopback-only publish, only the own directory writable', () => {
  const config = { ...base(), launcher: 'docker', dockerImage: 'img:1', hostLimits: { memoryMb: 768, cpuPercent: 50, tasksMax: 64, nofile: 1024, fileSizeMb: 8 } }
  const args = dockerArgs(config, request(config), 'pg-dsh-x')
  const joined = args.join(' ')
  for (const expected of ['--read-only', '--cap-drop ALL', '--security-opt no-new-privileges', '--memory 768m', '--memory-swap 768m', '--cpus 0.5',
    '--pids-limit 64', '--ulimit nofile=1024:1024', `--ulimit fsize=${8 * 1024 * 1024}`, '--ulimit core=0', '-p 127.0.0.1::3000', '--init', '--rm']) {
    assert.ok(joined.includes(expected), expected)
  }
  assert.ok(!joined.includes('--privileged') && !/--cap-add/.test(joined))
  const mounts = args.flatMap((arg, i) => (arg === '-v' ? [args[i + 1]] : []))
  const rw = mounts.filter(mount => mount.endsWith(':rw'))
  assert.deepEqual(rw, [`${hostPaths(config.hostsRoot, 'user-a').dir}:${hostPaths(config.hostsRoot, 'user-a').dir}:rw`])
  assert.ok(mounts.filter(mount => !mount.endsWith(':rw')).every(mount => mount.endsWith(':ro')))
  assert.ok(!joined.includes('sk-live-123'), 'values travel through the client environment, not argv')
  assert.ok(args.includes('SECRET_VALUE_SHOULD_NOT_APPEAR'))
})

test('each Host writes its own profile root file; the shared profile is only linked, never written', async () => {
  const shared = path.join(root, 'shared-profile')
  mkdirSync(path.join(shared, 'skills'), { recursive: true })
  writeFileSync(path.join(shared, 'cordis.yml'), '[]\n')
  writeFileSync(path.join(shared, 'cordis.patch.yml'), '[]\n')
  const config = base({ hostsRoot: path.join(root, 'profile-hosts'), profileDir: shared, instance: `p${randomBytes(3).toString('hex')}` })
  await withBroker(config, async (_broker, url) => {
    for (const session of ['sess-a', 'sess-b']) assert.equal((await call(url, '/api/debug', { session, headers: origin(config) })).status, 200)
    assert.equal(readFileSync(path.join(shared, 'cordis.yml'), 'utf8'), '[]\n', 'shared profile untouched')
    for (const user of ['user-a', 'user-b']) {
      const dir = path.join(hostPaths(config.hostsRoot, user).home, 'profiles', 'puregamma')
      assert.ok(lstatSync(dir).isDirectory() && !lstatSync(dir).isSymbolicLink())
      const own = path.join(dir, 'cordis.yml')
      assert.ok(lstatSync(own).isFile())
      assert.equal(lstatSync(own).mode & 0o077, 0)
      assert.match(readFileSync(own, 'utf8'), new RegExp(`written by ${hostPaths(config.hostsRoot, user).home}`))
      assert.equal(readlinkSync(path.join(dir, 'cordis.patch.yml')), path.join(shared, 'cordis.patch.yml'))
      assert.equal(readlinkSync(path.join(dir, 'skills')), path.join(shared, 'skills'))
    }
  })
})

function existsDir(dir) {
  try { return execFileSync('test', ['-d', dir]) !== undefined } catch { return false }
}

async function withBroker(config, fn) {
  const broker = createBroker(config, { log: () => {} })
  await new Promise(resolve => broker.server.listen(0, '127.0.0.1', resolve))
  try {
    await fn(broker, `http://127.0.0.1:${broker.server.address().port}`)
  } finally {
    await broker.close()
  }
}
const origin = config => ({ origin: config.publicOrigin })

test('disk quota (all launchers): an over-quota user gets 507 and no Host; others are unaffected; a running Host over quota is stopped', async () => {
  const config = base({ hostsRoot: path.join(root, 'quota-hosts'), diskQuotaMb: 16, instance: `q${randomBytes(3).toString('hex')}` })
  await withBroker(config, async (broker, url) => {
    assert.equal((await call(url, '/api/debug', { session: 'sess-a', headers: origin(config) })).status, 200)
    // A grows past the quota while running.
    writeFileSync(path.join(hostPaths(config.hostsRoot, 'user-a').workspace, 'blob.bin'), Buffer.alloc(20 * 1024 * 1024, 1))
    assert.ok(await directoryUsage(hostPaths(config.hostsRoot, 'user-a').dir) > 16 * 1024 * 1024)
    assert.deepEqual(await broker.hosts.checkDisk(), [userKey('user-a')])
    assert.equal(broker.hosts.size, 0)
    const refused = await call(url, '/api/debug', { session: 'sess-a', headers: origin(config) })
    assert.equal(refused.status, 507)
    assert.equal(refused.body.error, 'storage-quota-exceeded')
    assert.equal(broker.hosts.size, 0, 'no Host for an over-quota user')
    assert.equal((await call(url, '/api/debug', { session: 'sess-b', headers: origin(config) })).status, 200, 'B unaffected')
    rmSync(path.join(hostPaths(config.hostsRoot, 'user-a').workspace, 'blob.bin'))
    assert.equal((await call(url, '/api/debug', { session: 'sess-a', headers: origin(config) })).status, 200, 'back under quota')
  })
})

function systemdUserManager() {
  try {
    execFileSync('systemctl', ['--user', 'is-system-running'], { stdio: 'pipe' })
    return true
  } catch (error) {
    return /running|degraded/.test(String(error.stdout ?? ''))
  }
}
const units = instance => execFileSync('systemctl', ['--user', 'list-units', '--all', '--plain', '--no-legend', `pg-dsh-${instance}-*`], { encoding: 'utf8' }).trim()

/** The same checks for any kernel-isolating launcher, from inside the Host. */
async function assertSandboxed(config, url, { hiddenProbe }) {
  const a = await call(url, `/api/sandbox?writeMb=${config.hostLimits.fileSizeMb + 2}&hidden=${encodeURIComponent(hiddenProbe)}`, { session: 'sess-a', headers: origin(config) })
  const b = await call(url, '/api/sandbox', { session: 'sess-b', headers: origin(config) })
  assert.equal(a.status, 200, a.text)
  assert.equal(b.status, 200, b.text)
  const sa = a.body
  console.log(`  # ${config.launcher} sandbox (A): ${JSON.stringify(sa)}`)
  assert.deepEqual(sa.hostsRoot, [sa.ownDir], 'A sees only its own directory under the hosts root')
  assert.deepEqual(b.body.hostsRoot, [b.body.ownDir])
  assert.notEqual(sa.ownDir, b.body.ownDir)
  assert.equal(sa.writeOwn, 'ok')
  assert.match(sa.writeHostsRoot, /^ERR (EROFS|EACCES|EPERM)/)
  assert.match(sa.writeEtc, /^ERR (EROFS|EACCES|EPERM)/)
  assert.match(String(sa.readHidden), /^ERR ENOENT/, `${hiddenProbe} hidden`)
  assert.match(sa.bigFile, /^ERR EFBIG/, 'RLIMIT_FSIZE stops oversized files')
  assert.equal(sa.memoryMax, String(config.hostLimits.memoryMb * 1024 * 1024))
  assert.equal(sa.pidsMax, String(config.hostLimits.tasksMax))
  assert.equal(sa.cpuMax, `${config.hostLimits.cpuPercent * 1000} 100000`)
  assert.match(sa.nofile, new RegExp(`Max open files ${config.hostLimits.nofile} ${config.hostLimits.nofile}`))
  assert.match(sa.fsize, new RegExp(`Max file size ${config.hostLimits.fileSizeMb * 1024 * 1024} ${config.hostLimits.fileSizeMb * 1024 * 1024}`))
  assert.equal(sa.noNewPrivs, '1')
  assert.ok(sa.visibleProcesses <= 4, `own PID namespace (saw ${sa.visibleProcesses} processes)`)
}

const limits = { memoryMb: 640, cpuPercent: 50, tasksMax: 64, nofile: 1024, fileSizeMb: 4 }

test('systemd launcher (live): kernel limits and namespaces hold from inside the Host; reaping and restart sweep stop units', { skip: systemdUserManager() ? false : 'no systemd user manager' }, async () => {
  const instance = `t${randomBytes(3).toString('hex')}`
  const config = base({ hostsRoot: path.join(root, 'sd-hosts'), launcher: 'systemd', instance, hostLimits: limits, hostHeapMb: 256 })
  try {
    await withBroker(config, async (broker, url) => {
      await assertSandboxed(config, url, { hiddenProbe: '/data/home' })
      assert.equal(units(instance).split('\n').length, 2, 'one unit per user')
      for (const { name } of broker.hosts.launched()) {
        assert.equal(execFileSync('systemctl', ['--user', 'show', name, '-p', 'Slice', '--value'], { encoding: 'utf8' }).trim(), 'pgdsh.slice')
      }
      config.idleMs = 0
      await broker.hosts.reap()
      for (let i = 0; i < 50 && units(instance); i++) await new Promise(resolve => setTimeout(resolve, 100))
      assert.equal(units(instance), '', 'idle reaping stops the units')
      config.idleMs = 60_000
      // A broker that dies leaves units behind; the next one of the same instance sweeps them.
      assert.equal((await call(url, '/api/debug', { session: 'sess-a', headers: origin(config) })).status, 200)
    })
    // close() stops units too; start one more without close to simulate a crash.
    const orphan = createBroker(config, { log: () => {} })
    await new Promise(resolve => orphan.server.listen(0, '127.0.0.1', resolve))
    assert.equal((await call(`http://127.0.0.1:${orphan.server.address().port}`, '/api/debug', { session: 'sess-a', headers: origin(config) })).status, 200)
    orphan.server.close()
    assert.notEqual(units(instance), '')
    const next = createBroker(config, { log: () => {} })
    await next.hosts.ready
    for (let i = 0; i < 50 && units(instance); i++) await new Promise(resolve => setTimeout(resolve, 100))
    assert.equal(units(instance), '', 'stale units of this instance are swept on start')
    await next.close()
    await orphan.hosts.close()
  } finally {
    try { execFileSync('systemctl', ['--user', 'stop', `pg-dsh-${instance}-*`], { stdio: 'ignore' }) } catch {}
  }
})

const dockerImage = process.env.PG_BROKER_DOCKER_IMAGE
test('docker launcher (live): container limits and isolation hold from inside the Host; reaping removes containers', { skip: dockerImage ? false : 'set PG_BROKER_DOCKER_IMAGE (an image that can run the host Node, e.g. python:3.12-slim)' }, async () => {
  const instance = `t${randomBytes(3).toString('hex')}`
  const config = base({ hostsRoot: path.join(root, 'dk-hosts'), launcher: 'docker', instance, hostLimits: limits, hostHeapMb: 256, dockerImage, dockerNode: process.execPath })
  mkdirSync(config.hostsRoot, { recursive: true, mode: 0o700 })
  const containers = () => execFileSync('docker', ['ps', '-aq', '--filter', `label=puregamma.dsh-host=${instance}`], { encoding: 'utf8' }).trim()
  try {
    await withBroker(config, async (broker, url) => {
      await assertSandboxed(config, url, { hiddenProbe: '/data/home' })
      assert.equal(containers().split('\n').length, 2, 'one container per user')
      config.idleMs = 0
      await broker.hosts.reap()
      for (let i = 0; i < 100 && containers(); i++) await new Promise(resolve => setTimeout(resolve, 100))
      assert.equal(containers(), '', 'idle reaping removes the containers')
    })
  } finally {
    const left = containers()
    if (left) execFileSync('docker', ['rm', '-f', ...left.split('\n')], { stdio: 'ignore' })
  }
})
