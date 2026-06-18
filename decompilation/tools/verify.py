# -*- coding: utf-8 -*-
"""Recompile each top-level function from the reconstructed source and compare
its normalized opcode stream against the original code object from the pyc.
Functions whose streams differ are reported for manual review."""
import marshal, dis, types, ast, io, sys
sys.stdout.reconfigure(encoding="utf-8")

PYC = r"C:\Users\semin\AppData\Local\PatissonWork\Patisson.exe_extracted\patisson.pyc"
SRC = r"C:\Users\semin\OneDrive\Рабочий стол\раскомпилинг патисон гейм 2\source\patisson.py"

with open(PYC, "rb") as f:
    f.read(16); mod = marshal.loads(f.read())

# original top-level functions by name -> list of code objects (handles dups)
orig = {}
for c in mod.co_consts:
    if isinstance(c, types.CodeType) and c.co_name != "<lambda>":
        orig.setdefault(c.co_name, []).append(c)

SKIP = {"RESUME", "CACHE", "MAKE_CELL", "COPY_FREE_VARS", "RETURN_GENERATOR",
        "PRECALL", "NOP", "EXTENDED_ARG"}

def norm(code):
    """normalized list of (opname, key) for a code object, recursing into
    nested code consts (lambdas, genexprs, comprehensions)."""
    out = []
    for ins in dis.get_instructions(code):
        op = ins.opname
        if op in SKIP:
            continue
        if op.startswith("LOAD_CONST") or op == "RETURN_CONST" or op == "KW_NAMES":
            v = ins.argval
            key = "<code>" if isinstance(v, types.CodeType) else repr(v)
        elif op in ("LOAD_GLOBAL", "LOAD_NAME"):
            key = ins.argval
        elif op in ("JUMP_FORWARD", "JUMP_BACKWARD", "JUMP_ABSOLUTE",
                    "JUMP_BACKWARD_NO_INTERRUPT"):
            op = "JUMP"; key = ""           # normalize unconditional jump direction
        elif op.startswith("POP_JUMP") or op in (
                "JUMP_IF_TRUE_OR_POP", "JUMP_IF_FALSE_OR_POP", "FOR_ITER", "SEND"):
            # KEEP the opcode name so the FALSE/TRUE *sense* is compared
            # (this is what catches boolean-condition inversions); ignore target
            key = ""
        else:
            key = "" if ins.argval is None else (ins.argval if isinstance(ins.argval, str) else repr(ins.argval))
            if isinstance(ins.argval, types.CodeType):
                key = "<code>"
        out.append((op, key))
    # recurse nested code (sorted by appearance already)
    for cst in code.co_consts:
        if isinstance(cst, types.CodeType):
            out.append(("<<NESTED:%s>>" % cst.co_name, ""))
            out.extend(norm(cst))
    return out

# compile reconstructed source and pull each top-level function code object
with io.open(SRC, "r", encoding="utf-8") as f:
    src = f.read()
tree = ast.parse(src)
recon = {}
for node in tree.body:
    if isinstance(node, ast.FunctionDef):
        seg = ast.get_source_segment(src, node)
        try:
            modcode = compile(seg, "<f>", "exec")
            fcode = [c for c in modcode.co_consts if isinstance(c, types.CodeType)][0]
            recon.setdefault(node.name, []).append(fcode)
        except SyntaxError as e:
            recon.setdefault(node.name, []).append(("SYNERR", str(e)))

mismatch = []
ok = 0
for name, ocodes in orig.items():
    rcodes = recon.get(name)
    if not rcodes:
        mismatch.append((name, "MISSING in source"))
        continue
    o = norm(ocodes[0])
    r = rcodes[0]
    if isinstance(r, tuple):
        mismatch.append((name, "syntax error")); continue
    rn = norm(r)
    if o == rn:
        ok += 1
    else:
        # find first divergence
        diff_at = None
        for i, (a, b) in enumerate(zip(o, rn)):
            if a != b:
                diff_at = (i, a, b); break
        if diff_at is None:
            diff_at = (min(len(o), len(rn)), "len%d" % len(o), "len%d" % len(rn))
        mismatch.append((name, "opcodes differ @%d orig=%s recon=%s (lens %d/%d)"
                         % (diff_at[0], diff_at[1], diff_at[2], len(o), len(rn))))

print("MATCH (byte-faithful): %d / %d functions" % (ok, len(orig)))
print("MISMATCHES (%d):" % len(mismatch))
for n, why in sorted(mismatch):
    print("  %-28s %s" % (n, why))
