"""Function catalogue for RE3 (USA, SLUS-00923).
Usage: catalog.py <project_root> <psyq_matches.json> <out_dir>
Combines: psxrecomp `analyze` output, PsyQ signature hits, per-function
disassembly (constant-propagated data refs, GTE use, strings) and community
knowledge (GameShark RAM addresses / code patch sites, NTSC-U).
Writes functions.tsv, ram_variables.tsv and summary.json to <out_dir>, and
symbols.toml to <project_root>."""
import collections, json, os, re, sys
import capstone
from capstone import mips as M

root, psyq_path, out_dir = sys.argv[1:4]
an = json.load(open(os.path.join(root, 'analysis', 'analysis.json')))
edges = json.load(open(os.path.join(root, 'analysis', 'edges.json')))['edges']
psyq = json.load(open(psyq_path))['functions']
raw = open(os.path.join(root, 'disc', 'SLUS_009.23'), 'rb').read()
BASE = int.from_bytes(raw[0x18:0x1C], 'little')
img = raw[0x800:]
END = BASE + len(img)
GP = an.get('initial_gp') or 0

# ---------------------------------------------------------------- knowledge
LIB_CAT = {
    'LIBGPU.LIB': 'graphics', 'LIBGS.LIB': 'graphics', 'LIBGTE.LIB': '3d',
    'LIBCD.LIB': 'cd', 'LIBDS.LIB': 'cd', 'LIBSPU.LIB': 'audio', 'LIBSND.LIB': 'audio',
    'LIBPRESS.LIB': 'fmv', 'LIBPAD.LIB': 'controller', 'LIBTAP.LIB': 'controller',
    'LIBCARD.LIB': 'memcard', 'LIBMCRD.LIB': 'memcard', 'LIBAPI.LIB': 'system',
    'LIBETC.LIB': 'system', 'LIBC.LIB': 'utility', 'LIBC2.LIB': 'utility',
    'LIBSN.LIB': 'system', 'NOHEAP.OBJ': 'system', 'LIBMATH.LIB': 'utility',
}
BIOS_CAT = [(r'card|_bu_|FormatDevice|firstfile|nextfile|File', 'memcard'),
            (r'Cd', 'cd'), (r'GPU', 'graphics'), (r'Pad', 'controller'),
            (r'str|mem|printf|puts|setjmp|rand|toupper|tolower|bcopy|bzero|abs', 'utility')]

