# Local validation record

Prepared 2026-09-11, version 0.1.0a1.

- Environment executed: Python 3.12.14, Linux x86_64, glibc 2.39.
- Final source test run: **67 passed in 9.46 seconds**.
- Includes 680 real-source mutations, exhaustive input checks at widths 1..4,
  500 deterministic property-based cases, strict certificate validation,
  source/helper binding, comments/CRLF, complexity limits, API and CLI behavior.
- Ruff static checks and formatting checks completed locally.
- Runtime dependencies: none. Development dependency versions used:
  setuptools 84.0.0, build 1.6.1, pytest 9.1.1, hypothesis 6.168.0,
  Ruff 0.16.7, jsonschema 4.26.0.
- Local API timing output: `benchmarks/package_timings.json`. These are illustrative
  measurements on a shared host, not an isolated performance study.

Distribution build/install checks are recorded in the companion release archive's
`RELEASE_VERIFICATION.json`, generated after the distributions are built. That
record covers wheel installation outside the source checkout, building a wheel
from the source distribution, and running commands without runtime dependencies.

Not executed here: GitHub-hosted CI, Windows/macOS, other Python versions,
a native synthesis integration benchmark, or formal verification of the Python
implementation. The CI workflow is prepared to test the additional environments
once the repository is uploaded.
