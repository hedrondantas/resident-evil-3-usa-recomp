/* Title config for psxrecomp/host/psxrecomp_codegen_host.
 * Wired only when the build opts into -DPSX_SETUP_WIZARD=ON. */

#include "codegen_setup.h"

#include "psxrecomp_codegen_host.h"

static const PsxrecompCodegenHostConfig kCodegenConfig = {
    .display_name = "Resident Evil 3: Nemesis (USA)",
    .project_root_env = "RESIDENT_EVIL_3_USA_PROJECT_ROOT",
    .build_dir_env = "RESIDENT_EVIL_3_USA_BUILD_DIR",
    .force_setup_env = "RESIDENT_EVIL_3_USA_FORCE_SETUP",
    .psxrecomp_cli_relpath = "psxrecomp/psxrecomp_cli.py",
    .seed_cfg_relpath = "game.toml",
    .game_toml_relpath = "game.toml",
    .gen_marker_relpath = "generated/SLUS_009.23_dispatch.c",
    .build_dir_name = "build-release",
    .cmake_target = "psx-runtime",
    .exe_basename = "Resident_Evil_3_Nemesis_USA_Recompiled",
    .prepare_note =
        "Recompiles the game from your disc and BIOS, then restarts into it. "
        "This is needed once and takes about 10 to 20 minutes; progress is "
        "shown here. Everything stays inside the project folder.",
    .prepare_note_windows =
        "Recompiles the game from your disc and BIOS, then restarts into it. "
        "This is needed once and takes about 10 to 20 minutes: the launcher "
        "closes and a console window finishes the build, then the game opens.",
    .prepare_note_no_cmake =
        "Generates the game code from your disc. The build folder could not "
        "be found: rebuild with Launcher.sh --rebuild-launcher, then open the "
        "launcher again.",
};

void psx_game_codegen_setup_apply(RecompLauncherCGameInfo* gi) {
    psxrecomp_codegen_host_apply(gi, &kCodegenConfig);
    if (!gi)
        return;
    /* game.toml sets openbios = false: the retail SCPH-1001 is required. */
    gi->setup_bios_required = 1;
    gi->setup_disc_note =
        "Choose your Resident Evil 3: Nemesis (USA) disc (SLUS-00923): the .cue "
        "with its .bin (recommended), the .bin alone, or an .iso. A .cue/.bin is "
        "checked against the known dump; an .iso cannot be, so only its boot "
        "program is checked. The disc stays where it is: the build links to it "
        "instead of copying it when both are on the same drive.";
}

void psx_game_codegen_relaunch_or_exit(const char* disc_path) {
    psxrecomp_codegen_host_relaunch_or_exit(disc_path);
}

void psx_game_codegen_forward_if_built(int argc, char** argv) {
    psxrecomp_codegen_host_forward_if_built(&kCodegenConfig, argc, argv);
}

