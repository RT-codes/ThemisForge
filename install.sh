#!/bin/sh
# Installs Themis on Linux. Safe to run again: it is also how you repair an install.
#
#   curl -fsSL https://github.com/RT-codes/ThemisForge/releases/latest/download/install.sh | sh
#   curl -fsSL https://github.com/RT-codes/ThemisForge/releases/latest/download/install.sh | sh -s -- --port 8080
#
# Everything after `--` goes to `themis install` (see its --help: --host, --port, --https, --no-service, --channel...).
#
# All this script does is make sure `uv` is there (it fetches the right Python by itself), download the control file of the
# newest release, and run it. The control file (scripts/themisctl.py, plain Python, easy to read) does the installing.
set -eu

BASE="${THEMIS_INSTALL_BASE:-https://github.com/RT-codes/ThemisForge/releases/latest/download}"

main() {
  [ "$(uname -s)" = "Linux" ] || { echo "This installer is for Linux. Windows is coming; see https://github.com/RT-codes/ThemisForge" >&2; exit 1; }
  command -v curl >/dev/null 2>&1 || { echo "curl is needed to download Themis. Install it (for example: sudo apt install curl) and run this again." >&2; exit 1; }

  PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
  export PATH
  if ! command -v uv >/dev/null 2>&1; then
    echo "==> Installing uv (the Python tool Themis uses) from https://astral.sh/uv"
    curl -LsSf https://astral.sh/uv/install.sh | sh
  fi

  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT
  echo "==> Downloading the installer"
  curl -fsSL "$BASE/themisctl.py" -o "$tmp/themisctl.py"
  uv run --no-project --python 3.13 python "$tmp/themisctl.py" install "$@"
}

main "$@"
