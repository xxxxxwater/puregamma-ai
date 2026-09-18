#!/usr/bin/env bash
set -Eeuo pipefail
# =============================================================================
# PureGamma private-PM preservation.
#
# The private-PM work is deliberately NOT in main (it is the difference between
# this branch and main, listed in deploy/pm-paths.txt).  A deploy that starts
# from a plain main checkout therefore does not contain it, and one that rsyncs
# over the live tree would overwrite the files it *does* contain.
#
# So PM is treated like the database: it is backed up before a deploy and can be
# restored afterwards, and it never depends on the deploy source tree for its
# continued existence.
#
# Usage:
#   bash deploy/pm-preserve.sh paths
#   bash deploy/pm-preserve.sh verify   [--tree DIR]
#   bash deploy/pm-preserve.sh backup   [--tree DIR] [--out DIR]
#   bash deploy/pm-preserve.sh restore  <archive.tar.gz> [--tree DIR]
#   bash deploy/pm-preserve.sh sync     --from DIR --to DIR
#
# Exit codes: 0 ok, 1 usage/IO error, 2 a PM path is missing or unreadable.
# =============================================================================

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MANIFEST="${PM_MANIFEST:-${ROOT_DIR}/deploy/pm-paths.txt}"
DEFAULT_OUT="${PM_BACKUP_DIR:-/puregamma/pm-backups}"

TREE="${ROOT_DIR}"
OUT_DIR="${DEFAULT_OUT}"
FROM_DIR=""
TO_DIR=""
POSITIONAL=""

die() { echo "pm-preserve: $*" >&2; exit 1; }

load_paths() {
  [ -f "${MANIFEST}" ] || die "manifest not found: ${MANIFEST}"
  # shellcheck disable=SC2207
  PATHS=($(grep -vE '^\s*(#|$)' "${MANIFEST}"))
  [ "${#PATHS[@]}" -gt 0 ] || die "manifest is empty: ${MANIFEST}"
}

# Returns 2 (never exits) when a PM path is absent, so `restore` can still run
# against a tree that lost them — which is the case it exists to repair.
require_tree() {
  local tree="$1" missing=0 p
  [ -d "${tree}" ] || die "tree not found: ${tree}"
  for p in "${PATHS[@]}"; do
    if [ ! -f "${tree}/${p}" ]; then
      echo "pm-preserve: MISSING ${p}" >&2
      missing=$((missing + 1))
    fi
  done
  [ "${missing}" -eq 0 ] || return 2
}

cmd="${1:-}"
shift || true

while [ $# -gt 0 ]; do
  case "$1" in
    --tree) TREE="$2"; shift 2 ;;
    --out)  OUT_DIR="$2"; shift 2 ;;
    --from) FROM_DIR="$2"; shift 2 ;;
    --to)   TO_DIR="$2"; shift 2 ;;
    --*)    die "unknown option: $1" ;;
    *)      POSITIONAL="$1"; shift ;;
  esac
done

load_paths

case "${cmd}" in
  paths)
    printf '%s\n' "${PATHS[@]}"
    ;;

  verify)
    require_tree "${TREE}" || exit 2
    echo "pm-preserve: OK — ${#PATHS[@]} PM paths present under ${TREE}"
    ;;

  backup)
    require_tree "${TREE}" || exit 2
    install -d -m 0700 "${OUT_DIR}"
    stamp="$(date -u +%Y%m%dT%H%M%SZ)"
    archive="${OUT_DIR}/pm-${stamp}.tar.gz"
    # tar from the manifest, so a path that vanished is an error, not a
    # silently smaller archive.
    tar czf "${archive}" -C "${TREE}" "${PATHS[@]}"
    chmod 600 "${archive}"
    echo "pm-preserve: wrote ${archive} ($(wc -c <"${archive}" | tr -d ' ') bytes, ${#PATHS[@]} paths)"
    ;;

  restore)
    archive="${POSITIONAL}"
    [ -n "${archive}" ] || die "restore needs an archive path"
    [ -f "${archive}" ] || die "archive not found: ${archive}"
    [ -d "${TREE}" ] || die "tree not found: ${TREE}"
    tar xzf "${archive}" -C "${TREE}"
    require_tree "${TREE}" || exit 2
    echo "pm-preserve: restored ${#PATHS[@]} PM paths into ${TREE}"
    ;;

  sync)
    [ -n "${FROM_DIR}" ] && [ -n "${TO_DIR}" ] || die "sync needs --from and --to"
    [ -d "${FROM_DIR}" ] || die "from not found: ${FROM_DIR}"
    [ -d "${TO_DIR}" ] || die "to not found: ${TO_DIR}"
    n=0
    for p in "${PATHS[@]}"; do
      [ -f "${FROM_DIR}/${p}" ] || { echo "pm-preserve: SOURCE MISSING ${p}" >&2; exit 2; }
      # cp -p rather than install: BSD install has no -D, and this has to run
      # on the mac that prepares the release as well as on the Linux host.
      if [ "$(cd "${FROM_DIR}" && pwd)/${p}" = "$(cd "${TO_DIR}" && pwd)/${p}" ]; then
        n=$((n + 1)); continue          # sync --from X --to X is a no-op
      fi
      mkdir -p "$(dirname "${TO_DIR}/${p}")"
      cp -p "${FROM_DIR}/${p}" "${TO_DIR}/${p}"
      n=$((n + 1))
    done
    # A deploy target that lacks the PM files is the failure this script
    # exists to prevent, so prove it landed.
    require_tree "${TO_DIR}" || exit 2
    echo "pm-preserve: synced ${n} PM paths ${FROM_DIR} -> ${TO_DIR}"
    ;;

  *)
    sed -n '3,25p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit 1
    ;;
esac
