#!/usr/bin/env python3
"""Setup and recompilation for Resident Evil 3: Nemesis (USA) Recompiled.

What it does:
  * takes the disc image and the BIOS, checks them against the expected dumps,
    and runs the whole recompilation (toolchain, generate, rebuild) with a
    progress bar. Adding both files starts the recompilation on its own;
  * starts the game. Settings, controls and mods live in the game's own
    launcher and in the F1 menu, not here.

Start it by double-clicking Launcher.pyw in the project root, or run
`python launcher/re3_launcher.py`. Only the Python standard library is used.
"""

from __future__ import annotations

import collections
import errno
import hashlib
import json
import locale
import os
import queue
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import tomllib
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# --------------------------------------------------------------------------
# Project layout. These names match CMakeLists.txt and codegen_setup.c.
# --------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
CLI = ROOT / "psxrecomp" / "psxrecomp_cli.py"
GAME_TOML = ROOT / "game.toml"
BUILD_DIR = ROOT / "build-release"
GENERATED_DIR = ROOT / "generated"
EXE_BASENAME = "Resident_Evil_3_Nemesis_USA_Recompiled"
CMAKE_TARGET = "psx-runtime"
GEN_MARKER = "SLUS_009.23_dispatch.c"
SHARD_GLOB = "SLUS_009.23_full_*.c"
BIOS_FILENAME = "SCPH1001.BIN"
# SHA-256 of the retail SCPH-1001 image this build is compiled against.
BIOS_SHA256 = "71af94d1e47a68c11e8fdb9f8368040601514a42a5a399cda48c7d3bff1e99d3"
BIOS_SIZE = 512 * 1024
STATE_PATH = ROOT / "launcher" / "state.json"
LOG_PATH = ROOT / "launcher" / "last_build.log"
SETTINGS_PATH = BUILD_DIR / "settings.toml"
ICON_PATH = ROOT / "psxrecomp" / "assets" / "psxrecomp.png"

IS_WINDOWS = sys.platform == "win32"
EXE_PATH = BUILD_DIR / (EXE_BASENAME + (".exe" if IS_WINDOWS else ""))
CREATE_NO_WINDOW = 0x08000000

