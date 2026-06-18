# -*- coding: utf-8 -*-
import marshal, dis, importlib.util

PYC_IN  = r"C:\Users\semin\AppData\Local\PatissonWork\Patisson.exe_extracted\patisson.pyc"
PYC_OUT = r"C:\Users\semin\AppData\Local\PatissonWork\patisson_surgery.pyc"
REGION_START = 1090   # BUILD_LIST 0  (start of comprehension cluster)
REGION_END   = 1300   # STORE_NAME fence_positions (exclusive)

with open(PYC_IN, "rb") as f:
    header = f.read(16)
    mod = marshal.loads(f.read())

NOP = dis.opmap["NOP"]
BUILD_LIST = dis.opmap["BUILD_LIST"]

# ---- exception table varint codec (CPython 3.11+ format) ----
def encode_varint(val):
    chunks = [val & 0x3f]; val >>= 6
    while val:
        chunks.append(val & 0x3f); val >>= 6
    chunks.reverse()
    out = bytearray()
    for k, c in enumerate(chunks):
        out.append(c | 0x40 if k != len(chunks) - 1 else c)
    return out

def encode_entry(start_w, size_w, target_w, depth, lasti):
    b = encode_varint(start_w)
    b[0] |= 0x80
    b += encode_varint(size_w)
    b += encode_varint(target_w)
    b += encode_varint((depth << 1) | (1 if lasti else 0))
    return b

entries = list(dis._parse_exception_table(mod))  # byte offsets
def build_table(entries):
    out = bytearray()
    for e in entries:
        out += encode_entry(e.start // 2, (e.end - e.start) // 2, e.target // 2,
                             e.depth, e.lasti)
    return bytes(out)

# sanity: round-trip full table must equal original
roundtrip = build_table(entries)
print("exctable roundtrip matches original:", roundtrip == mod.co_exceptiontable,
      "(len orig=%d new=%d)" % (len(mod.co_exceptiontable), len(roundtrip)))

# ---- patch co_code ----
co = bytearray(mod.co_code)
assert co[REGION_START] == BUILD_LIST and co[REGION_START + 1] == 0, "start mismatch"
assert co[REGION_END] == dis.opmap["STORE_NAME"], "end mismatch"
# keep BUILD_LIST 0 at start, NOP the rest of the region
for i in range(REGION_START + 2, REGION_END):
    co[i] = NOP if (i % 2 == 0) else 0
new_code = bytes(co)

# drop exception entries fully inside the region
kept = [e for e in entries if not (e.start >= REGION_START and e.end <= REGION_END)]
print("exc entries: total=%d kept=%d dropped=%d" % (len(entries), len(kept), len(entries) - len(kept)))
new_table = build_table(kept)

new_mod = mod.replace(co_code=new_code, co_exceptiontable=new_table)

with open(PYC_OUT, "wb") as f:
    f.write(header)
    marshal.dump(new_mod, f)
print("wrote", PYC_OUT)
