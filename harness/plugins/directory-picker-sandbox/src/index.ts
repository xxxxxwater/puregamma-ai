import { opendir, realpath, stat } from 'node:fs/promises'
import path from 'node:path'
import type { Context } from '@deepseek-ai/cordis'
import z from '@deepseek-ai/schemastery'
import { DirectoryPicker, DirectoryPickerError } from '@deepseek-ai/dsh-host-directory-picker'
import type { DirectoryEntry, DirectoryListing, DirectoryPickerBrowseCapability } from '@deepseek-ai/dsh-host-directory-picker'

/**
 * Replaces upstream `directory-picker` (whose browse backend lists the whole
 * host filesystem from `$HOME` and creates directories) for the multi-user
 * site. It serves the same `browse` capability, so the upstream
 * `directoryPicker` Remote, ui-workspace and the browse picker UI are
 * unchanged, but:
 *
 * - every listing is confined to one root (the user's workspace, set by the
 *   session broker per Host): the requested path and every entry are
 *   realpath-resolved and must stay inside the realpath of the root, so `..`,
 *   absolute escapes and symlinks pointing outside are refused or omitted;
 * - `createDirectory` is always refused;
 * - no configured root means every call fails closed.
 *
 * `pick()` (root) is exposed for in-process consumers; over the wire the
 * upstream controller routes `pick` only to `native` backends.
 */
export interface Config {
  root?: string
  maxEntries: number
  showHidden: boolean
}

export type SandboxCapability = DirectoryPickerBrowseCapability & { pick(signal?: AbortSignal): Promise<string> }

const unreadable = (target: string, reason: string) =>
  new DirectoryPickerError('directory-unreadable', target, `cannot list "${target}": ${reason}`)

const inside = (root: string, candidate: string) => {
  const relative = path.relative(root, candidate)
  return relative === '' || (relative !== '..' && !relative.startsWith(`..${path.sep}`) && !path.isAbsolute(relative))
}

export function createSandboxCapability(config: Config): SandboxCapability {
  let realRoot: Promise<string> | undefined
  const root = (): Promise<string> => {
    const configured = config.root?.trim()
    if (!configured || !path.isAbsolute(configured)) return Promise.reject(unreadable(configured ?? '', 'no workspace root is configured'))
    realRoot ??= realpath(configured).catch(() => { realRoot = undefined; throw unreadable(configured, 'the workspace root does not exist') })
    return realRoot
  }

  async function list(requested?: string, signal?: AbortSignal): Promise<DirectoryListing> {
    const base = await root()
    if (requested !== undefined && (typeof requested !== 'string' || !path.isAbsolute(requested) || requested.includes('\0'))) {
      throw unreadable(String(requested), 'not a fully qualified path')
    }
    let target: string
    try {
      target = await realpath(requested ?? base)
    } catch {
      throw unreadable(requested ?? base, 'no such directory')
    }
    if (!inside(base, target)) throw unreadable(requested ?? base, 'outside the workspace')
    if (!(await stat(target)).isDirectory()) throw unreadable(target, 'not a directory')

    const entries: DirectoryEntry[] = []
    let truncated = false
    const dir = await opendir(target).catch(() => { throw unreadable(target, 'permission denied') })
    try {
      for await (const dirent of dir) {
        signal?.throwIfAborted()
        if (!dirent.isDirectory() && !dirent.isSymbolicLink()) continue
        const hidden = dirent.name.startsWith('.')
        if (hidden && !config.showHidden) continue
        let real: string
        try {
          real = await realpath(path.join(target, dirent.name))
          if (!(await stat(real)).isDirectory()) continue
        } catch {
          continue // broken link
        }
        // A symlink that leaves the root is not offered at all.
        if (!inside(base, real)) continue
        if (entries.length >= config.maxEntries) { truncated = true; break }
        entries.push({ name: dirent.name, path: real, hidden })
      }
    } finally {
      await dir.close().catch(() => {})
    }
    entries.sort((a, b) => a.name.localeCompare(b.name))
    const crumbs: DirectoryEntry[] = []
    for (let current = target; ; current = path.dirname(current)) {
      crumbs.unshift({ name: current === base ? path.basename(base) || base : path.basename(current), path: current, hidden: path.basename(current).startsWith('.') })
      if (current === base) break
    }
    return { path: target, home: base, crumbs, entries, truncated }
  }

  return {
    kind: 'browse',
    list,
    async createDirectory(parent: string, name: string): Promise<string> {
      throw new DirectoryPickerError('directory-create-failed', `${parent}`, `creating "${name}" is disabled: workspaces are provisioned by PureGamma`)
    },
    pick: () => root(),
  }
}

export default class SandboxDirectoryPicker extends DirectoryPicker {
  static Config: z<Config> = z.object({
    root: z.string(),
    maxEntries: z.natural().min(1).max(5000).default(500),
    showHidden: z.boolean().default(false),
  })

  private readonly sandbox: SandboxCapability

  constructor(ctx: Context, config: Config) {
    super(ctx)
    this.sandbox = createSandboxCapability(config)
  }

  capability(): SandboxCapability {
    return this.sandbox
  }
}
