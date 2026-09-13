# Changelog

## 0.2.0a1 — prepared candidate, 2026-09-13

- Rewrite Paper III as manuscript 2.0 around consumer observations, forced rows,
  whole-word reconstruction and signed mask/interval carriers. Preserve v1.
- Include frozen KnownBits research (11/39 whole programs, 104/411 components)
  and Graal universal upper / conditional lower proof capsules.
- Add a standalone Lean 4.33.0 pilot with audited assumptions and saved controls.
- Add a source-integrity-checking research replay runner and dedicated CI jobs.
- Add claim/evidence maps, historical reports and current release validation.
- Keep CLI semantics, its 29 rewrite rules and qkf-rewrite-v3 schema unchanged.
  The research profiles are separate; installing the wheel does not enable them.

This is a research alpha, not full Graal create verification or general SMT
replacement. Publication and the final remote CI status are separate steps.

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
