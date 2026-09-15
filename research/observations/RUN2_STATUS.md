# Run 2 status — not ready to merge

Base: `8e482b2f2f7343af24a8c5a2e3a17867e3bd7ae7` (merged PR #5).
Date: 15 September 2026.

This branch contains only the new typed specification syntax and template
modules, plus this status note. The complete implementation has NOT been
published on the branch: repository write requests for the runtime rules were
blocked by the connected tool. In particular, the referenced `target_rules`
module is still absent. Do not treat this branch as an executable run 2 release.

A complete local candidate was prepared separately: syntax, shared numerical
rules, source-factor/goal checker, producer, common-interface integration,
experiment, documentation and tests. It is supplied as a patch/archive in the
conversation, not as an already-validated commit in this branch.

Local validation passed 27 unit-test methods under ordinary Python and `-O`.
Ten methods test numerical rules directly; 17 test the finite checker and common
interface on explicitly declared test machines, not extracted Java programs.
The numerical suite includes 7,764 monitor/integer comparisons and 584 exact
quantified-successor controls. These are NOT a full source-to-target replay.

Eight full-repository integration tests and the 23-case experiment are written
but have not been run. No new CI success, legacy-corpus agreement, Java theorem,
Lean theorem or completed run 2 is claimed. Existing CI on this partial branch
would not establish acceptance of the missing implementation.

Before merge: publish/apply the full candidate; run the complete old/new tests,
compare all 18 legacy cases, check the five new change-property cases, replay
without search under Python `-O`, preserve actual evidence, and review the trust
boundary. Main has not been modified by this work.
