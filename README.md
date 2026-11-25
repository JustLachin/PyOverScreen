# PyOverScreen
[👉👉👉DOWNLOAD .EXE HERE!!! CLICK HERE!!! NO PYTHON NEEDED!👈👈👈](https://github.com/JustLachin/PyOverScreen/releases/download/v1/PyOverScreen.zip)

PyOverScreen is a powerful overlay management tool built with PySide6. It allows you to create, manage, and customize multiple overlays on your screen with ease.

## Features:
- Create multiple independent overlays.
- Customize position, size, scale, and opacity.
- Support for URLs, local images, GIFs, and Videos.
- Lock/Unlock overlays for interaction or click-through.
- Save and load profiles.
- Target individual windows on Windows and X11. Fullscreen stacking depends on the window manager.

## Installation
1. Install Python 3.10+
2. Install dependencies:
   ```bash
   python -m pip install -r requirements.txt
   ```

## Running the App
```bash
python PyOverScreen.py
```

## Linux sessions

- **X11** supports overlay positioning, click-through, and targeting windows
  listed by an EWMH-compatible window manager. Transparency needs a compositor.
- **Wayland** delegates global positioning and stacking to the compositor. On KDE
  Plasma, use KWin window rules for position and Keep Above if the compositor
  allows them. For X11 controls on a Wayland session, run
  `./PyOverScreen/PyOverScreen --x11` after extracting the archive.
  XWayland window targeting sees X11 clients. Native Wayland clients are managed
  by the compositor, and fullscreen stacking over them is compositor-dependent.

## Desktop packages

| Platform | Architectures | Package |
| --- | --- | --- |
| Windows | x64 | ZIP containing `PyOverScreen/PyOverScreen.exe` |
| Linux | x64, ARM64 | TAR.GZ containing `PyOverScreen/PyOverScreen` |
| macOS | Intel x64, Apple Silicon ARM64 | ZIP containing `PyOverScreen.app` |

Extract the entire archive before launching. The portable packages include
Python and Qt. The Linux builds target Ubuntu 22.04 or newer on x64 and Ubuntu
24.04 or newer on ARM64, with equivalent glibc and system libraries on other
distributions. Global overlay placement on Linux depends on the window manager
or Wayland compositor. The macOS app is built without Apple notarization.

### Building locally

The portable builds use Nuitka. Use Python 3.13 for the target architecture and install the build dependencies
with `python -m pip install -r requirements-build.txt`. Run
`./scripts/build-windows.ps1` in PowerShell 7 on Windows or
`bash scripts/build-unix.sh` on Linux or macOS. The package and its SHA-256 file
are written to `artifacts/`. Linux uses GCC and `patchelf`, Windows uses MSVC, and macOS uses the Xcode command-line tools.

## Publishing a GitHub release

1. Open a successful **Build Release Artifacts** run for the current commit on
   `main`. Its run ID is the last number in its URL. You can also build manually
   from `main`.
2. Run **Publish Release** from `main` with mode `validate`, that run ID, and
   a new tag such as `v1.1.0` or `v1.1.0-rc.1`.
3. Run **Publish Release** again with mode `publish` and the same inputs. It
   verifies the build again and publishes the desktop archives, their SHA-256 files, and
   generated release notes. The tag points to the commit that produced the build.

For an approval step, configure required reviewers and restrict deployments to
`main` in the repository's `release` environment. If an interrupted upload leaves
a draft, inspect the draft before retrying with the same tag.

## License
MIT License. Use at your own risk.
