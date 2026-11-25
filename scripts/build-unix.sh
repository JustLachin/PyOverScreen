#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

case "$(uname -m)" in
    x86_64) arch=x64 ;;
    aarch64|arm64) arch=arm64 ;;
    *) echo "Unsupported build architecture." >&2; exit 1 ;;
esac

python scripts/build_nuitka.py
mkdir -p artifacts

case "$(uname -s)" in
    Linux)
        archive="PyOverScreen-linux-$arch.tar.gz"
        tar -czf "artifacts/$archive" -C dist PyOverScreen
        (cd artifacts && sha256sum "$archive" > "$archive.sha256")
        ;;
    Darwin)
        archive="PyOverScreen-macos-$arch.zip"
        rm -f "artifacts/$archive"
        ditto -c -k --sequesterRsrc --keepParent dist/PyOverScreen.app "artifacts/$archive"
        (cd artifacts && shasum -a 256 "$archive" > "$archive.sha256")
        ;;
    *)
        echo "This build script requires Linux or macOS." >&2
        exit 1
        ;;
esac
