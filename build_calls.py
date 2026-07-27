#!/usr/bin/env python3
"""Uncapped call lists, sharded one file at a time.

Replaces build_callgraph.py, which had two faults that fed each other:

  * it keyed neighbourhoods by BARE FUNCTION NAME, so every `get` in the tree
    collapsed into one entry with 9,150 callers — a list that is not about any
    particular function;
  * because those merged entries were enormous, it capped each list at 24, and
    the page had to admit the list was truncated.

Keying by `name@file` fixes the first, and once entries are per-function the
lists are small enough to ship whole — but only if they are not all in one
payload. So the output is one shard per source file: open a file in the viewer,
fetch that file's shard, get every caller and callee of every function in it.

Neighbour paths are interned per shard (`paths` + index) because the same few
hundred files appear over and over inside one shard.

Edge endpoints carry extension-less paths (`cron/scheduler_provider`); claims
carry real ones (`cron/scheduler_provider.py`). Both are resolved through the
ground's node records so the two namespaces actually meet — see build_graph.py.

usage: build_calls.py <slices-dir> <claims.json> <out-dir>
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import ijson

WORKDIR = re.compile(r"^.*?/alembic-work/[^/]+/")
rel = lambda p: WORKDIR.sub("", str(p or ""))


def split_id(nid: str):
    name, _, f = str(nid or "").partition("@")
    return name, rel(f)


def shard_name(f: str) -> str:
    """One shard per source file; '/' → '__' keeps it flat and collision-free."""
    return re.sub(r"[^A-Za-z0-9_.-]", "_", f.replace("/", "__")) + ".json"


def main(argv):
    if len(argv) < 4:
        print(__doc__, file=sys.stderr)
        return 1
    slices, claims_p, outdir = Path(argv[1]), Path(argv[2]), Path(argv[3])
    grounds = sorted(slices.glob("*/ground.json"))
    if not grounds:
        print(f"no ground.json under {slices}", file=sys.stderr)
        return 1

    real_of: dict[str, str] = {}
    for g in grounds:
        with g.open("rb") as f:
            for _k, rec in ijson.kvitems(f, "graph.nodes"):
                nid, fp = rec.get("id"), rec.get("file")
                if nid and fp:
                    real_of.setdefault(split_id(nid)[1], rel(fp))
    resolve = lambda b: real_of.get(b, b)

    mc = json.loads(claims_p.read_text())
    want = {(c["fn"], rel(c.get("file"))) for c in mc.get("claims", []) if c.get("fn")}
    want_files = {f for _, f in want}
    print(f"  {len(want)} published functions in {len(want_files)} files "
          f"| path map {len(real_of)}", file=sys.stderr)

    callers, callees = defaultdict(set), defaultdict(set)
    seen = set()
    for g in grounds:
        with g.open("rb") as f:
            for e in ijson.items(f, "graph.edges.item"):
                if e.get("kind") != "Calls":
                    continue
                a, b = str(e.get("from") or ""), str(e.get("to") or "")
                if (a, b) in seen:          # slices overlap on boundary edges
                    continue
                seen.add((a, b))
                an, af = split_id(a)
                bn, bf = split_id(b)
                if not an or not bn:
                    continue
                ak, bk = (an, resolve(af)), (bn, resolve(bf))
                if ak == bk:                # true self-recursion only
                    continue
                if bk in want:
                    callers[bk].add(ak)
                if ak in want:
                    callees[ak].add(bk)
        print(f"  scanned {g.parent.name}", file=sys.stderr)

    outdir.mkdir(parents=True, exist_ok=True)
    for old in outdir.glob("*.json"):
        old.unlink()

    by_file = defaultdict(list)
    for fn, f in want:
        by_file[f].append(fn)

    manifest, total_entries, total_bytes, widest = {}, 0, 0, ("", 0)
    for f, fns in sorted(by_file.items()):
        paths, pidx = [], {}
        def ref(p):
            if p not in pidx:
                pidx[p] = len(paths); paths.append(p)
            return pidx[p]
        block = {}
        for fn in sorted(set(fns)):
            ins = sorted(callers.get((fn, f), ()))
            outs = sorted(callees.get((fn, f), ()))
            if not ins and not outs:
                continue
            block[fn] = {"in": [[n, ref(p)] for n, p in ins],
                         "out": [[n, ref(p)] for n, p in outs]}
            total_entries += len(ins) + len(outs)
            if len(ins) + len(outs) > widest[1]:
                widest = (f"{fn} @ {f}", len(ins) + len(outs))
        if not block:
            continue
        name = shard_name(f)
        p = outdir / name
        p.write_text(json.dumps({"file": f, "paths": paths, "fns": block},
                                separators=(",", ":")))
        total_bytes += p.stat().st_size
        manifest[f] = name

    (outdir / "_manifest.json").write_text(json.dumps(
        {"meta": {"files": len(manifest), "entries": total_entries,
                  "edges_considered": len(seen),
                  "note": ("one shard per source file; lists are complete, not capped. "
                           "`paths` interns neighbour file paths, entries are [name, pathIndex].")},
         "shards": manifest}, separators=(",", ":")))

    print(f"calls -> {outdir}  {len(manifest)} shards, {total_entries} entries, "
          f"{total_bytes/1048576:.1f} MB total "
          f"(mean {total_bytes/max(1,len(manifest))/1024:.0f} KB/shard)")
    print(f"  widest neighbourhood: {widest[0]} — {widest[1]} entries")
    big = sorted(((p.stat().st_size, p.name) for p in outdir.glob("*.json")), reverse=True)[:3]
    for s, n in big:
        print(f"  largest shard: {n} {s/1024:.0f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
