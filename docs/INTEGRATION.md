# Integration

## Synthesis or compiler pipeline

Call `verify(sources, target, entry)` for each candidate, with the concrete
specification chosen by the caller. Handle the result explicitly:

```python
from qkf_certifier import verify

result = verify(sources, target="xor")
if result["status"] == "certified":
    accepted_certificate = result["certificate"]
elif result["status"] == "unsound":
    counterexample = result["witness"]
else:
    # Queue the original candidate for the project's existing verifier.
    deferred_candidate = sources
```

The final branch does not mean sound. The package does not start another solver
automatically and does not impose its semantic contract on a different backend.
Check the frontend/lowering agreement separately when integrating a dialect.

Before reusing a certificate after rewriting/optimizing a candidate, replay it
against the actual new source. A stale source hash must fail. To preserve an
existing proof across source changes, generate a new source-bound certificate;
changing the hash alone does not prove the new expression.

## Semantic quotient

For coordinatewise mask functions, `inspect` returns a five-hex-digit string
encoding 18 meaningful bits. Rows are ordered as the Cartesian product of
`[(1,0), (0,1), (0,0)]` with itself. Bit `2*i` is the zero-mask output at row i;
bit `2*i+1` is its one-mask output. Equal signatures mean equal mask functions
under this input contract at all positive widths.

The pinned meet helper ORs corresponding masks, so its action on signatures is
bitwise OR. For a fixed target, sound signatures are subsets of the target's exact
known-bit obligations. This supports exact deduplication and residual-coverage
scoring. A soundness cache key needs the target, entry-input contract, semantic
contract, and signature. Every new source still needs a checked normalization
proof before it belongs to that class. This argument does not apply directly to
unnormalized addition, carries, arbitrary guards, or joins in other domains.

## Batch input

Paths are resolved relative to the manifest. Helper labels are explicit and unique.
The CLI checks every valid item and emits per-item results; malformed manifest
structure is an input error. Batch verification does not write certificates.

```json
{
  "schema": "qkf-batch-v1",
  "items": [
    {
      "id": "xor-candidate",
      "source": "ntmy/xor.mlir",
      "target": "xor",
      "helpers": {"meet": "ntmy/meet.mlir"},
      "entry": "solution"
    }
  ]
}
```
