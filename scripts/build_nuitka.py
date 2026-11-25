"""Compile the portable application with Nuitka on the current platform."""

from pathlib import Path
import shutil
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
output = root / "dist"
args = [
    "--standalone",
    "--enable-plugin=pyside6",
    "--include-module=PySide6.QtSvg",
    "--include-data-dir=src=src",
    "--assume-yes-for-downloads",
    "--output-dir=dist",
]

qt_plugins = "sensible,multimedia,imageformats,iconengines"

if sys.platform == "darwin":
    args += ["--macos-create-app-bundle", "--macos-app-name=PyOverScreen"]
elif sys.platform == "win32":
    args += ["--msvc=latest", "--windows-console-mode=disable"]
elif sys.platform == "linux":
    args += ["--output-filename=PyOverScreen", "--include-package=Xlib"]

args.append(f"--include-qt-plugins={qt_plugins}")

subprocess.run(
    [sys.executable, "-m", "nuitka", *args, "PyOverScreen.py"],
    cwd=root,
    check=True,
)

if sys.platform != "darwin":
    package = output / "PyOverScreen"
    if package.exists():
        shutil.rmtree(package)
    (output / "PyOverScreen.dist").rename(package)
