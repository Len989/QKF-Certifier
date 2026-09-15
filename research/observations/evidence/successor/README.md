# Independent ascending successor evidence

`SNAPSHOT.json` retains ten checked property certificates: two independent goals
for each of the five existing ascending sources. Seven are positive closed
observations; three are independently checked cyclic-successor refutations.
Source bytes and source-model certificates are reused from `../ascending/`, with
explicit hashes and fixed paths. Neither a bundled source model nor a bundled
choice of goal is silently trusted.

The snapshot was produced on commit
`33e1bd0e5163a89acba60d263d9059552ec569bf` by
[Research and Lean run 34931420357](https://github.com/Len989/QKF-Certifier/actions/runs/34931420357),
job `observation-inference`, step `Record the compact successor replay snapshot`.
The [full run artifact](https://github.com/Len989/QKF-Certifier/actions/runs/34931420357/artifacts/10382230316)
contains separate source/specification/certificate files, results, bounded JVM
validation, budget control and a SHA-256 manifest. Its zip SHA-256 is
`69347ef1c6aa00a09162a4b74b306bc752d074d17fb2f43c96371d9e772c8326`.

From the repository root, without producers, SMT or Java:

```sh
python -O -m research.observations.replay_successor_evidence
```

The command reports `replayed` only after the ordinary property checker verifies
all ten packages against independently chosen supported goals and obtains the
expected seven certifications / three refutations. Exit zero for this regression
runner does not mean that every source satisfies the strong target. For a
user-selected source and goal, use `successor_cli check` and inspect its verdict.

Recreate a standalone experiment with
`python -m research.observations.run_successor_experiment reproduction/successor_01`.
Add `--native` for the separate bounded Java 17+ validation. See the
[Russian report](../../SUCCESSOR_REPORT_RU.md) for contracts, results and limits.
