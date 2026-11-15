"""Double-click to open the Resident Evil 3: Nemesis (USA) Recompiled launcher.

The launcher is the one inside the game executable. On the first run this
builds it (a console window shows the progress) and then opens it; its setup
wizard takes the disc and the BIOS and recompiles the game. On Linux, use
Launcher.sh. Needs Python 3.11 or newer; no extra packages.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BOOTSTRAP = ROOT / "launcher" / "bootstrap.py"
IS_WINDOWS = sys.platform == "win32"


def message(text: str) -> None:
    if IS_WINDOWS:
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, text, "Launcher", 0x10)
    else:
        print(text, file=sys.stderr)


if sys.version_info < (3, 11):
    message("This launcher needs Python 3.11 or newer.\n"
            f"Found Python {sys.version.split()[0]}.")
    sys.exit(1)

if IS_WINDOWS:
    # pythonw has no console; run the bootstrap with python.exe in a new
    # console so the first-run build shows its progress.
    exe = Path(sys.executable)
    console = exe.with_name("python.exe") if exe.name.lower() == "pythonw.exe" else exe
    if not console.exists():
        console = exe
    exe_path = ROOT / "build-release" / "Resident_Evil_3_Nemesis_USA_Recompiled.exe"
    if exe_path.is_file():
        subprocess.Popen([str(exe_path), *sys.argv[1:]], cwd=str(exe_path.parent))
    else:
        subprocess.Popen([str(console), str(BOOTSTRAP), *sys.argv[1:]], cwd=str(ROOT),
                         creationflags=subprocess.CREATE_NEW_CONSOLE)
    sys.exit(0)

sys.path.insert(0, str(BOOTSTRAP.parent))
import bootstrap  # noqa: E402

sys.exit(bootstrap.main(sys.argv[1:]))
