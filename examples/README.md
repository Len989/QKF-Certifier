# Examples

The `ntmy` directory contains the three real positive examples and their explicit
helper definitions. Provenance and hashes are supplied alongside them.

`fallback_add.mlir` deliberately retains cross-bit arithmetic. Use it to verify
that normalization-only output is not mistaken for a target soundness proof.

Run `qkf batch examples/batch.json --json` from the repository root for the three
positive examples. See the root README for source-bound certificate generation
and replay commands.
