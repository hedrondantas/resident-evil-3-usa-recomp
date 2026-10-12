"""Match PsyQ OBJ signatures against a PS-X EXE.
Usage: psyq_match.py <exe> <sigs_root> <out.json>
For every SDK version, every OBJ signature is searched (?? = wildcard) in the
EXE text. An OBJ that matches exactly once gives names for its labels.
Versions are scored; per OBJ the match from the best-scoring version wins."""
import json, os, re, sys

exe_path, root, out_path = sys.argv[1:4]
raw = open(exe_path, 'rb').read()
text = raw[0x800:]
BASE = int.from_bytes(raw[0x18:0x1C], 'little')


def sig_regex(sig):
    parts = []
    for tok in sig.split():
        parts.append(b'.' if tok == '??' else re.escape(bytes([int(tok, 16)])))
    return re.compile(b''.join(parts), re.DOTALL)


versions = sorted(d for d in os.listdir(root) if d.isdigit())
per_version = {}
for ver in versions:
    vdir = os.path.join(root, ver)
    hits = {}
    for fn in sorted(os.listdir(vdir)):
        if not fn.endswith('.json'):
            continue
        lib = fn[:-5]
        for obj in json.load(open(os.path.join(vdir, fn))):
            sig = obj.get('sig') or ''
            ntok = len(sig.split())
            nfixed = ntok - sig.split().count('??')
            if ntok < 16 or nfixed < 12:
                continue
            ms = [m.start() for m in sig_regex(sig).finditer(text)]
            if len(ms) != 1:
                continue
            addr = BASE + ms[0]
            names = [(l['name'], addr + l['offset']) for l in obj.get('labels', [])
                     if not re.match(r'^(loc|text|data|bss|rdata|sdata|sbss)_', l['name'])]
            hits[(lib, obj['name'])] = {'addr': addr, 'size': ntok, 'names': names}
    per_version[ver] = hits
    print(ver, 'objs matched:', len(hits), 'bytes:', sum(h['size'] for h in hits.values()), flush=True)

score = {v: sum(h['size'] for h in hs.values()) for v, hs in per_version.items()}
order = sorted(versions, key=lambda v: -score[v])
print('best versions:', order[:4])

# Merge: walk versions best-first; keep the first match per (lib,obj) and never
# assign two names to one address or one name to two addresses.
by_addr, used_names, objs = {}, set(), {}
for ver in order:
    for (lib, obj), h in per_version[ver].items():
        if (lib, obj) in objs:
            continue
        span = range(h['addr'], h['addr'] + h['size'])
        if any(a in span for a in by_addr):
            continue
        objs[(lib, obj)] = (ver, h)
        for name, a in h['names']:
            if name in used_names or a in by_addr:
                continue
            by_addr[a] = {'name': name, 'lib': lib, 'obj': obj, 'version': ver}
            used_names.add(name)

out = {'base': hex(BASE), 'best_version': order[0], 'version_scores': score,
       'functions': {hex(a): v for a, v in sorted(by_addr.items())}}
json.dump(out, open(out_path, 'w'), indent=1)
print('named functions:', len(by_addr), 'objs:', len(objs))
