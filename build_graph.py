#!/usr/bin/env python3
"""File-level call graph for the atlas view.

994,093 function-level Calls edges is not a picture — at that density a
node-link view is a hairball that says nothing. The readable unit is the FILE,
with edges weighted by how many distinct function calls cross between them.
That is the shape an atlas view is for; drilling to functions is what the
browse tab already does.

PATH NAMESPACES — the trap this file exists to avoid
----------------------------------------------------
Graph edge endpoints are `<name>@<path>` where <path> has NO extension:

    start@/tmp/alembic-work/<repo>/cron/scheduler_provider

Claims carry the real path WITH extension:

    /tmp/alembic-work/<repo>/cron/blueprint_catalog.py

Aggregating on the raw id string therefore puts every file in the graph twice —
once bare, once with its extension — and the two copies never touch. The first
version of this script did exactly that: 5,221 "files", and `pub` (does this
file carry published claims?) was false for all 209,323 edge endpoints, because
the only nodes it was ever true for were the isolated extension-bearing twins.
Nothing errored; the numbers just looked plausible.

The fix is to resolve endpoints through the ground's own node records, which
carry an authoritative `file` field, and to key claims by that same resolved
path. Endpoints with no node record anywhere (call targets outside every slice)
keep their bare path and are counted in meta.unresolved rather than dropped.

Self-edges (a file calling itself) are counted in `s` but kept OUT of the link
set: they carry no layout information and would just thicken every node.

usage: build_graph.py <slices-dir> <claims.json> <out.json>
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import ijson

WORKDIR = re.compile(r"^.*?/alembic-work/[^/]+/")
rel = lambda p: WORKDIR.sub("", str(p or ""))


def bare(nid: str) -> str:
    """The extension-less path half of a `<name>@<path>` node id."""
    _, _, f = str(nid or "").partition("@")
    return rel(f)


def main(argv):
    if len(argv) < 4:
        print(__doc__, file=sys.stderr)
        return 1
    slices, claims_p, out = Path(argv[1]), Path(argv[2]), Path(argv[3])
    grounds = sorted(slices.glob("*/ground.json"))
    if not grounds:
        print(f"no ground.json under {slices}", file=sys.stderr)
        return 1

    # ---- pass 1: authoritative bare-path -> real-path map, from node records.
    real_of: dict[str, str] = {}
    ambiguous: dict[str, set] = defaultdict(set)
    for g in grounds:
        with g.open("rb") as f:
            for _key, rec in ijson.kvitems(f, "graph.nodes"):
                nid, fp = rec.get("id"), rec.get("file")
                if not nid or not fp:
                    continue
                b, r = bare(nid), rel(fp)
                if not b or not r:
                    continue
                prev = real_of.setdefault(b, r)
                if prev != r:
                    # e.g. main.py and main.ts collapsing to the same stem.
                    ambiguous[b].update({prev, r})
        print(f"  scanned nodes: {g.parent.name}  map={len(real_of)}", file=sys.stderr)

    resolve = lambda b: real_of.get(b, b)

    # ---- claims, keyed by the same resolved path.
    mc = json.loads(claims_p.read_text())
    claims_per_file = Counter()
    shapes_per_file = defaultdict(Counter)
    for c in mc.get("claims", []):
        f = rel(c.get("file"))
        claims_per_file[f] += 1
        shapes_per_file[f][c.get("shape")] += 1

    # ---- pass 2: edges.
    links = Counter()
    self_calls = Counter()
    seen = set()
    unresolved = set()
    for g in grounds:
        with g.open("rb") as f:
            for e in ijson.items(f, "graph.edges.item"):
                if e.get("kind") != "Calls":
                    continue
                a, b = str(e.get("from") or ""), str(e.get("to") or "")
                if (a, b) in seen:
                    continue
                seen.add((a, b))
                ba, bb = bare(a), bare(b)
                if not ba or not bb:
                    continue
                for x in (ba, bb):
                    if x not in real_of:
                        unresolved.add(x)
                fa, fb = resolve(ba), resolve(bb)
                if fa == fb:
                    self_calls[fa] += 1
                else:
                    links[(fa, fb)] += 1
        print(f"  scanned edges: {g.parent.name}  links={len(links)}", file=sys.stderr)

    # A file is a node if it carries claims (it is in the published set) OR it is
    # an endpoint of a retained edge — the latter keeps cross-module targets
    # visible instead of edges vanishing into nothing.
    ids = set(claims_per_file) | {x for pair in links for x in pair}
    idx = {f: i for i, f in enumerate(sorted(ids))}
    nodes = []
    for f, i in sorted(idx.items(), key=lambda kv: kv[1]):
        nodes.append({
            "i": i, "f": f, "m": f.split("/")[0] if "/" in f else "(root)",
            "c": claims_per_file.get(f, 0),
            "s": self_calls.get(f, 0),
            "top": (shapes_per_file[f].most_common(1)[0][0] if shapes_per_file.get(f) else None),
            "pub": f in claims_per_file,
        })
    edges = [[idx[a], idx[b], w] for (a, b), w in links.items()]
    edges.sort(key=lambda e: -e[2])

    pub_ids = {n["i"] for n in nodes if n["pub"]}
    pub_edges = sum(1 for a, b, _ in edges if a in pub_ids and b in pub_ids)
    doc = {"meta": {"nodes": len(nodes), "edges": len(edges),
                    "published_files": len(claims_per_file),
                    "published_edges": pub_edges,
                    "function_edges": len(seen),
                    "resolved_paths": len(real_of),
                    "unresolved": len(unresolved),
                    "ambiguous_stems": len(ambiguous),
                    "note": ("file-level aggregation of the Calls graph. Endpoints are resolved "
                             "from extension-less edge ids to real paths via the ground's node "
                             "records; `unresolved` counts endpoints with no node record in any "
                             "slice (call targets outside the sliced modules), which keep their "
                             "bare path. `pub` marks files carrying published claims. Self-calls "
                             "are counted in `s` but excluded from links.")},
           "nodes": nodes, "edges": edges}
    out.write_text(json.dumps(doc))
    mods = Counter(n["m"] for n in nodes)
    print(f"graph -> {out}  {len(nodes)} files, {len(edges)} file-edges "
          f"(from {len(seen)} function edges)  {out.stat().st_size/1048576:.1f} MB")
    print(f"  published files {len(claims_per_file)} carrying {pub_edges} edges between them")
    print(f"  path map {len(real_of)} resolved | {len(unresolved)} unresolved "
          f"| {len(ambiguous)} ambiguous stems")
    if ambiguous:
        for b, rs in list(ambiguous.items())[:3]:
            print(f"    ambiguous: {b} -> {sorted(rs)}")
    print("  top modules:", dict(mods.most_common(8)))
    inv = {i: f for f, i in idx.items()}
    print("  heaviest edges:")
    for a, b, w in edges[:5]:
        print(f"    {w:5d}  {inv[a]:44s} -> {inv[b]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
