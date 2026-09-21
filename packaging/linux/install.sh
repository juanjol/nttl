#!/usr/bin/env sh
# Install this NTTL build for the current user and register the systemd service.
set -eu

target="${NTTL_PREFIX:-$HOME/.local/share/nttl}"
bindir="${NTTL_BINDIR:-$HOME/.local/bin}"
here="$(cd "$(dirname "$0")" && pwd)"

echo "installing NTTL into $target"
mkdir -p "$target" "$bindir"
cp -a "$here/." "$target/"
ln -sf "$target/nttl" "$bindir/nttl"
ln -sf "$target/nttl-tray" "$bindir/nttl-tray"

echo "installed. next steps:"
echo "  $bindir/nttl web                 # run the interface now"
echo "  $bindir/nttl service install     # run it as a user service at boot"
