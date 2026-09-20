# Run32 / Block A acceptance — protocol v1

**Development acceptance, not a new holdout.** The protocol/case generator and comparison
harness are sealed before measurement. No production algorithm is tuned using results.
The PR27 33-method population is not used or relabelled; 1/15 and 2/33 remain historical.

## Fixed implementations and scope

- A `frozen_v3`: exact whole-tree post-PR25 baseline `c8c7b4eeaf848d31c8c324a4316ffec8aac81cda`, tree `4838b8badbb3a56f8a7d2a197ce6c0d3d6b3a77d` (1837 files).
- B `closure_cells`: PR31 snapshot `eb2e68023e272c51710a25cdfe0a0ff8dd5642ac`, tree `4c1dfe4047c7bc44ca45e0dc3e73b37517859dda`, plus the distinctly identified comparison-only `control.py`.
- C `closure_rows`: unchanged production `research.unified.v4` from that same PR31 snapshot.

B replaces only source transitions during target product discovery/replay with the
already checked forward cells. It retains full source reconstruction, observation
closure, atomic proofs and checked runtime loading, including two built-in target
checks as in C. It additionally audits its copied cells against that loaded runtime.
This is a controlled execution ablation, **not** a row-free proof algorithm or a newly
released checker. No monkeypatching or relabelling of B as production v4.

Source and target bytes/semantic contracts are identical in all arms. Completion
consumers are not: A has Boolean initialization; B/C retain `not-a-word`. Report total
and positive classes separately, never infer a regression from the extra root alone.
Target language, source grammar and existing source-model caps (512 vs 64) are unchanged.
Budget interfaces and limits are disclosed in CASES. The four known power-of-two
variants are not independent algorithm families. Large-literal stress is intentionally
constructed and is not a population-frequency estimate.

## Population and resources

All 28 entries of the fixed `cases.py` generator are retained: 11 PR31 development
cases (3 pinned upstream, 8 constructed), 4 equivalent power-of-two variants,
8 constant-depth/redundant-carrier stresses (exponents 4,8,30,31), one unsupported
shift and four budget controls. The 23 main cases and five failure controls are
reported separately. Two controls exercise new-only budget knobs; A uses defaults
there and these are not equal-budget contests. The prior external blobs are verified
against the accepted frozen_v2 source manifest, not downloaded by moving branch.

Three fresh discovery processes per case/arm, rotating arm order by case/repeat;
no warmup discarded and no favorable-attempt selection. Each proof receives three
normal fresh replay processes plus one optimized replay (the first proof).
Record every success/failure, full certificate, full result, source/target, imports,
operation wall/CPU time, complete process wall/CPU and peak RSS. Independent replay
blocks producer, subprocess and SMT imports before checker import. It is not
independence from shared semantic implementations. Numeric timings never enter
proof validity. No speed threshold gates CI.

Per process: 120 seconds wall timeout, 2 GiB address-space ceiling, one CPU process;
no rerunning failed candidate attempts silently. Source generation/acquisition and
export are outside solver timings and recorded as preparation. Serialization and
provenance collection are outside inner operation time but inside process time.
Engine exports are byte/mode-verified before/after; imported research modules must
originate in their designated export. Harness files are separately SHA-256 sealed.
Python exact versions, platform and CPU are retained. CI uses 3.10/3.12 on Linux;
local results have their own exact interpreter identity and are not called CI.

## Reuse/phase diagnostics and correctness

A separate common-interface experiment on the same accepted source-observation
package measures checked loading, one product discovery, one product replay and
warm direct/row execution over 2048 identical 64-bit words, three repeats. It is
not mixed with end-to-end latency or called a new target solver. Long cases may
exhaust model construction; they remain in the main denominator.

Finite IR/cell/row comparison and semantic-variant checks are explicitly development
controls. Reuse of saved native records is not new Java execution. This PR does not
claim new native coverage or a solver ranking against SMT. A new Java run, if made,
must be separately identified, not confused with proof replay.

Acceptance requires valid certificates for claimed proofs, agreement of B/C
observations/obligations and statuses, no hidden failed attempts, exact baseline
preservation and complete records. A failure status need not agree across A/C
because their caps differ; report it. An invalid claimed proof or semantic
contradiction blocks acceptance. Different witness lengths do not imply different
truth. Check concrete witness interpretation at the final width.

## Scientific update

Publish results, the claim/implementation/trust map and an additive Paper III update
note, preserving manuscript v2.0 and the original roadmap byte-for-byte. Distinguish
forced carrier equality, observational identification and chosen completion (Paper I);
operational distinguishing suffix length from term-depth visibility (Paper II);
atom-generated S=D=A from nontrivial forced-domain growth (Paper III §7.3).
Next PR priorities follow measured limitations, not another catalogue of special cases.
