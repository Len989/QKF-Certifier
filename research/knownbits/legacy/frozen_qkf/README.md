# QKF: complete Umin proof and checked observer identities

Research extension, 12 September 2026. The **actual seven-component Umin
solution is certified for every positive width** under QKF's explicit total
word semantics. Corpus coverage increases from 70 to 82 component proofs
and from four to five complete source-solution proofs.

The new code is `observer_kernel.py`, contract `qkf-observer-identities-v1`.
It layers twelve checked rule families over the previous rewrite passes.
The count-mask relation backend and concrete target registry are unchanged.
This is a standalone research package for integration with the public project;
it is not an already merged public release feature.

Read `QKF_UMIN_COMPLETE_RU.md` for the Russian report,
`OBSERVER_PROOFS.md` for mathematics, and `CONTINUE_HERE.md` for the current
state and next research target. `PAPER_III_INSERT.md` contains a proposed
paper addition, not a replacement of a published paper or DOI version.

## Reproduce

Requirements: Python 3.10+ and Git. No third-party Python dependency or SMT
solver is required. This run used Python 3.12. Obtain a separate pinned checkout:

```bash
git clone https://github.com/Len989/QKF-Certifier.git qkf-pinned
git -C qkf-pinned checkout --detach f93561682319e8b911ed32c01583f2a496dc59fc
```

From this package directory, replace `/path/to/qkf-pinned` with its actual path:

```bash
python reproduce.py --repo /path/to/qkf-pinned --out rerun_results
```

This rebuilds the old normalization from the bundled source text, applies and
replays the observer identities, checks all 411 components against actual SSA,
produces and replays certificates, checks actual whole-solution composition,
and compares with the 70-proof baseline. An intermediate pickle is created
locally from those text fixtures; no cached pickle is shipped or required.

The prior frozen configuration describes the preserved earlier passes, not
the number of rules introduced by this extension. The new layer is described
in `EXTENSION_CONFIGURATION.json`. Source provenance and file hashes are in
`PROVENANCE.json` and `SHA256SUMS.txt`.

## Check the full Umin certificate without proof search

```bash
python verify_umin.py --repo /path/to/qkf-pinned --operator KnownBits_Umin --target umin
```

Expected: PASS, all positive widths, **26,346 valid transition checks**.
This includes replaying the seven component certificates and checking their
actual source composition through the actual meet helper.

To check just the last component, which uses the shifted-mask identity:

```bash
python verify_umin.py --repo /path/to/qkf-pinned --operator KnownBits_Umin --entry partial_solution_6 --target umin
```

Expected: PASS, **1,910 valid transition checks**. To use newly reproduced
certificates, add `--results rerun_results` to either command.

The verifier recomputes all relevant transitions and does not run reachability
search. It checks the caller-selected target, source normalization, both
rewrite traces, the derived expression/compilation hashes, and the invariant.

## Package map

| File or directory | Purpose |
|---|---|
| `observer_kernel.py` | New checked width, constant, endpoint, terminal-window, and shifted-mask identities |
| `prefix_masks.py` | Byte-identical previous count-mask relation backend |
| `dependencies/` | Byte-identical earlier conditional kernel and regular target/relation module |
| `audit_fixed.py` | Byte-identical earlier source-normalization audit |
| `audit_observers.py` | New pass and separate compilation-coverage measurement |
| `check_observers.py` | Rule-premise checks, independent word comparisons for all components, accepting-path checks for Umin |
| `check_semantics.py` | Reused prior reference helper functions; use `check_observers.py` for this experiment |
| `prove_umin.py` | Component proof production/replay and actual whole-source composition |
| `verify_umin.py` | Certificate-only command |
| `analyze_umin.py` | Baseline retention, new proofs/counterexamples, costs, rule usage, remaining targets |
| `results/certificates/` | 82 component certificates and five whole-solution manifests |
| `fixtures/` | 39 original MLIR solutions, two helpers, third-party license and notice |
| `baseline/` | Previous 70-proof results and provenance |
| `OBSERVER_PROOFS.md` | Proofs for this extension |
| `RULES_AND_PROOFS.md`, `COUNT_MASK_PROOF.md` | Preserved prior mathematical foundations |

## Scope

The five complete solutions are AND, OR, XOR, Smax, and Umin in the stated
total target semantics. The 82 component proofs comprise 57 ordinary total
targets and 25 stronger unconditional modular targets for flag families.
All 24 counterexamples are to stronger flag-family obligations. They do not
constitute bug reports against NiceToMeetYou's native contracts.

The key shifted-mask identity is exact for an arbitrary word-valued shift.
It yields an already supported finite relation when the replacement high
mask itself has an available interface, including leading-run counts. It
does not add general variable shifts or arbitrary numeric counts to the
backend. Its generality is proved mathematically; its use in this corpus
occurs in Umin component 6. Other general rules account for the external
coverage gains.

Width independence does not imply a small product in program size. The
Python semantic implementations remain trusted; the new results are not
formalized in Lean. Bounded testing checks implementation fidelity, while
the documented equalities and closed invariants supply the width quantifier.
No SMT runtime comparison was performed in this experiment.

The project's MIT license is in `LICENSE`. Original fixtures retain their
own notices in `fixtures/LICENSE_MIT.txt` and `fixtures/NOTICE.md`.
