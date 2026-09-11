# Contributing

Install with `python -m pip install -e '.[dev]'`, then run `python -m pytest`,
`python -m ruff check .`, and `python -m ruff format --check .`.

Changes to trusted rules need a mathematical argument for every positive width,
including w=1 and boundary counts, plus an independent concrete regression.
A finite set of successful SMT queries is evidence, not an all-width argument.
Document every new semantic assumption; do not silently import backend-specific
poison/undefined behavior into the total-word contract.

New frontend operations must be fully parsed and typed. Unsupported syntax must
fail explicitly, including dead statements and unresolved external functions.
Do not infer the trusted concrete target from source annotations or certificates.

Changes to certificate meaning require a new schema version and compatibility
policy. Tests should cover both valid proofs and altered sources, helpers, paths,
steps, types, and specification bindings. A fallback must not be silently promoted
to `certified` by the CLI, batch wrapper, or examples.

For performance changes, state the input distribution, environment, whether source
parsing/proof generation is included, and timeout handling. Do not compare a warm
cache against a cold solver without saying so. Keep benchmarks separate from
correctness results. Include a minimal reproducer with correctness reports.
