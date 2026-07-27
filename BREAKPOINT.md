# Breakpoint

State of this project as of **2026-07-27**. A breakpoint is not a changelog — it records where the
work stands, what is deliberately absent, and what a next session would need to know before
touching anything. [HISTORY.md](HISTORY.md) records how it got here.

---

## §1 Current state

| | |
|---|---|
| target | `NousResearch/hermes-agent` @ `0a2c245cd6af3dfcdde3f61077f7429bb9c8a48a` |
| warehouse name | `hermes-agent-prod-0a2c245c` |
| stages run | calcination · citrinitas · fixatio · putrefactio (shape) |
| stages not run | cibatio · rosarium · coniunctio |
| published | 21,909 claims over 535 files in 5 modules · `degradations: []` · `llm_calls: 0` |
| page | https://rhcat.github.io/hermes-agent-transmutation/ — browse · atlas · similar functions |

Analysed **whole tree, one analysis root** (`subpath: "."`). The ground was then projected — not
partitioned — into five module slices; each stamps `_provenance.slice`.

## §2 What the page covers, and what it does not

The five analysed modules hold 12,720 functions. The tree holds **43,722 non-test functions**, so
the published claims cover about **29% of the non-test code**.

The largest uncovered bodies:

| module | non-test functions | in the analysed set? |
|---|---|---|
| `apps/` | 12,394 | no |
| `hermes_cli/` | 5,697 | yes |
| `plugins/` | 4,872 | no |
| `agent/` | 3,739 | yes |
| `tools/` | 3,600 | yes |
| `ui-tui/` | 3,425 | no |
| `gateway/` | 2,972 | yes |

`apps/` being the single largest non-test module and entirely absent is the most consequential gap.
Extending the slice set is mechanical — `slice_ground.py` over the same 2.04 GB ground, then
fixatio + shape per slice — and needs no re-analysis.

## §3 Known limits — read before trusting a number

**Analyser name-resolution collapse.** Calls resolve by name, so a common method binds every
call-site in the tree to one definition. `get@gateway/platforms/api_server.py` carries 9,095
callers spanning every module; that is not fan-in. The page flags any fan-in above 800 rather than
presenting it flat. **Never read a large caller count as a dependency count.**

**4,110 unresolved paths in the file graph.** Edge endpoints outside every slice have no node
record, so they keep their extension-less path (`tui_gateway/server`, not `…/server.py`). They are
counted in `graph.json` `meta.unresolved` and carry no claims. Source links are suppressed for them
because the path would 404.

**Function-count discrepancy, unreconciled.** The ground carries **112,985** `Function` nodes;
calcination reported **94,547** for the same tree — about 19% apart. Likely a difference in what
each counts as distinct (nested/closure definitions being the usual culprit), but it was not chased
down. Ratios computed within one source hold; treat cross-source absolutes as approximate.

**Resource books are only as complete as the walked substrate** for this commit. Where the ledger is
silent it is honestly silent rather than name-matched — an absence here means *not witnessed*, not
*does not exist*.

**Similar-function groups over-produce by design.** A shared `shape·bound·quant` signature is
evidence of mechanical similarity, not a duplicate. Judging that is the semantic half's job.

**The last-line LOC proxy** in §10 of HISTORY is `max(line)` per file, i.e. file extent, not
counted lines of code. Good enough for a ratio, wrong for a budget.

## §4 Open work

| | what | blocked on |
|---|---|---|
| 1 | **cibatio** — the one LLM seam | litellm `.env` needs `LOCAL_LLM_TOKEN`; gateway is up on the tailnet, pinned, with its backing DB |
| 2 | **rosarium · coniunctio** — the information plane and the witness union | (1) |
| 3 | extend slices to `apps/`, `plugins/`, `ui-tui/` | nothing — ground is on disk |
| 4 | reconcile the 112,985 / 94,547 function count | nothing |
| 5 | `docs/cibatio-intel-url` branch — INTEL URL as a passed-in var, not hardcoded | pushed, no PR opened; node restart sits behind it |

## §5 Operational notes that cost time to learn

**Perk placement is not uniform.** `fixatio` and `putrefactio` are cooperative-only. Submitting
them delegated fails quietly. Check where a perk lives before submitting it.

**Any file change in a skill tree re-blesses `skill_sha`** and invalidates cooperative runs until
the node is restarted — including a change to a data file like `stages.json`. There is no partial
re-blessing.

**A poisoned artifact self-perpetuates.** Because a bad run still stamps the *requested* sha, the
idempotency check will skip the honest re-run. Recovery requires a fresh warehouse name, not a
retry.

**Nothing goes through ad-hoc shell.** Every stage was submitted as a claim to a governance node,
which blesses a value-free plan; the agent emits skill name, perk name and var *keys* only.
Artifacts return on a shared mount and the wire carries status.

## §6 Reproduce

```sh
# ground -> per-module slices (streaming, constant memory)
python3 slice_ground.py <ground.json> <slices-dir>

# artifacts -> the page's data
python3 build_summary.py  docs/data/artifacts docs/data/summary.json
python3 find_twins.py     <merged-claims.json> docs/data/twins.json
python3 build_graph.py    <slices-dir> <merged-claims.json> docs/data/graph.json
python3 build_calls.py    <slices-dir> <merged-claims.json> docs/data/calls
```

`build_graph.py` and `build_calls.py` both resolve extension-less edge endpoints through the
ground's node records. That resolution is not optional — skipping it silently doubles the node set
and disconnects every published file. See HISTORY §9.
