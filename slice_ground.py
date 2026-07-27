#!/usr/bin/env python3
"""Project a whole-repo ground into per-module grounds — WITHOUT partitioning it.

The distinction this tool exists to preserve:

  PARTITIONING the ANALYSIS walks each module in ignorance of the others, so
  every cross-module call edge is destroyed at the boundary. Unrecoverable.

  PROJECTING an already-whole GROUND is safe, because the analysis saw the
  entire tree: the graph holds `agent -> tools -> gateway` edges and this tool
  keeps every edge with EITHER endpoint inside the slice. Cross-boundary calls
  survive as references to functions outside it.

Drop that "either endpoint" rule to "both endpoints" and you have silently
rebuilt the partition. That is the one line in here that matters.

Shape: ONE streaming pass per section, dispatching each item to every module
that wants it, appended straight to per-module part files. So the cost is
`sections x filesize` regardless of how many modules are requested, and memory
stays constant — no slice is ever resident. (The obvious version, a pass per
section per module, costs `modules x sections x filesize`: 70 GB of parsing for
five modules of a 2 GB ground.)

Each slice stamps its own boundary into `_provenance.slice`. A module ground is
honestly PARTIAL, and a consumer that cannot tell it from a whole-repo ground
would silently compare incomparable claim counts.

usage: slice_ground.py <ground.json> <outdir> [module ...]
       (no modules = survey only: every top-level directory that holds functions)
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path

import ijson

WORKDIR = re.compile(r"^.*?/alembic-work/[^/]+/")


def _plain(o):
    """ijson yields JSON numbers as Decimal, which json.dumps refuses. Convert
    on the way out rather than mutating parsed structures in place."""
    if isinstance(o, Decimal):
        f = float(o)
        return int(f) if f.is_integer() else f
    raise TypeError(f"not JSON serializable: {type(o).__name__}")


def rel(p) -> str:
    return WORKDIR.sub("", str(p or ""))


def module_of(path) -> str:
    r = rel(path)
    return r.split("/")[0] if "/" in r else "(root)"


def module_of_node_id(nid) -> str:
    """Graph ids are `<name>@<file>` — the file half decides the module."""
    _, _, f = str(nid or "").partition("@")
    return module_of(f)


def survey(ground: Path) -> Counter:
    c = Counter()
    with ground.open("rb") as f:
        for fn in ijson.items(f, "analysis.functions.item"):
            c[module_of(fn.get("file"))] += 1
    return c


class Parts:
    """Per-module, per-section JSONL sinks. One line per item, appended as the
    single pass encounters it."""

    def __init__(self, root: Path, modules):
        self.root, self.modules = root, list(modules)
        self.fh = {}
        for m in self.modules:
            (root / m).mkdir(parents=True, exist_ok=True)

    def write(self, module: str, section: str, obj) -> None:
        key = (module, section)
        if key not in self.fh:
            self.fh[key] = (self.root / module / f"_{section}.jsonl").open("w")
        self.fh[key].write(json.dumps(obj, default=_plain) + "\n")

    def close(self):
        for h in self.fh.values():
            h.close()

    def read(self, module: str, section: str):
        p = self.root / module / f"_{section}.jsonl"
        if not p.is_file():
            return []
        with p.open() as h:
            return [json.loads(l) for l in h if l.strip()]

    def cleanup(self, module: str):
        for p in (self.root / module).glob("_*.jsonl"):
            p.unlink()


def slice_all(ground: Path, modules, outdir: Path) -> list:
    want = set(modules)
    parts = Parts(outdir, modules)
    stats = {m: Counter() for m in modules}
    prov, schema = {}, ""

    # --- pass 1: functions -------------------------------------------------
    with ground.open("rb") as f:
        for fn in ijson.items(f, "analysis.functions.item"):
            m = module_of(fn.get("file"))
            if m in want:
                parts.write(m, "functions", fn)
                stats[m]["functions"] += 1

    # --- pass 2: flows (the CFGs; SHAPE indexes these by function_name) -----
    with ground.open("rb") as f:
        for fl in ijson.items(f, "analysis.flows.item"):
            m = module_of(fl.get("file"))
            if m in want:
                parts.write(m, "flows", fl)
                stats[m]["flows"] += 1

    # --- pass 3: files -----------------------------------------------------
    with ground.open("rb") as f:
        for fl in ijson.items(f, "analysis.files.item"):
            m = module_of(fl if isinstance(fl, str) else (fl or {}).get("path", ""))
            if m in want:
                parts.write(m, "files", fl)
                stats[m]["files"] += 1

    # --- pass 4: symmetry --------------------------------------------------
    # Items frequently carry no top-level `file`; the real location lives in
    # properties.locations. Unattributed evidence goes to EVERY slice rather
    # than being dropped — losing the symmetry channel would degrade the run,
    # and duplication across slices is honest over-production (eta).
    with ground.open("rb") as f:
        for it in ijson.items(f, "symmetry.item"):
            locs = (it.get("properties") or {}).get("locations") or []
            f0 = it.get("file") or (locs[0].get("file") if locs else "")
            if f0:
                m = module_of(f0)
                if m in want:
                    parts.write(m, "symmetry", it)
                    stats[m]["symmetry"] += 1
            else:
                for m in modules:
                    parts.write(m, "symmetry", it)
                    stats[m]["symmetry_unattributed"] += 1

    # --- pass 5: graph edges ----------------------------------------------
    with ground.open("rb") as f:
        for e in ijson.items(f, "graph.edges.item"):
            a = module_of_node_id(e.get("from"))
            b = module_of_node_id(e.get("to"))
            for m in ({a, b} & want):          # <<< EITHER endpoint. Not both.
                parts.write(m, "edges", e)
                stats[m]["edges"] += 1
                if a != b:
                    stats[m]["edges_crossing"] += 1

    # --- pass 6: graph nodes (a map, keyed by `<name>@<file>`) -------------
    with ground.open("rb") as f:
        for nid, node in ijson.kvitems(f, "graph.nodes"):
            m = module_of_node_id(nid)
            if m in want:
                parts.write(m, "nodes", [nid, node])
                stats[m]["nodes"] += 1

    # --- pass 7: the small top-level scalars -------------------------------
    with ground.open("rb") as f:
        for k, v in ijson.kvitems(f, ""):
            if k == "_provenance":
                prov = v
            elif k == "schema":
                schema = v

    parts.close()

    out = []
    for m in modules:
        s = stats[m]
        p = dict(prov or {})
        p["slice"] = {
            "module": m,
            "of_ground": str(ground),
            "kind": "module_projection",
            "note": ("PARTIAL by construction: functions/flows/files scoped to this module; graph "
                     "edges retained when EITHER endpoint is in the module, so cross-module calls "
                     "survive as references. Claim counts are NOT comparable with a whole-repo "
                     "ground."),
            "edges_total": s["edges"],
            "edges_crossing_boundary": s["edges_crossing"],
            "symmetry_unattributed_shared": s["symmetry_unattributed"],
        }
        doc = {
            "schema": schema,
            "_provenance": p,
            "analysis": {
                "files": parts.read(m, "files"),
                "functions": parts.read(m, "functions"),
                "flows": parts.read(m, "flows"),
            },
            "graph": {
                "nodes": dict(parts.read(m, "nodes")),
                "edges": parts.read(m, "edges"),
            },
            "symmetry": parts.read(m, "symmetry"),
        }
        dest = outdir / m / "ground.json"
        dest.write_text(json.dumps(doc, default=_plain))
        parts.cleanup(m)
        out.append({"module": m, "bytes": dest.stat().st_size, **dict(s)})
    return out


def main(argv):
    if len(argv) < 3:
        print(__doc__, file=sys.stderr)
        return 1
    ground, outdir = Path(argv[1]), Path(argv[2])
    mods = argv[3:]
    if not mods:
        for m, n in survey(ground).most_common():
            print(f"   {m:24s} {n:6d}")
        return 0
    for st in slice_all(ground, mods, outdir):
        print(f"  {st['module']:14s} fns {st.get('functions',0):6d}  flows {st.get('flows',0):6d}  "
              f"edges {st.get('edges',0):7d} ({st.get('edges_crossing',0)} crossing)  "
              f"sym {st.get('symmetry',0)+st.get('symmetry_unattributed',0):5d}  "
              f"{st['bytes']/1048576:8.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
