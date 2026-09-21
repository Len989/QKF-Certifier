# Current experimental summary SDK (PR45)

Start with [applicable summaries](applicable_summary/README_RU.md) for the current
`build → check → apply → explain` research path, and run:

```sh
python -m research.applicable_summary.example
```

Python 3.10+ and a full checkout are required. A fresh process checks portable
foundations without planner, producers, Java or SMT; checked application uses
the sufficient action without executing the original program.

| Capability | Current boundary |
|---|---|
| Signed native facts, independent consumers and direct dependency certificates | Conditional Boolean source equality, exact guards/width, target counts 0..3 |
| Source-free application and new-consumer sufficiency | Checked finite target action; changed scope or an uncovered goal requires explicit refinement |
| Cross-goal lemmas | Available explicitly; `no_lemmas` remains default after the PR44 cost result |
| Source-bound forcing I | Explicit in the separate three-physical-phase local profile; direct cell is default after A1 |
| PR41–44 and coverage certificates | Explicit checked imports preserve their original evidence and scope; new build has no legacy coverage fallback |
| Broader IR/adapters, whole transformers, F1 and causal acceptance | Planned; not established by this SDK |

See the [format and trust map](applicable_summary/FORMAT_TRUST_RU.md),
[validation record](applicable_summary/VALIDATION_RU.md), and
[roadmap](../docs/QKF_ROADMAP_v0.4_RU.md). This is an experimental repository API;
the installed `qkf` keeps its own contract. [Historical research and release profiles](README.md) retain their frozen documentation and results.
