import { Service, type Context } from '@deepseek-ai/cordis'

/**
 * Browser half of the refused uploads provider.
 *
 * Upstream's client Session controller and conversation UI inject the
 * browser `fileUpload` service, which only `@deepseek-ai/dsh-client-file-upload`
 * (the client face of the disabled `file-upload` row) provides. Without it
 * the whole DSH Web chat surface stays pending in the browser, even though
 * the Host-side Session RPCs work. This service satisfies the dependency and
 * answers every upload with a business error; it never touches the network.
 */
export const UPLOAD_DISABLED_CODE = 'file-upload/disabled'
export const UPLOAD_DISABLED_MESSAGE = 'File attachments are disabled in PureGamma'

/** Shape-compatible with Typert's RemoteError (code, message, details). */
export class UploadRefused extends Error {
  readonly code = UPLOAD_DISABLED_CODE
  readonly details: Record<string, never> = {}
  constructor() {
    super(UPLOAD_DISABLED_MESSAGE)
    this.name = 'RemoteError'
  }
}

export type RefusedUploadResult = { ok: false; error: UploadRefused }

export class RefusedFileUpload extends Service {
  constructor(ctx: Context) {
    super(ctx, 'fileUpload')
  }

  /** No transport exists. */
  post(_request: unknown): Promise<never> {
    return Promise.reject(new UploadRefused())
  }

  /** Every upload is refused before any byte is read. */
  async upload(_sessionId: string, _data: unknown, _name?: string, _signal?: AbortSignal): Promise<RefusedUploadResult> {
    return { ok: false, error: new UploadRefused() }
  }
}

export const inject: string[] = []

export function apply(ctx: Context): void {
  ctx.plugin(RefusedFileUpload)
}
