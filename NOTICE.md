# Attribution and scope

The QKF research line and this project are attributed to **Leonid Shcherbakov**.
Implementation and release preparation used AI assistance. This statement does not
assign authorship of third-party research or assert formal verification of the code.

`examples/ntmy/and.mlir`, `or.mlir`, `xor.mlir`, `meet.mlir`, and `top.mlir` are
unmodified excerpts/files from:

- Repository: https://github.com/Hatsunespica/xdsl-smt
- Commit: `4ec509edab067d62c00f76778789170061ae299c`
- Source paths: `synthesized-transformers/KnownBits_{And,Or,Xor}/solution.mlir`
  and `tests/synth/KnownBits/{meet,top}.mlir`
- License: MIT; the original notice is retained in
  `third_party/xdsl-smt-LICENSE`.

Hashes are recorded in `examples/ntmy/SOURCES.json`. NiceToMeetYou and the upstream
artifact are the work of their respective authors. This project is independent
and does not claim their endorsement. Prior art and upstream performance results
should be cited from the original publications, not inferred from this repository.

The release contains the certifier application. Earlier QKF article sources,
C++ relation-closure experiments, full upstream snapshots, and exploratory verifier
investigations are not part of the runtime package.
