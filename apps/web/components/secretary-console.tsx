"use client";

import { useEffect, useRef, useState } from "react";
import Image from "next/image";
import { Brain, Coins, Mic, Pause, Play, Send, ShieldCheck, Trash2, Volume2 } from "lucide-react";
import type { Locale } from "@/i18n/routing";
import { clearSecretaryMemory, getSecretary, sendSecretaryMessage, synthesizeSecretaryVoice, transcribeSecretaryAudio, type SecretaryMessage, type SecretarySkill } from "@/lib/api";
import { getMessageNamespace } from "@/lib/translations";

const skillLabels: Record<string, string> = {
  "voice-dialog": "Voice dialog", "persistent-memory": "Persistent memory", "memory-hygiene": "Memory hygiene",
  "self-improvement": "Self improvement", "agent-browser": "Agent Browser", "browser-use": "Browser Use",
  "webapp-testing": "Webapp testing", notebooklm: "NotebookLM", "better-auth-best-practices": "Better Auth",
  "supabase-postgres-best-practices": "Postgres practices", "langgraph-docs": "LangGraph docs",
  "memory-lancedb-hybrid": "LanceDB hybrid memory", "self-learning": "Self learning"
};

const waveformBars = [10, 18, 13, 24, 16, 28, 20, 12, 26, 18, 30, 15, 23, 11, 27, 17, 22, 13, 25, 16];

