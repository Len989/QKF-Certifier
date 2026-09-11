# Evidence and reproducible timings

Run `python benchmarks/run.py` after installing the package. The script measures
complete API calls, including parsing, with 31 repetitions and warm caches.
`verify` includes proof generation and replay; `check` replays a ready certificate.
`package_timings.json` records this release's local run. Timings vary with the host.

The precursor research study recorded:

- 22,140 exhaustive abstract-input pairs at widths 1..4 for the three real examples;
- 3,150 random pairs up to width 1024;
- 680 source mutations, with 270 sound verdicts, 180 refutations, 230 fallback cases;
- 39 real programs, with 3 complete coordinatewise proofs after normalization;
- 453 normalizable original/mutated candidates in 98 target-specific semantic classes.

The release tests rerun the exhaustive and mutation regressions. Randomized
expression tests additionally exercise rewrite semantics. The full 39-program
corpus and old solver harness are research artifacts outside this package; the
package does not claim to rerun them as part of its default CI.

Earlier microbenchmarks compared a precursor checker against a separate correct
word-semantics encoding in Z3. They are not native NiceToMeetYou integration
benchmarks and are not measurements of this packaged release. No end-to-end
synthesis speedup is claimed here.
