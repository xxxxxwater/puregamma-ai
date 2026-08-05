# PureGamma AI iMessage Relay

The relay is a self-hosted FastAPI service for users who choose to run iMessage delivery from their own Mac. It does not read the Messages private database and does not bypass Apple security controls.

## Run

```bash
cd apps/imessage-relay
export IMESSAGE_RELAY_SECRET=change-me
uvicorn relay:app --host 127.0.0.1 --port 8787
```

`POST /send` requires:

- `X-PG-Timestamp`
- `X-PG-Signature` as HMAC-SHA256 over `{timestamp}.{raw_body}`
- `X-PG-Idempotency-Key`

Non-macOS hosts return `unsupported_os` after validating HMAC and idempotency. macOS hosts call `scripts/send_imessage.applescript` through `osascript`.

## Media / voice bubbles

`POST /send-media` accepts `{recipient, file_base64, filename, kind, idempotency_key}` with the same HMAC headers.

- `kind="audio"` transcodes any audio payload (mp3/m4a/aiff/wav) with the built-in
  `afconvert` into the iMessage voice-bubble format — CAF container, Opus codec,
  24 kHz mono, transferred as `Audio Message.caf`
  (`uti=com.apple.coreaudio-format`). This matches what Messages records for real
  audio messages; plain `.mp3` attachments always render as generic file cards.
- `kind="file"` sends the payload as a regular attachment, keeping its filename.

Media is capped at `IMESSAGE_MAX_MEDIA_BYTES` (default 8 MB) and staged under
`IMESSAGE_MEDIA_WORK_DIR` (default `/tmp/puregamma-imessage-media`).
