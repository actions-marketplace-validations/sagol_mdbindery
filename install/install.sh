#!/usr/bin/env bash
# mdbindery installer for Linux and macOS. Needs only bash, curl, and tar.
#
#   curl -fsSL https://raw.githubusercontent.com/sagol/mdbindery/main/install/install.sh | bash
#   bash install/install.sh --local .          # from a checkout of the repository
#
# Options:
#   --local PATH        install mdbindery from a local folder instead of GitHub
#   --ref REF           branch, tag, or commit on GitHub (default: main)
#   --no-node           skip Node.js, mermaid-cli, and Ace (charts become placeholders, no Ace check)
#   --java MODE         auto (default: download a Java runtime only if none >= 11), always, never
#   --no-tools          install the mdbindery command only
#   --uninstall         remove mdbindery, its tools, and its Python
#
# Environment: MDBINDERY_HOME (tool home), MDBINDERY_BIN (where the command goes, default ~/.local/bin)
#
# Steps: 1) get uv (a pinned, checksum-verified binary) unless uv is already installed;
#        2) uv installs mdbindery into an isolated environment, with its own Python if needed;
#        3) `mdbindery install-tools` downloads pandoc, EPUBCheck, Node.js, mermaid-cli, Ace.
set -euo pipefail

UV_VERSION=0.12.19
REPO=https://github.com/sagol/mdbindery
REF=main
LOCAL=''
TOOLS_ARGS=()
NO_TOOLS=0
UNINSTALL=0

usage() {
  cat <<'USAGE'
mdbindery installer for Linux and macOS

  curl -fsSL https://raw.githubusercontent.com/sagol/mdbindery/main/install/install.sh | bash
  bash install/install.sh --local .          # from a checkout

  --local PATH     install from a local folder instead of GitHub
  --ref REF        branch, tag, or commit on GitHub (default: main)
  --no-node        skip Node.js, mermaid-cli, and Ace (charts become placeholders, no accessibility check)
  --java MODE      auto (default), always, never
  --no-tools       install the mdbindery command only
  --uninstall      remove mdbindery, its tools, and its Python

Environment: MDBINDERY_HOME (tool home), MDBINDERY_BIN (command folder, default ~/.local/bin)
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --local|--ref)
      if [[ $# -lt 2 || "$2" == -* ]]; then echo "$1 needs a value" >&2; exit 2; fi
      if [[ "$1" == --local ]]; then LOCAL="$2"; else REF="$2"; fi
      shift 2 ;;
    --no-node) TOOLS_ARGS+=(--no-node); shift ;;
    --java)
      case "${2:-}" in auto|always|never) ;; *) echo "--java needs auto, always, or never" >&2; exit 2 ;; esac
      TOOLS_ARGS+=(--java "$2"); shift 2 ;;
    --no-tools) NO_TOOLS=1; shift ;;
    --uninstall) UNINSTALL=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

say() { printf '%s\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

if [[ -n "$LOCAL" && ! -f "$LOCAL/pyproject.toml" ]]; then
  echo "error: --local needs the mdbindery source folder (with pyproject.toml): $LOCAL" >&2; exit 2
fi

OS=$(uname -s); ARCH=$(uname -m)
case "$OS" in
  Linux)  DEFAULT_HOME="${XDG_DATA_HOME:-$HOME/.local/share}/mdbindery" ;;
  Darwin) DEFAULT_HOME="$HOME/Library/Application Support/mdbindery" ;;
  *) die "unsupported system $OS (use install.ps1 on Windows)" ;;
esac
export MDBINDERY_HOME="${MDBINDERY_HOME:-$DEFAULT_HOME}"
BIN_DIR="${MDBINDERY_BIN:-$HOME/.local/bin}"
mkdir -p "$MDBINDERY_HOME" "$BIN_DIR"

