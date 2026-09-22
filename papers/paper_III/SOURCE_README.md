# Paper III, manuscript 3.0

Leonid Shcherbakov. *QKF-Certifier: observation kernels and width-independent word proofs.*
Prepared revision: 22 September 2026. Software release candidate: 0.3.0a1.

- `QKF_PAPER_III_v3.0_2026-09-22.pdf`: complete revised manuscript.
- `source/`: complete LaTeX sources; embedded bibliography; no BibTeX required.
- `CODE_VERSION.json`: exact accepted research snapshot and claim/source map.
- `REVISION_v3.md`: scientific changes and scope of the revision.
- `historical/v2/source/`: unchanged repository source of the preceding manuscript.
- `QKF_PAPER_III_v2.0_2026-09-13.pdf` and `historical/v1/`: retained prior material.

## Build

With standard TeX Live and pdfLaTeX, Latin Modern, AMS packages, microtype,
geometry, hyperref, xurl, booktabs, longtable, tabularx and enumitem:

```sh
cd papers/paper_III/source
pdflatex -interaction=nonstopmode -halt-on-error main.tex
pdflatex -interaction=nonstopmode -halt-on-error main.tex
pdflatex -interaction=nonstopmode -halt-on-error main.tex
```

## Evidence identity

All new research claims refer to the accepted snapshot
`eca90f9252da4480d77c1f8cb4b7062470c57b89` (through PR51). Its tree equals
`d6a352ed072f947429ec0896fad61350ab2540ab`, the final PR51 tree. Measured cost
reports identify their own earlier engines and environments; this revision
does not rerun those measurements or change the frozen evaluation protocols.
The release changes documentation, manuscript and software version metadata.

See `releases/v0.3.0a1.md` and `docs/RELEASE_VALIDATION_0.3.0a1.md` at the
repository root for reproduction routes and local validation. The installed
wheel remains the coordinatewise application. Research and Lean require the
complete source archive. Formal theorems do not imply verification of JSON
decoding, source rules, Java execution, or the entire Python implementation.

The earlier Paper III record is https://doi.org/10.5281/zenodo.22736714.
The DOI of this new manuscript version must be assigned by Zenodo; none is
invented in these sources. Retain the existing record's author and license
metadata when creating its new version.
