# -*- coding: utf-8 -*-
"""Compare the MODULE-level (top-frame) bytecode of the reconstructed source
against the original module, ignoring nested function/lambda bodies (verified
separately). Expected divergence only at the inlined `fence_positions`
comprehension (original used [*c1,*c2,...]; reconstruction uses c1+c2+...)."""
import marshal, dis, types, io, sys
sys.stdout.reconfigure(encoding="utf-8")

PYC = r"C:\Users\semin\AppData\Local\PatissonWork\Patisson.exe_extracted\patisson.pyc"
SRC = r"C:\Users\semin\OneDrive\Рабочий стол\раскомпилинг патисон гейм 2\source\patisson.py"

with open(PYC, "rb") as f:
    f.read(16); orig = marshal.loads(f.read())
with io.open(SRC, "r", encoding="utf-8") as f:
    mine = compile(f.read(), "patisson.py", "exec")

SKIP = {"RESUME", "CACHE", "EXTENDED_ARG", "NOP", "MAKE_CELL", "COPY_FREE_VARS",
        "PRECALL"}

def topstream(code):
    out = []
    for ins in dis.get_instructions(code):
        op = ins.opname
        if op in SKIP:
            continue
        if op in ("JUMP_FORWARD", "JUMP_BACKWARD", "JUMP_ABSOLUTE",
                  "JUMP_BACKWARD_NO_INTERRUPT"):
            out.append(("JUMP", "")); continue
        if op.startswith("POP_JUMP") or op in ("JUMP_IF_TRUE_OR_POP",
                                               "JUMP_IF_FALSE_OR_POP", "FOR_ITER", "SEND"):
            out.append((op, "")); continue
        v = ins.argval
        if isinstance(v, types.CodeType):
            out.append((op, "<code:%s>" % v.co_name))      # nested def/lambda
        elif op in ("LOAD_GLOBAL", "LOAD_NAME", "STORE_NAME", "STORE_GLOBAL",
                    "IMPORT_NAME", "IMPORT_FROM", "LOAD_ATTR", "STORE_ATTR",
                    "LOAD_METHOD"):
            out.append((op, str(v)))
        elif op in ("LOAD_CONST", "RETURN_CONST", "KW_NAMES"):
            out.append((op, repr(v)))
        else:
            out.append((op, "" if v is None else (v if isinstance(v, str) else repr(v))))
    return out

import difflib
o = topstream(orig)
m = topstream(mine)
print("orig top-level ops: %d   recon top-level ops: %d" % (len(o), len(m)))

sm = difflib.SequenceMatcher(a=o, b=m, autojunk=False)
def ctxname(seq, lo, hi, back=10):
    for k in range(min(hi, len(seq)) - 1, max(0, lo - back) - 1, -1):
        if seq[k][0] in ("STORE_NAME", "STORE_GLOBAL"):
            return seq[k][1]
    return "?"
blocks = [b for b in sm.get_opcodes() if b[0] != "equal"]
print("real diff blocks: %d" % len(blocks))
for tag, i1, i2, j1, j2 in blocks:
    name = ctxname(o, i1, i2) or ctxname(m, j1, j2)
    osnip = " ".join("%s%s" % (op, (":" + a) if a else "") for op, a in o[i1:i2][:6])
    msnip = " ".join("%s%s" % (op, (":" + a) if a else "") for op, a in m[j1:j2][:6])
    print("  [%s] near '%s'" % (tag, name))
    print("      orig: %s" % osnip)
    print("      mine: %s" % msnip)
