#!/usr/bin/env python3
"""Per-function call neighbourhood, for rendering.

The whole graph is 4,006,532 edges — not something a browser draws, and not
something anyone reads. What is useful at review time is the EGO NETWORK: for
the function in front of you, who calls it and what it calls. That is also the
question that decides whether a dedup candidate is safe to remove.

Cross-module edges are kept. They are 82-88% of every slice, they were the whole
reason the repo was analysed whole rather than partitioned, and a caller list
that stopped at the module boundary would be actively misleading — it would show
an unused-looking function that half the tree calls.

Capped per direction (--cap, default 24) because a handful of utility functions
have thousands of callers and would dominate the payload. The cap is RECORDED
per node, so a truncated neighbourhood is visible as truncated rather than
looking complete.

usage: build_callgraph.py <slices-dir> <claims.json> <out.json> [--cap N]
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
    """Graph ids are `<name>@<file-without-extension>`."""
    name, _, f = str(nid or "").partition("@")
    return name, rel(f)


def main(argv):
    if len(argv) < 4:
        print(__doc__, file=sys.stderr)
        return 1
    slices, claims_p, out = Path(argv[1]), Path(argv[2]), Path(argv[3])
    cap = 24
    if "--cap" in argv:
        cap = int(argv[argv.index("--cap") + 1])

    # only carry neighbourhoods for functions the page can actually show
    mc = json.loads(claims_p.read_text())
    want = {c.get("fn") for c in mc.get("claims", []) if c.get("fn")}

    callers, callees = defaultdict(set), defaultdict(set)
    seen = set()
    for g in sorted(slices.glob("*/ground.json")):
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
                if not an or not bn or an == bn:
                    continue
                if bn in want:
                    callers[bn].add((an, af))
                if an in want:
                    callees[an].add((bn, bf))

    graph = {}
    for fn in want:
        ins = sorted(callers.get(fn, ()))
        outs = sorted(callees.get(fn, ()))
        if not ins and not outs:
            continue
        graph[fn] = {
            "in": [{"fn": n, "file": f} for n, f in ins[:cap]],
            "out": [{"fn": n, "file": f} for n, f in outs[:cap]],
            "in_total": len(ins),
            "out_total": len(outs),
        }

    doc = {"meta": {"cap": cap, "functions": len(graph),
                    "edges_considered": len(seen),
                    "note": ("ego networks only — the full graph is ~4M edges. "
                             "in_total/out_total are the TRUE degrees; the lists are capped, "
                             "so a truncated neighbourhood reads as truncated.")},
           "graph": graph}
    out.write_text(json.dumps(doc))
    top = sorted(graph.items(), key=lambda kv: -kv[1]["in_total"])[:5]
    print(f"callgraph -> {out}  {len(graph)} functions, {len(seen)} unique Calls edges "
          f"({out.stat().st_size/1048576:.1f} MB)")
    for fn, v in top:
        print(f"   {fn:38s} in {v['in_total']:5d}  out {v['out_total']:4d}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
