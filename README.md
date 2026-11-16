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

Nothing else needs to be installed by hand. The build uses a portable toolchain pack
(CMake, Ninja, Clang, a prebuilt SDL3 and Python) that is downloaded once into
`~/.local/share/retcomm` (Linux) or `%LOCALAPPDATA%` (Windows), so no compiler, no
development packages and no administrator password are needed. On Linux,
`PSXRECOMP_NATIVE_TOOLCHAIN=1` builds with the system's CMake, Ninja and Clang instead.

## Setup and recompilation

Everything happens in one place: the launcher built into the game.

- **Ready-to-run package (recommended):** download the Linux `.tar.gz` or the Windows
  `.zip` from the [Releases](https://github.com/hedrondantas/resident-evil-3-usa-recomp/releases)
  page, extract it, and open `Launcher.sh` (Linux) or `Launcher.cmd` (Windows). The
  launcher is already built and nothing needs to be installed, not even Python.
- **From a source checkout:** on Linux run `./Launcher.sh`, which needs no Python. On
  Windows open `Launcher.cmd` or `Launcher.pyw`; this needs Python 3.11 or newer
  (python.org or Microsoft Store). The first run compiles the launcher itself, once, in
  a few minutes, with a progress window (or terminal output).

The launcher then opens its first-run setup:

1. **BIOS:** a `SCPH1001.BIN` in `assets/` (or `bios/`, or the project root) is picked
   up automatically; otherwise choose it with **Browse BIOS**. It is checked by size and
   CRC.
2. **Disc:** choose the `.cue` (recommended), the `.bin` alone, or an `.iso`. Keeping
   your dumps in `assets/` keeps them out of git and next to the project. A `.cue`/
   `.bin` is checked against the known dump. An `.iso` has no known checksum, so it is
   converted to BIN and only its boot program is checked. The working copy of a BIN is
   a hard link to yours when both are on the same drive, not a second 700 MB copy.
3. **Generate & rebuild:** generates the C code, compiles the full game into the same
   folder and restarts into it (about 10 to 20 minutes, with progress).

After that, the same shortcut opens the game's launcher directly. On Linux, the first
run also adds **Resident Evil 3: Nemesis Recompiled** to the applications menu.
**Generate & rebuild** stays available from the launcher's settings, and
`./Launcher.sh --rebuild-launcher` (or `python launcher/bootstrap.py
--rebuild-launcher`) recompiles the executable from the existing generated code, for
example after updating the project.

Settings, controls and mods live in the game's own launcher, and in the F1 menu during
play. The launcher's **Input** card sets the console port for controller 1, the same
route F1 changes live. **Load State**, next to PLAY, starts the game straight from one
of the 12 save-state slots, each shown with its thumbnail and date. Save states are made
during play with Select + R1 or F7.

**Skip launcher on boot** starts the game directly. To get the launcher back, hold
**Shift** while the game window opens (the game restarts into the launcher), or turn on
**Show launcher on boot** under System in the F1 menu. `--launcher` on the command line
(`./Launcher.sh --launcher`, `Launcher.cmd --launcher`) also opens it.

## Project layout

| Path | Contents |
|---|---|
| `Launcher.sh`, `Launcher.cmd`, `Launcher.pyw` | Entry points (Linux; Windows; Windows with Python) |
| `assets/` | Your disc and BIOS dumps (ignored by git) |
| `game.toml`, `CMakeLists.txt`, `codegen_setup.c/.h`, `VERSION`, `framework_pins.txt` | Title configuration. The framework's tools expect these at the root. |
| `src/` | Title code: the HUD mod plugin and the default keyboard layout |
| `mods/` | The gameplay mod package |
| `seeds/`, `symbols.toml`, `catalog/`, `catalog_identity.json` | Function seeds and the function catalogue |
| `launcher/` | First-run bootstrap (`bootstrap.py`) and its log |
| `scripts/`, `.github/workflows/` | Release packaging and its CI |
| `psxrecomp/`, `recomp-ui/` | Vendored framework and launcher, with this project's changes |

Created on your machine and ignored by git: `generated/` (the game's C code), `disc/`
(the working disc image, a hard link to your `.bin` when possible), `build-release/`
(the game, its settings and a copy of the BIOS), `saves/` (memory cards and save
states), and the launcher's pointers `bios.cfg`, `disc.cfg` and `toolchain/`.

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

These are the commands the launcher runs. Then copy your BIOS to
`build-release/bios/SCPH1001.BIN` and run
`build-release/Resident_Evil_3_Nemesis_USA_Recompiled`. The build stages the
mod packages from `mods/packages/` next to the executable.

## Releases

`python scripts/package_release.py --build` builds the setup host (the launcher with no
game code and no BIOS code) into `build-setup/` and writes the package for this
platform to `dist/`. It refuses to package a build that contains game or BIOS code, or
an executable that needs libraries players may not have.

The [Release workflow](.github/workflows/release.yml) does the same on GitHub Actions for
Linux and Windows. Run it by hand to get the packages as workflow artifacts, or bump
`VERSION`, commit, and push a matching tag (`git tag v0.1.2 && git push origin v0.1.2`)
to also create a draft release with both packages attached.

## Launcher look

The built-in launcher uses a Resident Evil theme: blood-red accents and aged-paper
headings on translucent panels over a blurred backdrop. The repository ships no game
art, so the backdrop is, in order of preference:

1. `launcher_background.png` or `.jpg` placed next to the executable (any size; it is
   scaled down and blurred when the launcher opens),
2. the thumbnail of your newest save state,
3. a plain dark gradient.

The disc card on the Home tab shows a cover the same way: put your own `cover.png` or
`cover.jpg` (portrait, any size) in `assets/`, next to your disc and BIOS, or next to the
executable, and reopen the launcher. Without one, it draws a stylised disc.

The theme is selected in `CMakeLists.txt` (`PSX_TITLE_LAUNCHER_THEME`).

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
| Graphics | Linear filter, texture filtering, FMV filtering, **resolution scale (1x–8x)**, geometry correction, perspective texturing, **SMAA**, **sharpening (CAS)** |
| Audio | Volume |
| System | Resume game, **Save states...** (opens the F7 save-state menu) |
| Input / Disc | Controller port route, change or reinsert disc |
| Quit game | **Save state, then quit** (pick a slot; the game closes once it is saved) or **Quit without saving**. Esc goes back |

Navigate with the arrow keys or D-pad, change values with Left/Right, go back with
Esc / Circle. The mouse pointer is hidden over the game window while playing (windowed
or fullscreen) and comes back while this menu is open. Live resolution scale needs the OpenGL renderer (the default).
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

### SMAA and sharpening

Two post effects run on the final window-size image, so unlike the resolution scale they
also reach the pre-rendered backgrounds. Both are off by default and need the OpenGL
renderer. Turn them on in the launcher's Display settings or the F1 menu, or in
`settings.toml`:

```toml
[video]
smaa          = true   # SMAA 1x (high preset): smooths stair-stepped edges
cas_sharpness = 50     # AMD CAS, 0 = off .. 100: restores detail without halos
```

SMAA softens a little; CAS at 25–50 brings that back. `PSX_SMAA=0|1` and `PSX_CAS=0..100`
override the file for one run.

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
  F1 runtime menu (declared in `main.cpp` with the launcher's names and value sets --
  window sizes, supersampling, sharpening in 10% steps -- and without geometry
  correction or disc tools; a Save states... entry that opens the F7 menu, a Show
  launcher on boot toggle, and a Quit game section that offers a save state first), Shift held as
  the game window opens reopening a skipped launcher, the 8x internal resolution, the saved controller 1 route
  (`[controller] p1_port` in `settings.toml`), live build progress in
  `psxrecomp_cli.py`, a hook for a title's own default keyboard layout
  (`PSX_TITLE_KEYBINDS_HEADER`) and launcher theme (`PSX_TITLE_LAUNCHER_THEME`), and
  SMAA + AMD CAS post effects in the OpenGL present
  (`[video] smaa` / `cas_sharpness`; SMAA vendored under
  `runtime/third_party/smaa/`, see its `THIRD_PARTY_ATTRIBUTION.md`). On Linux,
  `psxrecomp_cli.py` builds with the portable toolchain pack (and its prebuilt SDL3)
  whenever it is installed (`PSXRECOMP_NATIVE_TOOLCHAIN=1` opts out), and the setup host
  (`host/psxrecomp_codegen_host.c`) downloads and uses that pack, including its CPython,
  on Linux as it does on Windows (BIOS discovery in the host and in `main.cpp` also
  searches `assets/`), a setup-host build (`PSXRECOMP_FORCE_SETUP_HOST=ON`) links no
  BIOS backend even when `generated/` holds one; `generate` accepts
  an `.iso` (checked by its boot program), and `tools/prepare_disc.py` hard-links an
  unchanged BIN instead of copying it. Includes its `lib/recomp-net` and
  `lib/retcomm-rbengine` dependencies.
- `recomp-ui/`: [recomp-ui](https://github.com/mstan/recomp-ui), from
  [Alexbeav/recomp-ui](https://github.com/Alexbeav/recomp-ui) at `be8ac1d`, plus the 8x
  resolution ceiling in the launcher, the controller 1 port row on its Input card, the
  Load State picker on the dashboard, a Settings-menu host shortcut, the same title
  keyboard-layout hook, SMAA / Sharpening (CAS) rows in Display settings
  (`GameInfo.has_postfx`, `Settings.smaa` / `cas_sharpness`), the `re3` theme with a
  blurred backdrop (`LauncherTheme.backdrop`), a "Loading game..."
  screen after PLAY while the mod commit (a SHA-256 of the disc image) runs on a worker
  thread instead of freezing the window, a tab row under the title (Home, Settings,
  Mods, and Assist Tools / Credits when present) in place of the header buttons and
  "< Back", Settings rows on a fixed label column with dropdowns instead of
  click-to-cycle buttons (`value_combo`; PSX antialiasing is Off/On), a player-supplied
  `cover.{png,jpg}` (beside the exe or in `../assets/`) for the box art with a CD
  placeholder for disc titles, an aligned Controller page (label columns, bindings
  chips placed from the cell start) with a "< Back" button in its footer, a Home tab
  whose cards share one gap and end on one line (one-player titles fill both columns;
  memory cards span the column), a Mods tab with a measured option column (on/off
  options included), a wider feature list with elided two-tone rows and a
  full-width search (the Enable all / Disable all buttons are gone), the
  portable-toolchain page of the first-run
  wizard on Linux (it was Windows-only), and two first-run wizard fields:
  `GameInfo.setup_bios_required` (retail BIOS only, no "Use OpenBIOS") and
  `GameInfo.setup_disc_note` (the title's own disc note).
- Project layout and configuration derived from
  [resident-evil-3-recomp](https://github.com/alexbeavs-ps1-ports/resident-evil-3-recomp).

Each included folder keeps its own license and third-party notices. The upstream commits
are recorded in `framework_pins.txt`. Resident Evil and all related trademarks belong to
Capcom.
