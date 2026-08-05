#!/usr/bin/env bash
set -Eeuo pipefail
# =========================================================================
# PureGamma iOS - Release packaging (macOS + Xcode required)
# =========================================================================
# Produces a versioned, signed IPA identical in spirit to the web Docker
# images (deploy/deploy.sh) and the Android APKs (apps/android/releases/).
#
# Usage (run on a Mac with Xcode and a configured Apple Development team):
#   bash scripts/ios-build-release.sh [app-store|ad-hoc|development]
#
# Environment overrides:
#   IOS_VERSION_OVERRIDE    e.g. 1.2.0   (defaults to MARKETING_VERSION)
#   IOS_BUILD_OVERRIDE      e.g. 3       (defaults to CURRENT_PROJECT_VERSION)
#   PUREGAMMA_DEVELOPMENT_TEAM   (falls back to Config/Local.xcconfig)
#
# Helper modes:
#   bash scripts/ios-build-release.sh bump   # bump CURRENT_PROJECT_VERSION
#   bash scripts/ios-build-release.sh info   # print current version state
# =========================================================================

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IOS_DIR="${ROOT_DIR}/apps/ios"
PROJECT="${IOS_DIR}/PureGamma.xcodeproj"
SCHEME="PureGamma"
RELEASES_DIR="${IOS_DIR}/releases"
CONFIG="${IOS_DIR}/Config"
METHOD="${1:-app-store}"

# -----------------------------------------------------------------
# 0. Environment checks
# -----------------------------------------------------------------
if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "ERROR: iOS release packaging requires macOS with Xcode."
  echo "       The PureGamma iOS client cannot be compiled or signed on Windows/Linux."
  exit 1
fi
if ! command -v xcodebuild >/dev/null 2>&1; then
  echo "ERROR: xcodebuild not found. Install Xcode from the Mac App Store."
  exit 1
fi

read_pbx_value() {
  grep -o "$1 = [^;]*" "${PROJECT}/project.pbxproj" | head -n 1 | awk -F' = ' '{print $2}'
}

MARKETING_VERSION="$(read_pbx_value 'MARKETING_VERSION')"
CURRENT_BUILD="$(read_pbx_value 'CURRENT_PROJECT_VERSION')"

# -----------------------------------------------------------------
# 1. Helper modes
# -----------------------------------------------------------------
if [[ "${METHOD}" == "info" ]]; then
  echo "MARKETING_VERSION=${MARKETING_VERSION}"
  echo "CURRENT_PROJECT_VERSION=${CURRENT_BUILD}"
  echo "DEVELOPMENT_TEAM=$(grep -o 'PUREGAMMA_DEVELOPMENT_TEAM = [^;]*' "${CONFIG}/Local.xcconfig" 2>/dev/null | awk -F' = ' '{print $2}' || echo '(not configured)')"
  exit 0
fi

if [[ "${METHOD}" == "bump" ]]; then
  NEW_BUILD="$((CURRENT_BUILD + 1))"
  sed -i '' "s/CURRENT_PROJECT_VERSION = ${CURRENT_BUILD}/CURRENT_PROJECT_VERSION = ${NEW_BUILD}/" "${PROJECT}/project.pbxproj"
  echo "Bumped CURRENT_PROJECT_VERSION ${CURRENT_BUILD} -> ${NEW_BUILD}"
  exit 0
fi

if [[ "${METHOD}" != "app-store" && "${METHOD}" != "ad-hoc" && "${METHOD}" != "development" ]]; then
  echo "ERROR: unknown export method '${METHOD}'. Use app-store, ad-hoc or development."
  exit 1
fi

VERSION="${IOS_VERSION_OVERRIDE:-${MARKETING_VERSION}}"
BUILD="${IOS_BUILD_OVERRIDE:-${CURRENT_BUILD}}"
TEAM="${PUREGAMMA_DEVELOPMENT_TEAM:-}"
if [[ -z "${TEAM}" && -f "${CONFIG}/Local.xcconfig" ]]; then
  TEAM="$(grep -o 'PUREGAMMA_DEVELOPMENT_TEAM = [^;]*' "${CONFIG}/Local.xcconfig" | awk -F' = ' '{print $2}')"
fi

if [[ -z "${TEAM}" || "${TEAM}" == "YOUR_TEAM_ID" ]]; then
  echo "ERROR: Apple Development Team is not configured."
  echo "       Set PUREGAMMA_DEVELOPMENT_TEAM in ${CONFIG}/Local.xcconfig"
  exit 1
fi

# -----------------------------------------------------------------
# 2. Export options (generated per method; never commit team IDs)
# -----------------------------------------------------------------
EXPORT_OPTIONS="$(mktemp)"
cat > "${EXPORT_OPTIONS}" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>method</key><string>${METHOD}</string>
  <key>teamID</key><string>${TEAM}</string>
  <key>signingStyle</key><string>automatic</string>
  <key>stripSwiftSymbols</key><true/>
  <key>uploadSymbols</key><true/>
  <key>compileBitcode</key><false/>
</dict></plist>
EOF

# -----------------------------------------------------------------
# 3. Archive + export
# -----------------------------------------------------------------
ARCHIVE_PATH="${IOS_DIR}/build/PureGamma-${VERSION}-${BUILD}.xcarchive"
EXPORT_PATH="${IOS_DIR}/build/export-${METHOD}"

echo "=== Archive (${VERSION} (${BUILD}), method=${METHOD}) ==="
xcodebuild archive \
  -project "${PROJECT}" \
  -scheme "${SCHEME}" \
  -configuration Release \
  -destination 'generic/platform=iOS' \
  -archivePath "${ARCHIVE_PATH}" \
  DEVELOPMENT_TEAM="${TEAM}"

echo "=== Export IPA ==="
rm -rf "${EXPORT_PATH}"
xcodebuild -exportArchive \
  -archivePath "${ARCHIVE_PATH}" \
  -exportOptionsPlist "${EXPORT_OPTIONS}" \
  -exportPath "${EXPORT_PATH}"

rm -f "${EXPORT_OPTIONS}"

# -----------------------------------------------------------------
# 4. Versioned artifact, matching apps/android/releases convention
# -----------------------------------------------------------------
mkdir -p "${RELEASES_DIR}"
IPA_NAME="PureGamma-${VERSION}-${BUILD}-${METHOD}.ipa"
cp "${EXPORT_PATH}/${SCHEME}.ipa" "${RELEASES_DIR}/${IPA_NAME}"
echo ""
echo "=== Release package ready ==="
echo "${RELEASES_DIR}/${IPA_NAME}"
ls -lh "${RELEASES_DIR}/${IPA_NAME}"

echo ""
echo "=== Next steps ==="
if [[ "${METHOD}" == "app-store" ]]; then
  echo "Upload to TestFlight/App Store:"
  echo "  xcrun altool --upload-app -f \"${RELEASES_DIR}/${IPA_NAME}\" \\"
  echo "    -t ios --apiKey <KEY_ID> --apiIssuer <ISSUER_ID>"
fi
echo "Install on a device: use Apple Configurator, or distribute the ad-hoc IPA."
