# Verification manifest

Run all listed checks with `python verification/run_all.py` from the supplement root, or run individual commands below. Python >=3.10, no third-party dependencies, and no `-O` flag.

| Command | Coverage |
|---|---|
| `python verification/verify_article.py` | Two strict resource gaps; all 195 Catalan profiles through axiom depth 5; 1,077 bounded partition comparisons; 14 flattening extensions; the shared four-element example; all five visibility-square inputs and 15 additional bounded partition comparisons; empty input/default model. |
| `python prototype/test_fast_vs_reference.py` | 1,000 generated inputs, incremental versus reference DAG closure. |
| `python prototype/test_generic_ground.py` | 500 generated inputs, subterm DAG versus full bounded-universe closure. |
| `python prototype/test_certified_proofs.py` | 300 generated inputs and 3,418 positive query explanations. |
| `python prototype/test_countermodel.py` | 200 generated inputs, final finite models. |
| `python prototype/test_optimality_countermodels.py` | 81 delayed equalities separated below optimum and 3,662 final nonequalities. |
| `python prototype/test_forest_stabilization.py` | 500 generated inputs, merge-forest and partition stabilization. |

All seven commands passed in the packaged run. Counts describe overlapping test families, not one collection of independent presentations.

`results.json` contains the article-specific results. `regression_results.json` and `test_*.log` contain fresh outputs of the six inherited tests. `shared_example_certificates.json` contains the symbolic inputs, proof explanations, canonical threshold models, and explicit typed models. `visibility_square_certificates.json` contains all five inputs, threshold models, and observed partitions. Operation tables in canonical model JSON use a default value for unlisted tuples; constants not represented at the threshold also use that default.

The canonical model extraction is one-sorted. The article's many-sorted construction is a mathematical sortwise extension, and the common two-sorted example is additionally checked by independent typed evaluation functions. The prototype's internal proof explanation checks are not a general-purpose parser/checker for adversarially supplied certificate files.

Other inherited exploratory programs remain in `prototype/` for provenance. They are not part of the numerical evidence reported in the revised article unless listed here. Historical runtime tables have not been carried over as fresh measurements.
