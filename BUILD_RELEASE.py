from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VERSION = "53"
APP_INTERNAL = "RpiMStudio"
APP_DISPLAY = "RπM Studio"
APP_CONSOLE = "RpiM Studio"


def run(cmd, *, shell=False):
    print("\n>", cmd if isinstance(cmd, str) else " ".join(map(str, cmd)))
    subprocess.run(cmd, cwd=ROOT, check=True, shell=shell)


def clean_build_dirs():
    for name in ("build", "dist", ".setupvenv", ".buildvenv"):
        p = ROOT / name
        if p.exists():
            shutil.rmtree(p, ignore_errors=True)
    (ROOT / "installer_output").mkdir(exist_ok=True)
    (ROOT / "release_output").mkdir(exist_ok=True)


def venv_python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def prepare_venv() -> Path:
    venv = ROOT / ".buildvenv"
    run([sys.executable, "-m", "venv", str(venv)])
    py = venv_python(venv)
    run([str(py), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"])
    run([str(py), "-m", "pip", "install", "-r", "requirements.txt", "pyinstaller>=6.15,<7"])
    return py


def pyinstaller_common(py: Path):
    cmd = [
        str(py), "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed",
        "--name", APP_INTERNAL,
        "--collect-all", "edge_tts",
        "--collect-all", "pygame",
        "--hidden-import", "pyttsx3.drivers",
        "main.py",
    ]
    if os.name == "nt":
        cmd += ["--hidden-import", "pyttsx3.drivers.sapi5"]
    elif sys.platform == "darwin":
        cmd += ["--hidden-import", "pyttsx3.drivers.nsss", "--osx-bundle-identifier", "com.rpimstudio.app"]
    run(cmd)


def find_iscc() -> Path | None:
    candidates = [
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("ProgramFiles", "")) / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("LocalAppData", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
    ]
    for p in candidates:
        if str(p) and p.is_file():
            return p
    return None


def build_windows(py: Path):
    pyinstaller_common(py)
    exe = ROOT / "dist" / APP_INTERNAL / f"{APP_INTERNAL}.exe"
    if not exe.is_file():
        raise RuntimeError(f"EXE oluşturulamadı: {exe}")

    iscc = find_iscc()
    if not iscc and shutil.which("winget"):
        print("Inno Setup bulunamadı; winget ile kuruluyor...")
        run(["winget", "install", "--id", "JRSoftware.InnoSetup", "-e",
             "--accept-source-agreements", "--accept-package-agreements", "--silent"])
        iscc = find_iscc()
    if not iscc:
        raise RuntimeError("Inno Setup 6 bulunamadı. Inno Setup kurup tekrar çalıştırın.")
    run([str(iscc), str(ROOT / "installer" / "RpiM_Studio.iss")])
    setup = ROOT / "installer_output" / f"RpiM_Studio_Setup_v{VERSION}.exe"
    if not setup.is_file():
        raise RuntimeError(f"Setup EXE bulunamadı: {setup}")
    print(f"\nWINDOWS HAZIR: {setup}")


def build_macos(py: Path):
    if shutil.which("hdiutil") is None:
        raise RuntimeError("hdiutil bulunamadı. DMG yalnızca macOS üzerinde üretilebilir.")
    pyinstaller_common(py)
    app = ROOT / "dist" / f"{APP_INTERNAL}.app"
    if not app.is_dir():
        raise RuntimeError(f".app oluşturulamadı: {app}")

    stage = ROOT / "build" / "dmg_stage"
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    shutil.copytree(app, stage / "RpiM Studio.app")
    applications = stage / "Applications"
    try:
        applications.symlink_to("/Applications")
    except Exception:
        pass
    dmg = ROOT / "release_output" / f"RpiM_Studio_v{VERSION}_macOS.dmg"
    if dmg.exists():
        dmg.unlink()
    run(["hdiutil", "create", "-volname", "RpiM Studio", "-srcfolder", str(stage),
         "-ov", "-format", "UDZO", str(dmg)])
    if not dmg.is_file():
        raise RuntimeError(f"DMG oluşturulamadı: {dmg}")
    print(f"\nMACOS HAZIR: {dmg}")


def main():
    system = platform.system()
    print("=" * 68)
    # Keep the console banner ASCII-safe on Windows code pages; the app itself stays RπM Studio.
    print(f"{APP_CONSOLE} v{VERSION} - Cross-platform Release Builder")
    print(f"Platform: {system} {platform.machine()}")
    print("=" * 68)
    if system not in {"Windows", "Darwin"}:
        raise SystemExit("Bu builder paket üretmek için Windows veya macOS üzerinde çalıştırılmalıdır.")
    clean_build_dirs()
    py = prepare_venv()
    if system == "Windows":
        build_windows(py)
    else:
        build_macos(py)


if __name__ == "__main__":
    main()
