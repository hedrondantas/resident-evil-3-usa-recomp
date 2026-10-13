# Resident Evil 3: Nemesis (USA) Recompiled

Native PC port of **Resident Evil 3: Nemesis** for PlayStation (USA, `SLUS-00923`),
built with [PSXRecomp](https://github.com/mstan/psxrecomp): the game's MIPS code is
statically recompiled to C and linked against a PS1 hardware runtime.

**This repository contains no game data**: no disc image, no BIOS, no game code
(the generated C is produced on your machine from your own disc). Bring your own
legally dumped disc and BIOS.

> Status: experimental. Boots and runs stably in local testing; not a complete
> playthrough validation. Based on the configuration of the
> [European release candidate](https://github.com/alexbeavs-ps1-ports/resident-evil-3-recomp).

## Requirements

| Input | Expected |
|---|---|
| Disc | `Resident Evil 3 - Nemesis (USA).cue` + `.bin` (one track), 722,165,136 bytes, SHA-1 `c5993ac3ea6efb4181554aa32d8749a7f728a7ad` |
| BIOS | `SCPH1001.BIN` (USA), SHA-256 `71af94d1e47a68c11e8fdb9f8368040601514a42a5a399cda48c7d3bff1e99d3` |

No SBI file is needed (the USA release has no LibCrypt protection).

Tools: Python 3, CMake, Ninja and a C/C++ compiler. On Windows,
`psxrecomp_cli.py ensure-toolchain` downloads a portable CMake + Clang pack.

## Setup and recompilation

The easiest way to build the game is the recompiler window. Double-click `Launcher.pyw`
in the project root, or run `python Launcher.pyw`. It needs Python 3.11 or newer with
tkinter, which the python.org and Microsoft Store installers include.

1. Choose the disc and the BIOS. The disc can be a `.cue` with its `.bin` (recommended),
   a `.bin` or an `.iso`. Both files are checked against the expected dumps.
2. When both files are valid, the recompilation starts by itself. It prepares the
   toolchain, generates the C code, compiles the executable and installs the BIOS next to
   it, with a progress bar and a log. **Recompile** runs it again at any time.
3. **Play** starts the game, which opens its own launcher first.

This window only sets up and recompiles. It runs the same commands as the manual build
below, and its interface follows the system language (English or Portuguese). An `.iso`
has no known checksum, so it is converted to BIN without verification.

Settings, controls and mods live in the game's own launcher, and in the F1 menu during
play. The launcher's **Input** card sets the console port for controller 1, the same
route F1 changes live. **Load State**, next to PLAY, starts the game straight from one
of the 12 save-state slots, each shown with its thumbnail and date. Save states are made
during play with Select + R1 or F7.

## Build

```sh
git clone https://github.com/hedrondantas/resident-evil-3-usa-recomp.git
cd resident-evil-3-usa-recomp

python psxrecomp/psxrecomp_cli.py ensure-toolchain --project-root .

python psxrecomp/psxrecomp_cli.py generate --project-root . --config game.toml \
  --disc "path/to/Resident Evil 3 - Nemesis (USA).cue" \
  --bios path/to/SCPH1001.BIN --gen-marker SLUS_009.23_dispatch.c

python psxrecomp/psxrecomp_cli.py rebuild --project-root . --config game.toml \
  --build-dir build-release --target psx-runtime \
  --exe-basename Resident_Evil_3_Nemesis_USA_Recompiled --no-pgo
```

Then copy your BIOS to `build-release/bios/SCPH1001.BIN` and run
`build-release/Resident_Evil_3_Nemesis_USA_Recompiled`. The build stages the
mod packages from `mods/packages/` next to the executable.

## In-game settings (F1)

Press **F1**, or **Select + Start** on the controller, while playing to pause and open
**Runtime settings**. Changes apply immediately and are saved to `settings.toml`; no
restart is needed.

The controller shortcut can be rebound under Host shortcuts on the launcher's Controller
page, or with `[hotkeys] runtime_menu_pad` in `settings.toml`. People rarely press both
buttons in the same frame, so while part of the chord is down its buttons are kept from
the game for 120 ms. The game never sees a completed chord. A Select or Start pressed on
its own still reaches the game, just that much later.

| Category | Settings |
|---|---|
| Display | Fullscreen, window scale |
| Graphics | Linear filter, texture filtering, FMV filtering, **resolution scale (1x–8x)**, geometry correction, perspective texturing |
| Audio | Volume |
| Input / Disc | Controller port route, change or reinsert disc |

Navigate with the arrow keys or D-pad, change values with Left/Right, go back with
Esc / Circle. Live resolution scale needs the OpenGL renderer (the default).
This comes from this project's changes to the framework in `psxrecomp/` (see Credits).

| Resolution scale | Internal resolution | Good for |
|---|---|---|
| 4x | 1280x960 | 720p / 900p displays |
| 5x | 1600x1200 | **1080p** |
| 6x | 1920x1440 | 1440p |
| 8x | 2560x1920 | 4K (downsampled) |

The ceiling is 8x, lowered automatically if the graphics driver cannot allocate the
surface (8x uses about 400 MB of video memory). Pre-rendered backgrounds and FMVs keep
their original resolution; the scale sharpens the 3D models.

## Keyboard

The default keyboard layout matches the original PC release (Windows, 2000), as listed
in its ReadMe. It is defined in `src/re3usa_keybinds.h`.

| Action | Keys | PlayStation button |
|---|---|---|
| Move, turn | Arrow keys or Num 8 / 2 / 4 / 6 | D-pad |
| Select, action, attack | Space or Enter | Cross |
| Run, cancel | V or Esc | Square and Triangle |
| Aim at enemies, dodge | S | R1 |
| Aim at any target | X | R2 |
| Change target | B | L1 |
| Status screen | Z or F4 | Circle |
| Map | M | L2 |
| Options, skip cutscene | F5 | Select |
| Pause | P | Start |

Quick turn is Down + V. Each button holds two keys at most, so the PC's third action key
(C) is not bound. F6 stays the runtime's controller-port swap rather than a second map
key. Other runtime keys: F1 settings menu (Select + Start on a controller), F7 save
states, Tab fast-forward, Alt+Enter fullscreen.

Rebind keys in `build-release/keybinds.ini` (two keys per button, comma-separated) or
in the built-in launcher's Controls page. A `keybinds.ini` written before this layout
keeps its old keys: delete it, or use Reset in the Controls page, to get the new
defaults.

## Mods

`mods/packages/re3usa.gameplay/` is a mod package with optional gameplay changes
(all off by default; enable them in the launcher's **Mods** menu). Every change is a
guarded patch that checks the original instruction bytes before applying:

| Group | Feature |
|---|---|
| Save | Save without Ink Ribbon · Infinite Ink Ribbons |
| Items | Infinite items |
| Difficulty | Hardcore mode (one-hit death) |
| Video | Skip FMVs |
| HUD | Health and ammo HUD (bottom-left of the screen, hidden in menus; OpenGL renderer) |
| Experimental | More inventory slots · Walk through walls · Walk through enemies · Freeze enemies |

The patches are adapted from known NTSC-U GameShark codes
([Almar's Guides](https://almarsguides.com/retro/walkthroughs/ps1/games/residentevil3nemesis/gameshark/misccodes/)).
Build a distributable archive with:

```sh
python psxrecomp/tools/psxmod_pack.py mods/packages/re3usa.gameplay/1.0.0 dist/re3usa.gameplay-1.0.0.psxmod
```

## Function catalogue

`catalog/` catalogues all 2,075 functions of the main executable:
408 Sony PsyQ 4.5 SDK functions identified by byte signature
([psx_psyq_signatures](https://github.com/lab313ru/psx_psyq_signatures)), and the game's
own functions classified by subsystem with a confidence level. `symbols.toml` holds the
same names in PSXRecomp's symbol-map format, and `catalog/ghidra_import.py` loads them
into Ghidra. See [`catalog/README.md`](catalog/README.md).

## About this project

Developed with AI assistance (Claude Code).

## Credits and licenses

The framework and launcher are included in this repository as ordinary folders
(not submodules), with this project's changes applied on top:

- `psxrecomp/`: [PSXRecomp](https://github.com/mstan/psxrecomp), from the
  [Alexbeav/psxrecomp](https://github.com/Alexbeav/psxrecomp) fork at `6c7fdaa`, plus the
  F1 runtime menu, the 8x internal resolution, the saved controller 1 route
  (`[controller] p1_port` in `settings.toml`), live build progress in
  `psxrecomp_cli.py`, and a hook for a title's own default keyboard layout
  (`PSX_TITLE_KEYBINDS_HEADER`). Includes its `lib/recomp-net` and
  `lib/retcomm-rbengine` dependencies.
- `recomp-ui/`: [recomp-ui](https://github.com/mstan/recomp-ui), from
  [Alexbeav/recomp-ui](https://github.com/Alexbeav/recomp-ui) at `be8ac1d`, plus the 8x
  resolution ceiling in the launcher, the controller 1 port row on its Input card, the
  Load State picker on the dashboard, a Settings-menu host shortcut, and the same title
  keyboard-layout hook.
- Project layout and configuration derived from
  [resident-evil-3-recomp](https://github.com/alexbeavs-ps1-ports/resident-evil-3-recomp).

Each included folder keeps its own license and third-party notices. The upstream commits
are recorded in `framework_pins.txt`. Resident Evil and all related trademarks belong to
Capcom.
