/* pad_chord_guard.h - keep a controller chord's buttons away from the game.
 *
 * A host shortcut such as SELECT+START is rarely pressed in a single frame, so
 * whichever button lands first would reach the game for a few frames (Resident
 * Evil 3 opens its own options on SELECT and pauses on START). While part of
 * the chord is down, its buttons are held back for PAD_CHORD_HOLD_MS:
 *
 *   - the chord completes in time: none of its buttons reach the game, until
 *     every one of them is released;
 *   - a button stays down longer on its own: it goes through, just late;
 *   - a button is tapped and released inside the window: it is replayed as
 *     pressed for PAD_CHORD_REPLAY_MS so the game still sees the tap.
 *
 * Pure state machine (no SDL), so it can be tested on its own. Bit n of every
 * mask is controller button n.
 */
#ifndef PAD_CHORD_GUARD_H
#define PAD_CHORD_GUARD_H

#include <stdint.h>

#define PAD_CHORD_HOLD_MS   120u
#define PAD_CHORD_REPLAY_MS  70u

typedef struct PadChordGuard {
    uint32_t first_down_ms[32];  /* when each chord button went down; 0 = up */
    int      latched;            /* chord completed: hold until all are up */
    uint32_t replay_buttons;     /* taps being replayed to the game */
    uint32_t replay_until;
} PadChordGuard;

/* Advance one poll. `mask` is the chord, `held` the chord buttons down now,
 * `chord_down` whether the whole chord is down, `now_ms` a nonzero tick.
 * Returns the buttons to keep from the game this poll; `*replay` (optional)
 * receives the buttons to report as pressed. A zero mask clears the state. */
static inline uint32_t pad_chord_guard_update(PadChordGuard *g, uint32_t mask,
                                              uint32_t held, int chord_down,
                                              uint32_t now_ms, uint32_t *replay) {
    uint32_t hold = 0;
    int code;
    held &= mask;
    for (code = 0; code < 32; ++code) {
        const uint32_t bit = 1u << code;
        if (!(mask & bit)) {
            g->first_down_ms[code] = 0;
            continue;
        }
        if (held & bit) {
            if (!g->first_down_ms[code]) g->first_down_ms[code] = now_ms;
        } else if (g->first_down_ms[code]) {
            if (!g->latched &&
                (uint32_t)(now_ms - g->first_down_ms[code]) < PAD_CHORD_HOLD_MS) {
                g->replay_buttons |= bit;
                g->replay_until = now_ms + PAD_CHORD_REPLAY_MS;
            }
            g->first_down_ms[code] = 0;
        }
    }
    if (chord_down) g->latched = 1;
    else if (!held) g->latched = 0;
    for (code = 0; code < 32; ++code) {
        const uint32_t bit = 1u << code;
        if ((held & bit) &&
            (g->latched ||
             (uint32_t)(now_ms - g->first_down_ms[code]) < PAD_CHORD_HOLD_MS))
            hold |= bit;
    }
    if (g->replay_buttons && (int32_t)(now_ms - g->replay_until) >= 0)
        g->replay_buttons = 0;
    if (replay) *replay = g->replay_buttons;
    return hold;
}

#endif /* PAD_CHORD_GUARD_H */
