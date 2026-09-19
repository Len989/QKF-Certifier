# Frozen inference holdout v1

This protocol is committed before the first QKF/inference run on the selected
population.

## Denominator

The denominator is every public static unary method in the four pinned Java
files whose sole primitive parameter is `int` or `long` and whose primitive
return is `boolean`, `int`, or `long`. The resulting frozen population is
15 methods. No method may be removed because it is unsupported or lacks a goal.

## Target registration

A target is registered only when the method's full-word contract is exactly
expressible in the already accepted `qkf-target-v1` grammar. No target grammar
or source frontend may be extended after seeing holdout outcomes.

At freeze time exactly one method qualifies:
`kilim.concurrent.MPSCQueueColdFields.isPowerOf2(int)`, whose implementation
returns `(value & (value - 1)) == 0`; the independent target is
`popcount_le(1)` over all 32-bit patterns, including zero.

The three positive-only `isPowerOfTwo` methods are deliberately **not** mapped
to `popcount_eq(1)`: that would mis-handle the sign-bit-only negative value.
They stay in the denominator as `no_supported_target_language`.

## Frozen engine

`ENGINE.json` binds the exact inference/front-end/target implementation from
main commit `d1f67817...`, before any holdout execution. Holdout code lives
outside the frozen roots and may only perform acquisition, classification,
replay and reporting.

## Allowed result classes

Source applicability:
- `source_parsed`
- `source_unsupported`
- `no_source_profile`

Target:
- `certified`
- `refuted`
- `source_unsupported`
- `budget_exhausted`
- `no_supported_target_language`
- `no_source_profile`

`internal_error`, missing cases, moved Git blobs, changed engine files, or
nondeterministic replay fail the benchmark.

## No tuning rule

After the first holdout run begins, this PR must not change:
- the 15-method population;
- source commits/blobs;
- independent target(s);
- frozen engine files;
- feature/target budgets.

If the frozen run exposes a capability gap, that gap is reported and repaired
only in a later PR/run with a new benchmark version.

Finite/native checks, if any, are validation and never promoted to universal
proof evidence.
