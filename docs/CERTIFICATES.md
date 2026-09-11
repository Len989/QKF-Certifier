# Certificates and compatibility

The public format is `qkf-rewrite-v3`, described by
[certificate.schema.json](certificate.schema.json). Runtime checking uses a
strict, dependency-free validator and then verifies semantics; validating the JSON
schema alone does not verify a proof. Legacy research `qkf-rewrite-v2` files are
rejected: regenerate them from their original source bundles with this release.

A full certificate contains:

- `sources`: caller-chosen source labels mapped to SHA256 of exact UTF-8 content;
- `entry`, `target`, `semantics`: function and explicit specification binding;
- `initial_hash`: hash of the parsed/inlined expression;
- `steps`: local rule names and paths into the current expression, replayed in order;
- `normal_form`: the resulting expression tree;
- `rows`: nine input/output/concretization rows, recomputed by the checker.

A normalization-only certificate has `target=null` and no `rows`. Its only claim
is equality between source and normal form. The CLI requires `--normalization-only`
to check it, so it cannot accidentally become a target soundness verdict.

The source bundle is supplied again when checking. The checker never opens source
paths named inside a certificate and never infers the target from it. Source labels
and UTF-8 content are significant; comments and CRLF changes alter the hash even
if their mathematical semantics is unchanged. Use `read_bytes().decode('utf-8')`
when exact file-byte identity matters in Python.

Unknown fields, duplicate JSON keys, floats/Booleans in integer fields, NaN,
unknown format versions, missing steps, unsupported rule names and invalid paths
are rejected. Resource-budget failures are reported separately as fallback.

The versioned CLI result format is `qkf-result-v1`. Batch input/output use
`qkf-batch-v1` / `qkf-batch-result-v1`. Only a result with status `certified`
from target verification means the transformer was accepted. Results do not
inherit arbitrary claims from the certificate.

This is an alpha format. Breaking proof changes require a new schema tag; a future
release must not silently reinterpret a v3 proof under different semantics.