# (lo, hi_exclusive, label, category) -- from NTSC-U GameShark codes
# (almarsguides.com RE3 Nemesis GameShark pages). Exact addresses only,
# except the save/progress block whose extent is inferred from the codes.
RAM = [
    (0x800CCC90, 0x800CCC92, 'player health (Jill)', 'player'),
    (0x800CCC97, 0x800CCC98, 'player condition (Fine/Caution/Danger)', 'player'),
    (0x800CCC8C, 0x800CCC8E, 'weapon fire state', 'player'),
    (0x800CCCF0, 0x800CCCF2, 'enemy attack flag', 'enemies'),
    (0x800CC830, 0x800CC832, 'controller buttons (current)', 'input'),
    (0x800CC7EA, 0x800CC7EC, 'controller buttons (raw, inverted)', 'input'),
    (0x800CC852, 0x800CC854, 'reward received', 'progress'),
    (0x800CC858, 0x800CC85C, 'game state flags (bits used to skip to the ending)', 'game_state'),
    (0x800C79BA, 0x800C79BC, 'countdown timer', 'time'),
    (0x800BD8DE, 0x800BD8E0, 'blood amount', 'effects'),
    (0x800D1D18, 0x800D1D1C, 'routine pointer (used to open the save screen)', 'menu'),
    (0x800D1F28, 0x800D1F2C, 'total play time', 'time'),
    (0x800D1F2C, 0x800D1F2E, 'system flags (bit 0x200 opens the item box)', 'game_state'),
    (0x800D1F32, 0x800D1F34, 'item box: new game contents', 'inventory'),
    (0x800D1F3E, 0x800D1F40, 'epilogue pictures', 'progress'),
    (0x800D1F40, 0x800D1F42, 'save count', 'progress'),
    (0x800D1F98, 0x800D1F9A, 'time (counter)', 'time'),
    (0x800D20CC, 0x800D20D0, 'unlocked door flags', 'doors'),
    (0x800D2127, 0x800D212C, 'maps obtained', 'progress'),
    (0x800D212C, 0x800D2130, 'files obtained', 'progress'),
    (0x800D225E, 0x800D2260, 'inventory slot count', 'inventory'),
    (0x800D2260, 0x800D2290, 'inventory (items and ammo)', 'inventory'),
    (0x800D25EC, 0x800D25F0, 'reward total', 'progress'),
    (0x800D454C, 0x800D454E, 'hyper mode / speed', 'progress'),
    (0x800E01C4, 0x800E01C6, 'item box menu state', 'menu'),
    (0x800D1F00, 0x800D2700, 'progress/save block (probable)', 'progress'),
]
# code sites patched by the codes -> what the containing function does
SITES = [
    (0x80083454, 'skips FMVs ("Skip All FMVs" code)', 'fmv'),
    (0x80051404, 'ink ribbon check when saving', 'save'),
    (0x8006CD2C, 'ink ribbon consumption', 'save'),
    (0x8006CD30, 'ink ribbon consumption', 'save'),
    (0x80044E18, 'player damage calculation ("One Hit Death")', 'combat'),
    (0x800339FC, 'wall collision', 'collision'),
    (0x8004B2A0, 'wall collision', 'collision'),
    (0x800339BC, 'wall collision', 'collision'),
    (0x80033980, 'enemy collision', 'collision'),
    (0x80033790, 'collision (walls and enemies)', 'collision'),
    (0x80023EA8, 'enemy update/movement', 'enemies'),
    (0x8008DBCC, 'NTSC/PAL video mode', 'graphics'),
    (0x8008BAA4, 'NTSC/PAL video mode', 'graphics'),
    (0x80024290, 'soft reset', 'system'),
    (0x800101BC, 'game speed (hyper mode)', 'time'),
    (0x800809AC, 'frame timing (hyper mode)', 'time'),
    (0x8006D0C8, 'item use/consumption', 'inventory'),
    (0x800667D8, 'inventory slot count', 'inventory'),
    (0x800513CC, 'save screen routine (target of the "Save Anywhere" code)', 'save'),
]

STR_CAT = [(r'DOOR', 'doors'), (r'SPU|SOUND|VAB|SEQ', 'audio'), (r'BSS|SEEK|CD|cdrom', 'cd'),
           (r'MDEC|STR', 'fmv'), (r'GPU|Draw|OTag|Graph|DispEnv|DrawEnv', 'graphics'),
           (r'DMA|intr|interrupt|timer', 'system'), (r'PAD|pad', 'controller'), (r'card|bu[0-9]', 'memcard')]

# ---------------------------------------------------------------- functions
funcs = {}
for f in an['functions']:
    if f.get('is_data'):
        continue
    funcs[f['addr']] = f

lib = {int(k, 16): v for k, v in psyq.items()}
callees = collections.defaultdict(list)
callers = collections.defaultdict(list)
for e in edges:
    if e['kind'] in ('direct', 'jump_table', 'indirect') and e['from'] and e['to'] in funcs:
        callees[e['from']].append(e['to'])
        callers[e['to']].append(e['from'])

md = capstone.Cs(capstone.CS_ARCH_MIPS, capstone.CS_MODE_MIPS32 + capstone.CS_MODE_LITTLE_ENDIAN)
md.detail = True
LOADS = {'lb', 'lbu', 'lh', 'lhu', 'lw', 'lwl', 'lwr', 'lwc2'}
STORES = {'sb', 'sh', 'sw', 'swl', 'swr', 'swc2'}


def cstr(a):
    o = a - BASE
    if not (0 <= o < len(img)):
        return None
    e = img.find(b'\0', o, o + 200)
    if e - o < 4:
        return None
    s = img[o:e]
    if all(32 <= c < 127 or c in (9, 10) for c in s):
        return s.decode()
    return None


