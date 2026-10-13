/* re3usa_keybinds.h - default keyboard layout of the Resident Evil 3 PC release.
 *
 * Mirrors the defaults listed in the original Windows ReadMe (2000):
 *   Up/Down/Left/Right or Num8/Num2/Num4/Num6   move
 *   Space, Enter or C                           select / action
 *   Esc or V                                    cancel / run
 *   S                                           draw weapon (enemies only)
 *   X                                           draw weapon (all targets)
 *   B                                           change target
 *   Z or F4                                     status screen
 *   M or F6                                     map
 *   F5                                          options
 *
 * The PlayStation game splits two of those across separate buttons: Square
 * runs and Triangle cancels. Esc and V drive both, which gives the PC's single
 * cancel/run key. Each input holds two keys at most, so C (a third action key)
 * and F6 (the runtime's controller-port swap) are left out. Start, which only
 * pauses, has no PC equivalent and sits on P.
 *
 * Wired in through PSX_TITLE_KEYBINDS_HEADER (see CMakeLists.txt); both the
 * runtime (psx_keybinds.c) and the built-in launcher (psx_binds.c) read it, so
 * a fresh keybinds.ini and "Reset" give this layout. Entry format:
 *   X(keybinds.ini key, primary key, alternate key)
 */
#ifndef RE3USA_KEYBINDS_H
#define RE3USA_KEYBINDS_H

#define PSX_TITLE_KEYBINDS(X) \
    X(up,       SDL_SCANCODE_UP,      SDL_SCANCODE_KP_8)    \
    X(down,     SDL_SCANCODE_DOWN,    SDL_SCANCODE_KP_2)    \
    X(left,     SDL_SCANCODE_LEFT,    SDL_SCANCODE_KP_4)    \
    X(right,    SDL_SCANCODE_RIGHT,   SDL_SCANCODE_KP_6)    \
    X(cross,    SDL_SCANCODE_SPACE,   SDL_SCANCODE_RETURN)  \
    X(circle,   SDL_SCANCODE_Z,       SDL_SCANCODE_F4)      \
    X(square,   SDL_SCANCODE_V,       SDL_SCANCODE_ESCAPE)  \
    X(triangle, SDL_SCANCODE_ESCAPE,  SDL_SCANCODE_V)       \
    X(l1,       SDL_SCANCODE_B,       SDL_SCANCODE_UNKNOWN) \
    X(r1,       SDL_SCANCODE_S,       SDL_SCANCODE_UNKNOWN) \
    X(l2,       SDL_SCANCODE_M,       SDL_SCANCODE_UNKNOWN) \
    X(r2,       SDL_SCANCODE_X,       SDL_SCANCODE_UNKNOWN) \
    X(l3,       SDL_SCANCODE_UNKNOWN, SDL_SCANCODE_UNKNOWN) \
    X(r3,       SDL_SCANCODE_UNKNOWN, SDL_SCANCODE_UNKNOWN) \
    X(start,    SDL_SCANCODE_P,       SDL_SCANCODE_UNKNOWN) \
    X(select,   SDL_SCANCODE_F5,      SDL_SCANCODE_UNKNOWN) \
    X(ls_up,    SDL_SCANCODE_UP,      SDL_SCANCODE_KP_8)    \
    X(ls_down,  SDL_SCANCODE_DOWN,    SDL_SCANCODE_KP_2)    \
    X(ls_left,  SDL_SCANCODE_LEFT,    SDL_SCANCODE_KP_4)    \
    X(ls_right, SDL_SCANCODE_RIGHT,   SDL_SCANCODE_KP_6)    \
    X(rs_up,    SDL_SCANCODE_UNKNOWN, SDL_SCANCODE_UNKNOWN) \
    X(rs_down,  SDL_SCANCODE_UNKNOWN, SDL_SCANCODE_UNKNOWN) \
    X(rs_left,  SDL_SCANCODE_UNKNOWN, SDL_SCANCODE_UNKNOWN) \
    X(rs_right, SDL_SCANCODE_UNKNOWN, SDL_SCANCODE_UNKNOWN)

#endif /* RE3USA_KEYBINDS_H */