# --------------------------------------------------------------------------
# Strings. Portuguese when the system UI language is Portuguese, else English.
# RE3_LAUNCHER_LANG=en|pt overrides the detection.
# --------------------------------------------------------------------------
STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "app_title": "Resident Evil 3: Nemesis Recompiler",
        "header_title": "RESIDENT EVIL 3: NEMESIS",
        "header_sub": "USA  ·  SLUS-00923  ·  disc setup and recompilation",
        "files_card": "Game files",
        "disc": "Disc",
        "bios": "BIOS",
        "choose": "Choose…",
        "files_hint": "Disc: a .cue with its .bin (recommended), a .bin or an .iso. "
                      "BIOS: SCPH-1001 (USA). Adding both starts the recompilation.",
        "not_selected": "No file chosen",
        "checking": "Checking…",
        "checking_pct": "Checking… {pct}%",
        "missing": "File not found",
        "disc_ok": "Verified dump (SHA-1 {sha})",
        "disc_iso": "ISO image: it cannot be verified, and it will be converted to "
                    "BIN during the recompilation",
        "disc_bad": "This is not the expected Resident Evil 3 (USA) dump",
        "disc_bad_cue": "The .bin named in this .cue was not found",
        "disc_bad_iso": "This file is not a valid ISO image",
        "disc_bad_type": "Unsupported format. Use .cue, .bin or .iso",
        "bios_ok": "SCPH-1001 (USA) verified",
        "bios_bad": "This is not the SCPH-1001 (USA) BIOS this build needs",
        "build_card": "Recompilation",
        "build_none": "The game has not been compiled yet.",
        "build_ok": "Compiled on {when}.",
        "build_ok_unknown": "Compiled and ready to play.",
        "date_format": "%Y-%m-%d %H:%M",
        "build_stale": "The chosen files changed since the last build. Recompile to use "
                       "them.",
        "build_need_files": "Choose a valid disc and BIOS to compile the game.",
        "build_close_game": "Close the game to recompile.",
        "recompile": "Recompile",
        "cancel": "Cancel",
        "log_placeholder": "The recompilation log shows up here.",
        "step_start": "Starting…",
        "step_toolchain": "Preparing the compiler",
        "step_verify": "Checking the disc",
        "step_prepare": "Preparing the disc image",
        "step_emitters": "Building the recompiler",
        "step_emitters_n": "Building the recompiler ({done}/{total})",
        "step_bios": "Recompiling the BIOS",
        "step_emit": "Recompiling the game code",
        "step_emit_n": "Recompiling the game code (part {done} of ~{total})",
        "step_build": "Compiling the executable",
        "step_build_n": "Compiling the executable ({done}/{total})",
        "step_finish": "Installing the BIOS and settings",
        "step_done": "Done. The game is ready to play.",
        "step_failed": "The recompilation failed: {error}",
        "step_failed_hint": "The full log is in {path}.",
        "step_cancelled": "Recompilation cancelled.",
        "elapsed": "{time} elapsed",
        "status_ready": "Ready",
        "status_needs_build": "Needs compiling",
        "status_building": "Compiling",
        "status_running": "Playing",
        "status_missing": "Files missing",
        "status_failed": "Build failed",
        "play": "PLAY",
        "open_folder": "Open game folder",
        "pick_disc_title": "Choose the Resident Evil 3 (USA) disc image",
        "pick_bios_title": "Choose the SCPH-1001 BIOS",
        "filetype_disc": "PlayStation disc images",
        "filetype_bios": "BIOS images",
        "filetype_all": "All files",
        "confirm_title": "Confirm",
        "confirm_quit_build": "A recompilation is running. Cancel it and quit?",
        "error_title": "Error",
        "game_missing": "The game executable was not found. Recompile first.",
        "launch_failed": "Could not start the game: {error}",
        "settings_note": "Settings, controls and mods are in the game's own launcher, and "
                         "in the F1 menu during play.",
    },
    "pt": {
        "app_title": "Recompilador de Resident Evil 3: Nemesis",
        "header_title": "RESIDENT EVIL 3: NEMESIS",
        "header_sub": "USA  ·  SLUS-00923  ·  instalação e recompilação",
        "files_card": "Arquivos do jogo",
        "disc": "Disco",
        "bios": "BIOS",
        "choose": "Escolher…",
        "files_hint": "Disco: um .cue com o .bin (recomendado), um .bin ou um .iso. "
                      "BIOS: SCPH-1001 (USA). Ao adicionar os dois, a recompilação "
                      "começa sozinha.",
        "not_selected": "Nenhum arquivo escolhido",
        "checking": "Verificando…",
        "checking_pct": "Verificando… {pct}%",
        "missing": "Arquivo não encontrado",
        "disc_ok": "Dump verificado (SHA-1 {sha})",
        "disc_iso": "Imagem ISO: não dá para verificar, e ela será convertida para "
                    "BIN na recompilação",
        "disc_bad": "Este não é o dump esperado de Resident Evil 3 (USA)",
        "disc_bad_cue": "O .bin indicado neste .cue não foi encontrado",
        "disc_bad_iso": "Este arquivo não é uma imagem ISO válida",
        "disc_bad_type": "Formato não suportado. Use .cue, .bin ou .iso",
        "bios_ok": "SCPH-1001 (USA) verificada",
        "bios_bad": "Esta não é a BIOS SCPH-1001 (USA) que o build precisa",
        "build_card": "Recompilação",
        "build_none": "O jogo ainda não foi compilado.",
        "build_ok": "Compilado em {when}.",
        "build_ok_unknown": "Compilado e pronto para jogar.",
        "date_format": "%d/%m/%Y às %H:%M",
        "build_stale": "Os arquivos escolhidos mudaram desde o último build. Recompile "
                       "para usá-los.",
        "build_need_files": "Escolha um disco e uma BIOS válidos para compilar o jogo.",
        "build_close_game": "Feche o jogo para recompilar.",
        "recompile": "Recompilar",
        "cancel": "Cancelar",
        "log_placeholder": "O registro da recompilação aparece aqui.",
        "step_start": "Iniciando…",
        "step_toolchain": "Preparando o compilador",
        "step_verify": "Verificando o disco",
        "step_prepare": "Preparando a imagem do disco",
        "step_emitters": "Compilando o recompilador",
        "step_emitters_n": "Compilando o recompilador ({done}/{total})",
        "step_bios": "Recompilando a BIOS",
        "step_emit": "Recompilando o código do jogo",
        "step_emit_n": "Recompilando o código do jogo (parte {done} de ~{total})",
        "step_build": "Compilando o executável",
        "step_build_n": "Compilando o executável ({done}/{total})",
        "step_finish": "Instalando a BIOS e as configurações",
        "step_done": "Pronto. O jogo já pode ser jogado.",
        "step_failed": "A recompilação falhou: {error}",
        "step_failed_hint": "O registro completo está em {path}.",
        "step_cancelled": "Recompilação cancelada.",
        "elapsed": "{time} decorridos",
        "status_ready": "Pronto",
        "status_needs_build": "Precisa compilar",
        "status_building": "Compilando",
        "status_running": "Em jogo",
        "status_missing": "Faltam arquivos",
        "status_failed": "Falha no build",
        "play": "JOGAR",
        "open_folder": "Abrir pasta do jogo",
        "pick_disc_title": "Escolha a imagem do disco de Resident Evil 3 (USA)",
        "pick_bios_title": "Escolha a BIOS SCPH-1001",
        "filetype_disc": "Imagens de disco do PlayStation",
        "filetype_bios": "Imagens de BIOS",
        "filetype_all": "Todos os arquivos",
        "confirm_title": "Confirmar",
        "confirm_quit_build": "Uma recompilação está em andamento. Cancelar e sair?",
        "error_title": "Erro",
        "game_missing": "O executável do jogo não foi encontrado. Recompile primeiro.",
        "launch_failed": "Não foi possível iniciar o jogo: {error}",
        "settings_note": "Configurações, controles e mods ficam no launcher do jogo e no "
                         "menu F1 durante o jogo.",
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


class Translator:
    def __init__(self, lang: str) -> None:
        self.table = STRINGS.get(lang, STRINGS["en"])

    def __call__(self, key: str, **fields: Any) -> str:
        text = self.table.get(key) or STRINGS["en"].get(key) or key
        return text.format(**fields) if fields else text


# --------------------------------------------------------------------------
# settings.toml: read with tomllib, write by replacing single keys in place
# so every value the launcher does not own survives untouched.
# --------------------------------------------------------------------------
_SECTION_RE = re.compile(r"^\s*\[([^\[\]]+)\]\s*(?:#.*)?$")
_KEY_RE = re.compile(r"^\s*([A-Za-z0-9_-]+)\s*=")


def toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    text = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'


def upsert_toml(text: str, updates: dict[str, dict[str, Any]]) -> str:
    """Set section.key = value for every entry, keeping all other lines."""
    pending = {section: dict(keys) for section, keys in updates.items()}
    out: list[str] = []
    current = ""
    last_content = -1

    def close_section() -> None:
        keys = pending.get(current)
        if keys:
            at = last_content + 1
            out[at:at] = [f"{k} = {toml_value(v)}" for k, v in keys.items()]
            keys.clear()

    for line in text.splitlines():
        header = _SECTION_RE.match(line)
        if header:
            close_section()
            current = header.group(1).strip()
            out.append(line)
            last_content = len(out) - 1
            continue
        key = _KEY_RE.match(line)
        if key and key.group(1) in pending.get(current, {}):
            value = pending[current].pop(key.group(1))
            out.append(f"{line[: line.index('=') + 1]} {toml_value(value)}")
            last_content = len(out) - 1
            continue
        out.append(line)
        if line.strip():
            last_content = len(out) - 1
    close_section()
    for section, keys in pending.items():
        if keys:
            if out and out[-1].strip():
                out.append("")
            out.append(f"[{section}]")
            out.extend(f"{k} = {toml_value(v)}" for k, v in keys.items())
    return "\n".join(out) + "\n"


class SettingsStore:
    HEADER = (
        "# psxrecomp user settings - written by the launcher. Safe to hand-edit.\n"
        "# Overrides the bundled game.toml; the command line overrides this file.\n"
    )

    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock = threading.Lock()
        self.parse_error = False

    def read(self) -> dict[str, Any]:
        with self.lock:
            self.parse_error = False
            try:
                with self.path.open("rb") as f:
                    return tomllib.load(f)
            except FileNotFoundError:
                return {}
            except (OSError, tomllib.TOMLDecodeError):
                self.parse_error = True
                return {}

    def update(self, updates: dict[str, dict[str, Any]]) -> None:
        """Write the keys in place. Raises on I/O or syntax problems."""
        with self.lock:
            try:
                text = self.path.read_text(encoding="utf-8")
            except FileNotFoundError:
                text = self.HEADER
            tomllib.loads(text)  # refuse to edit a broken file
            new_text = upsert_toml(text, updates)
            tomllib.loads(new_text)  # never write something the runtime cannot parse
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_name(self.path.name + ".tmp")
            tmp.write_text(new_text, encoding="utf-8", newline="\n")
            os.replace(tmp, self.path)


# --------------------------------------------------------------------------
# Launcher state (chosen files, hash cache, last build stamp).
# --------------------------------------------------------------------------
def load_state() -> dict[str, Any]:
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(state: dict[str, Any]) -> None:
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATE_PATH.with_name(STATE_PATH.name + ".tmp")
        tmp.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp, STATE_PATH)
    except OSError:
        pass


@dataclass
class DiscSpec:
    sizes: set[int] = field(default_factory=set)
    sha1: set[str] = field(default_factory=set)
    cue_name: str = "game.cue"
    out_dir: str = "disc"

    @property
    def prepared_cue(self) -> Path:
        return ROOT / self.out_dir / self.cue_name