case "$OS-$ARCH" in
  Linux-x86_64)  UV_ASSET=uv-x86_64-unknown-linux-gnu.tar.gz;  UV_SHA=23bf5552d220e0842b65c862097b2ebaeba0064b74eda5e565e77fd25969d8c8 ;;
  Linux-aarch64|Linux-arm64) UV_ASSET=uv-aarch64-unknown-linux-gnu.tar.gz; UV_SHA=0804e9b164c64b6914182d5920c08551958a095986f10a3731056df701126436 ;;
  Darwin-x86_64) UV_ASSET=uv-x86_64-apple-darwin.tar.gz;       UV_SHA=cb5fa57bafe68fc0fb94b17f06bee0b0b9a7feb94ccbd110445afa0696e39273 ;;
  Darwin-arm64)  UV_ASSET=uv-aarch64-apple-darwin.tar.gz;      UV_SHA=a9a8df1eedeb192f2e47e40e2faabfb387db4b850209118786d42f89dde3e0ba ;;
  *) die "unsupported platform $OS $ARCH" ;;
esac

sha256() { if command -v sha256sum >/dev/null; then sha256sum "$1" | cut -d' ' -f1; else shasum -a 256 "$1" | cut -d' ' -f1; fi; }

# isolated uv state inside the tool home
export UV_TOOL_DIR="$MDBINDERY_HOME/uv-tools"
export UV_TOOL_BIN_DIR="$BIN_DIR"
export UV_PYTHON_INSTALL_DIR="$MDBINDERY_HOME/python"

UV="$(command -v uv || true)"
if [[ -z "$UV" && -x "$MDBINDERY_HOME/uv/uv" ]]; then UV="$MDBINDERY_HOME/uv/uv"; fi

if [[ $UNINSTALL == 1 ]]; then
  [[ -n "$UV" ]] && "$UV" tool uninstall mdbindery >/dev/null 2>&1 || true
  rm -f "$BIN_DIR/mdbindery"
  # only what mdbindery created; the folder itself goes only if nothing else is left in it
  rm -rf "$MDBINDERY_HOME/tools" "$MDBINDERY_HOME/uv" "$MDBINDERY_HOME/uv-tools" "$MDBINDERY_HOME/python"
  rmdir "$MDBINDERY_HOME" 2>/dev/null || true
  say "mdbindery removed from $MDBINDERY_HOME"
  exit 0
fi

if [[ -z "$UV" ]]; then
  say "getting uv $UV_VERSION ($UV_ASSET)"
  TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
  curl -fsSL --retry 3 -o "$TMP/uv.tgz" "https://github.com/astral-sh/uv/releases/download/$UV_VERSION/$UV_ASSET"
  [[ "$(sha256 "$TMP/uv.tgz")" == "$UV_SHA" ]] || die "checksum mismatch for $UV_ASSET"
  tar -xzf "$TMP/uv.tgz" -C "$TMP"
  mkdir -p "$MDBINDERY_HOME/uv"
  cp "$(find "$TMP" -type f -name uv | head -1)" "$MDBINDERY_HOME/uv/uv"
  chmod +x "$MDBINDERY_HOME/uv/uv"
  UV="$MDBINDERY_HOME/uv/uv"
fi

if [[ -n "$LOCAL" ]]; then
  SPEC="$(cd "$LOCAL" && pwd)"
else
  SPEC="mdbindery @ $REPO/archive/$REF.zip"
fi
say "installing mdbindery from ${LOCAL:-$REPO@$REF}"
LOG=$(mktemp)
if ! "$UV" tool install --force --python 3.12 "$SPEC" >"$LOG" 2>&1; then
  cat "$LOG" >&2; rm -f "$LOG"; die "uv could not install mdbindery"
fi
rm -f "$LOG"
MDB="$BIN_DIR/mdbindery"
[[ -x "$MDB" ]] || die "mdbindery was not installed into $BIN_DIR"

if [[ $NO_TOOLS == 0 ]]; then
  "$MDB" install-tools ${TOOLS_ARGS[@]+"${TOOLS_ARGS[@]}"}
fi

case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) say ""; say "add $BIN_DIR to your PATH, e.g.:"; say "  echo 'export PATH=\"$BIN_DIR:\$PATH\"' >> ~/.profile" ;;
esac
if [[ "$MDBINDERY_HOME" != "$DEFAULT_HOME" ]]; then
  say ""
  say "the tools are in $MDBINDERY_HOME; mdbindery finds them only with MDBINDERY_HOME set, e.g.:"
  say "  echo 'export MDBINDERY_HOME=\"$MDBINDERY_HOME\"' >> ~/.profile"
fi
say ""
say "done: run 'mdbindery doctor' to confirm, then 'mdbindery check <book-folder-or-repo-url>'"
