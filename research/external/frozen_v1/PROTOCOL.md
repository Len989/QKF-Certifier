# Frozen external applicability experiment, v1

Freeze before any corpus execution. Engine: main after PR #13,
`f974410e5635c789c1f76725f1d0c7ae4259bf38`, tree
`23e7b381d117d037fdb3d21893d1acc6b24e7f40`.
`CORPUS.json` fixes exact revisions, Git blobs, methods, native contracts,
populations and budgets. `ENGINE.json` fixes all 79 production Python files
under src and research/observations (tests excluded). They must not change.

## Question and selection

Can the published observation frontends directly bind ordinary external Java
bit-manipulation methods, without handwritten state machines or source rewrites?
This is deliberately a test beyond the Graal-shaped entry interface, not a claim
that these methods were advertised as supported. It is an applicability study,
not a solver ranking or a random, blind sample of all word programs. Source
bodies were inspected to select methods and state native contracts, but no corpus
outcomes were measured before this freeze. The known frontend restriction is not
concealed: a zero direct-coverage result is informative but does not measure the
proof engine's capacity after a suitable translation.

Twelve distinct methods from two external repositories: six OpenJDK Long bit
queries/permutations, six Lucene BitUtil mask/encoding operations. Prefer long
variants where overloaded; exclude strings, memory, variable-length containers,
I/O, and trivial forwarding arithmetic. No synthetic mutation enters this
population. The fixed list is authoritative: do not replace unsupported cases.
Previously studied Graal maximum/bound/successor/membership are FOUR calibration
goals over TWO known regions, outside the 12-method denominator.

## Stages and honest outcomes

1. Download complete original files at immutable commits and check Git blob IDs.
2. Identify exactly the selected declaration (signature and balanced lexical
   braces); retain exact bytes and offsets, full originals and notices. This
   extraction is experimental tooling, not a verified Java frontend.
3. In independent processes apply each unchanged ascending/descending source
   reader to the exact method. Preserve errors verbatim. No method renaming,
   synthetic loop, mask assumption or per-program model may be introduced.
4. A source-reader rejection is `source_unsupported`, NOT a failed theorem or
   program bug. Reader success alone is NOT a proof: it is `source_parsed` and
   still needs an independently reviewed domain/goal bridge. The existing CLI
   has no general function selector; the experiment must not let it certify a
   different method from the same file. Do not give an unrelated maximum or
   successor goal to a bit-count/encoding function. No typed goal translation for
   these new methods is provided in this frozen study.
5. Independently compile exact selected method bodies in explicit test classes
   and compare against simple numeric oracles at physical Java widths. JDK
   Integer count helpers are host-JVM dependencies, recorded as such; intrinsic
   annotations and enclosing library classes are not reproduced. Lucene constant
   declarations are copied exactly. The limited domain of nextHighestPowerOfTwo
   is 0 <= x <= 2^62. Native agreement is bounded testing, NOT an all-width proof.
6. Generate and replay the four calibration packages independently. No-search
   replay runs in a fresh process. Calibration cannot raise external coverage.

Native corpus: all unsigned 12-bit values and their two's-complement negatives;
all one-bit boundaries and their complements; 512 seeded full-width samples.
Interleave uses all pairs of 5-bit values, a boundary cross-product and 512 seeded
32-bit pairs. Deduplicate cases, record the exact populations and their hashes.
Use the frozen limits. Network failure, malformed selection, subprocess errors,
timeouts, protocol violations and unexpected exceptions are separate outcomes,
never reclassified as unsupported source, counterexamples or successful proofs.

## Retention, comparison and endpoint

Keep method-level records, input/output fingerprints, timings (diagnostic only),
full sources, generated native test wrappers, all four calibration proofs,
engine fingerprints, commands and runtime versions in the output artifacts.
Report the 12-method and 24-profile-attempt denominators separately. Count source
coverage, completed target proofs, native tests and calibration separately. No
new theorem, speedup, minimality or whole-library correctness is implied.

Repeat on Python 3.10/3.12 with Java 17; compare semantic records and full proof
bytes, not machine timings. Unit tests exercise extraction, tampering, explicit
unsupported statuses, oracle edge cases, and source-selection isolation. The
final CI validates the exact published head. Harness corrections are recorded
separately and cannot change the frozen engine, corpus or contract to improve
coverage. A research report must identify the earliest actual obstacle and one
next generalization, without inventing results for unreached stages.
