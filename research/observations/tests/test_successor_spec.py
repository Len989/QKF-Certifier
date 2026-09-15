"""Independent numerical controls for the new, source-free successor target."""
from copy import deepcopy
from itertools import product
import random
import unittest

from research.observations.successor_spec import (
    CLAIMS, INITIAL, check_spec, columns, concrete_violation, decode,
    order_step, specification, step, violation,
)


class SuccessorSpecTests(unittest.TestCase):
    def test_complete_six_column_alphabet(self):
        self.assertEqual(columns(), ("0000", "0100", "0101", "0110", "0111", "1111"))
        self.assertEqual({c[:3] for c in columns()}, {"000", "010", "011", "111"})
        # In an optional column the competitor varies independently of the seed.
        self.assertEqual({c[2:] for c in columns() if c[:2] == "01"},
                         {"00", "01", "10", "11"})

    def test_monitor_matches_integer_semantics_exhaustive(self):
        comparisons = 0
        for width in range(1, 4):
            for packed in product(tuple(product(columns(), (0, 1))), repeat=width):
                state = INITIAL
                for column, output in packed:
                    state = step(state, column, output)
                word, outputs = zip(*packed)
                values = decode(word, outputs)
                for claim in CLAIMS:
                    self.assertEqual(violation(claim, state),
                                     concrete_violation(specification(claim), values))
                    comparisons += 1
        self.assertEqual(comparisons, 3768)

    def test_quantified_target_is_exact_numeric_successor(self):
        outputs_checked = 0
        for width in range(1, 4):
            for must, may, seed in product(range(1 << width), repeat=3):
                if seed & must != must or seed & ~may:
                    continue
                legal = [z for z in range(1 << width) if z & must == must and not z & ~may]
                expected = next((z for z in legal if z > seed), legal[0])
                for output in range(1 << width):
                    accepted = all(concrete_violation(specification(), {
                        "width": width, "must": must, "may": may, "seed": seed,
                        "output": output, "alternative": z,
                    }) is None for z in legal)
                    self.assertEqual(accepted, output == expected)
                    outputs_checked += 1
        self.assertEqual(outputs_checked, 584)

    def test_wide_integer_order_and_monitor(self):
        rng = random.Random(15092026)
        for sample in range(300):
            width = rng.randint(1, 512)
            may = rng.getrandbits(width)
            must = rng.getrandbits(width) & may
            seed = may if sample % 4 == 0 else must | (rng.getrandbits(width) & may)
            alternative = must | (rng.getrandbits(width) & may)
            output = rng.getrandbits(width)
            if sample % 3:
                output = must | (output & may)
            values = dict(width=width, must=must, may=may, seed=seed,
                          alternative=alternative, output=output)
            state = INITIAL
            for i in range(width):
                column = "".join(str((v >> i) & 1) for v in (must, may, seed, alternative))
                state = step(state, column, (output >> i) & 1)
            self.assertEqual(state[3:], tuple((a > b) - (a < b) for a, b in (
                (output, seed), (alternative, seed), (output, alternative))))
            for claim in CLAIMS:
                self.assertEqual(violation(claim, state),
                                 concrete_violation(specification(claim), values))
            cut = rng.randrange(width + 1)
            mask = (1 << cut) - 1
            low = (output & mask) - (seed & mask)
            previous = (low > 0) - (low < 0)
            extended = (output & ((mask << 1) | 1)) - (seed & ((mask << 1) | 1))
            self.assertEqual(order_step(previous, (output >> cut) & 1, (seed >> cut) & 1),
                             (extended > 0) - (extended < 0))

    def test_singleton_and_wrap_with_fixed_one_bits(self):
        for width in (1, 64, 4096):
            must = 1 << (width - 1)
            for may in (must, (1 << width) - 1):
                values = dict(width=width, must=must, may=may, seed=may,
                              output=must, alternative=must)
                self.assertIsNone(concrete_violation(specification(), values))
                if may != must:
                    values["output"] = may
                    self.assertEqual(concrete_violation(specification(), values), "wrap_not_minimum")

    def test_invalid_specs_do_not_weaken_the_contract(self):
        good = specification()
        changes = [
            lambda s: s.update(schema="unknown"),
            lambda s: s.update(claim="strict_successor_without_wrap"),
            lambda s: s.update(claim=True),
            lambda s: s.update(preconditions=[]),
            lambda s: s["preconditions"].pop(),
            lambda s: s.update(obligations=["must subset output subset may"]),
            lambda s: s.update(semantics="signed Java"),
            lambda s: s.update(extra=True),
        ]
        for change in changes:
            altered = deepcopy(good)
            change(altered)
            with self.assertRaises((ValueError, TypeError)):
                check_spec(altered)
        self.assertEqual(check_spec(good), "cyclic_successor")
        self.assertEqual(check_spec(specification("membership")), "membership")

    def test_bad_output_is_not_excluded_from_the_alphabet(self):
        for column, output in (("0000", 1), ("1111", 0)):
            state = step(INITIAL, column, output)
            self.assertEqual(violation("membership", state), "output_outside_mask")
            self.assertEqual(violation("cyclic_successor", state), "output_outside_mask")

    def test_each_obligation_has_a_negative_control(self):
        for reason, values in (
            ("output_outside_mask", dict(width=1, must=1, may=1, seed=1, output=0, alternative=1)),
            ("wrap_not_minimum", dict(width=2, must=0, may=3, seed=3, output=1, alternative=0)),
            ("not_strictly_above_seed", dict(width=1, must=0, may=1, seed=0, output=0, alternative=1)),
            ("skipped_legal_successor", dict(width=2, must=0, may=3, seed=0, output=2, alternative=1)),
        ):
            self.assertEqual(concrete_violation(specification(), values), reason)

    def test_concrete_witness_domain_validation(self):
        good = dict(width=2, must=1, may=3, seed=1, output=3, alternative=3)
        for key, value in (("width", 0), ("width", 4097), ("width", True),
                           ("seed", 0), ("alternative", 0), ("output", -1),
                           ("output", True), ("output", 4), ("may", 0)):
            with self.assertRaises(ValueError):
                concrete_violation(specification(), {**good, key: value})
        with self.assertRaises(ValueError):
            concrete_violation(specification(), {**good, "extra": 1})


if __name__ == "__main__":
    unittest.main()
