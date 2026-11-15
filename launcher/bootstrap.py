#!/usr/bin/env python3
"""Open the game's launcher, building it first when it does not exist yet.

There is one launcher: the one inside the game executable. Before the game has
been recompiled, the same executable is built as a "setup host": the launcher
without the game code, whose first-run wizard takes the disc and the BIOS and
runs the whole recompilation (generate, rebuild, relaunch) itself.

This script only covers the step before that: on a fresh checkout it installs
the portable toolchain (CMake, Clang, SDL3, Python) and compiles the setup
host, with a progress window or terminal output, then starts it. Afterwards it
just starts the executable. Launcher.sh (Linux) and Launcher.pyw (Windows) call
it; it uses only the Python standard library.

    python3 launcher/bootstrap.py                 open the launcher (build it if needed)
    python3 launcher/bootstrap.py --rebuild-launcher   rebuild the executable first

Other arguments are passed to the executable. RE3_TOOLCHAIN_ZIP points at an
already downloaded cmake-clang-v1 zip (Launcher.sh sets it when the machine has
no Python of its own).
"""

from __future__ import annotations

import collections
import json
import locale
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
CLI = ROOT / "psxrecomp" / "psxrecomp_cli.py"
GAME_TOML = ROOT / "game.toml"
BUILD_DIR = ROOT / "build-release"
GEN_MARKER = ROOT / "generated" / "SLUS_009.23_dispatch.c"
EXE_BASENAME = "Resident_Evil_3_Nemesis_USA_Recompiled"
CMAKE_TARGET = "psx-runtime"
IS_WINDOWS = sys.platform == "win32"
EXE_PATH = BUILD_DIR / (EXE_BASENAME + (".exe" if IS_WINDOWS else ""))
LOG_PATH = ROOT / "launcher" / "first_run.log"
ICON_PATH = ROOT / "psxrecomp" / "assets" / "psxrecomp.png"
DESKTOP_ID = "re3-nemesis-recompiled.desktop"
TITLE = "Resident Evil 3: Nemesis Recompiled"

STRINGS = {
    "en": {
        "intro": "First run: preparing the launcher. This happens once and takes a "
                 "few minutes.",
        "toolchain": "Downloading and checking the compiler…",
        "configure": "Configuring the build…",
        "build": "Compiling the launcher",
        "build_n": "Compiling the launcher ({done}/{total})",
        "starting": "Opening the launcher…",
        "failed": "The launcher could not be built: {error}\n\nThe full log is in {log}.",
        "cancelled": "Cancelled.",
        "old_python": "Python 3.11 or newer is required (found {ver}).",
        "press_enter": "Press Enter to close.",
    },
    "pt": {
        "intro": "Primeira execução: preparando o launcher. Isso acontece uma vez só e "
                 "leva alguns minutos.",
        "toolchain": "Baixando e verificando o compilador…",
        "configure": "Configurando o build…",
        "build": "Compilando o launcher",
        "build_n": "Compilando o launcher ({done}/{total})",
        "starting": "Abrindo o launcher…",
        "failed": "Não foi possível compilar o launcher: {error}\n\nO registro "
                  "completo está em {log}.",
        "cancelled": "Cancelado.",
        "old_python": "É preciso Python 3.11 ou mais novo (encontrado {ver}).",
        "press_enter": "Pressione Enter para fechar.",
    },
}


def detect_language() -> str:
    forced = os.environ.get("RE3_LAUNCHER_LANG", "").strip().lower()
    if forced in STRINGS:
        return forced
    if IS_WINDOWS:
        try:
            import ctypes

            lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            return "pt" if (lang_id & 0x3FF) == 0x16 else "en"
        except Exception:  # noqa: BLE001
            pass
    for value in (os.environ.get("LANG", ""), locale.getlocale()[0] or ""):
        if value.lower().startswith("pt"):
            return "pt"
    return "en"


LANG = detect_language()


def t(key: str, **fields: object) -> str:
    text = STRINGS[LANG].get(key) or STRINGS["en"][key]
    return text.format(**fields) if fields else text


