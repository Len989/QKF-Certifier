"""Fresh full packages retain the archived fingerprints and replay without search."""
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
import tempfile

from research.observations.run_composition_experiment import BASELINE, run, verify_baseline
from research.observations.run_io import read_json

ROOT=Path(__file__).resolve().parents[3]


class CompositionEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        cls.evidence = Path(cls.directory.name) / 'proofs'
        with redirect_stdout(io.StringIO()):
            run(cls.evidence, max_width=1)

    def test_all_retained_proofs_are_replayed_unresolved_report_is_not_a_proof(self):
        with redirect_stdout(io.StringIO()): summary=run(self.evidence,replay=True)
        self.assertEqual(summary['proof_certificates'],16)
        self.assertEqual(summary['counts'],{'certified':3,'refuted':13,'unresolved':1})
        self.assertIsNone(summary['cases']['source.descending.strict']['proof_sha256'])
        self.assertEqual(summary['cases']['source.descending.strict']['replay_semantics'],
                         'report only; no mathematical verdict')

    def test_manifest_matches_every_generated_artifact(self):
        manifest=read_json(self.evidence/'MANIFEST.json',package=True)
        actual={p.relative_to(self.evidence).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                for p in self.evidence.rglob('*') if p.is_file() and p.name not in {'MANIFEST.json','README.md'}}
        self.assertEqual(manifest,actual)

    def test_fresh_retained_replay_without_search_or_native_modules(self):
        code='''
import builtins,json,io,sys
from contextlib import redirect_stdout
original=builtins.__import__
def guarded(name,*args,**kwargs):
    parts=name.split(".")
    blocked={"composition_validation","target_templates","subprocess","property_kernel","successor_kernel",
             "z3","cvc5","pysmt","bitwuzla","sympy","ascending_validation"}
    if any("producer" in p or p in blocked for p in parts):
        raise AssertionError("forbidden replay dependency: "+name)
    return original(name,*args,**kwargs)
builtins.__import__=guarded
from research.observations.run_composition_experiment import run
with redirect_stdout(io.StringIO()): result=run(sys.argv[1],replay=True)
print(json.dumps({"proofs":result["proof_certificates"],"counts":result["counts"]}))
'''
        for options in ([],['-O']):
            result=subprocess.run([sys.executable,*options,'-c',code,str(self.evidence)],cwd=ROOT,text=True,capture_output=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads(result.stdout),{'proofs':16,'counts':{'certified':3,'refuted':13,'unresolved':1}})


if __name__=='__main__':unittest.main()
