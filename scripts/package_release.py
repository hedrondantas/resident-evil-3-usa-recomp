#!/usr/bin/env python3
"""Package a ready-to-run setup-host release (Linux .tar.gz, Windows .zip).

The archive holds the project sources plus a prebuilt *setup host*: the game
executable built without any game code or BIOS code. Players open it and its
first-run wizard downloads the toolchain, takes their own disc and BIOS,
generates the game C and rebuilds the full game on their machine. So nobody
compiles the launcher first, and Windows players need no Python.

    python scripts/package_release.py --build            build the setup host, then package
    python scripts/package_release.py                    package an existing --build-dir

Gates (the script refuses to package otherwise):
  * the build must be a setup host: CMake cache FORCE_SETUP_HOST=ON and no
    recompiled game function (func_8xxxxxxx) in the executable's symbols. A
    full build contains the game's code and must never be distributed;
  * the executable may only depend on libraries every desktop has (glibc,
    libstdc++, libGL on Linux; Windows system DLLs);
  * --version, when given (CI passes the tag), must match the VERSION file.

Only the Python standard library is used.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
CLI = ROOT / "psxrecomp" / "psxrecomp_cli.py"
EXE_BASENAME = "Resident_Evil_3_Nemesis_USA_Recompiled"
CMAKE_TARGET = "psx-runtime"
ARCHIVE_PREFIX = "Resident_Evil_3_Nemesis_USA_Recompiled"
GAME_SYMBOL = re.compile(rb"\bfunc_8[0-9A-Fa-f]{7}\b")

# Files the build stages next to the executable that the setup host needs at
# run time. Everything else in the build dir is CMake state or per-user data.
STAGED_RUNTIME = ("game.toml", "psx_game_version.txt", "assets", "mods")
NEVER_SHIP = {"state.toml", "settings.toml", "keybinds.ini", "input.ini", "config.ini",
              "bios.cfg", "disc.cfg", "rom.cfg", "psx_last_run_report.json"}

LINUX_ALLOWED_NEEDED = {
    "libc.so.6", "libm.so.6", "libdl.so.2", "libpthread.so.0", "librt.so.1",
    "libstdc++.so.6", "libgcc_s.so.1", "libGL.so.1", "ld-linux-x86-64.so.2",
}
WINDOWS_ALLOWED_DLLS = {
    "kernel32.dll", "user32.dll", "gdi32.dll", "winmm.dll", "imm32.dll", "ole32.dll",
    "oleaut32.dll", "version.dll", "uuid.dll", "advapi32.dll", "setupapi.dll",
    "shell32.dll", "shlwapi.dll", "dinput8.dll", "comdlg32.dll", "comctl32.dll",
    "opengl32.dll", "ws2_32.dll", "iphlpapi.dll", "bcrypt.dll", "crypt32.dll",
    "dwmapi.dll", "dbghelp.dll", "hid.dll", "cfgmgr32.dll", "ucrtbase.dll",
    "msvcrt.dll", "ntdll.dll", "psapi.dll", "secur32.dll", "userenv.dll",
    "winhttp.dll", "wininet.dll", "dxgi.dll", "d3d11.dll", "d3d12.dll", "xinput1_4.dll",
    "powrprof.dll", "mswsock.dll", "normaliz.dll", "wldap32.dll", "rpcrt4.dll",
}


def fail(message: str) -> None:
    print(f"package_release: error: {message}", file=sys.stderr)
    sys.exit(1)


def host_platform() -> str:
    if sys.platform == "win32":
        return "windows-x64"
    if sys.platform.startswith("linux"):
        return "linux-x64"
    fail(f"unsupported platform {sys.platform}")
    return ""


def exe_name(platform: str) -> str:
    return EXE_BASENAME + (".exe" if platform.startswith("windows") else "")


def run(cmd: list[str]) -> None:
    print("> " + " ".join(cmd), flush=True)
    if subprocess.run(cmd, cwd=str(ROOT)).returncode != 0:
        fail(f"command failed: {cmd[2] if len(cmd) > 2 else cmd[0]}")


def build_setup_host(build_dir: Path) -> None:
    """Same commands as launcher/bootstrap.py, forced into setup-host mode."""
    py = sys.executable
    run([py, str(CLI), "ensure-toolchain", "--project-root", str(ROOT)])
    run([py, str(CLI), "rebuild", "--project-root", str(ROOT), "--config",
         str(ROOT / "game.toml"), "--build-dir", str(build_dir), "--target", CMAKE_TARGET,
         "--exe-basename", EXE_BASENAME, "--no-pgo",
         "--cmake-extra=-DPSXRECOMP_FORCE_SETUP_HOST=ON",
         "--cmake-extra=-DPSXRECOMP_ALLOW_NO_BIOS=ON",
         "--cmake-extra=-DPSXRECOMP_REQUIRE_GAME_C=OFF"])


C_LOCALE = dict(os.environ, LC_ALL="C", LANG="C")  # tool output is parsed in English


def toolchain_tool(name: str) -> Optional[str]:
    """llvm-* from the portable pack (installed by ensure-toolchain), else PATH."""
    sys.path.insert(0, str(ROOT / "psxrecomp" / "tools"))
    try:
        from toolchain_pack import resolve_toolchain_bin  # type: ignore

        bin_dir = resolve_toolchain_bin(ROOT)
    except Exception:  # noqa: BLE001
        bin_dir = None
    suffix = ".exe" if sys.platform == "win32" else ""
    if bin_dir and (Path(bin_dir) / (name + suffix)).is_file():
        return str(Path(bin_dir) / (name + suffix))
    return shutil.which(name)


# --------------------------------------------------------------------------
# Gates.
# --------------------------------------------------------------------------
def gate_setup_host(build_dir: Path, exe: Path) -> None:
    cache = build_dir / "CMakeCache.txt"
    if not cache.is_file():
        fail(f"{cache} not found: build with --build first")
    text = cache.read_text(encoding="utf-8", errors="replace")
    if not re.search(r"^PSXRECOMP_FORCE_SETUP_HOST:BOOL=ON$", text, re.M):
        fail(f"{build_dir} is not a setup-host build (PSXRECOMP_FORCE_SETUP_HOST is not "
             "ON). A full build contains the game's code and must not be packaged.")
    # Platform-independent: a full build compiles generated/ (game and BIOS C).
    # Checked on build files because a Windows .exe may carry no symbol table.
    ninja = build_dir / "build.ninja"
    if not ninja.is_file():
        fail(f"{ninja} not found")
    if re.search(r"generated[/\\][^\s]*\.c\b", ninja.read_text(encoding="utf-8",
                                                                errors="replace")):
        fail(f"{build_dir} compiles sources from generated/ (game or BIOS code). "
             "Refusing to package it.")
    gen_list = build_dir / f"{CMAKE_TARGET}_generated_sources.txt"
    if gen_list.is_file() and gen_list.read_text(encoding="utf-8").strip():
        fail(f"{gen_list} lists generated game sources. Refusing to package them.")
    nm = toolchain_tool("llvm-nm")
    if nm:
        out = subprocess.run([nm, "--defined-only", str(exe)], capture_output=True,
                             env=C_LOCALE)
        if out.returncode != 0:
            fail(f"llvm-nm could not read {exe}")
        hits = len(GAME_SYMBOL.findall(out.stdout))
    else:  # no nm: scan the binary itself (symbol names are stored as text)
        hits = len(GAME_SYMBOL.findall(exe.read_bytes()))
    if hits:
        fail(f"{exe} contains {hits} recompiled game functions. Refusing to package "
             "game code.")
    print("gate: setup host, no game code")


def gate_dependencies(exe: Path, platform: str) -> None:
    if platform.startswith("linux"):
        tool = toolchain_tool("llvm-readelf") or shutil.which("readelf")
        if not tool:
            fail("readelf not found to check the executable's libraries")
        out = subprocess.run([tool, "-d", str(exe)], capture_output=True, text=True,
                             env=C_LOCALE).stdout
        needed = set(re.findall(r"\(NEEDED\)\s+Shared library: \[([^\]]+)\]", out))
        bad = sorted(needed - LINUX_ALLOWED_NEEDED)
    else:
        tool = toolchain_tool("llvm-objdump") or shutil.which("objdump")
        if not tool:
            fail("objdump not found to check the executable's DLLs")
        out = subprocess.run([tool, "-p", str(exe)], capture_output=True, text=True,
                             env=C_LOCALE).stdout
        needed = {d.lower() for d in re.findall(r"DLL Name:\s*(\S+)", out)}
        bad = sorted(d for d in needed
                     if d not in WINDOWS_ALLOWED_DLLS and not d.startswith("api-ms-win-"))
    if not needed:
        fail(f"could not read the libraries of {exe}")
    if bad:
        fail(f"{exe.name} needs libraries players may not have: {', '.join(bad)}")
    print("gate: libraries ok (" + ", ".join(sorted(needed)) + ")")


def gate_version(version: str) -> str:
    pinned = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    if version and version.lstrip("v") != pinned:
        fail(f"version {version} does not match VERSION ({pinned})")
    return pinned


# --------------------------------------------------------------------------
# Staging and archiving.
# --------------------------------------------------------------------------
def tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=str(ROOT), capture_output=True)
    if out.returncode != 0:
        fail("git ls-files failed (run from a git checkout)")
    return [p for p in out.stdout.decode("utf-8").split("\0") if p]


def stage(build_dir: Path, exe: Path, platform: str, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    for rel in tracked_files():
        src = ROOT / rel
        if not src.is_file():  # deleted in the working tree
            continue
        out = dest / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, out)
    out_build = dest / "build-release"
    out_build.mkdir(parents=True, exist_ok=True)
    shutil.copy2(exe, out_build / exe.name)
    for name in STAGED_RUNTIME:
        src = build_dir / name
        if src.is_dir():
            shutil.copytree(src, out_build / name, ignore=lambda d, names: [
                n for n in names if n in NEVER_SHIP])
        elif src.is_file():
            shutil.copy2(src, out_build / name)
    if platform.startswith("linux"):
        for rel in ("Launcher.sh", "build-release/" + exe.name):
            (dest / rel).chmod(0o755)


def write_archive(staged: Path, platform: str, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    if platform.startswith("linux"):
        archive = out_dir / (staged.name + ".tar.gz")
        with tarfile.open(archive, "w:gz") as tar:  # keeps the executable bits
            tar.add(staged, arcname=staged.name)
    else:
        archive = out_dir / (staged.name + ".zip")
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
            for path in sorted(staged.rglob("*")):
                if path.is_file():
                    zf.write(path, Path(staged.name) / path.relative_to(staged))
    return archive


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--build", action="store_true",
                        help="build the setup host into --build-dir first")
    parser.add_argument("--build-dir", default=str(ROOT / "build-setup"))
    parser.add_argument("--platform", default="", help="linux-x64 or windows-x64 "
                        "(default: this machine)")
    parser.add_argument("--version", default="", help="expected version (vX.Y.Z tag)")
    parser.add_argument("--out", default=str(ROOT / "dist"))
    args = parser.parse_args()

    platform = args.platform or host_platform()
    version = gate_version(args.version)
    build_dir = Path(args.build_dir).resolve()
    if build_dir == (ROOT / "build-release").resolve():
        fail("build-release holds your own game build; use a separate --build-dir")
    if args.build:
        build_setup_host(build_dir)
    exe = build_dir / exe_name(platform)
    if not exe.is_file():
        fail(f"{exe} not found")

    gate_setup_host(build_dir, exe)
    gate_dependencies(exe, platform)

    out_dir = Path(args.out).resolve()
    staged = out_dir / f"{ARCHIVE_PREFIX}-{version}-{platform}"
    stage(build_dir, exe, platform, staged)
    archive = write_archive(staged, platform, out_dir)
    shutil.rmtree(staged)
    size = archive.stat().st_size / (1024 * 1024)
    print(f"package_release: wrote {archive} ({size:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