# --------------------------------------------------------------------------
# Progress: a terminal line, a zenity window, or desktop notifications.
# --------------------------------------------------------------------------
class ConsoleUI:
    def __init__(self) -> None:
        self.tty = sys.stdout.isatty()
        self.last = ""

    def start(self) -> None:
        print(t("intro"), flush=True)

    def update(self, frac: float, text: str) -> bool:
        line = f"[{int(frac * 100):3d}%] {text}"
        if line != self.last:
            if self.tty:
                print("\r\033[K" + line, end="", flush=True)
            else:
                print(line, flush=True)
            self.last = line
        return True

    def done(self) -> None:
        if self.tty:
            print(flush=True)

    def error(self, message: str) -> None:
        if self.tty:
            print(flush=True)
        print(message, file=sys.stderr, flush=True)
        if IS_WINDOWS and sys.stdin and sys.stdin.isatty():
            try:
                input(t("press_enter"))
            except EOFError:
                pass


class ZenityUI:
    """GTK progress window for a launch without a terminal (desktop entry)."""

    def __init__(self, zenity: str) -> None:
        self.zenity = zenity
        self.proc: Optional[subprocess.Popen] = None

    def start(self) -> None:
        self.proc = subprocess.Popen(
            [self.zenity, "--progress", f"--title={TITLE}", f"--text={t('intro')}",
             "--percentage=0", "--auto-close", "--width=520"],
            stdin=subprocess.PIPE, text=True, stderr=subprocess.DEVNULL)

    def update(self, frac: float, text: str) -> bool:
        if self.proc is None or self.proc.poll() is not None:
            return False  # the window was closed: cancel
        try:
            assert self.proc.stdin is not None
            self.proc.stdin.write(f"{min(99, int(frac * 100))}\n# {text}\n")
            self.proc.stdin.flush()
        except (BrokenPipeError, OSError):
            return False
        return True

    def done(self) -> None:
        if self.proc and self.proc.poll() is None:
            try:
                assert self.proc.stdin is not None
                self.proc.stdin.write("100\n")
                self.proc.stdin.close()
            except (BrokenPipeError, OSError):
                pass
            self.proc.wait(timeout=5)

    def error(self, message: str) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
        subprocess.run([self.zenity, "--error", f"--title={TITLE}", "--width=520",
                        f"--text={message}"], stderr=subprocess.DEVNULL)


class NotifyUI:
    """Last resort without a terminal or zenity: start and failure notices."""

    def __init__(self) -> None:
        self.notify = shutil.which("notify-send")
        self.kdialog = shutil.which("kdialog")

    def _send(self, text: str) -> None:
        if self.notify:
            subprocess.run([self.notify, TITLE, text], stderr=subprocess.DEVNULL)

    def start(self) -> None:
        self._send(t("intro"))

    def update(self, frac: float, text: str) -> bool:
        return True

    def done(self) -> None:
        pass

    def error(self, message: str) -> None:
        if self.kdialog:
            subprocess.run([self.kdialog, "--title", TITLE, "--error", message],
                           stderr=subprocess.DEVNULL)
        else:
            self._send(message)
        print(message, file=sys.stderr)


