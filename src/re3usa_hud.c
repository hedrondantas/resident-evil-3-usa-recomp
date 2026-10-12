/*
 * Resident Evil 3: Nemesis (USA, SLUS-00923) - health and ammo HUD.
 *
 * Trusted plugin "re3usa.hud", enabled by the "hud" feature of the
 * re3usa.gameplay mod package. Every VBlank it reads the player's health and
 * the equipped weapon's loaded ammo from RAM and shows them at the bottom-left
 * of the game image through the host HUD layer (not drawn into guest VRAM).
 *
 * RAM layout, verified with the debug server:
 *   0x800CCC90  s16  current health (200 = full; 0 before a player exists)
 *   0x800D2134       inventory, 4 bytes per slot: item id, quantity, flags, 0
 *                    (quantity is the loaded ammo for firearms)
 *   0x800D225C  u8   inventory slot of the equipped item
 *   0x800D225D  u8   equipped item id (0 = nothing equipped)
 *   0x800D225E  u8   number of inventory slots
 *   0x800D1F2D  u8   high byte of the system flags at 0x800D1F2C: non-zero while
 *                    the inventory, map or other menu screens are open
 */
#include "mod_plugins.h"

#include <stdint.h>
#include <stdio.h>

#define RE3_HEALTH       0x800CCC90u
#define RE3_INVENTORY    0x800D2134u
#define RE3_EQUIP_SLOT   0x800D225Cu
#define RE3_EQUIP_ID     0x800D225Du
#define RE3_SLOT_COUNT   0x800D225Eu
#define RE3_MENU_FLAGS   0x800D1F2Du
#define RE3_MAX_SLOTS    10u

#define RE3_ITEM_KNIFE   0x01u

static void re3usa_hud_vblank(void) {
    if (!psx_mod_game_started()) {
        psx_mod_set_hud_text(NULL);
        return;
    }

    const int health = (int16_t)psx_mod_read_half(RE3_HEALTH);
    if (health <= 0) {   /* no player yet (boot, title) or dead */
        psx_mod_set_hud_text(NULL);
        return;
    }
    if (psx_mod_read_byte(RE3_MENU_FLAGS) != 0) {   /* inventory, map, files */
        psx_mod_set_hud_text(NULL);
        return;
    }

    char text[64];
    int len = snprintf(text, sizeof text, "HP %d", health);

    const uint32_t id = psx_mod_read_byte(RE3_EQUIP_ID);
    const uint32_t slot = psx_mod_read_byte(RE3_EQUIP_SLOT);
    const uint32_t slots = psx_mod_read_byte(RE3_SLOT_COUNT);
    if (id != 0 && slot < slots && slot < RE3_MAX_SLOTS && len > 0 &&
        (size_t)len < sizeof text) {
        const uint32_t entry = RE3_INVENTORY + slot * 4u;
        if (psx_mod_read_byte(entry) == id) {
            if (id == RE3_ITEM_KNIFE)
                snprintf(text + len, sizeof text - (size_t)len, "   KNIFE");
            else
                snprintf(text + len, sizeof text - (size_t)len, "   AMMO %u",
                         (unsigned)psx_mod_read_byte(entry + 1u));
        }
    }
    psx_mod_set_hud_text(text);
}

PSX_MOD_CONSTRUCTOR(re3usa_register_hud_plugin) {
    (void)psx_mod_register_vblank_plugin("re3usa.hud", re3usa_hud_vblank);
}
