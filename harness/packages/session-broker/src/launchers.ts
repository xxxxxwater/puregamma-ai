import { execFile } from 'node:child_process'
import { randomBytes } from 'node:crypto'
import { existsSync, realpathSync } from 'node:fs'
import path from 'node:path'
import process from 'node:process'
import { promisify } from 'node:util'
import type { BrokerConfig } from './config.ts'
import type { HostPaths } from './hosts.ts'

const run = promisify(execFile)

/**
 * How a Host process is started.
 *
 * - `direct` (default, the v0.3.3 behaviour): a child process of the broker,
 *   same uid, isolated only by its own DSH_HOME/cwd and the V8 heap cap.
 * - `systemd`: a transient unit in the broker user's systemd manager
 *   (`systemd-run --user`, no root). Kernel cgroup limits (memory, CPU,
 *   tasks), rlimits (nofile, file size), its own user/PID/mount namespaces,
 *   a read-only system, other users' directories hidden, seccomp.
 * - `docker`: one container per Host: read-only root, all capabilities
 *   dropped, no-new-privileges, memory/CPU/pids/nofile/fsize limits, its own
 *   network namespace; only the user's directory is writable.
 */
export type LauncherKind = 'direct' | 'systemd' | 'docker'

export interface LaunchRequest {
  /** Path-safe user key (sha256 prefix); never the user id. */
  userKey: string
  paths: HostPaths
  /** Host environment (already allowlisted). */
  env: NodeJS.ProcessEnv
  /** DSH launcher arguments after the bin path (profile, --patch …, --port 0, --no-open). */
  dshArgs: string[]
}

/** Where the broker reaches a Host and which authority the Host's own fence expects. */
export interface HostTarget { port: number; authority: string }

export interface LaunchPlan {
  /** Process the broker spawns; its stdout carries the DSH ready line. */
  command: string
  args: string[]
  env: NodeJS.ProcessEnv
  cwd: string
  /** Unit or container name ('' for direct). */
  name: string
  /** Map the port from the ready line to the broker's connection target. */
  connect(readyPort: number): Promise<HostTarget>
  /** Out-of-band stop (unit/container); the broker still signals its own child afterwards. */
  stop(): Promise<void>
}

export interface HostLauncher {
  readonly kind: LauncherKind
  plan(request: LaunchRequest): LaunchPlan
  /** Remove Hosts left behind by an earlier broker run of the same instance. Returns how many. */
  sweep(): Promise<number>
}

const loopback = (port: number): HostTarget => ({ port, authority: `127.0.0.1:${port}` })
const suffix = () => randomBytes(3).toString('hex')

/** Name for a unit/container: instance-scoped so parallel brokers never touch each other's Hosts. */
export function hostName(config: BrokerConfig, userKey: string): string {
  return `pg-dsh-${config.instance}-${userKey.slice(0, 16)}-${suffix()}`
}

/**
 * Directories a sandboxed Host must read: the DSH install (the directory that
 * holds the `node_modules` the launcher lives in), the harness tree the
 * profile resolves plugins from, the Node binary, plus configured extras.
 */
export function readOnlyPaths(config: BrokerConfig): string[] {
  const real = (file: string) => { try { return realpathSync(file) } catch { return path.resolve(file) } }
  const out = new Set<string>()
  const bin = path.resolve(config.dshBin)
  const index = bin.split(path.sep).indexOf('node_modules')
  out.add(index > 0 ? bin.split(path.sep).slice(0, index).join(path.sep) || path.sep : path.dirname(bin))
  out.add(path.dirname(real(config.profileDir)))
  for (const patch of config.patchFiles) out.add(path.dirname(real(patch)))
  out.add(path.dirname(real(process.execPath)))
  for (const extra of config.sandboxReadOnlyPaths) out.add(path.resolve(extra))
  // Drop entries nested in another entry.
  const sorted = [...out].sort((a, b) => a.length - b.length)
  return sorted.filter((dir, i) => !sorted.slice(0, i).some(parent => dir === parent || dir.startsWith(`${parent}${path.sep}`)))
}