def make_ui():
    if sys.stdout is not None and sys.stdout.isatty() or IS_WINDOWS:
        return ConsoleUI()
    zenity = shutil.which("zenity")
    if zenity and (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return ZenityUI(zenity)
    return NotifyUI()


# --------------------------------------------------------------------------
# Running the CLI steps.
# --------------------------------------------------------------------------
class Cancelled(Exception):
    pass


def run_cli(args: list[str], lo: float, hi: float, ui, log, label) -> None:
    cmd = [sys.executable, str(CLI), *args, "--json-progress"]
    log.write("> " + " ".join(cmd) + "\n")
    log.flush()
    env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
    kwargs = {"creationflags": 0x08000000} if IS_WINDOWS else {"start_new_session": True}
    proc = subprocess.Popen(cmd, cwd=str(ROOT), env=env, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            encoding="utf-8", errors="replace", **kwargs)
    error = ""
    frac = lo
    echoed: collections.deque[str] = collections.deque(maxlen=2000)
    assert proc.stdout is not None
    try:
        for raw in proc.stdout:
            line = raw.rstrip("\r\n")
            event = None
            if line.startswith("{"):
                try:
                    event = json.loads(line)
                except ValueError:
                    event = None
            if not isinstance(event, dict):
                # With --json-progress the CLI also prints each log message
                # as plain text right after its event; keep one copy.
                if line in echoed:
                    echoed.remove(line)
                else:
                    log.write(line + "\n")
                continue
            kind = event.get("event")
            if kind == "log":
                message = str(event.get("message", ""))
                echoed.extend(part for part in message.splitlines() if part.strip())
                log.write(message + "\n")
            elif kind == "error":
                error = str(event.get("message", ""))
                log.write("ERROR: " + error + "\n")
            elif kind == "phase":
                pct = event.get("pct")
                if isinstance(pct, (int, float)):
                    frac = max(frac, lo + (hi - lo) * float(pct))
            text = label(event)
            if not ui.update(frac, text):
                raise Cancelled()
    except Cancelled:
        kill(proc)
        raise
    code = proc.wait()
    log.flush()
    if code != 0:
        raise RuntimeError(error or f"{args[0]} exited with code {code}")


def kill(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    if IS_WINDOWS:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        import signal

        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
    proc.wait()


def build_launcher(ui) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("w", encoding="utf-8") as log:
        log.write(time.strftime("%Y-%m-%d %H:%M:%S") + " first-run bootstrap\n")
        common = ["--project-root", str(ROOT)]
        toolchain = ["ensure-toolchain", *common]
        zip_path = os.environ.get("RE3_TOOLCHAIN_ZIP", "").strip()
        if zip_path and Path(zip_path).is_file():
            toolchain += ["--from-zip", zip_path]
        run_cli(toolchain, 0.0, 0.08, ui, log, lambda e: t("toolchain"))

        rebuild = ["rebuild", *common, "--config", str(GAME_TOML), "--build-dir",
                   str(BUILD_DIR), "--target", CMAKE_TARGET, "--exe-basename",
                   EXE_BASENAME, "--no-pgo"]
        if not GEN_MARKER.is_file():
            # No game C yet: build the setup host. Its wizard generates the
            # game C and rebuilds the full executable in this same folder.
            rebuild += ["--cmake-extra=-DPSXRECOMP_REQUIRE_GAME_C=OFF"]

        def build_label(event: dict) -> str:
            if event.get("steps"):
                return t("build_n", done=event.get("step"), total=event.get("steps"))
            return t("build") if event.get("phase") == "build" else t("configure")

        run_cli(rebuild, 0.08, 1.0, ui, log, build_label)
    if not EXE_PATH.is_file():
        raise RuntimeError(f"{EXE_PATH} was not produced")


# --------------------------------------------------------------------------
# Desktop integration and launch.
# --------------------------------------------------------------------------
def desktop_quote(path: Path) -> str:
    text = str(path)
    for ch in ("\\", '"', "`", "$"):
        text = text.replace(ch, "\\" + ch)
    return '"' + text.replace("%", "%%") + '"'


def install_desktop_entry() -> None:
    """Applications-menu entry pointing at Launcher.sh (Linux)."""
    if not sys.platform.startswith("linux"):
        return
    data_home = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    entry = data_home / "applications" / DESKTOP_ID
    text = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={TITLE}\n"
        "Comment=Recompiled native port of Resident Evil 3: Nemesis (USA)\n"
        f"Exec={desktop_quote(ROOT / 'Launcher.sh')}\n"
        f"Path={ROOT}\n"
        f"Icon={ICON_PATH}\n"
        "Terminal=false\n"
        "Categories=Game;\n"
    )
    try:
        if entry.is_file() and entry.read_text(encoding="utf-8") == text:
            return
        entry.parent.mkdir(parents=True, exist_ok=True)
        entry.write_text(text, encoding="utf-8")
        entry.chmod(0o755)
    except OSError:
        pass  # a menu entry is a convenience; never block the launch on it


def launch(args: list[str]) -> int:
    if IS_WINDOWS:
        subprocess.Popen([str(EXE_PATH), *args], cwd=str(BUILD_DIR),
                         creationflags=0x00000008)  # DETACHED_PROCESS
        return 0
    os.chdir(BUILD_DIR)
    os.execv(str(EXE_PATH), [str(EXE_PATH), *args])
    return 0  # not reached


def main(argv: list[str]) -> int:
    if sys.version_info < (3, 11):
        print(t("old_python", ver=sys.version.split()[0]), file=sys.stderr)
        return 1
    rebuild = "--rebuild-launcher" in argv
    passthrough = [a for a in argv if a != "--rebuild-launcher"]
    if rebuild or not EXE_PATH.is_file():
        ui = make_ui()
        ui.start()
        try:
            build_launcher(ui)
        except Cancelled:
            print(t("cancelled"), file=sys.stderr)
            return 1
        except Exception as exc:  # noqa: BLE001
            ui.error(t("failed", error=exc, log=LOG_PATH))
            return 1
        ui.update(1.0, t("starting"))
        ui.done()
    install_desktop_entry()
    return launch(passthrough)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