def load_disc_spec() -> DiscSpec:
    try:
        with GAME_TOML.open("rb") as f:
            prep = tomllib.load(f).get("prepare_disc", {})
    except (OSError, tomllib.TOMLDecodeError):
        prep = {}
    return DiscSpec(
        sizes={int(x) for x in prep.get("known_sizes", [])},
        sha1={str(x).lower() for x in prep.get("known_sha1", [])},
        cue_name=str(prep.get("cue_name") or "game.cue"),
        out_dir=str(prep.get("out_dir") or "disc"),
    )


# --------------------------------------------------------------------------
# File checks (run on worker threads).
# --------------------------------------------------------------------------
@dataclass
class FileCheck:
    status: str  # "ok" | "iso" | "bad" | "missing" | "checking" | "none"
    message: str = ""
    identity: str = ""

    @property
    def usable(self) -> bool:
        return self.status in ("ok", "iso")


class HashCache:
    def __init__(self, state: dict[str, Any]) -> None:
        self.state = state
        self.lock = threading.Lock()

    def get(self, path: Path, algo: str) -> Optional[str]:
        try:
            st = path.stat()
        except OSError:
            return None
        with self.lock:
            entry = self.state.get("hash_cache", {}).get(str(path.resolve()))
        if (isinstance(entry, dict) and entry.get("size") == st.st_size
                and entry.get("mtime") == st.st_mtime_ns):
            return entry.get(algo)
        return None

    def put(self, path: Path, algo: str, digest: str) -> None:
        try:
            st = path.stat()
        except OSError:
            return
        with self.lock:
            cache = self.state.setdefault("hash_cache", {})
            key = str(path.resolve())
            entry = cache.get(key)
            if not (isinstance(entry, dict) and entry.get("size") == st.st_size
                    and entry.get("mtime") == st.st_mtime_ns):
                entry = {"size": st.st_size, "mtime": st.st_mtime_ns}
            entry[algo] = digest
            cache[key] = entry


def hash_file(path: Path, algo: str, on_progress: Optional[Callable[[int], None]] = None) -> str:
    digest = hashlib.new(algo)
    total = max(1, path.stat().st_size)
    done = 0
    last_pct = -1
    with path.open("rb") as f:
        while chunk := f.read(4 * 1024 * 1024):
            digest.update(chunk)
            done += len(chunk)
            pct = done * 100 // total
            if on_progress and pct != last_pct:
                last_pct = pct
                on_progress(pct)
    return digest.hexdigest()


def cue_data_file(cue: Path) -> Optional[Path]:
    try:
        text = cue.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for line in text.splitlines():
        m = re.match(r'^\s*FILE\s+(?:"(.+?)"|(\S+))\s+\S+', line, re.IGNORECASE)
        if m:
            return cue.parent / (m.group(1) or m.group(2))
    return None


def looks_like_iso(path: Path) -> bool:
    try:
        if path.stat().st_size % 2048:
            return False
        with path.open("rb") as f:
            f.seek(16 * 2048 + 1)
            return f.read(5) == b"CD001"
    except OSError:
        return False


def check_disc(path: Path, spec: DiscSpec, cache: HashCache, t: Translator,
               on_progress: Callable[[int], None]) -> FileCheck:
    if not path.is_file():
        return FileCheck("missing", t("missing"))
    ext = path.suffix.lower()
    if ext == ".iso":
        if not looks_like_iso(path):
            return FileCheck("bad", t("disc_bad_iso"))
        st = path.stat()
        return FileCheck("iso", t("disc_iso"),
                         f"iso:{path.resolve()}:{st.st_size}:{st.st_mtime_ns}")
    if ext == ".cue":
        data = cue_data_file(path)
        if data is None or not data.is_file():
            return FileCheck("bad", t("disc_bad_cue"))
    elif ext in (".bin", ".img"):
        data = path
    else:
        return FileCheck("bad", t("disc_bad_type"))
    if spec.sizes and data.stat().st_size not in spec.sizes:
        return FileCheck("bad", t("disc_bad"))
    sha1 = cache.get(data, "sha1")
    if sha1 is None:
        sha1 = hash_file(data, "sha1", on_progress)
        cache.put(data, "sha1", sha1)
    if spec.sha1 and sha1 not in spec.sha1:
        return FileCheck("bad", t("disc_bad"))
    return FileCheck("ok", t("disc_ok", sha=sha1[:10]), f"sha1:{sha1}")


def check_bios(path: Path, cache: HashCache, t: Translator) -> FileCheck:
    if not path.is_file():
        return FileCheck("missing", t("missing"))
    if path.stat().st_size != BIOS_SIZE:
        return FileCheck("bad", t("bios_bad"))
    digest = cache.get(path, "sha256")
    if digest is None:
        digest = hash_file(path, "sha256")
        cache.put(path, "sha256", digest)
    if digest != BIOS_SHA256:
        return FileCheck("bad", t("bios_bad"))
    return FileCheck("ok", t("bios_ok"), f"sha256:{digest}")


# --------------------------------------------------------------------------
# Recompilation pipeline: psxrecomp_cli.py steps with --json-progress.
# --------------------------------------------------------------------------
def python_for_children() -> str:
    """Console python.exe for the CLI, so its pipes behave like a terminal's."""
    exe = Path(sys.executable)
    if IS_WINDOWS and exe.name.lower() == "pythonw.exe":
        console = exe.with_name("python.exe")
        if console.exists():
            return str(console)
    return str(exe)


def child_popen_kwargs() -> dict[str, Any]:
    if IS_WINDOWS:
        return {"creationflags": CREATE_NO_WINDOW}
    return {"start_new_session": True}


def kill_tree(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    if IS_WINDOWS:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       creationflags=CREATE_NO_WINDOW)
    else:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass


@dataclass
class Step:
    key: str        # "toolchain" | "generate" | "build"
    args: list[str]
    lo: float       # slice of the overall bar
    hi: float


_NINJA_RE = re.compile(r"^\[(\d+)/(\d+)\]")
_SHARD_RE = re.compile(r"\bshard (\d+)\b", re.IGNORECASE)  # "Saved shard N" / "Shard N unchanged"


def classify_line(line: str) -> str:
    low = line.lower()
    if "error:" in low or "error " in low[:6] or "failed" in low or "fatal" in low:
        return "error"
    if "warning" in low:
        return "warn"
    return "info"


