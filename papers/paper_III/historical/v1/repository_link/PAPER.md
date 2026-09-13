# Paper and software version map

Primary reference: Leonid Shcherbakov, *QKF-Certifier: finite quotient kernels and width-independent KnownBits proofs*, QKF Paper III, preprint v1.0, manuscript revision 12 September 2026.

Permanent paper links are pending actual Zenodo deposition. Add the version DOI for this text and the concept DOI for the evolving record; neither can be inferred from the software URL. The machine-readable map is `docs/paper-version.json` in the repository root's path convention (from this file, [paper-version.json](paper-version.json)).

| Axis | Version described by Paper III v1.0 |
|---|---|
| Software release | v0.1.0a1 |
| Audited commit | f93561682319e8b911ed32c01583f2a496dc59fc |
| Certificate format | qkf-rewrite-v3 |
| Result format | qkf-result-v1 |
| Semantic contract | total-transfer-words-v2; positive-width; modular-arithmetic; SMT-total-div-shift; standard-counts; nonbottom-KB |

Paper I establishes initial semantics, forced quotients, and completion. Paper II establishes finite-ground equality visibility and certificates, separating congruence-proof depth from sequential rewrite depth. Paper III specifies the algorithmic kernels and the public certifier. The shared four-element example has five interface classes at horizon one and three at horizon two; its missing action value is forced, not external.

| Claim | Scope and implementation |
|---|---|
| K1 | Finite partial core; inherited ground locality; supplement reference. |
| K2 | Exact full relation-matrix closure; supplement reference. |
| K3 | Sparse semilattice refinement, conditional on exact local closure, representation coverage, feedback, and a genuine fixed point. Historical C++ research backend is separate. |
| K4 | Source reconstruction, semantic guards, local replay, and source-to-verdict composition; frontend.py, certificate.py, kernel.py. |
| K5 | Nine-row all-width criterion, exact 18-bit quotient, and sound precision classes; kernel.py and supplement checks. |
| TERM | Decrease of expanded tree nodes plus addition occurrences for all 29 rules. |
| MONO | Additional monotone class counts 26/26/16; supplement only, no release flag. |

The Python implementation has mathematical correctness arguments and finite regression evidence. It is not a proof-assistant-verified executable, and the paper does not verify arbitrary compiler lowering. `normalized` proves equivalence only; unsupported residuals require fallback. A target must be accepted from a `certified` result.

## Updating together

1. Record the new source commit, software version, schema, and semantic contract. Preserve this historical row.
2. Identify affected claims. New rules need semantic proofs, guards, and a termination review. New frontend semantics need a contract update. Cross-bit targets need a theorem beyond nine coordinatewise rows.
3. Run source/certificate binding tests and relevant concrete checks. Preserve JSON evidence and exact source hashes.
4. Update Paper III and its claim map when scope, semantics, the trusted rules, or reported results change. Pure editorial repository edits need not change mathematical claims.
5. Deposit a new version of the Paper III record when the manuscript changes. Link the release to the specific version DOI; use the concept DOI for the general evolving-paper link.
6. Update `CITATION.cff`, the README, and `docs/paper-version.json` after the real DOI is available. Keep software and paper versions distinct.

Do not reinterpret an old certificate schema under changed semantics. K3 integration also requires explicit non-success on pass-budget exhaustion. Minimum rewrite length, minimum depth, confluence, general arithmetic coverage, and speedup over the upstream synthesis system are not current guarantees.
