# Checked observer identities and a complete Umin source proof

Research extension `qkf-observer-identities-v1`, 12 September 2026.
These are mathematical proofs supporting a trusted Python implementation;
they are not a proof-assistant development. Earlier contracts and lemmas are
retained in `RULES_AND_PROOFS.md` and `COUNT_MASK_PROOF.md`.

## Contract and source binding

Fix width w >= 1, M = 2^w - 1, and unsigned word operands. Arithmetic is
modular; shifts are total; counts are standard consecutive-bit counts in
[0,w]; mask counts clamp at w. `transfer.neg` means bitwise complement.
KnownBits inputs are nonbottom pairs (z,o), z&o=0, with concretization
gamma(z,o) = {a : a&z=0 and a&o=o}.

The new observer trace is applied after the byte-identical public and prior
conditional normalization passes. A trace step is an equality-preserving
source transformation; it is not itself a target correctness claim. The
checker replays every step at its actual expression path and enforces w >= 2.
The w = 1 obligation is checked separately on actual source SSA, for every
valid abstract pair and every represented concrete input pair. No width-one
case is excluded from an all-positive-width certificate.

Prior conditional rules remain available during the new pass. They obtain
their assumptions only from actual enclosing true branches, exactly as
before. New rules take no family name or caller-supplied premise.

## 1. Eliminating a shift inside a leading-run observation

Write L(x) = countl_one(x) and H(n) = set_high_bits(0,n). Complements below
are width-w complements. For every word x and every unsigned word n,

\[
 \operatorname{lshr}\bigl(H(L(\operatorname{shl}(x,n))),n\bigr)
 = H\bigl(L(x\lor H(n))\bigr)\land\neg H(n).
 \tag{1}
\]

**Proof.** If n >= w, the left side is 0 under total shift semantics. On
the right, H(n)=M, so the final conjunction with its complement is 0.

Suppose 0 <= n < w. Let r be the number of leading ones in the lower
w-n bits of x, viewed as a block of length w-n. Shifting x left by n
puts this block at the most significant end and appends n zeros. Its
leading-one count is r, including r=w-n and n=0. Thus the left side
has precisely the r bits immediately below the first n bits set.

The word x OR H(n) has n+r leading ones. Its leading-run mask, with
the first n bits removed, has precisely those same r bits set. ∎

The implemented `shifted-leading-mask` rule checks both occurrences of n
for structural equality and requires the inner set-mask base to be zero.
These conditions cannot be omitted. The statement is valid even when n
exceeds w; the test suite includes all word-valued shifts at widths 1–7.

If n = L(y), both masks on the right are instances of the already supported
same-end count-mask interface. Consequently this particular observation of
variable shifts is compiled exactly without adding a general variable-shift
operator to the bit-relation backend.

### A three-state description of the observed function

For n=L(y), read x and y from most to least significant bit. The resulting
mask can be produced by a deterministic transducer with the following states:
S (skip the leading ones of y), R (emit the following run of ones of x),
and D (the run has ended). Start in S; every end state is allowed.

| Current state | Condition on current bits | Output bit | Next state |
|---|---|---:|---|
| S | y=1 | 0 | S |
| S | y=0, x=1 | 1 | R |
| S | y=0, x=0 | 0 | D |
| R | x=1 | 1 | R |
| R | x=0 | 0 | D |
| D | any | 0 | D |

Induction on the most-significant prefix shows that S consumes exactly
L(y) bits, R emits exactly the following run of x, and D emits the remainder
as zeros. This proves the three-state bound for the observed function.
All three states are reachable. The pairs S/R, S/D, and R/D are distinguished
by one next input letter: (x=1,y=1), (x=1,y=0), and (x=1,y=0), respectively.
Thus three states are also necessary for a deterministic synchronous Mealy
transducer with this alphabet and reading convention.

This is a separate mathematical description of the function, not a claim
that the implemented Umin certificate was minimized to three states. The
actual checker retains its least-significant-first relational product and
uses identity (1) plus two existing high-run nodes. Its state count also
includes guards, target comparisons, and the error/length monitors.

