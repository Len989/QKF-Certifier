# Proposed addition to Paper III: observed shifts and a complete Umin proof

Research snapshot: 12 September 2026. Source pin:
`f93561682319e8b911ed32c01583f2a496dc59fc`.
New rewrite extension: `qkf-observer-identities-v1`.
Preserved relation backend: `qkf-count-mask-relation-v1`.

Insert the mathematical result after the count-mask interface construction,
and the measured results in the evaluation section. This text extends that
construction and does not assign new numbering or bibliographic identifiers
to Papers I and II. It has not been applied to a published paper version.

## Observing a shifted word through a leading-run mask

Let L(x) denote the number of leading one bits in a width-w word, and let
H(n) set the highest min(n,w) bits of an otherwise zero word. Under the
declared total shift semantics, for every positive w and unsigned word n,

\[
 \operatorname{lshr}\bigl(H(L(\operatorname{shl}(x,n))),n\bigr)
 = H\bigl(L(x\lor H(n))\bigr)\land\neg H(n).
\]

For n>=w, both sides are zero. For n<w, write r for the leading-one run
of the lower w-n-bit block of x. Both sides mark exactly the r bits
immediately below the first n bits. This proves the identity, including
the all-matching block and zero-shift boundaries.

When n=L(y), the right side consists of two nested instances of the existing
high-run interface and ordinary Boolean operations. Thus this observation
of variable shifts has an exact finite interface even though a general
numeric-shift interface was not added. The identity alone does not eliminate
an arbitrary numeric count: the remaining H(n) must itself be supported.

The resulting mask also has a three-state deterministic description under
most-significant-bit-first reading: skip the leading ones of y, emit the
following run of ones of x, then emit zeros. The states are reachable and
pairwise distinguishable by a single next input letter, so three states
are necessary under this deterministic synchronous transducer convention.
This is a property of the observed function. The implemented certificate
uses the existing least-significant-first relation product; it is not
claimed to have been minimized to that transducer.

For a fixed k and w>=max(1,k), a second useful observer is
\(\operatorname{clear\_low\_bits}(x,w-k)=x\land J_k\), where J_k marks
the highest k bits. J_k can be constructed from the sign-bit mask and
fixed one-bit shifts. This interface depends on k rather than on w; the
width condition is needed to exclude modular underflow of w-k.

These constructions give further concrete instances of the observational
approach developed across the preceding papers: adequacy is established
for a source-derived observation before finite invariant checking is used
to certify an abstract transformer.

## Evaluation: closing the original Umin solution

Twelve checked rule families were layered over the previous normalization
and count-mask backend. The concrete target registry and search limits
were held unchanged. On the same 39-solution, 411-component corpus, exact
compilation coverage increased from 102 to 124 components, and positive-width
component certificates increased from 70 to 82. All earlier proofs were
retained. Seven new proofs concern ordinary total targets and five concern
stronger unconditional modular obligations for flag families.

The original Umin solution is now completely certified: all seven guarded
components and their actual SSA composition through the actual meet helper
were checked. Its component invariants contain 60, 662, 134, 17, 158, 409,
and 116 states, respectively, totaling 1,556 states and 26,346 valid transition
checks. Component 6 uses the shifted-mask identity after its source guard
has been proved equivalent to the second input's zero mask being zero.
Whole-solution coverage therefore increases from four to five of 39:
AND, OR, XOR, Smax, and Umin under the explicit total target semantics.

The twelve new proofs use 899 states and 15,630 valid transition checks in
total. Four earlier proofs become smaller, saving another 446 states and
7,141 checks. All current proofs total 26,698 states and 440,391 checks.
No configured search budget was exhausted. These counts measure this
certificate representation and are not an SMT performance comparison.

For implementation validation, 54,138 bounded identity instances were checked
against an independent whole-word oracle, including 21,844 exhaustive
word/shift pairs for the principal identity at widths one through seven.
All 411 actual source components were compared with the rewritten expressions
on 332,910 valid abstract input pairs at widths two and three. For all seven
Umin components, every accepting relation path was enumerated on 5,670 of
those inputs. Full-source regression of the five certified solutions at
widths one through four covered 36,900 abstract pairs and 349,520 represented
concrete pairs. Width/premise failures and altered certificates were rejected.

Two additional source-validated counterexamples were found for stronger
unconditional flag-family obligations. All 24 retained counterexamples belong
to that scope; they do not refute the native flag/poison contracts of the
upstream artifact. The new equalities are mathematically justified, but the
Python rewrite and relation interpreters remain trusted. Formalization of
the kernel and general solver coverage are further tasks.
