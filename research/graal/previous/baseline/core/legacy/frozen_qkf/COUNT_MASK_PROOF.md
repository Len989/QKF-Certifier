# Exact finite interfaces for count-to-mask compositions

Research note, 12 September 2026. Backend: `qkf-count-mask-relation-v1`.

## Scope and semantic contract

Words have a positive width \(w\), and bits are indexed from 0 (least
significant) to \(w-1\). Arithmetic and counts follow the pinned QKF contract
`total-transfer-words-v2`; `transfer.neg` is bitwise complement. Counts of
consecutive equal bits lie in \([0,w]\), including the all-equal word. They
are representable as width-w words, since \(w<2^w\) for every \(w\ge1\).
Mask operations clamp their count to w. Logical shifts by w or more return 0.

The source-rewrite kernel is unchanged and is used only for w >= 2. Actual
source SSA is checked separately and exhaustively at w = 1. The new mask
interface itself is exact for every positive width, including w = 1.

This note supplies a mathematical justification for the new interface. Its
Python implementation and the existing rewrite/bit-relation interpreters
remain trusted. There is no claim of a Lean-checked theorem here.

## Definition: two observations of a consecutive run

Fix a desired bit \(d\in\{0,1\}\) and a word y. Let
\(t_i=[y_i=d]\). Define the low-end and high-end run masks by

\[
 R_i^{\mathrm{low}}=\bigwedge_{j=0}^{i}t_j,
 \qquad R_i^{\mathrm{high}}=\bigwedge_{j=i}^{w-1}t_j.
\]

If n is `countr_one(y)` for d = 1 or `countr_zero(y)` for d = 0,
then \(R_i^{\mathrm{low}}=1\) exactly when \(i<n\). If n is the
corresponding `countl` operation, \(R_i^{\mathrm{high}}=1\) exactly
when \(i\ge w-n\). These statements include n = 0 and n = w.

Therefore, for either matching end:

\[
 \operatorname{set}(x,n)_i=x_i\lor R_i,
 \qquad \operatorname{clear}(x,n)_i=x_i\land\neg R_i.
\]

For low-end counts, `shl(ones, n)` is the complement of the low run mask.
For high-end counts, `lshr(ones, n)` is the complement of the high run mask.
At n = w these shifts are 0, exactly as required. This proves the lowering
identities for eight mask compositions and four shift forms.

## Theorem 1: exact two-state low-end interface

Initialize \(p_0=1\). At position i output
\(R_i=p_i\land t_i\), and update \(p_{i+1}=R_i\).
The state alphabet is {0,1}; it does not depend on w.

**Proof.** By forward induction, \(p_i=\bigwedge_{j<i}t_j\), with the
empty conjunction equal to 1. Thus the emitted bit is exactly
\(R_i^{\mathrm{low}}\). All transitions are determined by their input;
each input word has one run and one output word. ∎

## Theorem 2: exact two-state high-end relation

Read in the same, least-to-most-significant direction. Guess the initial
state \(h_0\in\{0,1\}\). At each nonfinal position guess \(h_{i+1}\),
require

\[
 h_i=t_i\land h_{i+1},
\]

and emit \(R_i=h_i\). At the final position fix \(h_w=1\) instead
of guessing it, and check the same equation. This is a finite relation,
not a causal transducer in this reading direction.

**Proof of soundness.** Starting from the terminal boundary, backward
induction gives \(h_i=\bigwedge_{j=i}^{w-1}t_j\). Hence every accepting
run emits the required mask. **Proof of completeness and uniqueness.**
Assign those conjunctions to all states and assign \(h_w=1\). Every
transition equation is satisfied. Backward induction also shows that no
other state sequence can satisfy the terminal boundary. Thus every input
word has exactly one accepting run and one output word. ∎

The terminal boundary is essential. If it is replaced by 0, an all-matching
word can receive the all-zero mask. If one initial choice is omitted,
some inputs have no accepting run. Both mistakes are exercised by mutation
checks in `check_semantics.py`.

## Theorem 3: source-derived composition

