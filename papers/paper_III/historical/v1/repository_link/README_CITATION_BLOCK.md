## Scientific reference

The primary algorithm paper is **Leonid Shcherbakov, _QKF-Certifier: finite quotient kernels and width-independent KnownBits proofs_**, Paper III, preprint v1.0 (manuscript revision 12 September 2026). Its permanent link will be added after Zenodo deposition.

Paper III describes source-bound certificate replay, the complete coordinatewise KnownBits semantics, the exact supported scope, and the relation to the research Relation-QKF kernel. It is the paper that will evolve with the implementation. Papers I and II provide the initial-semantics and equality-visibility foundations.

The code audited for paper v1.0 is software **v0.1.0a1**, commit [`f93561682319e8b911ed32c01583f2a496dc59fc`](https://github.com/Len989/QKF-Certifier/tree/f93561682319e8b911ed32c01583f2a496dc59fc). Later commits require their own evidence. The public release supports AND/OR/XOR certification in its documented fragment; it does not run Relation-QKF or compute minimum proof depth.

See [the paper/software version map](docs/PAPER.md) and [citation metadata](CITATION.cff). Cite the algorithm paper and record the actual software version/commit used in an experiment.
