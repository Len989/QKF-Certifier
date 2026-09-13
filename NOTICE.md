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

The wheel and ordinary Python source distribution contain the certifier
application. The full research source archive additionally contains the selected
research capsules, source excerpts, experiment records and three manuscript
packages. Their original attribution and source manifests are retained.

QKF-authored code is MIT, as stated in the project and accompanying code licenses.
Upstream Graal excerpts retain their original GPL-2.0-only with Classpath-exception
notice; their complete license texts are under `third_party/graal/`. The expanded
NiceToMeetYou research corpus retains the upstream MIT notice. Do not apply this
repository's code license to third-party source or to the manuscripts by inference.

The manuscript/prose license remains the author's publication choice described
in each manuscript package. The retained notes propose CC BY 4.0 for a later
deposit; this preparation does not make that deposit or assign a DOI.