Consider an acyclic word-expression DAG in the previously supported
regular fragment, extended with the twelve matched count-mask forms above.
Numeric count occurrences not consumed by such a form remain outside the
fragment. The compiler replaces each matched composition by a run-mask
node combined with AND, OR, or complement. Equal run nodes share state.

The resulting bit relation has exactly the graph of the original word
expression at every positive width, assuming the exactness of the prior
operator relations.

**Proof.** Apply structural induction to word-expression nodes. For a
matched composition, first fix the entire word produced by its child DAG.
Theorems 1 and 2 yield exactly its required run mask; the mask identities
give exactly the source output. Ordinary operator nodes use their existing
exact relations. The original DAG is acyclic, so each child word is fixed
before the corresponding semantic induction step, even when its bit-level
relation uses guesses about later positions. Synchronous product composes
these relations by equating shared child bits. Exactness gives both
directions of the graph equality. Structurally equal nodes denote the same
word, so sharing their unique run does not change the graph. ∎

This is a compositional theorem about the observed word operation. It does
not say that a numeric count has a two-element value domain, or that two
states suffice for an arbitrary surrounding program.

## State bound and certificate theorem

Let g be the number of comparison nodes, c the number of add/sub nodes,
l the number of one-bit left shifts, r the number of one-bit right shifts,
p the number of distinct low run nodes, and h the number of distinct high
run nodes. Let L be the largest bit length of an absolute literal in the
program, or 0. The implemented state-space bound before restricting length is

\[
 (L+1)\,2^{g+c+l+p+h+1}\,3^{r+g}.
\]

The factors account respectively for literal phase, Boolean comparison
guesses, carry/borrow bits, left-shift delays, the run states, a sticky
violation bit, pending right-shift bits, and comparison relations. The
width-at-least-two wrapper adds one Boolean length flag, multiplying this
bound by 2. It is independent of w but can be exponential in program size.
The primitive two-state result alone gives no guarantee of a small product.

There are \(2^{g+h}\) initial states and up to
\(16\cdot2^{r+h}\) nonterminal transition attempts per state. The 16
letters are exactly the valid one-bit pairs of nonbottom KnownBits inputs
and represented concrete inputs. End transitions fix shift boundaries,
fix the high-run terminal boundary, and validate comparison guesses.

A certificate lists an invariant I. The checker reconstructs the machine
from source and requires: (1) all initial states belong to I; (2) every
valid nonterminal successor of I is in I; (3) no valid terminal successor
of I has a set violation bit. Induction on prefix length then excludes
every accepted error word. Exactness of the expression relation converts
that language fact into KnownBits soundness for the caller-selected target
at all w >= 2. Exhaustive checking of the actual source at w = 1 completes
the positive-width claim. The checker does not trust the producer's verdict
or run reachability search; it recomputes all relevant transitions.

Source binding uses the existing public normalization certificate, checked
conditional rewrites, a simplified-expression digest, a newly recomputed
compiled-expression digest, and the explicit backend and target contracts.
Whole-solution proofs also check actual SSA calls and the actual meet helper.

## Explicit boundaries

* Low-end masks of `countl` and high-end masks of `countr` are not included.
* A count used numerically elsewhere still needs its own interface.
* Arbitrary variable shifts, division, and full multiplication are not added.
* Flag preconditions and poison are not modeled by the frozen target registry.
  Add/Sub flag families have stronger unconditional modular obligations;
  a counterexample to one is not an upstream correctness bug.
* Finite testing supports implementation confidence; it is not the reason
  these claims quantify over all positive widths.

Finite word automata for width-independent bitvector predicates are prior
work. A relevant primary reference is Bhat, Stefanesco, Hughes and Grosser,
“Certified Decision Procedures for Width-Independent Bitvector Predicates,”
OOPSLA 2025, [author publication page](https://grosser.science/pub/10.1145/3763148/).
This experiment concerns the exact count-mask interfaces, source binding,
and their measured contribution on the pinned corpus; it makes no claim
that finite automata themselves are new.
