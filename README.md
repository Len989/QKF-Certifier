# QKF Certifier

[![Test and build](https://github.com/Len989/QKF-Certifier/actions/workflows/ci.yml/badge.svg)](https://github.com/Len989/QKF-Certifier/actions/workflows/ci.yml)

**Width-independent proof certificates for KnownBits and word programs, with research tools and scoped Lean 4 soundness proofs.**

[Release 0.3.0a1 notes](releases/v0.3.0a1.md) · [Papers](#papers) · [Research instructions](research/README.md) · [Русская версия](README_RU.md)

QKF develops proofs from incomplete observations, forced rows, their kernels,
and compatible quotients. The research tools explore how those observations
can determine a computation and compose across an arbitrary word width.

## Papers

The three preprints by **Leonid Shcherbakov** develop the foundations and the
certificate architecture in sequence:

| Paper | Title and published record | Focus |
|---|---|---|
| I | [Initial semantics of incompletely specified actions: forced quotients, kernel saturation, and completion](https://doi.org/10.5281/zenodo.22736397) | Forced equalities, determined action values, and carrier-valued completion. |
| II | [Equality-visibility depth in equational presentations: finite-ground spectra, certificates, and semigroup space](https://doi.org/10.5281/zenodo.22736558) | Equality visibility, proof horizons, and certificates. |
| III | [QKF-Certifier: observation kernels and width-independent word proofs](https://doi.org/10.5281/zenodo.22736714) | Observation-based word proofs, research evidence, and the Lean pilot. |

Start with Paper III for the algorithm and experiments, then Papers I and II for
the mathematical foundations. The DOI links identify the published preprints.
The Paper III DOI above identifies the earlier published record. This checkout
contains [Paper III v3.0](papers/paper_III/QKF_PAPER_III_v3.0_2026-09-22.pdf),
prepared on 22 September 2026 for a new Zenodo version. Its new DOI is not yet
assigned; see the [paper/code map](docs/paper-version.json).

## Software and current scope

QKF Certifier reads a supported subset of transfer MLIR, proves local simplifications,
then checks the remaining coordinatewise function on all nine one-bit KnownBits
input pairs. For this fragment, the certificate establishes soundness for **every
positive bit width**, and reports whether the transformer is optimal.

Version **0.3.0a1** is a research alpha release candidate based on the accepted
implementation through PR51. It adds source-derived observation inference,
independent target proofs, signed source interfaces, typed ground proof DAGs,
checked cross-goal lemmas, reusable contexts, direct dependency emission, and
standalone Lean proofs for ground soundness and chronological composition.

The ordinary SDK and query-directed SDK are both QKF implementations. The
registered development comparisons retain the ordinary SDK as the less costly
matched control; direct emission reduces overhead within the newer path without
establishing a general speed advantage. See the [complete changes and measured
scope](releases/v0.3.0a1.md) and [PR inventory](releases/CHANGES_v0.3.0a1.md).

The installable CLI still completes coordinatewise AND, OR, and XOR proofs.
The research SDKs and formal projects require the full source archive or checkout.
The CLI runtime semantics and `qkf-rewrite-v3` certificate format are unchanged.

| New research layer | Entry point and scope |
|---|---|
| Inference and unified targets | [Inference](research/inference/README_RU.md), [runner](research/unified/README_RU.md) |
| Signed source observations and execution | [Bridge](research/signed_bridge/README_RU.md), [runtime](research/signed_runtime/README_RU.md), [targets](research/signed_targets/README_RU.md) |
| Ground DAGs and native source facts | [Ground queries](research/ground_query/README_RU.md), [source queries](research/source_query/README_RU.md) |
| Checked SDK and direct dependencies | [Applicable summaries](research/applicable_summary/README_RU.md), [direct emission](research/direct_emission/README_RU.md) |
| Lean ground and composition soundness | [Ground](formal/ground/README_RU.md), [composition](formal/composition/README_RU.md); decoded typed structures under explicit native assumptions |

## Retained v0.2.0a1 baseline

| Profile | Current result | How to use it |
|---|---|---|
| Installable Python CLI | Complete coordinatewise AND/OR/XOR proofs | `qkf verify` / `qkf check` |
| KnownBits research | 11/39 whole programs; 104/411 component proofs | Research replay runner |
| Graal research | Exact upper masked bound; conditional lower preservation | Research replay runner |
| Lean 4.33.0 pilot | Forced rows, carry factor, arbitrary-length gluing and numerical successor | `lake build` |

From a **full repository checkout or the research source archive**, with Python
3.12 on Linux/POSIX:

```sh
python tools/replay_research.py --suite all --output reproduction/run_01
```

This verifies and restores the packed data, then replays saved proofs without SMT
or producer search. Restored KnownBits JSON occupies about 488 MB. For Lean:

```sh
cd research/lean
lake build
```

The wheel and PyPI-style source distribution contain the coordinatewise Python
application. Use the full research archive for `research/`, `papers/`, and the
repository tools. See [research instructions](research/README.md),
[Paper III v3](papers/paper_III/QKF_PAPER_III_v3.0_2026-09-22.pdf), and the
[claim map](docs/CLAIMS.md).

The lower Graal theorem requires `lower <= 0` or a forbidden negative sign. It
preserves the joint mask/interval carrier and may return a conservative bound.
Later work supplies a source-bound Graal `create` joint-carrier profile and
conditional Lean caller-invariant lemmas. This is not end-to-end formal
verification of the Java frontend, complete JVM execution, or Python checkers. These results make no general speed claim over
SMT solvers. Historical and fresh validation records remain separate.

[Русская версия](README_RU.md) · [Semantics](docs/SEMANTICS.md) ·
[Certificate format](docs/CERTIFICATES.md) · [Release guide](docs/RELEASING.md)

## Install from this checkout

Python 3.10 or newer is required. No runtime dependencies or network access are
needed during verification. The package has not been published to PyPI.

```sh
python -m venv .venv
# Linux / macOS:
. .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install .
qkf --version
```

## Check a real transformer

From the repository root:

```sh
qkf verify examples/ntmy/xor.mlir --target xor --helper meet=examples/ntmy/meet.mlir --certificate xor-proof.json
qkf check examples/ntmy/xor.mlir --target xor --helper meet=examples/ntmy/meet.mlir --certificate xor-proof.json
```

Expected result: `certified`, with `all_positive_widths=true` and `optimal=true`.
The proof is bound to the exact UTF-8 contents of **both** source files. The target
is supplied independently by the caller; it is not taken on trust from a certificate.

```sh
qkf verify examples/ntmy/and.mlir --target and --json
qkf verify examples/ntmy/or.mlir --target or --json
qkf batch examples/batch.json --json
```

`--json` produces one machine-readable result on stdout. Existing certificate
files are preserved unless `--force` is supplied. Output files cannot replace
any input source file.

## Outcomes

| Status | Exit code | Meaning |
|---|---:|---|
| `certified` | 0 | Sound at all positive widths, under the documented semantics |
| `unsound` | 1 | A concrete one-bit counterexample was found |
| `fallback_required` | 2 | No complete verdict: unsupported syntax, target, residual operation, or complexity limit |
| `invalid_certificate` | 3 | The supplied proof is malformed or fails replay |
| `input_error` | 64 | Invalid arguments, unreadable files, or output conflict |
| `internal_error` | 70 | Unexpected implementation error; never treat as acceptance |
| `normalized` | 0 | **Only** expression equivalence proved by `normalize`/`inspect`; target soundness is unproved |

In automation, accept a transformer only when the result of **verify/check** has
`status == "certified"`. `normalized`, a timeout in another tool, and
`fallback_required` are not soundness results. Batch results have a status for
each item and return nonzero if any item is unresolved, invalid, or unsound.

## Normalization and semantic signatures

```sh
qkf normalize examples/fallback_add.mlir --certificate normalization.json --json
qkf check examples/fallback_add.mlir --normalization-only --certificate normalization.json --json
qkf inspect examples/ntmy/xor.mlir --helper meet=examples/ntmy/meet.mlir --json
```

`normalize` writes a proof of source-to-normal-form equality, even when cross-bit
operations remain. It does not emit optimized MLIR. `inspect` reports residual
operations and, where available, an exact 18-bit signature of the normalized
mask function. That signature supports semantic deduplication **within the stated
input contract**; soundness caches must also include the target and contract.

## Python API

```python
from pathlib import Path
from qkf_certifier import verify, check_certificate

sources = {
    "program": Path("examples/ntmy/xor.mlir").read_bytes().decode("utf-8"),
    "meet": Path("examples/ntmy/meet.mlir").read_bytes().decode("utf-8"),
}
result = verify(sources, target="xor")
assert result["status"] == "certified"
replayed = check_certificate(sources, "xor", result["certificate"])
assert replayed["optimal"]
```

Public API: `verify`, `check_certificate`, `normalize`, and `inspect`. Source labels
are part of the certificate binding. See [integration examples](docs/INTEGRATION.md).

## What is trusted?

The trusted implementation consists of the narrow frontend, call expansion,
local rewrite rules and their side conditions, proof replay, and nine-row checker.
The proof checker does **not** run the normalization search. Producer and checker
share the local rule implementations; this is not a Lean/Coq mechanization.

The contract uses nonempty KnownBits inputs, modular word arithmetic, standard bit
counts, and total SMT-style shifts/division. A proof does not certify a separate
compiler's implementation of those operations. See [the exact semantics and
limits](docs/SEMANTICS.md) before integrating a new dialect/backend.

## Baseline evidence and development

The precursor study checked three real transformers, 680 program mutations,
22,140 exhaustive abstract-input pairs, and 3,150 random pairs. A 39-program corpus
showed complete coordinatewise proofs for 3 programs in that precursor profile.
The separate current research profile proves 11/39; the denominators describe
different supported proof interfaces. These are bounded empirical
results, separate from the mathematical lifting argument. Selected results are
recorded in [benchmarks](benchmarks/README.md); they are not an end-to-end speed claim.

```sh
python -m pip install -e '.[dev]'
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m build
```

CI tests Linux/Python 3.10–3.14 and Python 3.12 on Windows/macOS, builds the
distributions, and checks the installed wheel outside the checkout. All eight
jobs passed for the first uploaded source snapshot; see the
[recorded successful run](https://github.com/Len989/QKF-Certifier/actions/runs/34636148287). The badge above links to current CI results.
The [original validation record](docs/LOCAL_VALIDATION.md) describes the earlier
preparation checks. [Candidate validation](docs/RELEASE_VALIDATION_0.2.0a1.md)
records the local checks for 0.2.0a1. On the merged release commit
`382fc5e2073746fe5154cb4fd781e863266cad55`, both
[Test and build](https://github.com/Len989/QKF-Certifier/actions/runs/34777754487)
and [Research and Lean](https://github.com/Len989/QKF-Certifier/actions/runs/34777754528)
passed. These are recorded results for that commit; consult Actions for later changes.

## License and provenance

QKF Certifier code is distributed under MIT. The five small upstream MLIR examples
retain the MIT license and attribution of the pinned xdsl-smt artifact; see
[NOTICE.md](NOTICE.md). No affiliation with the NiceToMeetYou authors is implied.
The wheel is the coordinatewise application. The full source release additionally
contains the selected research capsules and three manuscript packages; manuscript
licensing is described separately in their author-facing license notes.

## Release verification

The accepted research snapshot is `eca90f9252da4480d77c1f8cb4b7062470c57b89`.
Its Git tree equals the final PR51 tree. The exact PR51 head had 32 successful
workflow runs; the merge commit had six successful push workflows. These records
do not claim CI results for the later release documentation/version changes.
See [candidate validation](docs/RELEASE_VALIDATION_0.3.0a1.md) for the local
package checks and limitations, and [release preparation](docs/RELEASING.md).
