# Conditional rewrite lemmas and proof obligations

This is the mathematical justification of the additional Python rule kernel.
It is not a machine-checked Lean development. The pinned public QKF rules keep
their existing justification and semantics; this file describes the new rules.

Fix a positive width w. Let M=2^w−1, sign(x) be the most significant bit,
L(x)=countl_one(x), C(x,n)=clear_high_bits(x,n), and S(x,n)=set_high_bits(x,n).
Counts are unsigned words; C and S clamp the count to w. Arithmetic is modulo
2^w. Signed comparisons use two's complement. Thus 0≤L(x)≤w≤M.
The `ones` literal is M, interpreted as −1 in signed comparisons. Unless a
minimum width is stated below, a lemma applies to every w≥1.

## 1. Context and branch rules

`branch-value` obtains premises only from the actual syntax path. Entering the
true branch of `select(G,u,v)` adds G; conjunctions add both conjuncts. No premise
is inferred from the false branch. From an equality of a mask to zero or M the
corresponding value can be substituted. From z=M infer o=0, and from o=M infer
z=0, using the nonbottom KnownBits invariant z&o=0. This rule is restricted to
the four original mask variables, whose pairings are fixed by the frontend.
Replacing an expression in that branch preserves the whole conditional; the
branch guard itself is not assumed when rewriting its own expression.

`ones-bound-equality`: M≤u x iff x=M, and x≥u M iff x=M, by 0≤x≤M.
`ones-implies-nonzero`: (x=M) and (0<u x) iff x=M, since M≥1.
`bool-neutral` and `bool-idempotent` use Boolean identities: true and p=p,
false or p=p, false xor p=p, p and p=p, p or p=p, p xor p=false.

These rules are local equivalences under checked premises, not claims about
the correctness of a target operation.

## 2. Width, constants, division, and signs

| Rule | Identity and reason |
|---|---|
| `literal-arithmetic` | Constant add/sub/and/or/xor may be computed as integer literals and then reduced to the word width. Low bits commute with these operations, including signed integer-literal bitwise operations. |
| `width-one-false` | For w≥2, w=1 is false. This rewrite is forbidden in the width-one proof. |
| `width-at-least-one` | umax(w,1)=w because w≥1 and w≤M. |
| `shift-width` | shl(x,w)=lshr(x,w)=0; ashr(x,w)=M if sign(x)=1, else 0, under the total shift contract. |
| `set-width` | Setting either w low or w high bits gives M. |
| `clear-width-plus-one` | For w≥2, w+1≤M and w+1≥w, so clearing w+1 bits clears the whole word. At w=1, w+1 wraps to zero; this rewrite is forbidden there. |
| `clear-one-constant` | Clearing the lowest bit of literal 1 yields zero. |
| `sign-mask` | Clearing/setting one high bit is clearing/setting the sign bit. |
| `set-low-width-minus-one` | set_low_bits(x,w−1)=x OR clear_sign_bit(M); w−1 is representable and nonnegative. |
| `divide-by-zero` | udiv(x,0)=M is the stipulated total word semantics. This is not a claim about C division. |
| `remainder-special` | urem(x,0)=srem(x,0)=x under the total contract. Signed remainder by −1 or +1 is zero. Literal 1 is −1 at w=1, so that case also gives zero. |
| `trailing-one-set` | set_low_bits(x,countr_one(x))=x: every bit being set was already one. |
| `leading-one-nonzero` | 1≤u L(x) iff sign(x)=1 iff x<s 0. |
| `signed-zero-min` | smin(x,0)=x if x<s 0, else 0. |
| `signed-minus-one-max` | smax(x,M)=M if x<s 0, else x; −1 is the largest negative signed value. |
| `distribute-select` | Applying a pure total expression to select(G,a,b) equals selecting the corresponding expression applied to a or b. The implementation uses this only for NOT, remainders, and clear_high_bits. |

## 3. Disjoint masks and leading-count elimination

All uses of x&y=0 below are checked by the pinned public kernel's `disjoint`
procedure on the actual expressions. The current KnownBits instances use z&o=0.

### Underflow-dependent high-bit clearing

Assume x&y=0 and put c=L(y). Then

\[
C\bigl(x,\operatorname{umax}((c-1)\bmod2^w,c)\bigr)
=\begin{cases}x,&\operatorname{sign}(y)=1,\\0,&\operatorname{sign}(y)=0.\end{cases}
\]

If c=0, the subtraction gives M, and clearing M≥w bits yields zero.
If c≥1, the subtraction does not wrap and umax(c−1,c)=c. The first c bits
of y are one, so the first c bits of x are zero; clearing them leaves x.
Finally c≥1 iff sign(y)=1. This proves `clear-leading-disjoint-underflow`,
including w=1.