export function directLauncher(config: BrokerConfig): HostLauncher {
  return {
    kind: 'direct',
    plan: request => ({
      command: process.execPath,
      args: [config.dshBin, ...request.dshArgs],
      env: request.env,
      cwd: request.paths.workspace,
      name: '',
      connect: async port => loopback(port),
      stop: async () => {},
    }),
    sweep: async () => 0,
  }
}

export const SYSTEMD_SLICE = 'pgdsh.slice'

/** Environment systemd-run itself needs to reach the user manager. */
const MANAGER_ENV = ['XDG_RUNTIME_DIR', 'DBUS_SESSION_BUS_ADDRESS']

/**
 * `systemd-run --user` properties for one Host. Every property here was
 * checked on systemd 257 in a user manager (see the ingress/isolation doc):
 * IP address ACLs are deliberately absent because the user manager silently
 * ignores them.
 */
export function systemdProperties(config: BrokerConfig, request: LaunchRequest): string[] {
  const limits = config.hostLimits
  const props = [
    `MemoryMax=${limits.memoryMb}M`,
    'MemorySwapMax=0',
    `CPUQuota=${limits.cpuPercent}%`,
    `TasksMax=${limits.tasksMax}`,
    `LimitNOFILE=${limits.nofile}`,
    `LimitFSIZE=${limits.fileSizeMb * 1024 * 1024}`,
    'LimitCORE=0',
    'KillMode=control-group',
    'TimeoutStopSec=5',
    'UMask=0077',
    'NoNewPrivileges=yes',
    'PrivateUsers=yes',
    'PrivatePIDs=yes',
    'PrivateTmp=yes',
    'ProtectSystem=strict',
    'ProtectHome=tmpfs',
    'ProtectKernelTunables=yes',
    'ProtectKernelModules=yes',
    'ProtectControlGroups=yes',
    'RestrictNamespaces=yes',
    'RestrictSUIDSGID=yes',
    'RestrictRealtime=yes',
    'LockPersonality=yes',
    'SystemCallArchitectures=native',
    'SystemCallFilter=@system-service',
    'SystemCallFilter=~@privileged @resources @mount @debug @cpu-emulation @obsolete',
    'RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX AF_NETLINK',
  ]
  // Hide every other user's state and the configured roots (e.g. /data with
  // the repository, other projects and secrets), then bind back only what
  // this Host needs: its own directory (rw) and the read-only install.
  for (const hidden of new Set([config.hostsRoot, ...config.sandboxHide])) if (existsSync(hidden)) props.push(`TemporaryFileSystem=${hidden}:ro`)
  for (const dir of readOnlyPaths(config)) props.push(`BindReadOnlyPaths=${dir}`)
  props.push(`BindPaths=${request.paths.dir}`, `ReadWritePaths=${request.paths.dir}`)
  return props
}

export function systemdLauncher(config: BrokerConfig): HostLauncher {
  const prefix = `pg-dsh-${config.instance}-`
  const manager = (args: string[]) => run('systemctl', ['--user', ...args], { timeout: 15_000 })
  return {
    kind: 'systemd',
    plan(request) {
      const name = hostName(config, request.userKey)
      const unit = `${name}.service`
      // One slice for all Hosts: deploy-side controls (an aggregate MemoryMax
      // on the slice, an nftables `socket cgroupv2` egress rule) target it.
      const args = ['--user', `--unit=${unit}`, `--slice=${SYSTEMD_SLICE}`, '--quiet', '--collect', '--wait', '--pipe', '--same-dir']
      for (const prop of systemdProperties(config, request)) args.push('-p', prop)
      // Values come from systemd-run's own environment, never the command line.
      for (const key of Object.keys(request.env)) args.push(`--setenv=${key}`)
      args.push('--', process.execPath, config.dshBin, ...request.dshArgs)
      const env: NodeJS.ProcessEnv = { ...request.env }
      for (const key of MANAGER_ENV) if (process.env[key] !== undefined) env[key] = process.env[key]
      return {
        command: 'systemd-run', args, env, cwd: request.paths.workspace, name: unit,
        connect: async port => loopback(port),
        stop: async () => { await manager(['stop', unit]).catch(() => {}) },
      }
    },
    async sweep() {
      const { stdout } = await manager(['list-units', '--all', '--plain', '--no-legend', `${prefix}*`]).catch(() => ({ stdout: '' }))
      const units = String(stdout).split('\n').map(line => line.trim().split(/\s+/)[0]).filter(unit => unit?.startsWith(prefix))
      if (units.length) await manager(['stop', ...units]).catch(() => {})
      return units.length
    },
  }
}

