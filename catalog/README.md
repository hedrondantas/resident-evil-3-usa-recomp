# Function catalogue: Resident Evil 3: Nemesis (USA, SLUS-00923)

This catalogue covers only the main executable, `SLUS_009.23`, which holds 2,075 functions.
It does not cover the code the game loads from the disc during play (`CD_DATA\STAGE*\*.BIN`).

## Files

| File | Contents |
|---|---|
| `functions.tsv` | One row per function. Opens in any spreadsheet app. |
| `ram_variables.tsv` | Known RAM addresses (health, inventory, controller…). |
| `psyq_matches.json` | Identified Sony SDK functions, with their library and SDK version. |
| `summary.json` | Function counts by origin, subsystem and confidence. |
| `ghidra_import.py` | Ghidra script that creates the functions and applies the SDK names. |
| `../symbols.toml` | The same names as a PSXRecomp symbol map, which `analyze` reads. |
| `tools/` | The scripts that generated these files. |

## Columns of `functions.tsv`

- **origin**: `psyq` means a Sony SDK library function. `capcom` means the game's own code.
- **subsystem**: what the function does. Values: graphics, 3d, cd, audio, fmv, controller,
  memcard, system, utility, player, inventory, doors, collision, enemies, combat, progress,
  game_state, time, menu, save, input, effects, unknown.
- **confidence**:
  - `confirmed`: official SDK name, matched by byte signature.
  - `high`: several direct clues agree, or a GameShark code patches this function.
  - `medium`: direct evidence that is weak or mixed.
  - `low`: inferred only from the functions it calls, or a small leaf function.
  - empty: no evidence.
- **callers / callees**: direct calls into and out of the function.
- **strings**: text the function references.
- **notes**: which known variables the function reads or writes, and where its classification came from.

## Method

1. **Structure.** `psxrecomp_cli.py analyze` finds function boundaries, the call graph and jump tables.
2. **Sony SDK (PsyQ 4.5).** Byte signatures from
   [lab313ru/psx_psyq_signatures](https://github.com/lab313ru/psx_psyq_signatures) are matched
   against the executable. Of the 414 names found, 408 land exactly on a function start that
   `analyze` found on its own.
3. **Capcom code.** Each function is classified by the libraries it calls, its use of the GTE
   (the 3D math coprocessor), the strings it references and its accesses to known RAM addresses.
   Those accesses are found by propagating `lui`/`addiu` constants within each function.
4. **Community knowledge.** RAM addresses and code patch sites come from the NTSC-U GameShark
   codes on [Almar's Guides](https://almarsguides.com/retro/walkthroughs/ps1/games/residentevil3nemesis/gameshark/misccodes/).

## Regenerating

With `capstone` installed and the local `disc/` and `analysis/` folders present:

```sh
python psxrecomp/psxrecomp_cli.py analyze --project-root . --config game.toml
python catalog/tools/catalog.py . catalog/psyq_matches.json catalog
python psxrecomp/psxrecomp_cli.py analyze --project-root . --config game.toml --emit-ghidra
cp analysis/psxrecomp_import.py catalog/ghidra_import.py
```

`tools/psyq_match.py <exe> <signatures_root> <out.json>` rebuilds `psyq_matches.json` from a
checkout of the signature repository.

## Limits

- Capcom's functions keep their `func_XXXXXXXX` names. The catalogue says what each one
  probably does, not what it was originally called.
- Treat `low` classifications as guesses. Confirm them in Ghidra or with the game running
  before you change anything.
- 233 indirect calls are unresolved, and about 21% of the executable belongs to no known function.
- `0x800D1F00–0x800D2700` is labelled "progress/save block (probable)" because it groups several
  addresses from the codes. Its exact extent has not been confirmed. It is recorded in the notes
  but does not count towards classification.