class BuildRunner:
    """Runs the CLI steps on a worker thread and posts UI events to a queue."""

    def __init__(self, post: Callable[[tuple], None], t: Translator) -> None:
        self.post = post
        self.t = t
        self.proc: Optional[subprocess.Popen] = None
        self.cancel_event = threading.Event()
        self.thread: Optional[threading.Thread] = None

    @property
    def running(self) -> bool:
        return self.thread is not None and self.thread.is_alive()

    def start(self, steps: list[Step], finalize: Callable[[], dict[str, Any]],
              expected_shards: int) -> None:
        self.cancel_event.clear()
        self.expected_shards = max(1, expected_shards)
        self.thread = threading.Thread(target=self._run, args=(steps, finalize),
                                       daemon=True)
        self.thread.start()

    def cancel(self) -> None:
        self.cancel_event.set()
        proc = self.proc
        if proc is not None:
            kill_tree(proc)

    # ---- worker thread -------------------------------------------------
    def _run(self, steps: list[Step], finalize: Callable[[], dict[str, Any]]) -> None:
        try:
            LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            log_file = LOG_PATH.open("w", encoding="utf-8")
        except OSError:
            log_file = None
        try:
            for step in steps:
                if self.cancel_event.is_set():
                    self.post(("cancelled",))
                    return
                ok, error = self._run_step(step, log_file)
                if self.cancel_event.is_set():
                    self.post(("cancelled",))
                    return
                if not ok:
                    self.post(("failed", error))
                    return
            self.post(("progress", 0.985, self.t("step_finish")))
            result = finalize()
            self.post(("progress", 1.0, self.t("step_done")))
            self.post(("done", result))
        except Exception as exc:  # noqa: BLE001
            self.post(("log", traceback.format_exc(), "error"))
            self.post(("failed", str(exc)))
        finally:
            if log_file is not None:
                log_file.close()

    def _run_step(self, step: Step, log_file) -> tuple[bool, str]:
        cmd = [python_for_children(), str(CLI), *step.args]
        self.post(("log", "> " + " ".join(cmd[1:]), "cmd"))
        if log_file:
            log_file.write("> " + " ".join(cmd) + "\n")
        env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
        self.proc = subprocess.Popen(
            cmd, cwd=str(ROOT), env=env, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", **child_popen_kwargs())
        self.post(("progress", step.lo, self._label(step, "", None)))
        mirrored: collections.deque[str] = collections.deque(maxlen=4000)
        state = {"phase": "", "error": ""}
        assert self.proc.stdout is not None
        for raw in self.proc.stdout:
            line = raw.rstrip("\r\n")
            event = None
            if line.startswith("{"):
                try:
                    event = json.loads(line)
                except ValueError:
                    event = None
            if isinstance(event, dict) and "event" in event:
                self._on_event(step, event, mirrored, state, log_file)
                continue
            # With --json-progress the CLI echoes each log message as plain
            # text after its JSON event. Drop those copies.
            if line in mirrored:
                mirrored.remove(line)
                continue
            if line.strip():
                if log_file:
                    log_file.write(line + "\n")
                self.post(("log", line, classify_line(line)))
        code = self.proc.wait()
        self.proc = None
        if code != 0:
            return False, state["error"] or f"exit code {code}"
        return True, ""

    def _on_event(self, step: Step, event: dict, mirrored, state, log_file) -> None:
        kind = event.get("event")
        if kind == "log":
            message = str(event.get("message", ""))
            for part in message.splitlines():
                if part.strip():
                    mirrored.append(part)
            if log_file:
                log_file.write(message + "\n")
            self.post(("log", message, classify_line(message)))
            self._progress_from_log(step, message, state)
        elif kind == "phase":
            state["phase"] = str(event.get("phase") or "")
            pct = event.get("pct")
            overall = None
            if isinstance(pct, (int, float)):
                overall = step.lo + (step.hi - step.lo) * float(pct)
            self.post(("progress", overall, self._label(step, state["phase"], event)))
        elif kind == "error":
            message = str(event.get("message", ""))
            state["error"] = message
            if log_file:
                log_file.write("ERROR: " + message + "\n")
            self.post(("log", message, "error"))

    def _progress_from_log(self, step: Step, message: str, state: dict) -> None:
        """Finer progress for the two long generate phases."""
        if step.key != "generate":
            return
        span = step.hi - step.lo
        m = _NINJA_RE.match(message)
        if m and state["phase"] == "emitters":
            done, total = int(m.group(1)), int(m.group(2))
            frac = 0.12 + 0.10 * done / max(1, total)
            self.post(("progress", step.lo + span * frac,
                       self.t("step_emitters_n", done=done, total=total)))
            return
        m = _SHARD_RE.search(message)
        if m and state["phase"] == "emit":
            done = int(m.group(1)) + 1
            total = self.expected_shards
            frac = 0.35 + 0.6 * min(1.0, done / total)
            self.post(("progress", step.lo + span * frac,
                       self.t("step_emit_n", done=done, total=total)))

    def _label(self, step: Step, phase: str, event: Optional[dict]) -> str:
        if step.key == "toolchain":
            return self.t("step_toolchain")
        if step.key == "build":
            if event and event.get("steps"):
                return self.t("step_build_n", done=event.get("step"), total=event.get("steps"))
            return self.t("step_build")
        return {
            "verify": self.t("step_verify"),
            "prepare_disc": self.t("step_prepare"),
            "emitters": self.t("step_emitters"),
            "bios": self.t("step_bios"),
            "emit": self.t("step_emit"),
        }.get(phase, self.t("step_emit") if phase == "done" else self.t("step_verify"))


# --------------------------------------------------------------------------
# Look and feel.
# --------------------------------------------------------------------------
BG = "#121316"
PANEL = "#1b1d22"
FIELD = "#24272e"
BORDER = "#2c3038"
BUTTON = "#2a2e36"
BUTTON_HOVER = "#353a44"
FG = "#e8e6e3"
MUTED = "#9a9fa8"
ACCENT = "#b3121b"
ACCENT_HOVER = "#d01f29"
ACCENT_DISABLED = "#4a2326"
OK = "#3fb950"
WARN = "#d29922"
BAD = "#f85149"
INFO = "#58a6ff"
PILL = {"ready": "#238636", "needs": "#9e6a03", "missing": "#9e6a03",
        "building": "#1f6feb", "running": "#8957e5", "failed": "#b62324"}


def enable_dpi_awareness() -> None:
    if not IS_WINDOWS:
        return
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:  # noqa: BLE001
        try:
            import ctypes

            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:  # noqa: BLE001
            pass


def dark_title_bar(root: tk.Tk) -> None:
    if not IS_WINDOWS:
        return
    try:
        import ctypes

        root.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        value = ctypes.c_int(1)
        for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (new, old)
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, attr, ctypes.byref(value), ctypes.sizeof(value)) == 0:
                break
    except Exception:  # noqa: BLE001
        pass


