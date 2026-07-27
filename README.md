# hermes-agent — mechanical transmutation

A structural analysis of [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent),
produced by the **mechanical** half of the Cyberware Alchemistry pipeline and published as a
static, browsable page.

**[→ View the result](https://rhcat.github.io/hermes-agent-transmutation/)**

Everything here is derived. No source code from the analysed repo is reproduced — the artifacts
carry names, shapes, counts and positions only.

```
commit     0a2c245cd6af3dfcdde3f61077f7429bb9c8a48a   (main, 2026-07-27)
analysed   94,547 functions / 5,036 files — the WHOLE tree, one analysis root
published  21,909 claims over 535 files in 5 source modules
books      RETURN 9,830 · ABSORB 3,343 · GATE 2,780 · ALTER_STATE 2,520
           NO_EFFECT 1,294 · RAISE 1,038 · RELEASE 828 · ACQUIRE 276
channels   flows · functions · graph · symmetry · ledger      degradations: none
llm_calls  0
```

---

## What "mechanical" means

The pipeline has a deliberate seam. Everything in this repository comes from **before** it:

| | reads | dispatches an LLM | asserts |
|---|---|---|---|
| **mechanical** (here) | the code's structure | **never** — `llm_calls: 0` | what the code *structurally does* |
| semantic (not here) | the code's docs | yes, once, quarantined | whether that matches what it *says* |

So these are **claims, not findings**. A claim is a ledger posting: *this function acquires a
socket on some paths*, *this one returns on all paths*. It is not a bug report, and nothing here
says any of it is wrong. Judging that requires the semantic half, which was not run.

The one thing worth stating plainly: an unwitnessed structure is recorded as **absent**, never
guessed. Where a channel was missing the run says so rather than filling the gap — a claim with no
evidence behind it would be worse than no claim.

## The four stages that ran

| stage | what it does | output |
|---|---|---|
| **calcination** | burn the code to its ash — parse to functions, CFG, symmetry, blueprints; register in the warehouse | evidence plane |
| **citrinitas** | compose the scattered evidence into one *ground* (functions + flows + symmetry + graph) | `ground.json` |
| **fixatio** | fix the volatile: resolve each function's resource lifecycle into a durable ledger | `ledger.json` |
| **putrefactio** | hard-gate the channels, then map the ground into intent-shape claims | `mechanical_claims.json` |

Stages 5–7 (cibatio, rosarium, coniunctio) were **not** run. See *Not here*, below.

## How it was run — the governed channel

Every stage was submitted as a **claim** to a cyberware governance node, never as an ad-hoc
command. The agent emits only a skill name, a perk name and var **keys**; the node blesses a
value-free plan and records the run. Artifacts return on a shared mount — the wire itself carries
status only.

```jsonc
// stage 2 — citrinitas
{ "skill": "magnumopus:transmutation", "perk": "citrinitas",
  "record_store": "${CARGO}/citrinitas",
  "vars": { "ALEMBIC_WORKER_URL": "${WORKER}", "TARGET": "hermes-agent-prod-0a2c245c" } }

// stages 3+4 — fixatio (stage 0 of the perk) then shape
{ "skill": "magnumopus:transmutation", "perk": "putrefactio",
  "record_store": "${CARGO}/putrefactio-fixatio",
  "vars": { "GROUND_IN": "${CARGO}/citrinitas/ground.json", "FIXATIO": "1",
            "REPO": "hermes-agent-prod-0a2c245c", "LANGUAGE": "python",
            "DSN": "${DSN}", "ALEMBIC_WORKER_URL": "${WORKER}" } }
```

Infrastructure addresses and credentials are placeholders here by design; they are private
deployment detail, not part of the result.

## One finding about the *analysis*, worth publishing

Submitting this repo the obvious way analyses **6% of it**.

`hermes_cli/setup.py` trips the analyser's Python monorepo detection. Sub-package detection then
returns `[hermes_cli]` alone — and `agent/`, `tools/`, `gateway/` and every root module are
silently dropped. 224 of 3,448 Python files, with no error and a green exit.

Passing `subpath: "."` forces a single analysis root over the whole tree, which both restores full
coverage and keeps the run single-package — the condition under which the analyser emits the flow
map at all. Partitioning the repo by hand would have severed every cross-module call edge, which
is precisely the structure worth having.

This is the failure mode the pipeline is built around: **the exit code was honest about crashes
and silent about doing nothing.** Every figure on the page was checked by content, not by status.

## Slicing — a projection, not a partition

The whole-tree ground is **2.04 GB**, which SHAPE must load entire. Rather than analyse the repo
in pieces, it was analysed whole and the *ground* was then projected per module — a different
thing, and the difference is the whole point:

- **Partitioning the ANALYSIS** walks each module in ignorance of the others, destroying every
  cross-module call edge at the boundary. Unrecoverable.
- **Projecting a whole GROUND** keeps them: `slice_ground.py` retains every graph edge with
  **either** endpoint inside the module, so calls out of it survive as references.

That distinction is not academic. In the `agent` slice, **231,694 of 274,379 edges — 84% — cross
the module boundary**; in `cron` it is 88%. Narrowing the rule to *both* endpoints would silently
discard most of each module's call structure, and every downstream claim would describe a codebase
that does not exist.

Each slice stamps `_provenance.slice`, so a partial ground can never be mistaken for a whole-repo
one.

## Layout

```
docs/index.html       the static viewer (no build step, no dependencies)
docs/data/summary.json    the page's data — a projection of the claims
docs/data/artifacts/      the raw mechanical_claims per module + the walked ledger, gzipped
slice_ground.py       whole ground -> per-module grounds (streaming, constant memory)
build_summary.py      artifacts -> summary.json
```

Regenerate the page data with:

```sh
python3 build_summary.py docs/data/artifacts docs/data/summary.json
```

## Not here

- **The semantic half.** No `intent_difference` — nothing here compares the code to its own
  documentation. The claims are one side of a diff whose other side was not computed.
- **Judgment.** Over-produces by design and never prunes: a claim is a posting, not an accusation.
- **Resource books** are only as complete as the walked substrate for this commit; where the
  ledger is silent it is *honestly* silent rather than name-matched.

Read the stats bar first — `degradations` and `llm_calls` say how much of the page to trust.
