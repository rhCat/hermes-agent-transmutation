# Project history

How this analysis was actually produced, in order, including the things that went wrong.
The [README](README.md) says what the result *is*; this says what it cost to get right, and
[BREAKPOINT.md](BREAKPOINT.md) says where it stands now.

It is written down for one reason. Every serious defect in this run **exited 0 and produced a
plausible number.** Not one announced itself. A history that recorded only the successes would
teach the wrong lesson about which checks are load-bearing.

---

## 1 — Target

`NousResearch/hermes-agent` at `main`, commit `0a2c245cd6af3dfcdde3f61077f7429bb9c8a48a`.
Registered in the warehouse as `hermes-agent-prod-0a2c245c` — `<project>-<tier>-<hash>`, generated
by tooling, never typed by hand, because that name is the join key for every later stage.

## 2 — Calcination, and a repo that analysed 6% of itself

The first submission returned green over **224 of 3,448 Python files.**

`hermes_cli/setup.py` trips the analyser's Python monorepo detection; sub-package detection then
returns `[hermes_cli]` alone, and `agent/`, `tools/`, `gateway/` and every root module are dropped
without a word. Passing `subpath: "."` forces a single analysis root over the whole tree, which
restores coverage *and* keeps the run single-package — the condition under which the analyser emits
the flow map at all.

**The tell was not the exit code. It was the file count being an order of magnitude too small.**

## 3 — A worker that analysed the wrong tree and stamped it with the right sha

Found while chasing a different discrepancy. The worker resolved refs with `git rev-parse` **without
`--verify`**, and did not check the return of the subsequent `reset`. A ref it could not resolve
therefore left the work tree on whatever was checked out — usually `main` — while the artifact was
still stamped with the *requested* commit.

Fixed in `worker_api.py` by extracting two checked helpers:

```python
def resolve_commit(repo_dir, ref, runner=None):
    r = runner(["git", "-C", str(repo_dir), "rev-parse", "--verify", "--quiet",
                f"{ref}^{{commit}}"], capture_output=True, text=True)
    if r.returncode or not r.stdout.strip():
        raise RuntimeError(f"Cannot resolve ref '{ref}'")
    return r.stdout.strip()
```

plus a `FETCH_REFSPEC` set on clone and before every fetch, so branch refs actually exist locally.

Two of my own diagnoses were wrong first — "the analyser drops files", then "only the first clone is
honest" — and both were killed by a counterexample: the CVE repos, which clone specific labelled
commits and had always been correct. **The counterexample did the work, not the theory.**

The nastiest property is self-perpetuation: a poisoned run stamps the requested sha, so the
idempotency check then *skips* the honest re-run. Recovery needs a fresh warehouse name, not a retry.

## 4 — Ingest

`/run-conservation-stack` exited 4 on `fk_car_crate_name`. The repo had never been ingested; the FK
was telling the truth. A scoped ingest with `expected_version: "0.9.0"` cleared it.

## 5 — Citrinitas, and slicing as projection

The whole-tree ground is **2.04 GB**, which SHAPE must load entire. So the repo was analysed whole
and the *ground* projected per module — not the same as analysing the modules separately:

- **Partitioning the analysis** walks each module blind to the others and destroys every
  cross-module edge at the boundary. Unrecoverable.
- **Projecting a whole ground** keeps them. `slice_ground.py` retains every edge with **either**
  endpoint inside the module.

In the `agent` slice, 84% of edges cross the boundary; in `cron`, 88%. A both-endpoints rule would
have discarded most of the call structure and every downstream claim would have described a
codebase that does not exist.

Two slicer defects on the way: `Decimal` is not JSON-serialisable (which surfaced only at the final
write, after all the work), and the first design made seven passes per module — 70 GB of reads —
before being cut to one pass per section.

## 6 — The wrong-column family

Three defects, one shape: **read the wrong field of a record that has the right one nearby.**
None raised. Each silently discarded a large fraction of the result.

