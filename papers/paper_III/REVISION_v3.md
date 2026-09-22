# Paper III version 3.0 — revision record

Date: 22 September 2026. Author: Leonid Shcherbakov.
Technical snapshot: `eca90f9252da4480d77c1f8cb4b7062470c57b89` (merged main through PR51).
Accompanying software: `0.3.0a1`, research alpha.

## Integrated scientific update

The manuscript preserves the finite core, relation-matrix closure, conditional sparse contract, coordinatewise classification, source replay arguments, original observation mathematics, upper/lower masked-bound contracts, and the original K1–K10 scope.

Version 3 integrates subsequent research into the abstract, introduction, technical development, implementation profile, experiments, formal scope, and conclusion. It is not a journal of pull requests. The major additions are:

- Restricted source-derived observation selection; stable factors with labels and separating continuations; positive-width completion, independent targets, and atomic-row execution.
- Checked reduction before residual enumeration, concrete witnesses, conditional residual coverage, reusable checked contexts, and compact dependency transport.
- Exact initial pure-row semantics with native quotient feedback, forced domains, derivations and separating models; a source-bound local example with `|S|=4` and `|D|=8`.
- Typed finite-ground DAG queries, source-native premises, consumer-directed acquisition, closed checked lemmas, prepared obligations, direct proof emission, and the applicable-summary SDK.
- The later source-bound Graal caller profile and explicit numeric/conditional caller Lean results.
- F1a/F1b: formal soundness of the decoded typed positive calculus and chronological checked-lemma composition under explicit native assumptions. This is not a theorem about Python JSON parsing, source frontends/rules, the full source adapter, or interface-to-runtime correspondence.
- Controlled development comparisons through PR49. QKF's ordinary SDK is explicitly identified as an internal route. Preparation/direct-emission improvements do not establish a query-backend advantage over this simpler route.

Historical program coverage remains `11/39`, and component coverage remains `104/411`. The external frontend studies retain `0/12`, `1/15`, and `2/33`, with their contracts and denominators separated. The two Run27 certified methods are overloads of one body/algorithm group. The manuscript distinguishes historical preliminary records from later completed CI when their statuses differ.

## Identity and references

The existing Paper III version-2 DOI is `10.5281/zenodo.22736714`; it is cited only as the preceding revision. No version-3 DOI is invented. Paper I and Paper II use their published DOIs `10.5281/zenodo.22736397` and `10.5281/zenodo.22736558`.

New artifact links resolve to the exact technical snapshot. Formal acceptance reports, which were published in separate results-only commits, link to those exact commits. Benchmark reports retain their measured engine identities; their timing values are not relabeled as measurements of the release packaging revision.

## Validation of this manuscript revision

- Compiled with pdfTeX/LaTeX, resolving all citations and cross-references in repeated passes.
- Final PDF: 37 pages, searchable text and embedded Type 1 fonts.
- Final compile: no LaTeX warnings, overfull boxes, or underfull boxes.
- Inspected rendered contact sheets covering all 37 pages; no clipped or overlapping content detected.
- Checked that all snapshot-relative artifact links refer to files present in the technical checkout.
- Targeted independent editorial review checked the new source/SDK/Lean claims, experimental figures, historical statuses, and proof wording.
- Historical benchmarks, native runs, and Lean projects were not rerun merely to edit the manuscript. Their own retained reports are the evidence; additional release checks belong to the release validation record.

## Build

From `papers/paper_III/source`, with a standard TeX Live installation including the declared packages:

```sh
pdflatex -interaction=nonstopmode -halt-on-error main.tex
pdflatex -interaction=nonstopmode -halt-on-error main.tex
```

The distributed PDF is `QKF_PAPER_III_v3.0_2026-09-22.pdf` in the parent directory. No runtime, schema, benchmark engine, default, or formal source was changed by this manuscript revision.
