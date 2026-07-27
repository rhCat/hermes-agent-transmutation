#!/usr/bin/env python3
"""Find functions that do STRUCTURALLY the same thing — candidates for dedup.

The claim-set of a function is already a fingerprint. Two functions carrying the
same multiset of `shape·bound·quant` postings acquire the same resources on the
same path-strength, gate on the same families, absorb the same errors, and
return the same way. That is a mechanical statement about what they *do*, made
without reading a line of their bodies and without an LLM.

So: group by signature, and every group of size > 1 is a set of candidates.
Ranked by `removable` = total body_lines minus the largest member, i.e. the LOC
you would save if the group collapsed to one implementation.

WHAT THIS IS NOT. A shared signature is EVIDENCE OF SIMILARITY, NOT A DUPLICATE.
Two validators that both "gate on py_file_family and raise on some paths" have
the same shape and may be entirely different code. Over-produces by design (the
same eta as the rest of the chain) — this ranks candidates for a human to look
at, and every candidate links to its source line so that look is one click.

Signature strength is reported, because a 1-claim signature is nearly worthless
and a 6-claim one is a strong hint. Groups below --min-claims are dropped.

usage: find_twins.py <claims.json> <slices-dir> <out.json> [--min-claims N]
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


def load_fn_meta(slices: Path) -> dict:
    """name -> {loc, complexity, params, file, line} from every slice ground.

    Streamed: the slices are 8-150 MB each and only four fields are wanted.
    """
    meta = {}
    for g in sorted(slices.glob("*/ground.json")):
        with g.open("rb") as f:
            for fn in ijson.items(f, "analysis.functions.item"):
                n = fn.get("name")
                if not n:
                    continue
                key = (rel(fn.get("file")), n)
                meta[key] = {
                    "loc": int(fn.get("body_lines") or 0),
                    "complexity": int(fn.get("complexity") or 0),
                    "params": len(fn.get("params") or []),
                    "line": fn.get("line_start"),
                }
    return meta


def call_degree(slices: Path) -> tuple:
    """in/out degree per bare function name, over the Calls edges of every slice.

    Cross-module edges are included — they were deliberately retained by the
    slicer, and a function's callers are most of what says whether removing it
    is safe.
    """
    ind, outd = Counter(), Counter()
    seen = set()
    for g in sorted(slices.glob("*/ground.json")):
        with g.open("rb") as f:
            for e in ijson.items(f, "graph.edges.item"):
                if e.get("kind") != "Calls":
                    continue
                a, b = str(e.get("from") or ""), str(e.get("to") or "")
                if (a, b) in seen:      # slices overlap on boundary edges
                    continue
                seen.add((a, b))
                outd[a.split("@", 1)[0]] += 1
                ind[b.split("@", 1)[0]] += 1
    return ind, outd


def signature(claims):
    """The structural fingerprint: sorted (shape, bound, quant) postings.

    Guard is deliberately excluded — it names the CFG condition, which differs
    between genuinely equivalent implementations. Shape/bound/quant is what the
    function DOES; guard is where.
    """
    # `bound` is NESTED as target.bound in the raw perk output — only the page's
    # summary builder flattens it. Reading the flat key yields "" for every claim,
    # which collapses the fingerprint to shape+quant: 100% of claims carry a bound,
    # so that silently discards ALL the discriminating power and every ordinary
    # function looks like every other one. (Measured: a 175-member "twin group"
    # whose signature was merely gates-absorbs-returns.)
    def bound(c):
        return (c.get("target") or {}).get("bound") or c.get("bound") or ""
    return tuple(sorted((c.get("shape"), bound(c), c.get("quant") or "")
                        for c in claims))


def main(argv):
    if len(argv) < 4:
        print(__doc__, file=sys.stderr)
        return 1
    claims_p, slices, out = Path(argv[1]), Path(argv[2]), Path(argv[3])
    min_claims = 2
    if "--min-claims" in argv:
        min_claims = int(argv[argv.index("--min-claims") + 1])

    mc = json.loads(claims_p.read_text())
    by_fn = defaultdict(list)
    for c in mc.get("claims", []):
        # key on (file, fn) — the raw perk output carries no `module` field, and
        # a composite key including one silently misses every lookup (measured: all
        # LOC read 0, so every group ranked equal and the ranking meant nothing).
        by_fn[(rel(c.get("file")), c.get("fn"))].append(c)

    meta = load_fn_meta(slices)
    ind, outd = call_degree(slices)

    groups = defaultdict(list)
    for key, cs in by_fn.items():
        if len(cs) < min_claims:
            continue
        groups[signature(cs)].append((key, cs))

    twins = []
    for sig, members in groups.items():
        if len(members) < 2:
            continue
        rows = []
        for (f, fn), cs in members:
            m = meta.get((f, fn), {})
            rows.append({"module": f.split("/")[0], "file": f, "fn": fn,
                         "line": m.get("line") or (cs[0].get("line")),
                         "loc": m.get("loc", 0), "complexity": m.get("complexity", 0),
                         "params": m.get("params", 0),
                         "callers": ind.get(fn, 0), "callees": outd.get(fn, 0)})
        rows.sort(key=lambda r: -r["loc"])
        total = sum(r["loc"] for r in rows)
        removable = total - (rows[0]["loc"] if rows else 0)
        twins.append({
            "signature": [{"shape": s, "bound": b, "quant": q} for s, b, q in sig],
            "sig_len": len(sig),
            "members": rows,
            "count": len(rows),
            "total_loc": total,
            "removable_loc": removable,
            # a group is only interesting if the shape says something specific
            "distinct_shapes": len({s for s, _, _ in sig}),
        })

    twins.sort(key=lambda t: (-t["removable_loc"], -t["sig_len"]))
    doc = {
        "meta": {
            "source_claims": str(claims_p),
            "min_claims": min_claims,
            "groups": len(twins),
            "functions_in_groups": sum(t["count"] for t in twins),
            "removable_loc_total": sum(t["removable_loc"] for t in twins),
            "note": ("A shared signature is EVIDENCE OF SIMILARITY, not a duplicate. "
                     "Over-produces by design; every member links to its source line so a "
                     "human can judge in one click. Guard is excluded from the signature — "
                     "it names where, not what."),
        },
        "twins": twins,
    }
    out.write_text(json.dumps(doc))
    print(f"twins -> {out}  {len(twins)} groups, "
          f"{doc['meta']['functions_in_groups']} functions, "
          f"{doc['meta']['removable_loc_total']} removable LOC")
    for t in twins[:8]:
        shapes = "+".join(sorted({s['shape'] for s in t['signature']}))
        print(f"   x{t['count']:3d}  {t['removable_loc']:5d} LOC  [{shapes}]  "
              f"e.g. {t['members'][0]['fn']} ({t['members'][0]['file'].split('/')[-1]})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