## 2. Fixed terminal windows

For a fixed integer k >= 0 and w >= max(1,k), let

\[
 J_k=\bigvee_{j=0}^{k-1}(S\operatorname{lshr}j),
 \qquad S=\operatorname{set\_sign\_bit}(0).
\]

The empty disjunction is 0. Then

\[
 \operatorname{clear\_low\_bits}(x,w-k)=x\land J_k.
 \tag{2}
\]

**Proof.** The integer w-k lies in [0,w] and is represented without modular
underflow. Clearing it leaves exactly the k highest bits. J_k has precisely
those bits set. At w=k, it is the full word mask, as required. ∎

The implementation recognizes an affine word expression a*w+b using only
addition, subtraction, integer literals, and w. This proves a modular
equality, not an inequality. The rule applies only if a=1 and b=-k with
0<=k<=the checked minimum width. That extra condition converts the modular
count to the required nonnegative integer w-k.

J_k is expanded into the sign-bit mask and repeated one-bit logical right
shifts. Its interface size can depend on k but not on w. The current width
partition has minimum 2 and therefore enables k=0,1,2. At w=1 the expression
w-2 wraps; the rewrite is correctly forbidden there.

## 3. Width, bit boundaries, and literal identities

The remaining identities are general cleanup and observation rules. In the
table, m is the minimum certified width and a literal denotes reduction of
its integer value to the current word width.

| Rule | Preconditions and justification |
|---|---|
| `width-comparison` | Since 1<=w<2^w, w>u0 for all positive widths; if m>=2, w>u1. Equality and unsigned comparisons follow. No signed order of w is inferred. |
| `count-boundary-zero` | A consecutive-bit count is zero when the bit at the counted end differs from the desired bit. The low-end observation uses the prior checked `lowbit` analysis; the high-end observation uses explicit sign operations, stable literals, complement, and bitwise Boolean combinations. |
| `literal-count` | If v<0, countl_one(v)=w-bit_length(~v) whenever w>=bit_length(~v). If v>0, countl_zero(v)=w-bit_length(v) whenever w>=bit_length(v). The special all-matching literals yield w. A finite trailing run of length k in the infinite two's-complement literal yields k whenever w>=k. No result is asserted below these thresholds. |
| `literal-not` | Width truncation commutes with bitwise complement: NOT_w(v mod 2^w)=(~v) mod 2^w. |
| `literal-order` | Both integers must lie in the signed range [-2^(m-1),2^(m-1)-1]. Their signed order stays fixed for every w>=m. Their unsigned order also stays fixed: negative literals form the upper unsigned half, and within each sign class integer order is preserved. This justifies literal comparisons and min/max choices. |
| `unsigned-unit-bound` | x<u1 iff x=0, since unsigned x is a nonnegative integer; equivalently 1>u x iff x=0. |
| `count-zero-test` | A leading-one count is zero iff the sign bit is 0; a leading-zero count is zero iff the sign bit is 1. Trailing analogues use x&1. Inequality with zero gives the complementary condition. |
| `distribute-observer-select` | Pure total f(...,select(G,a,b),...)=select(G,f(...,a,...),f(...,b,...)). This pass adds distribution for clear_low_bits, umin, and umax; the previously supported operations retain their old rule. |

For high-bit analysis, a literal's sign is used only when the literal is
representable as a signed m-bit integer. Explicitly clearing or setting the
sign bit forces 0 or 1 at every positive width. Complement and AND/OR/XOR
combine known endpoint bits by their Boolean truth tables. Unknown endpoint
bits remain unknown. These facts justify every successful `known_sign` result.

For the negative leading-literal formula, ~v is nonnegative and fits in k
bits, where k=bit_length(~v). The upper w-k bits of v are then ones and the
next bit, if k>0, is zero. The positive formula is its zero-prefix analogue.
For trailing counts, the first nonmatching bit lies at index k. If it falls
just outside the word (w=k), the entire word matches and the count is still k.