function formatTime(value: number) {
  const seconds = Number.isFinite(value) ? Math.max(0, Math.floor(value)) : 0;
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

function isUnauthorized(reason: unknown) {
  return Boolean(reason && typeof reason === "object" && "status" in reason && (reason as { status?: number }).status === 401);
}

function hasStatus(reason: unknown, status: number) {
  return Boolean(reason && typeof reason === "object" && "status" in reason && (reason as { status?: number }).status === status);
}

export function SecretaryConsole({ locale }: { locale: Locale }) {
  const copy = getMessageNamespace(locale, "secretary");
  const [messages, setMessages] = useState<SecretaryMessage[]>([]);
  const [skills, setSkills] = useState<SecretarySkill[]>([]);
  const [creditsPerReply, setCreditsPerReply] = useState(20);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [recording, setRecording] = useState(false);
  const [recordingRemaining, setRecordingRemaining] = useState(60);
  const [transcribing, setTranscribing] = useState(false);
  const [activeAudioId, setActiveAudioId] = useState<string | null>(null);
  const [loadingAudioId, setLoadingAudioId] = useState<string | null>(null);
  const [audioPaused, setAudioPaused] = useState(false);
  const [audioProgress, setAudioProgress] = useState(0);
  const [audioDuration, setAudioDuration] = useState(0);
  const [audioDurations, setAudioDurations] = useState<Record<string, number>>({});
  const [error, setError] = useState("");
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const activeAudioIdRef = useRef<string | null>(null);
  const loadingAudioIdRef = useRef<string | null>(null);
  const audioCacheRef = useRef(new Map<string, string>());
  const playbackResolveRef = useRef<(() => void) | null>(null);
  const synthesisAbortRef = useRef<AbortController | null>(null);
  const playRequestRef = useRef(0);
  const streamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const holdRequestedRef = useRef(false);
  const discardRecordingRef = useRef(false);
  const recordingStartedAtRef = useRef(0);
  const recordingTimerRef = useRef<number | null>(null);
  const processingRef = useRef(false);
  const messageListRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const audioCache = audioCacheRef.current;
    getSecretary(locale).then((state) => {
      setMessages(Array.isArray(state?.messages) ? state.messages.filter((item) => item && typeof item.content === "string") : []);
      setSkills(Array.isArray(state?.skills) ? state.skills.filter((item) => item && typeof item.id === "string") : []);
      if (Number.isFinite(state?.billing?.credits_per_reply)) setCreditsPerReply(state.billing.credits_per_reply);
    }).catch((reason) => setError(isUnauthorized(reason) ? copy.loginRequired : copy.loadError));
    return () => {
      stopHoldRecording(true);
      synthesisAbortRef.current?.abort();
      for (const url of audioCache.values()) URL.revokeObjectURL(url);
      audioCache.clear();
    };
    // The locale route remounts this component when language changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [locale]);

  useEffect(() => {
    const list = messageListRef.current;
    if (!list) return;
    try { list.scrollTo({ top: list.scrollHeight, behavior: "smooth" }); }
    catch { list.scrollTop = list.scrollHeight; }
  }, [messages, busy, transcribing]);

  function finishPlayback() {
    audioRef.current?.pause();
    audioRef.current = null;
    activeAudioIdRef.current = null;
    setActiveAudioId(null);
    setAudioPaused(false);
    setAudioProgress(0);
    setAudioDuration(0);
    const resolve = playbackResolveRef.current;
    playbackResolveRef.current = null;
    resolve?.();
  }

  async function playMessage(message: SecretaryMessage, waitForEnd = false): Promise<void> {
    if (activeAudioIdRef.current === message.id && audioRef.current) {
      if (audioRef.current.paused) {
        await audioRef.current.play();
        setAudioPaused(false);
      } else {
        audioRef.current.pause();
        setAudioPaused(true);
      }
      return;
    }
    if (loadingAudioIdRef.current === message.id) return;
    const requestId = ++playRequestRef.current;
    synthesisAbortRef.current?.abort();
    synthesisAbortRef.current = null;
    finishPlayback();
    setError("");
    loadingAudioIdRef.current = message.id;
    setLoadingAudioId(message.id);
    try {
      let url = audioCacheRef.current.get(message.id);
      if (!url) {
        const controller = new AbortController();
        synthesisAbortRef.current = controller;
        const blob = await synthesizeSecretaryVoice(message.content, locale, controller.signal);
        if (requestId !== playRequestRef.current || controller.signal.aborted) return;
        url = URL.createObjectURL(blob);
        audioCacheRef.current.set(message.id, url);
      }
      if (requestId !== playRequestRef.current) return;
      const audio = new Audio(url);
      audioRef.current = audio;
      activeAudioIdRef.current = message.id;
      setActiveAudioId(message.id);
      setAudioPaused(false);
      setAudioProgress(0);
      audio.onloadedmetadata = () => {
        const duration = Number.isFinite(audio.duration) ? audio.duration : 0;
        setAudioDuration(duration);
        if (duration > 0) setAudioDurations((current) => ({ ...current, [message.id]: duration }));
      };
      audio.ontimeupdate = () => setAudioProgress(audio.currentTime);
      const completed = new Promise<void>((resolve) => { playbackResolveRef.current = resolve; });
      audio.onended = finishPlayback;
      audio.onerror = () => { setError(copy.voiceError); finishPlayback(); };
      await audio.play();
      if (waitForEnd) await completed;
    } catch (reason) {
      if (requestId === playRequestRef.current) {
        if (!(reason instanceof DOMException && reason.name === "AbortError")) setError(isUnauthorized(reason) ? copy.loginRequired : copy.voiceError);
        finishPlayback();
      }
    } finally {
      if (requestId === playRequestRef.current) {
        loadingAudioIdRef.current = null;
        setLoadingAudioId(null);
        synthesisAbortRef.current = null;
      }
    }
  }

  async function sendContent(content: string) {
    const clean = content.trim();
    if (!clean || processingRef.current) return;
    processingRef.current = true;
    setInput("");
    setBusy(true);
    setError("");
    const optimistic: SecretaryMessage = { id: `local-${Date.now()}`, role: "user", content: clean, created_at: new Date().toISOString() };
    setMessages((current) => [...current, optimistic]);
    try {
      const requestId = typeof window.crypto.randomUUID === "function" ? window.crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
      const result = await sendSecretaryMessage(clean, locale, requestId);
      setMessages((current) => [...current.filter((item) => item.id !== optimistic.id), result.user_message, result.assistant_message]);
      await playMessage(result.assistant_message, true);
    } catch (reason) {
      setMessages((current) => current.filter((item) => item.id !== optimistic.id));
      setInput(clean);
      setError(isUnauthorized(reason) ? copy.loginRequired : hasStatus(reason, 402) ? copy.insufficientCredits : copy.messageError);
    } finally {
      setBusy(false);
      processingRef.current = false;
    }
  }

  async function processVoice(blob: Blob) {
    setRecording(false);
    setTranscribing(true);
    processingRef.current = true;
    try {
      const transcript = await transcribeSecretaryAudio(blob, locale);
      processingRef.current = false;
      setTranscribing(false);
      await sendContent(transcript.text);
    } catch (reason) {
      processingRef.current = false;
      setTranscribing(false);
      setError(isUnauthorized(reason) ? copy.loginRequired : copy.transcriptionError);
    }
  }

  function beginHoldRecording(stream: MediaStream) {
    if (!holdRequestedRef.current || processingRef.current || recorderRef.current?.state === "recording") {
      stream.getTracks().forEach((track) => track.stop());
      return;
    }
    const supported = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"].find((type) => MediaRecorder.isTypeSupported(type));
    const recorder = supported ? new MediaRecorder(stream, { mimeType: supported }) : new MediaRecorder(stream);
    const chunks: BlobPart[] = [];
    streamRef.current = stream;
    discardRecordingRef.current = false;
    recordingStartedAtRef.current = Date.now();

    recorder.ondataavailable = (event) => { if (event.data.size) chunks.push(event.data); };
    recorder.onstop = () => {
      if (recordingTimerRef.current !== null) window.clearInterval(recordingTimerRef.current);
      recordingTimerRef.current = null;
      stream.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
      recorderRef.current = null;
      setRecording(false);
      setRecordingRemaining(60);
      const elapsed = Date.now() - recordingStartedAtRef.current;
      if (discardRecordingRef.current) return;
      if (elapsed < 350 || chunks.length === 0) { setError(copy.tooShort); return; }
      const blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
      void processVoice(blob);
    };
    recorderRef.current = recorder;
    recorder.start(250);
    setRecording(true);
    setRecordingRemaining(60);
    recordingTimerRef.current = window.setInterval(() => {
      const elapsed = Date.now() - recordingStartedAtRef.current;
      setRecordingRemaining(Math.max(0, 60 - Math.floor(elapsed / 1000)));
      if (elapsed >= 60_000) stopHoldRecording();
    }, 200);
  }

  async function startHoldRecording() {
    if (processingRef.current || busy || transcribing || recording) return;
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setError(copy.permissionDenied);
      return;
    }
    synthesisAbortRef.current?.abort();
    ++playRequestRef.current;
    loadingAudioIdRef.current = null;
    setLoadingAudioId(null);
    finishPlayback();
    holdRequestedRef.current = true;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
      if (!holdRequestedRef.current) { stream.getTracks().forEach((track) => track.stop()); return; }
      setError("");
      beginHoldRecording(stream);
    } catch {
      holdRequestedRef.current = false;
      setError(copy.permissionDenied);
    }
  }

  function stopHoldRecording(discard = false) {
    holdRequestedRef.current = false;
    discardRecordingRef.current = discard;
    if (recordingTimerRef.current !== null) window.clearInterval(recordingTimerRef.current);
    recordingTimerRef.current = null;
    if (recorderRef.current?.state === "recording") recorderRef.current.stop();
  }

  async function clearMemory() {
    if (!window.confirm(copy.clearConfirm)) return;
    try { await clearSecretaryMemory(); stopHoldRecording(true); setMessages([]); }
    catch (reason) { setError(isUnauthorized(reason) ? copy.loginRequired : copy.loadError); }
  }

  function statusLabel(status: SecretarySkill["status"]) {
    if (status === "active") return copy.active;
    if (status === "confirmation_required") return copy.confirmation;
    if (status === "setup_required") return copy.setup;
    if (status === "planned") return copy.planned;
    return copy.available;
  }

  return (
    <div className="relative xl:pr-[300px]">
      <div className="grid border border-border-pg bg-bg-panel lg:h-[calc(100dvh-6.5rem)] lg:min-h-[520px] lg:grid-cols-[minmax(0,1fr)_260px] lg:overflow-hidden xl:grid-cols-[minmax(0,1fr)_240px]">
      <section className="flex h-[calc(100dvh-10rem)] min-h-[408px] min-w-0 flex-col overflow-hidden lg:h-auto lg:min-h-0">
        <header className="shrink-0 flex flex-wrap items-start justify-between gap-4 border-b border-border-pg p-5">
          <div><div className="text-[0.68rem] font-semibold uppercase tracking-[0.18em] text-text-pg-muted">{copy.eyebrow}</div><h1 className="mt-2 text-2xl font-semibold">{copy.title}</h1><p className="mt-2 max-w-2xl text-sm leading-6 text-text-pg-muted">{copy.description}</p></div>
          <div className="flex flex-wrap gap-2 text-xs"><span className="inline-flex items-center gap-1.5 border border-border-pg bg-bg-panel-muted px-2 py-1"><Volume2 className="h-3.5 w-3.5" />{copy.voiceName} · {copy.fixedVoice}</span><span className="inline-flex items-center gap-1.5 border border-border-pg bg-bg-panel-muted px-2 py-1"><Coins className="h-3.5 w-3.5" />{creditsPerReply} {copy.creditsPerReply}</span><span className="inline-flex items-center gap-1.5 border border-border-pg bg-bg-panel-muted px-2 py-1 text-status-positive"><Brain className="h-3.5 w-3.5" />{copy.memoryOn}</span></div>
        </header>

        <div ref={messageListRef} className="min-h-0 flex-1 space-y-4 overflow-y-auto overscroll-contain p-4 md:p-6">
          {messages.length === 0 ? <div className="mx-auto flex min-h-[360px] max-w-lg flex-col items-center justify-center text-center"><div className="flex h-12 w-12 items-center justify-center border border-border-pg bg-bg-panel-muted"><Mic className="h-5 w-5" /></div><h2 className="mt-5 text-xl font-semibold">{copy.emptyTitle}</h2><p className="mt-2 text-sm leading-6 text-text-pg-muted">{copy.emptyDescription}</p></div> : messages.map((message) => {
            const assistant = message.role === "assistant";
            const active = activeAudioId === message.id;
            const loading = loadingAudioId === message.id;
            const playing = active && !audioPaused;
            const ratio = active && audioDuration > 0 ? Math.min(1, audioProgress / audioDuration) : 0;
            const knownDuration = active ? audioDuration : (audioDurations[message.id] || 0);
            const remaining = active ? Math.max(0, knownDuration - audioProgress) : knownDuration;
            return (
              <div key={message.id} className={`flex ${assistant ? "justify-start" : "justify-end"}`}>
                <div className={`max-w-[86%] border px-4 py-3 text-sm leading-6 ${assistant ? "secretary-bubble-assistant" : "border-border-pg-strong bg-pg-white text-pg-black"}`}>
                  <div className="whitespace-pre-wrap">{String(message.content || "")}</div>
                  {assistant ? (
                    <div className="mt-3 flex min-h-14 w-[min(320px,72vw)] items-center gap-3 rounded-[8px] bg-[#229ed9] px-3 py-2 text-white shadow-sm">
                      <button type="button" title={playing ? copy.stop : copy.play} disabled={loading} onClick={() => void playMessage(message)} className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-white/20 hover:bg-white/30 disabled:opacity-60">
                        {loading ? <span className="h-3.5 w-3.5 animate-pulse rounded-full bg-white" /> : playing ? <Pause className="h-4 w-4 fill-current" /> : <Play className="h-4 w-4 fill-current" />}
                      </button>
                      <div className="min-w-0 flex-1">
                        <div className="flex h-8 items-center gap-[3px] overflow-hidden" aria-hidden>{waveformBars.map((height, index) => <span key={index} className={`w-[3px] shrink-0 rounded-full ${index / waveformBars.length <= ratio ? "bg-white" : "bg-white/45"}`} style={{ height }} />)}</div>
                        <div className="mt-0.5 flex justify-between text-[0.68rem] leading-none text-white/85"><span>{loading ? copy.speaking : formatTime(active ? audioProgress : 0)}</span><span>{knownDuration > 0 ? `-${formatTime(remaining)}` : "0:00"}</span></div>
                      </div>
                    </div>
                  ) : null}
                </div>
              </div>
            );
          })}
          {recording ? <div className="flex items-center gap-2 text-sm text-status-positive"><span className="h-2 w-2 animate-pulse rounded-full bg-status-positive" />{copy.listening} {formatTime(recordingRemaining)}</div> : null}
          {transcribing ? <div className="text-sm text-text-pg-muted">{copy.transcribing}</div> : null}
          {busy ? <div className="text-sm text-text-pg-muted">{copy.thinking}</div> : null}
        </div>

        <div className="shrink-0 border-t border-border-pg bg-bg-panel p-4">
          {error ? <div className="mb-3 text-sm text-status-negative">{error}</div> : null}
          <div className="flex items-end gap-2">
            <button
              type="button"
              title={`${copy.holdToTalk} · ${copy.recordingLimit}`}
              disabled={busy || transcribing}
              onPointerDown={(event) => { if (event.button !== 0) return; event.preventDefault(); event.currentTarget.setPointerCapture(event.pointerId); void startHoldRecording(); }}
              onPointerUp={(event) => { event.preventDefault(); stopHoldRecording(); }}
              onPointerCancel={() => stopHoldRecording(true)}
              onKeyDown={(event) => { if ((event.key === " " || event.key === "Enter") && !event.repeat) { event.preventDefault(); void startHoldRecording(); } }}
              onKeyUp={(event) => { if (event.key === " " || event.key === "Enter") { event.preventDefault(); stopHoldRecording(); } }}
              onContextMenu={(event) => event.preventDefault()}
              className={`flex h-11 w-[150px] shrink-0 touch-none select-none items-center justify-center gap-2 border px-3 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-40 ${recording ? "border-status-positive bg-status-positive text-white" : "border-border-pg text-text-pg-muted hover:border-border-pg-strong hover:text-text-pg"}`}
            >
              <Mic className="h-4 w-4" />{recording ? `${copy.releaseToSend} ${formatTime(recordingRemaining)}` : copy.holdToTalk}
            </button>
            <textarea value={input} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void sendContent(input); } }} rows={2} maxLength={4000} placeholder={copy.placeholder} className="min-h-11 min-w-0 flex-1 resize-none border border-border-pg bg-bg-app px-3 py-2 text-sm outline-none placeholder:text-text-pg-dim focus:border-border-pg-strong" />
            <button type="button" title={copy.send} disabled={!input.trim() || busy || transcribing} onClick={() => void sendContent(input)} className="flex h-11 w-11 shrink-0 items-center justify-center border border-border-pg-strong bg-pg-white text-pg-black disabled:cursor-not-allowed disabled:opacity-40"><Send className="h-4 w-4" /></button>
          </div>
        </div>
      </section>

      <aside className="border-t border-border-pg p-5 lg:min-h-0 lg:overflow-y-auto lg:border-l lg:border-t-0"><div className="flex items-center gap-2 font-semibold"><ShieldCheck className="h-4 w-4" />{copy.skills}</div><div className="mt-4 divide-y divide-border-pg border-y border-border-pg">{skills.map((skill) => <div key={skill.id} className="py-3"><div className="text-sm font-medium">{skillLabels[skill.id] || skill.id}</div><div className={`mt-1 text-xs ${skill.status === "active" ? "text-status-positive" : skill.status === "confirmation_required" ? "text-status-warning" : "text-text-pg-muted"}`}>{statusLabel(skill.status)}</div></div>)}</div><p className="mt-5 text-xs leading-5 text-text-pg-muted">{copy.privacy}</p><button type="button" onClick={() => void clearMemory()} className="mt-5 inline-flex items-center gap-2 border border-border-pg px-3 py-2 text-xs text-text-pg-muted hover:border-status-negative hover:text-status-negative"><Trash2 className="h-3.5 w-3.5" />{copy.clearMemory}</button></aside>
      </div>

      <aside className="pointer-events-none absolute bottom-0 right-[-50px] top-0 z-10 hidden w-[400px] xl:block" aria-label={locale === "zh" ? "抓住技能面板边框的亲密秘书" : "Private Secretary holding the Skills panel edge"}>
        <div className="secretary-theme-dark absolute inset-0">
          <Image src="/secretary/private-secretary-dark.png" alt="" fill priority unoptimized sizes="400px" className="object-contain object-bottom" />
          <Image src="/secretary/private-secretary-dark-blink.png" alt="" fill priority unoptimized sizes="400px" className="secretary-portrait-blink object-contain object-bottom" />
        </div>
        <div className="secretary-theme-light absolute inset-0">
          <Image src="/secretary/private-secretary-light.png" alt="" fill priority unoptimized sizes="400px" className="object-contain object-bottom" />
          <Image src="/secretary/private-secretary-light-blink.png" alt="" fill priority unoptimized sizes="400px" className="secretary-portrait-blink object-contain object-bottom" />
        </div>
      </aside>
    </div>
  );
}
