# v6 frozen experiment

Goal: complete partial_normalization_clamp, all three original claims, with
fresh v3/v4/v5/v6 runs on identical source bytes. Main question: checked
whole-word reconstruction by a quotient representative and membership.
Keep v5 sources and papers immutable; copy exact baselines to this stage.

Development: eight valid synthetic sources, two known targets. Fifteen
certificate tests and finite theory/semantics validation before freeze.
Freeze all mechanism Python, unchanged baselines, tests, validation, this
protocol, theory, and principles before writing the new evaluation sources.

Evaluation: eighteen new synthetic sources selected after freeze and before
running any engine: eleven valid, five invalid mutations, two true examples
expected to exceed implemented count/capture interfaces. Include both shift
directions, same/other-word captures, compound inputs, multiple consumers,
old-lemma integration, boundary s=w, repeated cheap consumers, negative shifts,
lost bits and incorrect outputs. Labels describe mathematical intent;
actual solver status is reported even when it differs from expectation.
This is constructed synthetic evaluation, not an external blind holdout.

Keep every selected source, success, unsupported result, UNKNOWN, failure,
and timing. UNKNOWN is not a counterexample; search for independent finite
counterexamples at w=1..5 and parameters -1..w+1 for every invalid source.
Check finite full-claim semantics and each accepted reconstruction, including
partial certificates on failed queries. Universal soundness rests on proof
replay, not finite testing.

Replay every successful certificate in a fresh process with search imports
blocked. Shared budget: 100000 search nodes / 500000 constructed FM rows;
per-call FM limit 20000. Reconstruction probe 8/1000, each membership attempt
1024/40000, each universal factor 512/20000; v5/v4 limits unchanged. Failed
trials are charged. Factor proofs are produced once per direction per source,
included and replayed inside every applicable full certificate; not free
precomputed lemmas. Record full proof steps and pretty and compact bytes.
Report single-run timings as observations, not robust performance estimates.

Regression: all 127 v5 source occurrences, including its development,
evaluation, known targets and 98 older occurrences. Preserve the distinction
between repeated sources and independent tasks. Compare all previous statuses,
proof objects, and costs. Main gain means fewer search nodes, fewer full proof
steps and fewer compact certificate bytes on a common proved source.

Do not claim that pushout splitting alone proves native shift invertibility.
Do not claim a new saturation or visibility theorem from ordinary lemma
instantiation. Keep the finite separator showing that same kernel and extreme
cells do not determine representative labels. No horizon minimality claim.
