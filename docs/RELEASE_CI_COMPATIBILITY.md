# Release 0.3.0a1 and historical research checks

The release changes package metadata and Paper III. Its published tree is
`441169fea2a6f17bd2ec393a06e0abcb2b3b257e`; its accepted research base is
`eca90f9252da4480d77c1f8cb4b7062470c57b89`. The historical whole-tree guards
include README, papers, workflows, and the package version. Consequently, they
correctly reject the unmodified release tree as different from those archives.

Package **Test and build** jobs build and test the actual PR tree, including
version `0.3.0a1`, on the existing OS/Python matrix. The release compatibility
job also audits that actual tree and runs negative controls in both Python modes.

Research jobs now create an explicitly recorded, temporary Git commit. Only
the exact publication changes in the pinned release tree and the nine enumerated
CI harness files are restored to accepted pre-release metadata. Both version
files must differ by the single `0.2.0a1` to `0.3.0a1` substitution. Unrecognized
metadata bytes, missing files, mode changes, and package logic changes in those
files fail the audit. Every other PR change remains in the research tree.

Each affected job uploads `release-compatibility.json` alongside its evidence.
It records the actual PR commit/tree, temporary research commit/tree, and every
restored path with its old/new blob and mode. Source archives and experiments
refer to this explicitly identified research tree. They are not claimed as
experiments on a byte-identical release tree. Temporary commits are not pushed.

All scientific source bytes are retained from the actual PR, except the
validated package version literal. None of the original preservation modules,
test registries, engine inventories, corpus seals, proof checks, or negative
controls is edited or disabled. Existing scientific modifications and deletions
still reach the original guards; additive research files still reach the normal
registered test harness. Future publication versions require an explicit policy
update instead of silently accepting arbitrary metadata.

## Archived Run27 runtime

PR and manual runs validate the exact corpus, inventory, seals and constructed
tests using the gate's existing metadata-only mode. Their artifact separately
records actual and registered runtime data and any drift. They do not evaluate
external candidates or claim exact runtime reproduction. The original authorized
push path still requires the complete strict runtime gate before evaluation.
No runtime lock or historical result is rewritten to match a newer hosted image.

## Published release

This PR integrates the already published release into `main` and updates CI.
It does not move `v0.3.0a1`, replace its assets, or label the integration commit
as the source of those existing distributions. The release manifest remains the
record of the published release payload; this document records the later CI work.
