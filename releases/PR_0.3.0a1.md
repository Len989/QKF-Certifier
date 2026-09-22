# Prepare QKF 0.3.0a1 and Paper III v3.0

The accepted work through PR51 is newer than the published 0.2.0a1 release and
Paper III v2.0. This preparation integrates the scientific account, records the
complete follow-up history, and builds versioned application and research assets.

The release delta changes manuscript/release documentation and version metadata.
Research engines, formal sources, public runtime behavior, frozen data, historical
protocols and preservation policies are unchanged. `RELEASE_MANIFEST.json` and
the kit's `RELEASE_DELTA.json` bind the prepared tree to accepted base
`eca90f9252da4480d77c1f8cb4b7062470c57b89`.

Paper III v3.0 incorporates observation inference, signed source interfaces,
typed ground proofs, checked summaries, internal SDK comparisons and Lean
ground/composition soundness. It preserves the distinction between native source
assumptions and the decoded typed calculus. Ordinary SDK is a QKF implementation.

Local validation: 67 package tests; 77 ground-query/SDK tests; lint/format;
wheel/sdist builds; clean installed-wheel XOR verification; 45 formal adapter
tests on the unchanged accepted baseline in each Python mode. See
`docs/RELEASE_VALIDATION_0.3.0a1.md` for exact scope and manuscript QA.

The historical whole-tree preservation guards deliberately reject changed
release documents. A release-only delta audit is provided; those guards were
not relaxed. Do not present baseline CI as fresh CI for this preparation commit.
If merging through a PR requires new policies for release documentation, review
that separately rather than disabling an existing required check.

The candidate release is an alpha pre-release. Zenodo receives a new version
of the existing Paper III record. No new version DOI or publication is asserted
by preparing these files.
