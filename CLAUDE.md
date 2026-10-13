# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A native PC port of Resident Evil 3: Nemesis (USA, SLUS-00923) built with PSXRecomp: the
game's MIPS code is statically recompiled to C (`generated/`) and linked against a PS1
hardware runtime. The repo holds no game data. The disc, BIOS (SCPH1001) and all
generated C come from the user's own dumps and must never be committed (`assets/`,
`disc/`, `generated/`, `build*/` and `saves/` are gitignored).

## Build

Python 3.11+ drives everything through `psxrecomp/psxrecomp_cli.py`:

```sh
python psxrecomp/psxrecomp_cli.py ensure-toolchain --project-root .
python psxrecomp/psxrecomp_cli.py generate --project-root . --config game.toml \
  --disc "path/to/Resident Evil 3 - Nemesis (USA).cue" --bios path/to/SCPH1001.BIN \
  --gen-marker SLUS_009.23_dispatch.c
python psxrecomp/psxrecomp_cli.py rebuild --project-root . --config game.toml \
  --build-dir build-release --target psx-runtime \
  --exe-basename Resident_Evil_3_Nemesis_USA_Recompiled --no-pgo
```

- `generate` only needs re-running when the disc, BIOS, `game.toml`, `seeds/` or the
  recompiler change. Runtime/launcher edits only need `rebuild`, which is incremental
  (a change to `main.cpp` rebuilds a few objects; a full build is ~565 steps).
- `--json-progress` makes the CLI emit one JSON event per line on stdout (`phase`, `log`,
  `error`, `result`); `Launcher.pyw` consumes this.
- The rebuild fails at link time if the game is running (the exe is locked).
- The toolchain is a portable cmake + clang (llvm-mingw) pack cached under
  `~/.local/share/retcomm/toolchains/cmake-clang-v1/<ver>/`; its `deps/` has static SDL3,
  and `bin/` has `llvm-nm`, `llvm-objdump`, `x86_64-w64-mingw32-clang`.
- Run the game: `build-release/Resident_Evil_3_Nemesis_USA_Recompiled.exe` (needs
  `build-release/bios/SCPH1001.BIN`). `--launcher` forces the built-in launcher;
  `PSX_NO_LAUNCHER=1` skips it.

## Tests

There is no test target in the game build. `psxrecomp/runtime/CMakeLists.txt` is a
separate project with framework unit tests (C tests registered with `add_test`, plus
Python tests in `psxrecomp/runtime/tests/*.py`). A single C test can be compiled
directly with the toolchain, for example:

```sh
TC=~/.local/share/retcomm/toolchains/cmake-clang-v1/1.0.14
"$TC/bin/x86_64-w64-mingw32-clang.exe" -std=gnu11 -DPSX_SDL3=1 -DSDL_MAIN_HANDLED \
  -Ipsxrecomp/runtime/include -I"$TC/deps/include" \
  psxrecomp/runtime/tests/test_keyboard_pad_chord.c psxrecomp/runtime/src/psx_keybinds.c \
  -L"$TC/deps/lib" -lSDL3 -lm -lkernel32 -luser32 -lgdi32 -lwinmm -limm32 -lole32 \
  -loleaut32 -lversion -luuid -ladvapi32 -lsetupapi -lshell32 -ldinput8 -o test.exe
```

## Layout and architecture

- **Project files (root):** `game.toml` (game identity, disc hashes, entry PC, recompiler
  inputs), `CMakeLists.txt` (calls `psxrecomp_add_game_runtime`, stages `game.toml` and
  mod packages next to the exe), `codegen_setup.c` (setup-host / "Generate & rebuild"
  config), `seeds/` (function entry seeds), `symbols.toml` + `catalog/` (function
  catalogue, see `catalog/README.md`).
- **`src/`:** title-specific C linked into the runtime. `re3usa_hud.c` is a trusted mod
  plugin registered with `PSX_MOD_CONSTRUCTOR`; `re3usa_keybinds.h` is the default
  keyboard layout (RE3 PC layout), injected through the `PSX_TITLE_KEYBINDS_HEADER`
  hook set per-source in `CMakeLists.txt`.
- **`psxrecomp/` and `recomp-ui/` are vendored folders, not submodules**, with this
  project's changes applied on top (upstream pins in `framework_pins.txt`, change list in
  README "Credits"). Edit them in place; keep changes additive and describe new ones in
  the README credits.
  - `psxrecomp/recompiler/` emits C (`psxrecomp-game`, `psxrecomp-bios`);
    `config_loader.{h,cpp}` also parses `settings.toml` for the runtime
    (`UserSettings`, `load_user_settings`, `save_user_settings`).
  - `psxrecomp/runtime/src/main.cpp` (~15k lines) is the host: settings load, launcher
    handoff, SDL loop, hotkeys, the F1 runtime menu, save states.
  - `recomp-ui/` is the built-in ImGui launcher compiled into the same exe. The contract
    is `recomp-ui/src/recomp_launcher.h`: `RecompLauncherCGameInfo` (capability flags and
    callbacks the runtime fills in `ae_fill_psx_launcher_game_info`) and
    `RecompLauncherCSettings` (values passed in and out). New fields are appended at the
    end of these structs. Data flows host → `GameInfo`/`ls` → `launcher_model.c` (`m`) →
    `launcher_imgui.cpp`, and back through `ls` → `seed` (`UserSettings`) → saved to
    `settings.toml`.
- **Two launchers:** `Launcher.pyw` / `launcher/re3_launcher.py` (tkinter) only checks
  the disc/BIOS and runs the recompilation; all settings, controls, mods and Load State
  live in the built-in launcher and the F1 menu.
- **Runtime files next to the exe:** `settings.toml` (written by the built-in launcher,
  the F1 menu and `Launcher.pyw`; writers must preserve keys they do not own),
  `keybinds.ini`, `input.ini`, `config.ini` (host hotkeys). Save states live in
  `saves/scph1001/state_80011B80_slotNN.pst` (+ `.thumb`).
- **Mods:** `mods/packages/re3usa.gameplay/<ver>/manifest.toml` declares features made of
  guarded one-word patches (`expected`/`replace`) and trusted plugins. Packages are staged
  into `build-release/mods/packages` at build time.

## Debugging

- A crash writes `build-release/psx_last_run_report.json` (SEH code, module offset,
  stack scan, CPU state). Symbolize offsets with `llvm-nm -n -C` on the exe using image
  base `0x140000000`. `psx_freeze_dump_*.json` with `wedge_kind_name = slow_frames` are
  slow-frame diagnostics, not crashes. Save-state events are logged to
  `saves/writable-state.log`.
- `LNG_SCRIPT="wait:90;view:settings;click:x,y;shot:out.png;quit"` drives the built-in
  launcher headlessly and saves screenshots (see `recomp-ui/src/common/launcher_debug.c`).
- `PSX_LOAD_SLOT=N` boots straight into save-state slot N (0-based).

## Constraints

- Do not expose `geometry_correction` on any new settings surface: upstream documents it
  as cracking meshes in this build (`psxrecomp/ENHANCEMENTS.md`, G1.8/G1.9).
- The user commits directly on `main`; do not push unless asked.
- In this Windows Git Bash environment, heredocs mangle backslashes. Write scripts or
  replacement text containing `\` to a file with the Write tool before running them.
