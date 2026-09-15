# Actual execution record and acquisition deviation

The frozen protocol, corpus and engine fingerprints were prepared before local
corpus execution. Publication of that protocol through GitHub.create_tree was
blocked by the tool safety layer with the message that it could not determine
the request's safety status. No alternative publication channel or renamed
payload was tried. No new branch, commit, PR or CI run was created.

The two new source files were read through the GitHub connector at the pinned
revisions (BitUtil.java blob 2389e3b0485dbd754593957986c78c8b83573aad;
Long.java blob 2fb2d18a78c80dea8e2ca0c17d6c7c7d8716e85c). Complete originals could
not be materialized into the computation environment. Direct network reads
failed DNS resolution; Files materialization reported disabled library access.
Thus the complete original blob verification required by PROTOCOL.md has NOT
been performed locally for these two files.

Instead, a clearly separate provisional run used twelve manually transferred,
reviewed public-static declaration substrings from the connector's source reads.
No method name, signature or body logic was rewritten. Their exact local bytes,
SHA256 values, source repository/commit/blob identities and original notices
are preserved with the experiment artifacts. This review is NOT a mechanized
proof of excerpt-to-original correspondence. Native wrapper constants are copied
from the same source reads. Their ordinary enclosing classes and intrinsic
annotations are not reproduced; the Long counting methods use the host JVM's
Integer helpers.

Four known Graal calibration goals use complete originals restored from the
previous PR #9 artifact. Their full Git blob identities WERE checked locally.
These calibration proofs are not twelve-method external coverage.

Two provisional runs, ordinary Python and python -O, have identical SEMANTIC.json
records and all four package bytes. Each reports frozen_protocol_complete=false.
The pending full-source mode uses complete downloads, verifies immutable Git
blobs and copies the declarations mechanically. It must be run separately; the
provisional run cannot be relabeled as that acceptance. No Python 3.10/3.12 CI,
new Lean build, solver comparison or frozen-proof benchmark acceptance is claimed.

A full old 256-test observation-suite attempt under -O was interrupted by the
execution tool without a final suite/exit record. It is not counted as passing.
The completed 22 harness tests were run both normally and under -O. The engine
file set/hash remained identical to the frozen 79-file production baseline.
