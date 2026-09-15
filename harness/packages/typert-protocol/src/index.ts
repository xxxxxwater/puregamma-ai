import {
  Remote as pinnedRemote,
  RemoteScope as pinnedRemoteScope,
  bindTypertRemote as pinnedBindTypertRemote,
  isTypertRemoteSegment as pinnedIsTypertRemoteSegment,
  RemoteError,
  remoteErrorOf,
  TypertRemoteService as PinnedTypertRemoteService,
} from '@deepseek-ai/dsh-typert-protocol-runtime'

export type * from '@deepseek-ai/dsh-typert-protocol-runtime'

/** Runtime implementation comes from the pinned DeepSeek Harness protocol. */
export const Remote = pinnedRemote
/** Runtime implementation comes from the pinned DeepSeek Harness protocol. */
export const RemoteScope = pinnedRemoteScope
/** Runtime implementation comes from the pinned DeepSeek Harness protocol. */
export const bindTypertRemote = pinnedBindTypertRemote
/** Runtime implementation comes from the pinned DeepSeek Harness protocol. */
export const isTypertRemoteSegment = pinnedIsTypertRemoteSegment

/**
 * Local declaration anchor for the official protocol package name.
 * The class delegates all lifecycle and Cordis registration behavior to the
 * pinned Harness implementation; it exists locally only so Typert source-mode
 * discovery can register the protocol symbols inside the PureGamma workspace.
 */
export abstract class TypertRemoteService<T = never> extends PinnedTypertRemoteService<T> {}

export { RemoteError, remoteErrorOf }