/** Port the in-container forwarder listens on (DSH itself refuses non-loopback binds). */
export const CONTAINER_PORT = 3000

export function dockerArgs(config: BrokerConfig, request: LaunchRequest, name: string): string[] {
  const limits = config.hostLimits
  const args = [
    'run', '--rm', '--init', '--name', name,
    '--label', `puregamma.dsh-host=${config.instance}`,
    '--user', config.dockerUser,
    '--read-only', '--tmpfs', '/tmp:rw,nosuid,nodev,size=64m',
    '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
    '--memory', `${limits.memoryMb}m`, '--memory-swap', `${limits.memoryMb}m`,
    '--cpus', String(limits.cpuPercent / 100),
    '--pids-limit', String(limits.tasksMax),
    '--ulimit', `nofile=${limits.nofile}:${limits.nofile}`,
    '--ulimit', `fsize=${limits.fileSizeMb * 1024 * 1024}`,
    '--ulimit', 'core=0',
    '--network', config.dockerNetwork,
    '-p', `127.0.0.1::${CONTAINER_PORT}`,
    '-w', request.paths.workspace,
  ]
  for (const host of config.dockerAddHosts) args.push('--add-host', host)
  for (const dir of readOnlyPaths(config)) args.push('-v', `${dir}:${dir}:ro`)
  args.push('-v', `${request.paths.dir}:${request.paths.dir}:rw`)
  // `-e NAME` takes the value from the docker client's environment.
  for (const key of Object.keys(request.env)) args.push('-e', key)
  args.push(config.dockerImage, config.dockerNode, config.containerEntry, String(CONTAINER_PORT), config.dshBin, ...request.dshArgs)
  return args
}

export function dockerLauncher(config: BrokerConfig): HostLauncher {
  const docker = (args: string[]) => run(config.dockerBin, args, { timeout: 30_000 })
  return {
    kind: 'docker',
    plan(request) {
      const name = hostName(config, request.userKey)
      return {
        command: config.dockerBin,
        args: dockerArgs(config, request, name),
        // The client needs PATH/DOCKER_HOST; the Host variables ride along for `-e NAME`.
        env: { ...request.env, PATH: process.env.PATH, ...(process.env.DOCKER_HOST ? { DOCKER_HOST: process.env.DOCKER_HOST } : {}) },
        cwd: request.paths.workspace,
        name,
        async connect(readyPort) {
          const { stdout } = await docker(['port', name, `${CONTAINER_PORT}/tcp`])
          const published = /127\.0\.0\.1:(\d+)/.exec(String(stdout))
          if (!published) throw new Error('container port is not published on loopback')
          // The broker connects to the published port; DSH's fence inside the
          // container still sees its own loopback authority.
          return { port: Number(published[1]), authority: `127.0.0.1:${readyPort}` }
        },
        stop: async () => { await docker(['stop', '-t', '5', name]).catch(() => {}) },
      }
    },
    async sweep() {
      const { stdout } = await docker(['ps', '-aq', '--filter', `label=puregamma.dsh-host=${config.instance}`]).catch(() => ({ stdout: '' }))
      const ids = String(stdout).split('\n').map(id => id.trim()).filter(Boolean)
      if (ids.length) await docker(['rm', '-f', ...ids]).catch(() => {})
      return ids.length
    },
  }
}

export function createLauncher(config: BrokerConfig): HostLauncher {
  switch (config.launcher) {
    case 'systemd': return systemdLauncher(config)
    case 'docker': return dockerLauncher(config)
    default: return directLauncher(config)
  }
}
