# Preparing the first GitHub release

The source tree is ready to become a repository named `qkf-certifier`. This package
has not been uploaded to GitHub or PyPI. There are no repository-owner placeholders
inside the executable code, no tokens, and no automatic publishing workflow.

## Decisions before publishing

1. Use the proposed MIT license or replace it before publication. MIT is already
   recorded in LICENSE, pyproject.toml and CITATION.cff; keep these consistent.
   Preserve the separate upstream MIT notice in every case.
2. Choose the GitHub account/repository location. Once it exists, add its real URL
   to pyproject project URLs and CITATION.cff if desired. No URL was invented.
3. Publish as **0.1.0a1 / research alpha**. A narrow functioning tool can be useful
   now; a general all-operation verifier or machine-checked trusted core is a later
   milestone. Do not describe this release as a complete replacement for SMT.

## Upload and run CI

Create an empty repository on GitHub, then follow GitHub's commands for pushing an
existing local directory. Include the `.github` directory so automated checks run.
The package is self-contained; do not upload the surrounding scratch workspace,
virtual environments, old research archives, or installed third-party dependencies.

The included CI tests Linux/Python 3.10–3.14 plus Python 3.12 on Windows and macOS.
It also builds distributions and installs the wheel outside the checkout. These
remote environments remain unverified until the workflow actually runs on GitHub.
Resolve a failing job before attaching a release artifact.

## Local gates and release artifacts

```sh
python -m pip install -e '.[dev]'
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m build
```

Create a GitHub release marked as a prerelease, tag `v0.1.0a1`, and attach the wheel
and source distribution from `dist`. The uploaded source repository remains the
primary place for examples and full documentation. PyPI publication is optional;
the distribution name has not been reserved or checked for availability.

Suggested release description:

> First alpha of QKF Certifier, a dependency-free Python CLI and API for
> source-bound KnownBits certificates. Supports complete all-positive-width proofs
> for a coordinatewise fragment, including real AND/OR/XOR examples, and checked
> normalization with explicit fallback elsewhere. Includes strict proof validation,
> mutation tests, concrete-oracle regressions, and documented semantics.

## What remains research work

- A maintained adapter to an actual synthesis loop and measured end-to-end impact.
- Proof coverage for carry-dependent arithmetic and more guarded components.
- Independent audit or formalization of the trusted kernel/frontend.
- Stable semantics agreement with each production lowering/backend.
- Broader real-corpus evaluation, beyond the three complete examples.

These are meaningful milestones for a stronger future tool, not prerequisites for
sharing this clearly scoped alpha. See LOCAL_VALIDATION.md for what was actually
run during preparation.

Packaging and workflow conventions follow the
[Python Packaging User Guide](https://packaging.python.org/en/latest/tutorials/packaging-projects/)
and [GitHub's Python CI guide](https://docs.github.com/en/actions/tutorials/build-and-test-code/python).