def scan(f):
    a0, size = f['addr'], max(f['size'], 4)
    regs = {M.MIPS_REG_ZERO: 0}
    if GP:
        regs[M.MIPS_REG_GP] = GP
    refs, gte, strs = [], 0, []
    for ins in md.disasm(img[a0 - BASE:a0 - BASE + size], a0):
        mn = ins.mnemonic
        ops = ins.operands
        if mn in ('cop2', 'mfc2', 'mtc2', 'cfc2', 'ctc2', 'lwc2', 'swc2') or (ins.bytes[3] >> 2) == 0x12:
            gte += 1
        if mn in LOADS | STORES and len(ops) == 2 and ops[1].type == M.MIPS_OP_MEM:
            b = ops[1].mem.base
            if b in regs:
                t = (regs[b] + ops[1].mem.disp) & 0xFFFFFFFF
                refs.append((t, mn in STORES, ins.address))
            if mn in LOADS and ops[0].type == M.MIPS_OP_REG:
                regs.pop(ops[0].reg, None)
            continue
        if mn == 'lui':
            regs[ops[0].reg] = (ops[1].imm << 16) & 0xFFFFFFFF
            continue
        if mn in ('addiu', 'ori', 'addi') and len(ops) == 3 and ops[1].type == M.MIPS_OP_REG:
            src = ops[1].reg
            if src in regs:
                v = regs[src] + ops[2].imm if mn != 'ori' else regs[src] | (ops[2].imm & 0xFFFF)
                v &= 0xFFFFFFFF
                regs[ops[0].reg] = v
                if BASE <= v < END:
                    refs.append((v, False, ins.address))
                    s = cstr(v)
                    if s:
                        strs.append(s)
            else:
                regs.pop(ops[0].reg, None)
            continue
        if mn in ('jal', 'jalr', 'bal'):
            for r in list(regs):
                if r not in (M.MIPS_REG_ZERO, M.MIPS_REG_GP, M.MIPS_REG_S0, M.MIPS_REG_S1,
                             M.MIPS_REG_S2, M.MIPS_REG_S3, M.MIPS_REG_S4, M.MIPS_REG_S5,
                             M.MIPS_REG_S6, M.MIPS_REG_S7, M.MIPS_REG_FP, M.MIPS_REG_SP):
                    regs.pop(r)
            continue
        if ops and ops[0].type == M.MIPS_OP_REG and mn not in STORES and not mn.startswith(('b', 'j', 'mt', 'sw', 'sh', 'sb')):
            regs.pop(ops[0].reg, None)
    return refs, gte, strs


def ram_label(t):
    hits = [(lo, hi, lab, cat) for lo, hi, lab, cat in RAM if lo <= t < hi]
    if not hits:
        return None
    return min(hits, key=lambda h: h[1] - h[0])  # most specific

# ---------------------------------------------------------------- classify
rows = {}
for a, f in funcs.items():
    refs, gte, strs = scan(f)
    ev = collections.Counter()
    notes, origin, name, libname, conf = [], 'capcom', f['name'], '', ''
    if a in lib:
        origin, name, libname = 'psyq', lib[a]['name'], lib[a]['lib']
        ev[LIB_CAT.get(libname, 'system')] += 100
        conf = 'confirmed'
    elif f.get('bios_call'):
        origin, name = 'bios', f['name']
        cat = 'system'
        for pat, c in BIOS_CAT:
            if re.search(pat, f['name']):
                cat = c
                break
        ev[cat] += 100
        conf = 'confirmed'
    else:
        for c in callees[a]:
            if c in lib:
                ev[LIB_CAT.get(lib[c]['lib'], 'system')] += 3
            elif funcs[c].get('bios_call'):
                for pat, cat in BIOS_CAT:
                    if re.search(pat, funcs[c]['name']):
                        ev[cat] += 3
                        break
                else:
                    ev['system'] += 2
        if gte:
            ev['3d'] += 2 + min(gte, 10) // 3
        seen = set()
        for t, w, pc in refs:
            lab = ram_label(t)
            if lab and lab[2] not in seen:
                seen.add(lab[2])
                ev[lab[3]] += 0 if lab[1] - lab[0] >= 0x100 else (1 if lab[3] == 'game_state' else 4)
                notes.append(('writes ' if w else 'reads ') + lab[2])
        for st in strs:
            for pat, cat in STR_CAT:
                if re.search(pat, st):
                    ev[cat] += 6
                    break
        for site, desc, cat in SITES:
            if a <= site < max(f['end'], a + 4):
                ev[cat] += 10
                notes.insert(0, desc)
    rows[a] = dict(addr=a, size=f['size'], name=name, origin=origin, lib=libname,
                   ev=ev, notes=notes, strs=strs[:3], gte=gte, conf=conf,
                   callers=len(callers[a]), callees=len(callees[a]))

