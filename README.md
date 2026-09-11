# QKF Certifier

[![Test and build](https://github.com/Len989/QKF-Certifier/actions/workflows/ci.yml/badge.svg)](https://github.com/Len989/QKF-Certifier/actions/workflows/ci.yml)

**A small, dependency-free checker for width-independent KnownBits certificates.**

QKF Certifier reads a supported subset of transfer MLIR, proves local simplifications,
then checks the remaining coordinatewise function on all nine one-bit KnownBits
input pairs. For this fragment, the certificate establishes soundness for **every
positive bit width**, and reports whether the transformer is optimal.

Version **0.1.0a1** is an alpha research tool with a usable CLI, Python API, tests,
and independently replayed rewrite certificates. It currently completes proofs for
real AND, OR, and XOR transformers from the NiceToMeetYou artifact. Other operations
can be normalized, but may require another verifier. This is not a general MLIR
verifier or a replacement for an entire synthesis system.

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

## Evidence and development

The precursor study checked three real transformers, 680 program mutations,
22,140 exhaustive abstract-input pairs, and 3,150 random pairs. A 39-program corpus
showed complete coordinatewise proofs for 3 programs. These are bounded empirical
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
The [local validation record](docs/LOCAL_VALIDATION.md) describes the earlier
local preparation checks.

## License and provenance

QKF Certifier code is distributed under MIT. The five small upstream MLIR examples
retain the MIT license and attribution of the pinned xdsl-smt artifact; see
[NOTICE.md](NOTICE.md). No affiliation with the NiceToMeetYou authors is implied.
The package is one concrete application of the QKF research line, not a distribution
of every algorithm or theorem developed in that research.
