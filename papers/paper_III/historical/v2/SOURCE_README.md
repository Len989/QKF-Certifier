# Paper III, manuscript 2.0

Leonid Shcherbakov. *QKF-Certifier: observation kernels and width-independent word proofs.*
Prepared revision: 13 September 2026. Accompanies software candidate 0.2.0a1.

- `QKF_PAPER_III_v2.0_2026-09-13.pdf`: compiled manuscript.
- `source/`: complete LaTeX sources; embedded bibliography, no BibTeX required.
- `CODE_VERSION.json`: version, contract and stable claim mapping.
- `CHANGES_RU.md`: editorial changes, limitations and next priorities.
- `historical/v1/`: unmodified earlier paper and its evidence/scripts/manifests.
  Those scripts still check the public 0.1.0a1 commit, not this new candidate.

## Build

Use standard TeX Live with pdfLaTeX, Latin Modern, AMS packages, microtype,
geometry, hyperref, xurl, booktabs, longtable, tabularx and enumitem:

```sh
cd papers/paper_III/source
pdflatex -interaction=nonstopmode -halt-on-error main.tex
pdflatex -interaction=nonstopmode -halt-on-error main.tex
pdflatex -interaction=nonstopmode -halt-on-error main.tex
```

The delivered PDF has embedded Type 1 fonts. Compilation logs and the page review
record are identified in `docs/RELEASE_VALIDATION_0.2.0a1.md` at the repository root.

## Reproduce current evidence

From the full repository root on Linux/POSIX with Python 3.12, without `-O`:

```sh
python tools/replay_research.py --suite all --output reproduction/run_01
cd research/lean
lake build
```

See `research/README.md`. This replays saved certificates and builds the Lean
proofs. Historical producer/native/SMT experiments are retained, not relabeled
as new runs. The original finite algebraic supplement remains self-contained in
`historical/v1/`; follow its own source README to reproduce its pinned checks.

## Version identity

The unchanged coordinatewise core refers to public commit
`f93561682319e8b911ed32c01583f2a496dc59fc` (v0.1.0a1). New candidate files are
identified by `RELEASE_MANIFEST.json` at the repository root. The manuscript does
not assume that v0.2.0a1 has been published. A later release record must identify
its actual reviewed commit. No DOI has been assigned here.
