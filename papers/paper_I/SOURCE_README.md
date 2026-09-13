# Paper I — source and finite verification

Leonid Shcherbakov. *Initial semantics of incompletely specified actions:
forced quotients, kernel saturation, and completion*. Preprint, version 1.0,
manuscript revision dated 11 September 2026.

## Build the paper

Use a standard TeX Live or MiKTeX installation with Latin Modern, AMS packages,
mathtools, booktabs, tabularx, enumitem, microtype, geometry, hyperref, and xurl.
The bibliography is embedded; BibTeX and external downloads are not required.

```sh
cd source
latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
```

Alternatively, run `pdflatex main.tex` twice from `source/`. The output is
`source/main.pdf`. All section files must remain beside `main.tex`.

## Reproduce the examples

From the archive root, run:

```sh
python verification/verify_article.py --output verification/results.json
```

See `verification/README.md` for scope and limitations. The JSON contains the
checked partitions and witnesses; the source contains all finite input tables.

## Rights and citation

The article's reuse terms are the license selected by its author in the
publication record. The verification Python code is provided under MIT;
see `LICENSE_CODE_MIT.txt`. No article DOI is asserted in these sources.
The citation in `CITATION.bib` is a pre-publication citation; use the actual
Zenodo record's citation after publication.