## 4. A shift of the unit word and a mixed signed/unsigned threshold

For any positive width,

\[
 \operatorname{lshr}(1,n) = \begin{cases}1,&n=0,\\0,&n>0.\end{cases}
 \tag{3}
\]

For arithmetic right shift the same identity requires w>=2, since literal
1 is then nonnegative. At w=1 it is the signed value -1 and arithmetic
right shift preserves it for every shift amount. This real counterexample
is included in the tests of the width guard. Combined with `count-zero-test`,
identity (3) replaces the numeric count by a single endpoint observation.

For any c known to be signed-nonnegative,

\[
 x <_u \operatorname{smax}(x,c) \quad\Longleftrightarrow\quad x<_u c.
 \tag{4}
\]

If x is nonnegative, signed and unsigned max agree on x,c, and the statement
is the ordinary maximum identity. If x is negative, signed max returns c
but unsigned x is larger than every nonnegative c; both sides are false.
The rule checks the nonnegative condition using `known_sign`. It is not
valid for arbitrary negative c.

At w>=2, c=1 satisfies the premise, so the actual Umin component-6 guard
reduces to x<u1 and then to x=0. Only after that guard has been rewritten
does the existing true-branch rule substitute the input's zero mask.

## 5. What happens in the seven original Umin components

The components remain the original artifact entries. Let their input masks
be (za,oa) and (zb,ob). The new pass does not replace them by a separately
designed transformer.

| Component | New reduction used in its source proof |
|---:|---|
| 0 | Previously proved count-mask expression; no observer rewrite needed. |
| 1 | Previously proved guarded min/max expression; no observer rewrite needed. |
| 2 | countl_one of a sign-cleared word is 0, so the apparent variable low mask disappears. |
| 3 | Positive width eliminates the width-zero branch and width-sized shifts; the result is (H(L(zb)),0). |
| 4 | countl_one(-2)=w-1; low clearing at w-1 or w-2 becomes a fixed highest-bit window. |
| 5 | Stable literal facts and a right shift of 1 reduce the count to a sign test; the remainder denominator becomes 0 or 1 under the total contract. |
| 6 | The actual guard reduces to zb=0; branch substitution exposes identity (1) with x=za, n=L(ob). |

As an independent semantic explanation of the last component, put n=L(ob)
and let r be the following run of ones of za after its first n bits. The
candidate zero mask marks exactly those r bits. Every represented b is at
least B=2^w-2^(w-n), since its first n bits are known ones.

If min(a,b)=a, the mask is valid directly from za. Otherwise b<a. Since
b>=B, also a>=B: the first n bits of a are ones. The next r bits of a
are zero by za, so a<B+2^(w-n-r). Hence B<=b<a<B+2^(w-n-r), and those
r bits of b are zero as well. This proves the mask soundness, including
n=0 and the vacuous r=0 case when n=w. The source checker establishes the
same claim through its finite invariant and source-derived guard reduction.

## 6. Certificate lifting and remaining trust

After both rewrite traces are replayed, the checker reconstructs the unchanged
count-mask relation from the resulting expression and the caller-selected
concrete target. It checks inclusion of all initial states, closure of the
listed invariant under every nonfinal transition, and absence of any valid
terminal transition with a sticky KnownBits violation. Induction on length
then proves the claim at every w>=2; the actual-SSA width-one table closes
the width partition.

For a whole solution, the checker validates every component certificate,
the actual SSA calls on the original arguments, and the actual meet helper.
Meet ORs the zero masks and ORs the one masks, taking the intersection of
component concretizations. Since every component contains the concrete
target result, the intersection contains it too.

The proof producer may search; the checker performs no reachability search.
It still trusts these Python semantic implementations and the previously
documented kernels. Finite regression tests are evidence of implementation
fidelity, not the basis for quantifying over unbounded widths. Native flag
preconditions, LLVM poison, and generated C++ equivalence remain outside this
explicit total-word target contract.