# --------------------------------------------------------------------------
# The window.
# --------------------------------------------------------------------------
class LauncherApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.t = Translator(detect_language())
        self.spec = load_disc_spec()
        self.state = load_state()
        self.cache = HashCache(self.state)
        self.settings = SettingsStore(SETTINGS_PATH)
        self.events: queue.Queue[tuple] = queue.Queue()
        self.runner = BuildRunner(self.events.put, self.t)
        self.game_proc: Optional[subprocess.Popen] = None
        self.external_running = exe_in_use()  # a game started elsewhere

        self.disc_path: Optional[Path] = None
        self.bios_path: Optional[Path] = None
        self.disc_check = FileCheck("none")
        self.bios_check = FileCheck("none")
        self.check_generation = {"disc": 0, "bios": 0}
        self.auto_build_pending = False
        self.build_started_at = 0.0
        self.last_failed = False

        scale = root.winfo_fpixels("1i") / 96.0
        self.px = lambda n: max(1, int(round(n * scale)))
        family = "Segoe UI" if IS_WINDOWS else "Helvetica"
        self.font = (family, 10)
        self.font_bold = (family, 10, "bold")
        self.font_small = (family, 9)
        self.font_title = (family, 20, "bold")
        self.font_card = (family, 11, "bold")
        self.font_mono = ("Consolas" if IS_WINDOWS else "Courier", 9)

        self._setup_window()
        self._setup_style()
        self._build_ui()
        self._restore_files()
        self._refresh_status()
        root.after(40, self._drain_events)
        root.after(1000, self._tick)

    def _save_state(self) -> None:
        with self.cache.lock:  # worker threads write the hash cache
            save_state(self.state)

    # ---- window and style ---------------------------------------------
    def _setup_window(self) -> None:
        root = self.root
        root.title(self.t("app_title"))
        root.configure(bg=BG)
        screen_w, screen_h = root.winfo_screenwidth(), root.winfo_screenheight()
        root.minsize(min(self.px(820), screen_w), min(self.px(560), screen_h - self.px(60)))
        width = min(self.px(980), screen_w - self.px(40))
        height = min(self.px(720), screen_h - self.px(90))
        root.geometry(f"{width}x{height}+{max(0, (screen_w - width) // 2)}"
                      f"+{max(0, (screen_h - height) // 3)}")
        if ICON_PATH.is_file():
            try:
                self.icon = tk.PhotoImage(file=str(ICON_PATH))
                root.iconphoto(True, self.icon)
            except tk.TclError:
                pass
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        root.option_add("*TCombobox*Listbox.background", FIELD)
        root.option_add("*TCombobox*Listbox.foreground", FG)
        dark_title_bar(root)

    def _setup_style(self) -> None:
        px = self.px
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(".", background=BG, foreground=FG, fieldbackground=FIELD,
                        bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER,
                        troughcolor=FIELD, focuscolor=BORDER, selectbackground=ACCENT,
                        selectforeground="#ffffff", font=self.font, insertcolor=FG)
        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=PANEL)
        style.configure("TLabel", background=BG, foreground=FG)
        style.configure("Muted.TLabel", background=BG, foreground=MUTED, font=self.font_small)
        style.configure("Title.TLabel", background=BG, foreground=FG, font=self.font_title)
        style.configure("Card.TLabel", background=PANEL, foreground=FG)
        style.configure("Strong.Card.TLabel", background=PANEL, foreground=FG, font=self.font_bold)
        style.configure("CardTitle.TLabel", background=PANEL, foreground=FG, font=self.font_card)
        style.configure("Muted.Card.TLabel", background=PANEL, foreground=MUTED, font=self.font_small)
        for name, color in (("Ok", OK), ("Warn", WARN), ("Bad", BAD), ("Info", INFO)):
            style.configure(f"{name}.Card.TLabel", background=PANEL, foreground=color,
                            font=self.font_small)
        style.layout("Dark.Vertical.TScrollbar", [
            ("Vertical.Scrollbar.trough", {"sticky": "ns", "children": [
                ("Vertical.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})]})])
        style.configure("Dark.Vertical.TScrollbar", background=BUTTON, troughcolor=PANEL,
                        bordercolor=PANEL, lightcolor=BUTTON, darkcolor=BUTTON,
                        gripcount=0, arrowsize=px(10))
        style.map("Dark.Vertical.TScrollbar",
                  background=[("disabled", PANEL), ("pressed", BUTTON_HOVER),
                              ("active", BUTTON_HOVER)],
                  lightcolor=[("disabled", PANEL)], darkcolor=[("disabled", PANEL)])
        style.configure("TButton", background=BUTTON, foreground=FG, borderwidth=0,
                        padding=(px(14), px(7)), focusthickness=0)
        style.map("TButton", background=[("disabled", PANEL), ("pressed", BORDER),
                                         ("active", BUTTON_HOVER)],
                  foreground=[("disabled", "#5d626b")])
        style.configure("Accent.TButton", background=ACCENT, foreground="#ffffff",
                        font=self.font_bold, padding=(px(18), px(8)))
        style.map("Accent.TButton", background=[("disabled", ACCENT_DISABLED),
                                                ("pressed", "#8f0e16"),
                                                ("active", ACCENT_HOVER)],
                  foreground=[("disabled", "#8d6a6c")])
        style.configure("Play.TButton", background=ACCENT, foreground="#ffffff",
                        font=(self.font[0], 13, "bold"), padding=(px(42), px(11)))
        style.map("Play.TButton", background=[("disabled", ACCENT_DISABLED),
                                              ("pressed", "#8f0e16"),
                                              ("active", ACCENT_HOVER)],
                  foreground=[("disabled", "#8d6a6c")])
        style.configure("TEntry", fieldbackground=FIELD, foreground=FG, borderwidth=0,
                        padding=(px(8), px(6)))
        style.map("TEntry", fieldbackground=[("readonly", FIELD)])
        style.configure("Horizontal.TProgressbar", background=ACCENT, troughcolor=FIELD,
                        bordercolor=FIELD, lightcolor=ACCENT, darkcolor=ACCENT,
                        thickness=px(8))
        style.configure("Ok.Horizontal.TProgressbar", background=OK, lightcolor=OK,
                        darkcolor=OK, troughcolor=FIELD, bordercolor=FIELD)
        style.configure("Bad.Horizontal.TProgressbar", background=BAD, lightcolor=BAD,
                        darkcolor=BAD, troughcolor=FIELD, bordercolor=FIELD)

    # ---- layout --------------------------------------------------------
    def _build_ui(self) -> None:
        px, t = self.px, self.t
        root = self.root
        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)

        header = ttk.Frame(root, padding=(px(24), px(18), px(24), px(10)))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text=t("header_title"), style="Title.TLabel").grid(
            row=0, column=0, sticky="w")
        ttk.Label(header, text=t("header_sub"), style="Muted.TLabel").grid(
            row=1, column=0, sticky="w")
        self.pill = tk.Label(header, text="", fg="#ffffff", bg=PILL["needs"],
                             font=self.font_bold, padx=px(12), pady=px(4))
        self.pill.grid(row=0, column=1, rowspan=2, sticky="e")

        page = ttk.Frame(root, style="Card.TFrame", padding=px(16))
        page.grid(row=1, column=0, sticky="nsew")
        self._build_page(page)

        footer = ttk.Frame(root, padding=(px(24), px(14)))
        footer.grid(row=2, column=0, sticky="ew")
        footer.columnconfigure(2, weight=1)
        self.open_button = ttk.Button(footer, text=t("open_folder"), command=self._open_folder)
        self.open_button.grid(row=0, column=0, sticky="w")
        ttk.Label(footer, text=t("settings_note"), style="Muted.TLabel",
                  wraplength=px(460), justify="left").grid(
            row=0, column=1, sticky="w", padx=(px(16), 0))
        self.play_button = ttk.Button(footer, text=t("play"), style="Play.TButton",
                                      command=self._play)
        self.play_button.grid(row=0, column=3, sticky="e")

    def _card(self, parent, title: str) -> ttk.Frame:
        card = ttk.Frame(parent, style="Card.TFrame", padding=(self.px(4), self.px(4)))
        ttk.Label(card, text=title, style="CardTitle.TLabel").grid(
            row=0, column=0, columnspan=4, sticky="w", pady=(0, self.px(10)))
        return card

    def _build_page(self, tab: ttk.Frame) -> None:
        px, t = self.px, self.t
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(1, weight=1)

        files = self._card(tab, t("files_card"))
        files.grid(row=0, column=0, sticky="ew")
        files.columnconfigure(1, weight=1)
        self.disc_var = tk.StringVar(value=t("not_selected"))
        self.bios_var = tk.StringVar(value=t("not_selected"))
        self.disc_status = ttk.Label(files, style="Muted.Card.TLabel")
        self.bios_status = ttk.Label(files, style="Muted.Card.TLabel")
        self.disc_button = ttk.Button(files, text=t("choose"), command=self._pick_disc)
        self.bios_button = ttk.Button(files, text=t("choose"), command=self._pick_bios)
        rows = ((t("disc"), self.disc_var, self.disc_button, self.disc_status),
                (t("bios"), self.bios_var, self.bios_button, self.bios_status))
        for i, (label, var, button, status) in enumerate(rows):
            r = 1 + i * 2
            ttk.Label(files, text=label, style="Strong.Card.TLabel", width=7).grid(
                row=r, column=0, sticky="w", pady=(px(2), 0))
            entry = ttk.Entry(files, textvariable=var, state="readonly")
            entry.grid(row=r, column=1, sticky="ew", padx=(0, px(8)))
            button.grid(row=r, column=2, sticky="e")
            status.grid(row=r + 1, column=1, columnspan=2, sticky="w",
                        pady=(px(3), px(10)))
        ttk.Label(files, text=t("files_hint"), style="Muted.Card.TLabel",
                  wraplength=px(820), justify="left").grid(
            row=5, column=0, columnspan=3, sticky="w")

        build = self._card(tab, t("build_card"))
        build.grid(row=1, column=0, sticky="nsew", pady=(px(22), 0))
        build.columnconfigure(0, weight=1)
        build.rowconfigure(5, weight=1)
        self.build_status = ttk.Label(build, style="Card.TLabel", wraplength=px(820),
                                      justify="left")
        self.build_status.grid(row=1, column=0, columnspan=3, sticky="w")
        buttons = ttk.Frame(build, style="Card.TFrame")
        buttons.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(px(10), px(10)))
        buttons.columnconfigure(2, weight=1)
        self.recompile_button = ttk.Button(buttons, text=t("recompile"), style="Accent.TButton",
                                           command=self._start_build)
        self.recompile_button.grid(row=0, column=0, sticky="w")
        self.cancel_button = ttk.Button(buttons, text=t("cancel"), command=self._cancel_build)
        self.cancel_button.grid(row=0, column=1, sticky="w", padx=(px(8), 0))
        self.elapsed_label = ttk.Label(buttons, style="Muted.Card.TLabel")
        self.elapsed_label.grid(row=0, column=2, sticky="e")
        self.progress = ttk.Progressbar(build, orient="horizontal", mode="determinate",
                                        maximum=1000)
        self.progress.grid(row=3, column=0, columnspan=3, sticky="ew")
        self.step_label = ttk.Label(build, style="Muted.Card.TLabel")
        self.step_label.grid(row=4, column=0, columnspan=3, sticky="w", pady=(px(4), px(8)))

        log_frame = ttk.Frame(build, style="Card.TFrame")
        log_frame.grid(row=5, column=0, columnspan=3, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log = tk.Text(log_frame, height=10, wrap="none", bg="#0d0e10", fg="#b9bec7",
                           insertbackground=FG, relief="flat", borderwidth=0,
                           highlightthickness=0, font=self.font_mono,
                           padx=px(10), pady=px(8))
        self.log.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview,
                               style="Dark.Vertical.TScrollbar")
        scroll.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=scroll.set)
        self.log.tag_configure("cmd", foreground=INFO)
        self.log.tag_configure("error", foreground=BAD)
        self.log.tag_configure("warn", foreground=WARN)
        self.log.tag_configure("ok", foreground=OK)
        self.log.tag_configure("muted", foreground="#5d626b")
        self.log.insert("end", t("log_placeholder") + "\n", "muted")
        self.log.configure(state="disabled")
        self.log_has_placeholder = True

    # ---- files ---------------------------------------------------------
    def _restore_files(self) -> None:
        doc = self.settings.read()
        disc_candidates = [self.state.get("disc"),
                           (doc.get("disc") or {}).get("path") if isinstance(doc.get("disc"), dict) else None,
                           str(self.spec.prepared_cue)]
        bios_candidates = [self.state.get("bios"),
                           (doc.get("bios") or {}).get("path") if isinstance(doc.get("bios"), dict) else None,
                           str(BUILD_DIR / "bios" / BIOS_FILENAME),
                           str(ROOT / "psxrecomp" / "bios" / BIOS_FILENAME)]
        for candidate in disc_candidates:
            if candidate and Path(candidate).is_file():
                self._set_disc(Path(candidate), user_pick=False)
                break
        for candidate in bios_candidates:
            if candidate and Path(candidate).is_file():
                self._set_bios(Path(candidate), user_pick=False)
                break

    def _initial_dir(self, current: Optional[Path]) -> str:
        if current and current.parent.is_dir():
            return str(current.parent)
        assets = ROOT / "assets"
        return str(assets if assets.is_dir() else ROOT)

    def _pick_disc(self) -> None:
        t = self.t
        name = filedialog.askopenfilename(
            parent=self.root, title=t("pick_disc_title"),
            initialdir=self._initial_dir(self.disc_path),
            filetypes=[(t("filetype_disc"), "*.cue *.bin *.iso *.img"),
                       (t("filetype_all"), "*.*")])
        if name:
            self._set_disc(Path(name), user_pick=True)

    def _pick_bios(self) -> None:
        t = self.t
        name = filedialog.askopenfilename(
            parent=self.root, title=t("pick_bios_title"),
            initialdir=self._initial_dir(self.bios_path),
            filetypes=[(t("filetype_bios"), "*.bin *.BIN *.rom"),
                       (t("filetype_all"), "*.*")])
        if name:
            self._set_bios(Path(name), user_pick=True)

    def _set_disc(self, path: Path, *, user_pick: bool) -> None:
        self.disc_path = path
        self.disc_var.set(str(path))
        if user_pick:
            self.state["disc"] = str(path)
            self._save_state()
            self.auto_build_pending = True
        self._run_check("disc")

    def _set_bios(self, path: Path, *, user_pick: bool) -> None:
        self.bios_path = path
        self.bios_var.set(str(path))
        if user_pick:
            self.state["bios"] = str(path)
            self._save_state()
            self.auto_build_pending = True
        self._run_check("bios")

    def _run_check(self, which: str) -> None:
        self.check_generation[which] += 1
        generation = self.check_generation[which]
        checking = FileCheck("checking", self.t("checking"))
        if which == "disc":
            self.disc_check = checking
            path = self.disc_path
        else:
            self.bios_check = checking
            path = self.bios_path
        self._show_check(which)
        self._refresh_status()

        def work() -> None:
            try:
                if which == "disc":
                    result = check_disc(
                        path, self.spec, self.cache, self.t,
                        lambda pct: self.events.put(("check_progress", which, generation, pct)))
                else:
                    result = check_bios(path, self.cache, self.t)
            except OSError as exc:
                result = FileCheck("bad", str(exc))
            self.events.put(("check", which, generation, result))

        threading.Thread(target=work, daemon=True).start()

    def _show_check(self, which: str) -> None:
        check = self.disc_check if which == "disc" else self.bios_check
        label = self.disc_status if which == "disc" else self.bios_status
        style = {"ok": "Ok", "iso": "Warn", "bad": "Bad", "missing": "Bad",
                 "checking": "Info"}.get(check.status, "Muted")
        text = check.message or self.t("not_selected")
        prefix = {"ok": "✓  ", "iso": "!  ", "bad": "✕  ", "missing": "✕  "}.get(check.status, "")
        label.configure(text=prefix + text, style=f"{style}.Card.TLabel")

    def _on_check_result(self, which: str, result: FileCheck) -> None:
        if which == "disc":
            self.disc_check = result
        else:
            self.bios_check = result
        self._show_check(which)
        self._save_state()  # keeps the hash cache
        if "checking" in (self.disc_check.status, self.bios_check.status):
            self._refresh_status()
            return
        self._adopt_existing_build()
        self._refresh_status()
        if self.auto_build_pending:
            self.auto_build_pending = False
            if (self.disc_check.usable and self.bios_check.usable
                    and self._build_state() in ("none", "stale")
                    and not self.runner.running and not self._game_running()):
                self._start_build()
            elif self._build_state() == "ready":
                self._point_settings_at_files()

    # ---- build state ---------------------------------------------------
    def _is_built(self) -> bool:
        return EXE_PATH.is_file() and (GENERATED_DIR / GEN_MARKER).is_file()

    def _build_state(self) -> str:
        if not self._is_built():
            return "none"
        stamp = self.state.get("build")
        if not isinstance(stamp, dict):
            return "ready"
        if self.disc_check.usable and stamp.get("disc") != self.disc_check.identity:
            return "stale"
        if self.bios_check.usable and stamp.get("bios") != self.bios_check.identity:
            return "stale"
        return "ready"

    def _adopt_existing_build(self) -> None:
        """A build made outside the launcher counts as built from these files."""
        if (self._is_built() and not isinstance(self.state.get("build"), dict)
                and self.disc_check.usable and self.bios_check.usable):
            self.state["build"] = {"disc": self.disc_check.identity,
                                   "bios": self.bios_check.identity,
                                   "time": EXE_PATH.stat().st_mtime}
            self._save_state()

    def _point_settings_at_files(self) -> None:
        """Same build, other copies of the files: make the game use them."""
        if self.bios_path and self.bios_check.usable:
            try:
                install_bios(self.bios_path)
            except OSError:
                pass
        updates: dict[str, dict[str, Any]] = {
            "bios": {"path": (BUILD_DIR / "bios" / BIOS_FILENAME).as_posix()}}
        if self.disc_path and self.disc_check.usable:
            updates["disc"] = {"path": self.disc_path.resolve().as_posix()}
        self._write_settings(updates)

    def _write_settings(self, updates: dict[str, dict[str, Any]]) -> None:
        try:
            self.settings.update(updates)
        except (OSError, tomllib.TOMLDecodeError) as exc:
            self._append_log([(f"settings.toml: {exc}", "warn")])

    def _refresh_status(self) -> None:
        t = self.t
        built = self._is_built()
        files_ok = self.disc_check.usable and self.bios_check.usable
        checking = "checking" in (self.disc_check.status, self.bios_check.status)
        state = self._build_state()
        if self._game_running():
            pill = ("running", t("status_running"))
        elif self.runner.running:
            pill = ("building", t("status_building"))
        elif self.last_failed and state != "ready":
            pill = ("failed", t("status_failed"))
        elif state == "ready":
            pill = ("ready", t("status_ready"))
        elif not files_ok and not checking:
            pill = ("missing", t("status_missing"))
        else:
            pill = ("needs", t("status_needs_build"))
        self.pill.configure(text=pill[1], bg=PILL[pill[0]])

        if not self.runner.running:
            if state == "ready":
                try:  # the exe itself: also counts builds made outside this app
                    when = EXE_PATH.stat().st_mtime
                except OSError:
                    when = None
                if when:
                    text = t("build_ok", when=time.strftime(t("date_format"),
                                                            time.localtime(when)))
                else:
                    text = t("build_ok_unknown")
            elif state == "stale":
                text = t("build_stale")
                if self._game_running():
                    text += " " + t("build_close_game")
            elif files_ok and self._game_running():
                text = t("build_close_game")
            elif files_ok or checking:
                text = t("build_none")
            else:
                text = t("build_need_files")
            self.build_status.configure(text=text)

        busy = self.runner.running or self._game_running()
        can_build = files_ok and not busy and not checking
        self.recompile_button.state(["!disabled"] if can_build else ["disabled"])
        self.cancel_button.state(["!disabled"] if self.runner.running else ["disabled"])
        for button in (self.disc_button, self.bios_button):
            button.state(["disabled"] if self.runner.running else ["!disabled"])
        play_ok = built and not busy
        self.play_button.state(["!disabled"] if play_ok else ["disabled"])

    # ---- recompilation -------------------------------------------------
    def _start_build(self) -> None:
        if self.runner.running or not (self.disc_path and self.bios_path):
            return
        if not (self.disc_check.usable and self.bios_check.usable):
            return
        self.external_running = self.game_proc is None and exe_in_use()
        if self._game_running():
            self._refresh_status()
            messagebox.showwarning(self.t("confirm_title"), self.t("build_close_game"),
                                   parent=self.root)
            return
        disc = self.disc_path.resolve()
        bios = self.bios_path.resolve()
        prepared_dir = (ROOT / self.spec.out_dir).resolve()
        common = ["--project-root", str(ROOT), "--json-progress"]
        generate = ["generate", *common, "--config", str(GAME_TOML), "--disc", str(disc),
                    "--bios", str(bios), "--gen-marker", GEN_MARKER]
        if self.disc_check.status == "iso":
            generate.append("--skip-hash-check")
        if disc.parent != prepared_dir:
            generate.append("--force-prepare")  # re-copy from the newly chosen dump
        steps = [
            Step("toolchain", ["ensure-toolchain", *common], 0.0, 0.04),
            Step("generate", generate, 0.04, 0.32),
            Step("build", ["rebuild", *common, "--config", str(GAME_TOML),
                           "--build-dir", str(BUILD_DIR), "--target", CMAKE_TARGET,
                           "--exe-basename", EXE_BASENAME, "--no-pgo"], 0.32, 0.98),
        ]
        identities = (self.disc_check.identity, self.bios_check.identity)
        prepared_cue = self.spec.prepared_cue

        def finalize() -> dict[str, Any]:
            install_bios(bios)
            disc_for_game = prepared_cue if prepared_cue.is_file() else disc
            self.settings.update({
                "bios": {"path": (BUILD_DIR / "bios" / BIOS_FILENAME).as_posix()},
                "disc": {"path": disc_for_game.as_posix()},
            })
            return {"disc": identities[0], "bios": identities[1], "time": time.time()}

        expected = len(list(GENERATED_DIR.glob(SHARD_GLOB))) or 200
        self._clear_log()
        self.last_failed = False
        self.progress.configure(style="Horizontal.TProgressbar", value=0)
        self.step_label.configure(text=self.t("step_start"), style="Muted.Card.TLabel")
        self.build_status.configure(text=self.t("status_building") + "…")
        self.build_started_at = time.monotonic()
        self.runner.start(steps, finalize, expected)
        self._refresh_status()

    def _cancel_build(self) -> None:
        if self.runner.running:
            self.runner.cancel()

    def _clear_log(self) -> None:
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        self.log_has_placeholder = False

    def _append_log(self, items: list[tuple[str, str]]) -> None:
        if not items:
            return
        at_bottom = self.log.yview()[1] >= 0.999
        self.log.configure(state="normal")
        if self.log_has_placeholder:
            self.log.delete("1.0", "end")
            self.log_has_placeholder = False
        for text, tag in items:
            self.log.insert("end", text + "\n", tag)
        lines = int(self.log.index("end-1c").split(".")[0])
        if lines > 6000:
            self.log.delete("1.0", f"{lines - 5000}.0")
        self.log.configure(state="disabled")
        if at_bottom:
            self.log.see("end")

    def _on_build_finished(self, kind: str, payload: Any) -> None:
        t = self.t
        if kind == "done":
            self.state["build"] = payload
            self._save_state()
            self.progress.configure(style="Ok.Horizontal.TProgressbar", value=1000)
            self.step_label.configure(text=t("step_done"), style="Ok.Card.TLabel")
            self._append_log([(t("step_done"), "ok")])
            self.last_failed = False
            self.root.bell()
        elif kind == "cancelled":
            self.step_label.configure(text=t("step_cancelled"), style="Warn.Card.TLabel")
            self._append_log([(t("step_cancelled"), "warn")])
        else:
            self.last_failed = True
            self.progress.configure(style="Bad.Horizontal.TProgressbar")
            message = t("step_failed", error=payload) + " " + t(
                "step_failed_hint", path=LOG_PATH.relative_to(ROOT).as_posix())
            self.step_label.configure(text=message, style="Bad.Card.TLabel",
                                      wraplength=self.px(820))
            self._append_log([(message, "error")])
        self._refresh_status()

    # ---- playing -------------------------------------------------------
    def _game_running(self) -> bool:
        own = self.game_proc is not None and self.game_proc.poll() is None
        return own or self.external_running

    def _play(self) -> None:
        """Start the game the normal way: its own launcher opens first."""
        if not EXE_PATH.is_file():
            messagebox.showerror(self.t("error_title"), self.t("game_missing"),
                                 parent=self.root)
            return
        env = dict(os.environ)
        env.pop("PSX_NO_LAUNCHER", None)
        try:
            self.game_proc = subprocess.Popen([str(EXE_PATH)], cwd=str(BUILD_DIR), env=env)
        except OSError as exc:
            messagebox.showerror(self.t("error_title"),
                                 self.t("launch_failed", error=exc), parent=self.root)
            return
        self._refresh_status()
        self.root.after(600, self.root.iconify)

    def _open_folder(self) -> None:
        folder = BUILD_DIR if BUILD_DIR.is_dir() else ROOT
        if IS_WINDOWS:
            os.startfile(str(folder))  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(folder)])
        else:
            subprocess.Popen(["xdg-open", str(folder)])

    # ---- event loop ----------------------------------------------------
    def _drain_events(self) -> None:
        logs: list[tuple[str, str]] = []
        last_progress = None
        try:
            for _ in range(2000):
                event = self.events.get_nowait()
                kind = event[0]
                if kind == "log":
                    for part in str(event[1]).splitlines() or [""]:
                        logs.append((part, event[2]))
                elif kind == "progress":
                    last_progress = event
                elif kind == "check_progress":
                    _, which, generation, pct = event
                    if generation == self.check_generation[which]:
                        label = self.disc_status if which == "disc" else self.bios_status
                        label.configure(text=self.t("checking_pct", pct=pct),
                                        style="Info.Card.TLabel")
                elif kind == "check":
                    _, which, generation, result = event
                    if generation == self.check_generation[which]:
                        self._on_check_result(which, result)
                elif kind in ("done", "failed", "cancelled"):
                    self._append_log(logs)
                    logs = []
                    if last_progress:
                        self._apply_progress(last_progress)
                        last_progress = None
                    self._on_build_finished(kind, event[1] if len(event) > 1 else None)
        except queue.Empty:
            pass
        self._append_log(logs)
        if last_progress:
            self._apply_progress(last_progress)
        self.root.after(40, self._drain_events)

    def _apply_progress(self, event: tuple) -> None:
        _, value, label = event
        if value is not None:
            self.progress.configure(value=int(max(0.0, min(1.0, value)) * 1000))
        if label:
            self.step_label.configure(text=label, style="Muted.Card.TLabel")

    def _tick(self) -> None:
        if self.runner.running:
            secs = int(time.monotonic() - self.build_started_at)
            self.elapsed_label.configure(
                text=self.t("elapsed", time=f"{secs // 60:02d}:{secs % 60:02d}"))
        was_running = self._game_running()
        if self.game_proc is not None and self.game_proc.poll() is not None:
            self.game_proc = None
            self.root.deiconify()
        # The linker holds the file open during a build; skip the probe then.
        if self.game_proc is None and not self.runner.running:
            self.external_running = exe_in_use()
        if was_running != self._game_running():
            self._refresh_status()
        self.root.after(1000, self._tick)

    def _on_close(self) -> None:
        if self.runner.running:
            if not messagebox.askyesno(self.t("confirm_title"),
                                       self.t("confirm_quit_build"), parent=self.root):
                return
            self.runner.cancel()
            deadline = time.monotonic() + 5
            while self.runner.running and time.monotonic() < deadline:
                time.sleep(0.1)
        self._save_state()
        self.root.destroy()


def exe_in_use() -> bool:
    """True while the game executable runs, whoever started it.

    Windows refuses to open a running image for writing, and Linux reports
    ETXTBSY. Either way the build could not replace the file.
    """
    if not EXE_PATH.is_file():
        return False
    try:
        with open(EXE_PATH, "r+b"):
            return False
    except PermissionError:
        return True
    except OSError as exc:
        return exc.errno == errno.ETXTBSY


def install_bios(bios: Path) -> None:
    """Copy the BIOS next to the executable, where the game looks for it."""
    dest = BUILD_DIR / "bios" / BIOS_FILENAME
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not (dest.exists() and dest.resolve() == bios.resolve()):
        shutil.copy2(bios, dest)


def main() -> None:
    enable_dpi_awareness()
    root = tk.Tk()
    try:
        LauncherApp(root)
    except Exception:  # noqa: BLE001
        root.withdraw()
        messagebox.showerror("Launcher", traceback.format_exc())
        raise
    root.mainloop()


if __name__ == "__main__":
    main()
