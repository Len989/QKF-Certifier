# Changelog

## 0.1.0a1 — 2026-09-11

First prepared public alpha of QKF Certifier.

- Package installation, `qkf` CLI, module entry point and Python API.
- Source-bound proofs for real AND, OR and XOR, including explicit helper definitions.
- Separate normalization search and proof replay.
- Version 3 certificates with strict JSON shape/type checking and published schema.
- Explicit soundness, refutation, normalization-only and fallback outcomes.
- Exact semantic signatures and batch verification.
- Comments and exact UTF-8 file hashing, output/input protection, bounded expansion.
- Mutation, concrete-oracle, property-based, CLI and packaging validation.
- CI configuration, reproducible examples, license and attribution.

Research v2 certificates are intentionally not accepted by this release. Regenerate
certificates from their source bundle; no migration may simply change the schema tag.
