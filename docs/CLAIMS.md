# Manuscript 2.0: claim and evidence map

Claims are scoped to their named source and semantic contract. Finite experiments
support implementation checks; the width-independent conclusions use the stated
mathematical induction or the explicitly identified Lean theorem.

| Claim | Statement | Principal files and evidence |
|---|---|---|
| K1 | Finite ground partial core | `papers/paper_III/source/02_finitecore.tex`; Paper I; `papers/paper_III/historical/v1/verification/core_results.json` |
| K2 | Exact relation-matrix closure | `papers/paper_III/source/03_relations.tex`; historical/v1 `evidence_sources/relation_matrix_exact.py` and independent matrix/ground checks |
| K3 | Conditional sparse representation | `papers/paper_III/source/04_sparse.tex`; historical/v1 sparse prototype. The old 100-pass limit is not a fixed-point guarantee |
| K4 | Source / replay / target composition | `src/qkf_certifier/frontend.py`, `certificate.py`, `kernel.py`; original tests and new package validation |
| K5 | Complete coordinatewise quotient and nine-row semantics | `src/qkf_certifier/kernel.py`; 29 rules unchanged; historical finite classification and concrete-word checks |
| K6 | Sufficient observations and labeled word reconstruction | `research/knownbits/observation_kernel.py`, `context_kernel.py`, `result_kernel.py`, `symbolic/producer_v6.py`; `research/history/word_reconstruction/` |
| K7 | Forced rows and arbitrary-length gluing | `research/graal/previous/row_kernel.py`, `carry_kernel.py`; Lean `QKF/RowRules.lean` and `QKF/Gluing.lean` |
| K8 | Exact upper masked maximum and empty-case distinction | `research/graal/previous/universal_kernel.py`, `sweep_kernel.py`, `order_kernel.py`; saved upper certificate and replay |
| K9 | Conditional lower joint-carrier preservation | `research/graal/lower_kernel.py`, `carry_kernel.py`; saved lower certificate and replay; requires lower <= 0 or may-sign = 0 |
| K10 | Lean ascending fragment and modeled source cells | `research/lean/QKF/WordSemantics.lean`, `SourceBridge.lean`, `Checked.lean`, `Audit.lean`; fresh `lake build` |

TERM and MONO from manuscript v1 remain supplementary claims: the decreasing
rewrite measure and the additional 26/26/16 monotone sound-class counts. They do
not expand the supported public target language.

## Evidence populations

| Population | Result | Record |
|---|---|---|
| Current original KnownBits corpus | 11/39 whole programs; 104/411 components | `research/knownbits/COVERAGE_RU.md`; restored `results_v2/observed/summary.json`; current replay logs |
| Known LLVM transcriptions | Historical development 11/11 | `research/history/gcc/frozen_core_report.md` |
| Selected frozen external GCC cases | Historical 9/9 | `research/history/gcc/FINAL_SUMMARY.json` |
| Full Graal mask outcomes | Control 1/5, joint 2/5 | `research/graal/previous/baseline/REPORT_RU.md` and saved joint replay |
| Whole-word reconstruction | Historical 4905 to 530 total steps; 4401 to 26 subproof | `research/history/word_reconstruction/FINAL_SUMMARY.json` and report |
| SMT comparisons | Historical, contract/encoding/budget specific | `research/history/smt_corpus/`, `research/history/smt_contracts/` |

The upper/lower helper theorems are separate from the five-procedure Graal
population. Neither theorem adds a full `create` result. The Lean theorem is
about the mathematical successor and explicit nonsign source-cell model, not the
whole lower Java helper or Python checker. Producer discovery is not Lean-checked.

`RELEASE_MANIFEST.json` binds the candidate source bytes. The immutable public
baseline is `f93561682319e8b911ed32c01583f2a496dc59fc`. Source-binding checks do not
establish that upstream semantics or arbitrary source translations are correct.
