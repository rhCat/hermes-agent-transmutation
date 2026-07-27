#!/usr/bin/env python3
"""Cut the static page's data file from the transmutation artifacts.

The chain's own outputs are large (a full mechanical_claims.json for a repo this
size runs to tens of MB) and carry per-claim provenance the page never renders.
This projects them down to what the viz actually needs — and to nothing that the
value-free discipline would object to: names, shapes, counts, positions. No
source bodies, no argument values, no secrets.

usage: build_summary.py <artifact-dir> <out.json>
  <artifact-dir> holds mechanical_claims.json (+ optionally ledger.json and the
  citrinitas ground.json alongside, for the channel/flow figures).
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

# Cap what ships in the page. The full claim set is committed separately as the
# raw artifact; this is the browsable projection, and an unbounded one would
# make the page unusable rather than more honest.
MAX_CLAIMS = 12000

# The analyser records absolute paths inside its own scratch checkout, e.g.
#   /tmp/alembic-work/<repo_name>-<job_id8>/agent/tool_executor.py
# That prefix is build-host detail, not a property of the analysed code, and it
# has no business in a published artifact. Strip it to a repo-relative path.
_WORKDIR = re.compile(r"^.*?/alembic-work/[^/]+/")


def _relpath(p):
    return _WORKDIR.sub("", str(p or ""))


def _commit(mc, ground):
    """The commit the evidence was actually built from.

    NOT `commit_hash` — that key does not exist on this record, and reaching for
    it yields a silent empty string. The analyser writes `git_hash` (with
    `branch` echoing whatever ref was requested, which is why branch is not a
    substitute: a requested ref and an analysed tree are different claims).
    """
    md = (mc.get("provenance") or {}).get("metadata") or {}
    for src in (md.get("git_hash"), md.get("commit_hash"),
                ((ground or {}).get("_provenance") or {}).get("commit_hash")):
        if src:
            return str(src)
    return ""


def main(argv):
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 1
    d, out = Path(argv[1]), Path(argv[2])

    mc = json.loads((d / "mechanical_claims.json").read_text())
    claims_raw = mc.get("claims", [])
    ch = mc.get("channels", {})
    stats = mc.get("stats", {})

    shapes = Counter(c.get("shape") for c in claims_raw)

    claims = []
    for c in claims_raw[:MAX_CLAIMS]:
        tgt = c.get("target") or {}
        claims.append({
            "shape": c.get("shape"),
            "fn": c.get("fn"),
            "file": _relpath(c.get("file")),
            "line": c.get("line"),
            "quant": c.get("quant"),
            "guard": c.get("guard"),
            "bound": tgt.get("bound"),
        })

    meta = {
        "repo": mc.get("repo") or (mc.get("provenance") or {}).get("repo"),
        "commit": "",   # filled below, once the ground is loaded
        "functions": stats.get("functions"),
        "claims": stats.get("claims", len(claims_raw)),
        "claims_shown": len(claims),
        "evidence_units": stats.get("evidence_units"),
        "unmapped": stats.get("unmapped"),
        "channels": ch.get("present", []),
        "degradations": ch.get("degradations", []),
        "llm_calls": mc.get("llm_calls", 0),
        "docs_read": mc.get("docs_read", False),
        "purity_closure_complete": mc.get("purity_closure_complete"),
        "acquire": shapes.get("ACQUIRE", 0),
        "release": shapes.get("RELEASE", 0),
        "transfer": shapes.get("TRANSFER", 0),
        "by_shape": dict(shapes.most_common()),
        "files": len({_relpath(c.get("file")) for c in claims_raw}),
    }

    # The ground carries the flow count; it is the channel whose absence would
    # silently degrade every quantifier, so it is worth showing on the page.
    g = d / "ground.json"
    if not g.is_file():
        g = d.parent / "citrinitas" / "ground.json"
    if g.is_file():
        try:
            gd = json.loads(g.read_text())
            a = gd.get("analysis", gd)
            meta["flows"] = len(a.get("flows") or {})
            meta["symmetry"] = len(gd.get("symmetry") or [])
        except Exception:
            gd = None
    else:
        gd = None
    meta["commit"] = _commit(mc, gd)

    # The walked resource ledger, when fixatio ran.
    led = d / "ledger.json"
    if led.is_file():
        try:
            L = json.loads(led.read_text())
            meta["ledger"] = L.get("stats", {})
        except Exception:
            pass

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"meta": meta, "claims": claims}, indent=1))
    print(f"summary -> {out}  ({len(claims)} of {len(claims_raw)} claims, "
          f"{meta['files']} files, shapes {dict(shapes.most_common(5))})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
