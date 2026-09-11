# Releasing QKF Certifier

The source repository is [Len989/QKF-Certifier](https://github.com/Len989/QKF-Certifier).
The initial version is **0.1.0a1 / research alpha**, licensed under MIT.
Preserve the separate upstream MIT notice in `third_party/xdsl-smt-LICENSE`.

## Verified first upload

The first complete code upload passed all eight GitHub Actions jobs: tests on
Linux/Python 3.10–3.14 and Python 3.12 on Windows/macOS, plus distribution build,
lint/format checks, and an installed-wheel smoke check outside the checkout.

- Reviewed commit: `4beeb5b5399909dc9abb7da25acec2d8704657bf`.
- [Successful run](https://github.com/Len989/QKF-Certifier/actions/runs/34636148287).
- [Current runs](https://github.com/Len989/QKF-Certifier/actions/workflows/ci.yml).

The historical local preparation record remains in `LOCAL_VALIDATION.md`.
A subsequent release must use a successful run of its own final commit.

## Create the first release

1. Finish the intended file and documentation changes on `main`.
2. Wait for all eight jobs of **Test and build** to pass for that final commit.
   Check that the run refers to the commit being released.
3. Open the successful run, download the **distributions** artifact, and extract
   its wheel and source distribution. Use these files from the final run, since
   older distributions may contain older metadata or documentation.
4. Open [Releases](https://github.com/Len989/QKF-Certifier/releases) and draft a
   new release with tag **v0.1.0a1** at the tested commit. If `main` has moved,
   select the tested commit rather than an untested branch tip.
5. Use title **QKF Certifier 0.1.0a1**, add the description below, and attach
   `qkf_certifier-0.1.0a1-py3-none-any.whl` and
   `qkf_certifier-0.1.0a1.tar.gz` from the artifact.
6. Mark **This is a pre-release**, review the files and publish when ready.

PyPI publication is a separate optional step; a GitHub release does not publish
the package to PyPI. There is no automatic package publishing workflow here.

## Suggested release description

First public alpha of QKF Certifier, a Python CLI and API for source-bound
KnownBits certificates with no runtime dependencies.

- Complete all-positive-width proofs for a coordinatewise fragment, including
  real AND, OR and XOR transformer examples from the NiceToMeetYou artifact.
- Checked normalization, explicit fallback outcomes, and independent proof replay
  without rerunning the normalization search.
- Strict certificate validation, mutation tests, concrete-oracle regressions,
  documented word semantics, and cross-platform CI.
- MIT license; QKF research line and project attributed to Leonid Shcherbakov.

The guarantees are conditional on the documented semantics and supported input
fragment. The Python implementation is not formally verified, and this release
is not a general replacement for an SMT verifier or a full synthesis system.

## Local release checks

```sh
python -m pip install -e '.[dev]'
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m build
```

## Research development

Future work includes integration into a synthesis loop, wider proof coverage for
carry-dependent arithmetic, independent audit or formalization of the trusted
kernel/frontend, and larger real-corpus evaluation. These are research goals
rather than claims of this alpha release.

Release UI instructions follow [GitHub's release guide](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository).
