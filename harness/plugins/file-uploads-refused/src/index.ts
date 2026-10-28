import { Service, type Context } from '@deepseek-ai/cordis'

/**
 * The public profile disables upstream `file-upload` because generic uploads
 * resolve through the model filesystem tools, and the shipped local filesystem
 * backend is not a containment boundary. Upstream's Session controller,
 * however, injects `fileUploads`, so without a provider the native Session
 * path never activates.
 *
 * This provider registers `ctx.fileUploads` with the four members the Session
 * controller calls and admits nothing: it mounts no HTTP upload route and no
 * Remote, `resolve` never knows a receipt (DSH then rejects the prompt as an
 * invalid attachment), and binding a prompt that names receipts throws.
 * Image attachments keep using the DSH attachment store, which does not go
 * through `fileUploads`.
 */
export const UPLOADS_DISABLED = 'generic file uploads are disabled in PureGamma'

export interface PromptFileBinding extends Disposable { commit(): void }

export default class RefusedFileUploads extends Service {
  constructor(ctx: Context) {
    super(ctx, 'fileUploads')
  }

  /** Accepted so the Session controller can mount; no upload ever needs an Agent. */
  registerAgentResolver(_resolve: unknown): () => void {
    return () => {}
  }

  /** No receipt exists. */
  resolve(_agent: unknown, _receiptId: string): undefined {
    return undefined
  }

  bindPrompt(_agent: unknown, receiptIds: readonly string[], _requestId: string): PromptFileBinding {
    if (receiptIds.length > 0) throw new Error(UPLOADS_DISABLED)
    return { commit() {}, [Symbol.dispose]() {} }
  }

  retirePrompt(_agent: unknown, _requestId: string): void {}
}
