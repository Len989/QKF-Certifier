"""Constructed-only checks for the Run32 harness and its comparison control."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from . import cases,control,identity

SOURCE='class Demo { public static boolean f(long x) { return x > 0 && (x & (x - 1)) == 0; } }'
TARGET={'schema':'qkf-target-v2','kind':'signed_boolean_predicate',
        'source':{'entry':{'class':'Demo','method':'f'},'word_type':'long'},'goal':cases.POWER}


class Acceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from research.unified.v4 import prove
        cls.rows,cls.row_proof=prove(SOURCE,TARGET)
        cls.cells,cls.cell_proof=control.prove(SOURCE,TARGET)

    def test_matching_target_results(self):
        self.assertEqual(self.rows['inner'],self.cells['inner'])

    def test_identical_observation_package(self):
        self.assertEqual(self.row_proof['proof']['observations'],self.cell_proof['proof']['observations'])

    def test_identical_product_obligation(self):
        self.assertEqual(self.row_proof['proof']['obligation'],self.cell_proof['proof']['obligation'])

    def test_direct_check(self):
        self.assertEqual(control.check(SOURCE,TARGET,self.cell_proof),self.cells)

    def test_control_is_not_production_proof(self):
        from research.unified.v4 import check
        with self.assertRaises(ValueError): check(SOURCE,TARGET,self.cell_proof)

    def test_source_binding(self):
        with self.assertRaises(ValueError): control.check(SOURCE.replace('> 0','>= 0'),TARGET,self.cell_proof)

    def test_target_binding(self):
        other=deepcopy(TARGET); other['goal']=['negative']
        with self.assertRaises(ValueError): control.check(SOURCE,other,self.cell_proof)

    def test_closed_subset_rejected(self):
        bad=deepcopy(self.cell_proof); bad['proof']['obligation']['states'].pop()
        with self.assertRaises(ValueError): control.check(SOURCE,TARGET,bad)

    def test_rows_still_checked(self):
        bad=deepcopy(self.cell_proof); bad['proof']['observations']['observations']['rows'].clear()
        with self.assertRaises(ValueError): control.check(SOURCE,TARGET,bad)

    def test_cells_are_checked(self):
        bad=deepcopy(self.cell_proof); bad['proof']['observations']['observations']['cells'][0]['next']=0
        with self.assertRaises(ValueError): control.check(SOURCE,TARGET,bad)

    def test_result_is_not_trusted(self):
        bad=deepcopy(self.cell_proof); bad['result']['status']='refuted'
        with self.assertRaises(ValueError): control.check(SOURCE,TARGET,bad)

    def test_negative_final_width(self):
        source=SOURCE.replace('x > 0 && ','')
        r,p=control.prove(source,TARGET)
        self.assertEqual(r['status'],'refuted')
        self.assertEqual(control.check(source,TARGET,p),r)

    def test_budget_no_certificate(self):
        for budget in ({'max_states':1},{'max_observations':0},{'max_target_states':1}):
            r,p=control.prove(SOURCE,TARGET,budgets=budget)
            self.assertEqual(r['status'],'budget_exhausted'); self.assertIsNone(p)

    def test_unsupported(self):
        r,p=control.prove(SOURCE.replace('x > 0','(x >> 1) > 0'),TARGET)
        self.assertEqual(r['status'],'unsupported'); self.assertIsNone(p)

    def test_no_row_step_after_direct_monitor_creation(self):
        from unittest.mock import patch
        from research.signed_runtime.runtime import load
        from research.signed_targets.common import prepare
        from research.signed_runtime.core import Machine
        compiled,selection=prepare(TARGET)
        observation=self.cell_proof['proof']['observations']
        runner,_=load(SOURCE,selection,observation)
        monitor=control.DirectMonitor(runner,compiled['specification'],observation)
        with patch.object(Machine,'step',side_effect=RuntimeError('row call')):
            self.assertIsInstance(monitor.step(monitor.initial,'1'),tuple)

    def test_snapshot_catches_change(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'a'; p.write_text('a'); before=identity.snapshot(d)
            p.write_text('b'); self.assertNotEqual(before,identity.snapshot(d))

    def test_snapshot_catches_addition(self):
        with tempfile.TemporaryDirectory() as d:
            before=identity.snapshot(d); (Path(d)/'a').write_text('a')
            self.assertNotEqual(before,identity.snapshot(d))

    def test_snapshot_executable_modes(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'a'; p.write_text('a'); p.chmod(0o644); before=identity.snapshot(d)
            p.chmod(0o755); self.assertNotEqual(before['tree'],identity.snapshot(d)['tree'])

    def test_snapshot_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d)/'a').symlink_to('/tmp')
            with self.assertRaises(ValueError): identity.snapshot(d)

    def test_duplicate_json(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'a'; p.write_text('{"a":1,"a":2}')
            with self.assertRaises(ValueError): cases.load(p)

    def test_nonfinite_json(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'a'; p.write_text('{"a":NaN}')
            with self.assertRaises(ValueError): cases.load(p)

    def test_exclusive_write(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'a'; cases.save(p,{})
            with self.assertRaises(FileExistsError): cases.save(p,{})


if __name__=='__main__': unittest.main()