| where | read | should have read | cost |
|---|---|---|---|
| `fixatio._compose_marble` | `contract_at_rest.fn_name` — a display *title* | `blueprint_id` → `synth_<bare>` | resource books empty, 0/53 binding |
| `_engine._derive_from_symmetry` | `item["locations"]` | `properties.locations` | every control/error book — 6,123 claims |
| `find_twins.signature` | `claim["bound"]` | `claim["target"]["bound"]` | 100% of bounds; "71,296 removable LOC" was really 23,490 |

In all three the **correct** field was already used elsewhere in the same file. A file that reads one
record two different ways is the strongest available signal.

What caught them was never a count. `stats.functions > 0` passed every time. What caught them was
`len(ledger_keys & ground_names)` — verifying a join by its **overlap**, not by its totals — and
noticing that a "twin group" of 175 functions had a signature that was merely
gates-absorbs-returns.

`degradations: []` sat there through all of it, reporting a healthy channel that was contributing
nothing. That is worse than the honest-empty case the doctrine promises, because the loss was not
ledgered.

## 7 — Placement, and a blessing that must be re-earned

`fixatio` and `putrefactio` are **cooperative-only** — they do not exist on the delegated node.
Submitted delegated, they failed quietly. Checking where a perk actually lives is part of
submitting it.

Separately: editing `stages.json` invalidated the blessed skill index —
`registry authenticity failed: ['changed: stages.json']`. I had said no restart was needed. Wrong:
the index covers the whole skill tree, so **any** file change re-blesses `skill_sha` and
invalidates cooperative runs until the node is restarted.

## 8 — Publishing

The page returned 200 while every data file 404'd: `data/` sat outside the `/docs` Pages root.
`git mv data docs/data` fixed it. *Status codes on the page you asked for say nothing about the
files it fetches.*

## 9 — The viewer

Built in three passes, each of which exposed something about the data.

**Browse** — module → file → function → claim, with every claim one click from its source line at
the analysed commit.

**Atlas** — the call graph at *file* level, because 994,093 function edges is not a picture. Two
defects here. A canvas is a replaced element, so `inset: 0` alone left it at its intrinsic 300×150
and the map drew into a stamp. And the first aggregation keyed on the raw edge id — but edge ids
carry **extension-less** paths (`cron/scheduler_provider`) while claims carry real ones
(`cron/blueprint_catalog.py`), so every file appeared in the graph twice and `pub` was false for all
209,323 edge endpoints. Resolving endpoints through the ground's own node records collapsed 5,221
"files" to 4,687 and recovered the 19,059 edges the published subgraph always had.

**Call lists** — originally keyed by bare function name, which merged every `get` in the tree into
one entry with 9,150 callers, and were then capped at 24 to keep that payload down. Keying by
`name@file` and sharding one JSON per source file ships them whole: 534 shards, 956,842 entries,
~53 KB fetched per file opened, replacing a 14.6 MB blob.

Precise keys then made visible what the merge had hidden: `get@gateway/platforms/api_server.py`
*still* has 9,095 callers spanning every module. That is the analyser binding every call of a common
name to one definition — not fan-in. The page says so rather than presenting the number flat.

One more, worth its own line: the row lists were first rendered across animation frames to keep the
UI smooth. Backgrounding the tab stopped the loop, leaving a list that ended at row 400 of 9,175
with nothing to indicate it. **A slow complete list beats a fast silently-truncated one.** It builds
synchronously now.

## 10 — What the tree is made of

Measured over the whole-tree ground, not just the published slice:

| | test | non-test | share |
|---|---|---|---|
| files | 2,940 | 2,224 | 57% test |
| functions | 69,263 | 43,722 | **61% test** |
| file extent (last-line proxy) | 954,880 | 1,009,562 | 49% test |

Test-majority by count, about even by volume — many short test functions. They also sit on 60% of
the file-to-file edges, which is why the atlas has a *hide tests* toggle: with them out, the wide
view drops from 2,804 files to 909, and what is left is the application graph.

---

## The one lesson

Verification by **status** caught nothing in this run. Verification by **content** caught everything:

- overlap counts, not totals (`ledger_keys & ground_names`)
- trap functions known to exist only at one commit
- adversarial probes — submitting a deliberately bogus sha and requiring failure
- reading the numbers for shape: a file count 10× too small, a signature too generic to mean
  anything, a "degradation-free" channel next to a missing book