# propagate bottom-up: unclassified game functions take the dominant category
# of what they call, at low confidence
for rnd in range(3):
    for a, r in rows.items():
        if r['origin'] != 'capcom' or +r['ev']:
            continue
        agg = collections.Counter()
        for c in callees[a]:
            cr = rows.get(c)
            if cr and +cr['ev']:
                agg[cr['ev'].most_common(1)[0][0]] += 1
        if agg:
            r['prop'] = agg
for a, r in rows.items():
    if r['origin'] != 'capcom':
        r['cat'] = r['ev'].most_common(1)[0][0]
        continue
    if r['ev'] and +r['ev']:
        r['ev'] = +r['ev']
        cat, score = r['ev'].most_common(1)[0]
        r['cat'] = cat
        total = sum(r['ev'].values())
        r['conf'] = 'high' if score >= 8 and score / total >= 0.6 else ('medium' if score >= 3 else 'low')
        others = [c for c, _ in r['ev'].most_common(3)[1:]]
        if others:
            r['notes'].append('also: ' + ', '.join(others))
    elif r.get('prop'):
        r['cat'] = r['prop'].most_common(1)[0][0]
        r['conf'] = 'low'
        r['notes'].append('inferred from callees')
    elif r['callees'] == 0 and r['size'] <= 64:
        r['cat'], r['conf'] = 'utility', 'low'
        r['notes'].append('small leaf function')
    else:
        r['cat'], r['conf'] = 'unknown', ''

# ---------------------------------------------------------------- outputs
os.makedirs(out_dir, exist_ok=True)
with open(os.path.join(out_dir, 'functions.tsv'), 'w', encoding='utf-8') as o:
    o.write('address\tsize\tname\torigin\tlibrary\tsubsystem\tconfidence\tcallers\tcallees\tstrings\tnotes\n')
    for a in sorted(rows):
        r = rows[a]
        o.write('\t'.join([f'0x{a:08X}', str(r['size']), r['name'], r['origin'], r['lib'], r['cat'],
                           r['conf'], str(r['callers']), str(r['callees']),
                           ' | '.join(s.replace('\t', ' ').replace('\n', ' ') for s in r['strs']),
                           '; '.join(r['notes'])]) + '\n')

with open(os.path.join(out_dir, 'ram_variables.tsv'), 'w', encoding='utf-8') as o:
    o.write('start\tend\tdescription\tcategory\tsource\n')
    for lo, hi, lab, cat in RAM:
        o.write(f'0x{lo:08X}\t0x{hi:08X}\t{lab}\t{cat}\tNTSC-U GameShark codes (almarsguides.com)\n')

with open(os.path.join(root, 'symbols.toml'), 'w', encoding='utf-8') as o:
    o.write('# Resident Evil 3: Nemesis (USA) SLUS-00923 - symbol map.\n'
            '# PsyQ 4.5 names: byte-signature matches (lab313ru/psx_psyq_signatures).\n'
            '# Game functions: "guessed" from GameShark patch sites; not authoritative.\n\n')
    for a in sorted(rows):
        r = rows[a]
        if r['origin'] == 'psyq':
            o.write(f'[[func]]\npc = 0x{a:08X}\nname = "{r["name"]}"\nemit = false\n'
                    f'status = "confirmed"\nnote = "PsyQ {r["lib"]}"\n\n')
        elif r['origin'] == 'capcom' and any(a <= s < max(funcs[a]['end'], a + 4) for s, _, _ in SITES):
            desc = next(d for s, d, _ in SITES if a <= s < max(funcs[a]['end'], a + 4))
            o.write(f'[[func]]\npc = 0x{a:08X}\nname = "func_{a:08X}"\nemit = false\n'
                    'status = "guessed"\nnote = ' + json.dumps(desc) + '\n\n')

summary = {
    'total': len(rows),
    'by_origin': collections.Counter(r['origin'] for r in rows.values()),
    'capcom_by_subsystem': collections.Counter(r['cat'] for r in rows.values() if r['origin'] == 'capcom'),
    'capcom_by_confidence': collections.Counter(r['conf'] or 'none' for r in rows.values() if r['origin'] == 'capcom'),
}
json.dump(summary, open(os.path.join(out_dir, 'summary.json'), 'w'), indent=1)
print(json.dumps(summary, indent=1))
