# Semantic contract and proof boundary

## Inputs and outputs

A word has an arbitrary, fixed positive width `w`. Integer values are residues
modulo `2**w`. A KnownBits pair `(Z,O)` denotes concrete words `x` satisfying
`x & Z == 0` and `x & O == O`. Inputs satisfy `Z & O == 0`; bottom inputs are
outside the current interface. The entry takes two such pairs and returns a pair.

For a `certified` result the output contains every concrete result of the supplied
target (`and`, `or`, or `xor`). `optimal=true` means its concretization equals the
best result representable by this domain. Unsoundness has a width-one concrete
witness. All-positive-width soundness is a conditional theorem about this exact
word semantics, not a claim about a separate compiler or machine-code backend.

## Operations

| Family | Semantics |
|---|---|
| `get`, `make` | Pair projection (indices 0,1) and construction |
| `and`, `or`, `xor`, `neg` | Bitwise operations; **neg means bitwise NOT** |
| `constant(x,n)` | `n modulo 2**w`; the operand supplies the word type |
| `get_all_ones` | `2**w-1` |
| `get_bit_width` | `w`, encoded as a w-bit word (it always fits) |
| `add`, `sub`, `mul` | Modular arithmetic |
| `umin`, `umax` | Unsigned order |
| `smin`, `smax` | Two's-complement signed order |
| `shl`, `lshr` | Zero if unsigned count ≥w; otherwise normal word shifts |
| `ashr` | Sign-filling arithmetic right shift, also when count ≥w |
| `clear/set_low/high_bits` | Clear/set the requested `min(count,w)` bits |
| `clear/set_sign_bit` | Clear/set bit w-1 |
| `countl/countr_zero/one` | Count matching bits from the selected end, in 0..w |
| `udiv`, `urem` | SMT total unsigned division/remainder: divisor zero gives all-ones / dividend |
| `sdiv` | Truncation toward zero, modulo width; zero divisor gives 1 for a negative dividend, otherwise all-ones |
| `srem` | Remainder with the dividend's sign; zero divisor gives the dividend |
| `cmp` | Predicates 0..9: eq, ne, slt, sle, sgt, sge, ult, ule, ugt, uge |
| `select` | Boolean-conditioned choice between words |
| `arith.andi/ori/xori` | Boolean operations on i1 values |

A frontend may accept an operation even when the normalizer has no useful rule
for it. Acceptance of syntax is not a proof of the resulting transformer. Operations
are pure and total in this contract, so unused computations may be discarded during
expression construction. A lowering that introduces inconsistent assumptions for
such an operation does not implement this contract. Literal constants are limited
to 256-bit magnitude; a particular backend can have additional literal restrictions.

## Supported text

This is a line-oriented subset of transfer MLIR, not the MLIR specification.
It accepts a `builtin.module` of single-block functions, one or two abstract
arguments per function, abstract or i1 results, typed SSA, straight-line calls,
and explicit returns. Calls must resolve to definitions supplied by the caller;
recursive calls, unknown operations/attributes, wrong types, trailing statements,
and duplicate definitions are rejected. The root used by the public API takes two
abstract inputs. The generic function envelope of the pinned meet/top helpers is
supported. Other generic regions, block branches, loops, poison values, and arbitrary
attribute syntax are not supported. Line comments are supported.

`applied_to` and `CPPCLASS` are checked metadata, not the source of the trusted target.
The caller supplies the target independently. `ret_type`/`input_type` strings are
checked hints; `int` and `bint` both have word semantics in this fragment.

## Why nine rows suffice after normalization

For each input bit the valid KnownBits possibilities are known-zero `(1,0)`,
known-one `(0,1)`, and unknown `(0,0)`. Two inputs give nine pairs. A normalized
expression is accepted by the final checker only if both masks contain variables,
zero, all-ones, and bitwise AND/OR/XOR/NOT. These operators act separately on every
bit. Thus the nine-row result lifts to every coordinate of every positive-width
word. Constants such as the integer 1, comparisons, and bit counts are **not**
treated as coordinatewise words.

## Rewrite laws

The trusted rule names live in `kernel.RULES`. The following arguments account for
their families; their syntactic conditions are checked again during replay.

- Idempotence, self-cancellation, zero identities, AND-zero, OR-ones, AND-ones,
  NOT constants, and double NOT follow directly from modular/bitwise definitions.
- `disjoint-and`: disjoint support has empty intersection. `disjoint-add`: when
  operands have no common one bits, ordinary addition produces no carries and
  equals OR; reduction modulo the width preserves the equality.
- Support tests on coordinatewise expressions exhaust the nine valid input pairs.
  Structural support tests use AND restriction and OR inclusion. They are sufficient
  conditions, not a complete theorem prover for word expressions.
- Clearing width-many bits gives zero. Clearing/setting zero bits is identity.
  Clearing any number of bits from zero gives zero. Counting a constant zero/ones
  word gives either zero or width. Setting one low bit of zero gives the integer 1.
- Setting `countl_one(x)` high bits of `y` changes nothing when the support of `x`
  is included in `y`. Every bit that would be set is already present in `y`.
- Unsigned minimum with zero and maximum with all-ones are constant. Zero remainder
  is zero, unsigned remainder by 1 is zero, and unsigned division by 1 is identity.
  These statements include the documented divisor-zero behavior where relevant.
- Every bit count is ≤width. Reflexive comparisons and unsigned extrema give the
  corresponding Boolean constants. If the low bit of a word is provably one,
  it is positive in unsigned order at every positive width.
- Low-bit propagation uses Boolean operations and parity of modular addition/
  subtraction. A left shift by the integer 1 has a zero low bit, including w=1.
- Constant or equal-branch selections collapse; Boolean constant identities and
  zero/count-zero shift identities hold directly.

Rewriting a subexpression by one of these equal expressions preserves its enclosing
expression by congruence. The checker replays a finite sequence of such replacements
starting from the parsed and inlined source. The certificate cannot introduce an
unproved hypothesis. KnownBits input validity is the only source-specific hypothesis.

## Limits and trust

The runtime dependency set is empty. The trusted implementation includes source
parsing, inlining, schema validation, local rules, side conditions, replay, and the
final table. The search procedure is excluded, but shares the implementation of
local rules. There is no machine-checked proof of the Python implementation.

Default limits: 32 files / 2 MiB combined source, 512 functions, 20,000 operations,
32 call-depth budget, 10,000 expanded calls, 50,000 expanded expression nodes,
100 expression-depth budget, 10,000 proof steps, and 8 MiB certificate files.
These limits deliberately prefer `fallback_required` over uncontrolled expansion.
They are engineering budgets, not a mathematical completeness boundary or a service
isolation mechanism. This alpha release is designed as a local development tool.
