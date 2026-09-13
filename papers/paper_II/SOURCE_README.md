# Paper II source supplement

Leonid Shcherbakov, *Equality-visibility depth in equational presentations: finite-ground spectra, certificates, and semigroup space*. Preprint v1.0, manuscript revision 12 September 2026.

The `source/` directory contains the complete English manuscript. `prototype/` contains the inherited finite-ground visibility prototype with obsolete machine-specific paths removed. `verification/` contains the new article-specific checks, generated examples, and fresh regression logs. `editorial/` records the substantive correction and the relation to Papers I and III.

## Build the paper

Use a standard TeX Live installation providing pdfLaTeX, latexmk, Latin Modern, and the packages loaded in `source/main.tex`:

```sh
cd source
latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
```

Alternatively run `pdflatex main.tex` twice from `source/`. Bibliography entries are included in `references.tex`; no BibTeX or external figures are required. The prebuilt PDF is supplied alongside this archive in the Zenodo record. Local compilation dates and TeX versions can change PDF bytes without changing the manuscript.

## Reproduce the checks

Python 3.10 or later; standard library only. The packaged run used Python 3.12.14. Run without `-O`, since assertions implement the research checks.

```sh
python verification/run_all.py
```

This runs `verify_article.py` and the six regression programs listed in `verification/README.md`. It writes fresh results and logs under `verification/`. Seeds are fixed inside the regression scripts. Elapsed time and environment fields need not match the packaged run. Running checks modifies output files and therefore invalidates the original output-file checksums; the source-file hashes should remain unchanged.

The article verifier independently compares subterm-DAG results against full bounded-universe closure, evaluates the explicit typed example models, and uses bounded reachability to test the strict proof-format gaps. General theorems are proved in the manuscript, not established by finite testing.

## Scope

The prototype computes congruence-proof visibility for finite ground equations. It does not implement arbitrary universal word-problem search, semigroup-space functions, or a standalone externally supplied certificate format. Its explanation validation assumes a generated closure run. The common typed example has separate explicit model checks. The public QKF-Certifier repository is a distinct software artifact; this supplement is not a replacement release of it.

Use `lambda`/`delta` for congruence proofs and `lambda^rw`/`delta^rw` for sequential rewrites. The exact semigroup-space formula belongs to the second pair. See `editorial/III_IMPLICATIONS_RU.md` before reusing earlier series plans that conflated the two.

Python code is MIT-licensed. Manuscript licensing is to be selected by the author in the publication record; see `MANUSCRIPT_LICENSE_NOTE.txt`. No DOI, ORCID, or affiliation has been invented.
