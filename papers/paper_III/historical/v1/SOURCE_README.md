# Paper III: source and evidence

Leonid Shcherbakov. *QKF-Certifier: finite quotient kernels and width-independent KnownBits proofs.* Manuscript v1.0, revision 12 September 2026.

This is the scientific reference package for public software v0.1.0a1 at commit `f93561682319e8b911ed32c01583f2a496dc59fc`. `CODE_VERSION.json` is the exact software/contract/claim manifest. The public repository is retrieved by commit and checked by file hashes; this supplement does not contain a second copy of it.

## Build the paper

Use a standard TeX Live installation with pdfLaTeX, latexmk, Latin Modern, AMS packages, microtype, geometry, hyperref, xurl, booktabs, longtable, tabularx, and enumitem.

```sh
cd source
latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
```

Alternatively run `pdflatex main.tex` at least twice until references settle. The bibliography is embedded in `references.tex`; BibTeX is not required. The supplied PDF was compiled with pdfLaTeX (TeX Live 2023/Debian), checked for unresolved references and overfull boxes, and visually inspected page by page. Installed fonts and local runtime configuration are not part of the supplement.

## Reproduce the fresh finite checks

From this extracted supplement, use Python 3.10+ and git:

```sh
python verification/fetch_release.py ../qkf-paper-iii-release
python verification/verify_algebraic_core.py --certifier-root ../qkf-paper-iii-release
python verification/verify_release.py --repo ../qkf-paper-iii-release
```

If you already have the pinned clean checkout, pass its directory to `fetch_release.py --check-only` first. Existing directories are never reset or overwritten. A moving tag is insufficient: a commit or file-hash mismatch causes failure. Run Python without `-O`, since these research checks use assertions. The algebraic check can also run without `--certifier-root` to skip the public-program examples.

These scripts use only the standard library and write their JSON evidence and generated certificates into `verification/`. Save the distributed results elsewhere before rerunning if you want to retain the recorded timings. Elapsed times and host details are expected to change; finite verdicts, counts, signatures, and deterministic certificates should agree.

The release's own test suite additionally needs pytest and Hypothesis. In a virtual environment with the repository's declared development dependencies installed:

```sh
python -m pip install -e '../qkf-paper-iii-release[dev]'
cd ../qkf-paper-iii-release
python -m pytest -q
```

The recorded suite result is 67 passed. `verification/release_pytest.log`, `core_results.json`, and `release_results.json` distinguish suite results, independent algebraic checks, and the paper-specific audit. The word oracle used by the latter is separate from the symbolic rewrite rules but belongs to the pinned repository; it is not presented as an independently developed formal verifier.

## Scope

K1/K2 have a small research reference implementation in `evidence_sources/`. K3 is a conditional sparse representation theorem; the historical C++ file still has a 100-pass limit without an exhaustion status. K4/K5 describe the public Python certifier. The public release neither calls Relation-QKF nor computes minimum equality-visibility depth.

`evidence_sources/historical/` contains earlier measurements and the associated sparse prototype for provenance. These measurements were not rerun for Paper III. Fresh checks do not prove universal theorems by sampling; the manuscript supplies their mathematical arguments.

`repository_link/` contains proposed citation and version-link additions for the repository. No remote changes are performed by this package. `editorial/` explains the series connection, provenance, remaining implementation work, and publication workflow in Russian.