### A masked logical shift

For x&y=0,

\[
x\mathbin{\&}(M\operatorname{lshr}L(y))=x.
\]

Shifting M right by c clears precisely its c highest bits (all bits if c=w).
Those bits of x are already zero. This proves `masked-leading-shift`.

### General observable identity with an arbitrary count

For every word-valued n, every w≥1, and x&y=0,

\[
x\mathbin{\&}\operatorname{smax}\bigl(C(S(y,n),L(y)),0\bigr)
=\begin{cases}
x\mathbin{\&}S(0,n),&\operatorname{sign}(y)=1,\\
0,&\operatorname{sign}(y)=0.
\end{cases}
\tag{G}
\]

If sign(y)=0, c=L(y)=0. For n=0 the left expression reduces to x&y=0.
For n>0, S(y,n) has its sign bit set, so signed max with zero yields zero.

If sign(y)=1, c≥1. Clearing c high bits removes the sign bit, making the
argument to signed max nonnegative. The cleared prefix consists of ones in y
and therefore zeros in x. Clearing it cannot change the final conjunction
with x. Hence the left expression equals x&S(y,n)=x&(y OR S(0,n))=x&S(0,n).
This proof includes n=0, n≥w, and w=1.

The current kernel implements a specialization, `masked-set-two`. For w≥2
and n=2, in the negative-y branch the sign bit of x is zero. Thus x&S(0,2)
is just x AND the second-highest-bit mask:

\[
x\mathbin{\&}\bigl(\operatorname{set\_sign\_bit}(0)\operatorname{lshr}1\bigr).
\]

This exactly matches the expression emitted by the rule. The general identity
(G) is a proved mathematical generalization and a separately tested statement;
it is not an additional automatically selected rule in this kernel.

For fixed n=h, the right side observes the sign of y and a fixed terminal
window of x. Consequently the family admits finite relational interfaces whose
memory depends on h, not on word width. A word-valued variable n can still leave
an unsupported variable mask operation; identity (G) alone does not decide it.

## 4. The four-state sign proof

The actual component-8 guard rewrites to o_b=M. KnownBits validity then gives
z_b=0 and concrete b=M, i.e. signed b=−1. The two simplified output masks are

\[
z'=\operatorname{sign}(z_a)?z_a:0,
\qquad o'=\operatorname{sign}(o_a)?M:o_a.
\]

The concrete result is y=sign(a)?M:a. The possible triples
(sign(z_a),sign(o_a),sign(a)) are exactly

\[
(1,0,0),\ (0,1,1),\ (0,0,0),\ (0,0,1).
\]

These are the four persistent sign cases. At each nonfinal position, the
current (z_a,o_a,a) bit has four allowed values from concrete membership in
KnownBits, independent of the final sign case. The checker enumerates all
4×4=16 combinations. At the final position it checks the four compatible
combinations whose current bits equal the stored sign case. Every output
constraint holds locally; word soundness follows for every positive length.
On the false guard branch the actual output is top=(0,0).

This is a decomposition of a source-bound proof: guard equivalence, branch
substitution, source/spec rewrites, and a finite sign interface. It is not a
claim that the earlier NFA was minimized to four states, nor that four is minimal.

There are three abstract sign cases for a: known nonnegative, known negative,
and unknown sign. Under b=−1 the output is respectively A, exact −1, or (0,o_a).
Each is the best KnownBits result in that branch: in the unknown-sign case,
all negative inputs produce −1 and nonnegative completions preserve a's lower
bits. This conditional statement does not claim optimality of the whole Smax
transformer or of the component outside its guard.

## 5. Lifting and whole-source composition

Each component is treated by a complete width partition: w=1, checked directly
on every valid input and concrete choice, and w≥2. Conditional rewrites preserve
the original expression on the latter domain. The regular proof then checks a
finite invariant of the expression/specification product, including the regular
length constraint w≥2. Initial-state inclusion, transition closure, and absence
of an accepted error imply correctness at every length in that domain.

The mixed certificate can instead use the sign proof for component 8, covering
all w≥1. Both proof forms establish the same component-level soundness contract.

The actual `solution` SSA is checked to call the certified components on the
original two arguments, then combine their results using the actual `meet`
definition. That definition is expanded and checked to OR the zero masks and
OR the one masks. Such an output represents the intersection of component
concretizations. If every component contains every concrete signed-max result,
their intersection does too. Totality and nonbottom inputs make that result
set nonempty, so no conflicting output masks can be introduced.

No external name, recorded success flag, or assumed helper semantics substitutes
for these checks. Models of LLVM poison and equivalence to generated C++ remain
separate from the explicit total-word contract proved here.
