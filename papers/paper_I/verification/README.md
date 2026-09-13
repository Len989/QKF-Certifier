# Reproduce the finite checks

Python 3.10 or later; standard library only. From the extracted source archive:

```sh
python verification/verify_article.py --output verification/results.json
```

The script exits with an assertion failure if a checked property fails.
The stored results were generated successfully during preparation.

It compares the entire labelled interface at horizons 1 and 2, using (a) input
subterm congruence closure and (b) raw row pushouts, carrier feedback, and the
kernel-saturation construction. The methods share a small union-find utility,
so they are separate mathematical implementations, not independently developed
formal verifiers. There are 148 two-element unary cases, 592 two-element binary
cases, and 64 seeded three-element mixed cases: 804 in total.

Additional checks cover the displayed four-element table (5 classes then 3),
all congruence partitions and completion maps for the three four-element repair
examples, the three-element amplification example, the empty-row completion
example, and the sharp feedback family for 2 through 8 carrier elements.

The script contains the tables explicitly. No external repository or dataset is
needed. Finite evidence does not replace the mathematical proofs in the article.
