"""The composition command does not reinterpret the old run CLI or its packages."""
from contextlib import redirect_stdout, redirect_stderr
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research.observations.composition_cli import main
from research.observations.composition_program import program, variants
from research.observations.composition_spec import specification
from research.observations.run_io import read_json

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT / 'research/observations/evidence/typed_targets'


class CompositionCliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources, cls.dependencies = {}, {}
        for role, claim in (('ascending','cyclic_successor'),('descending','maximum')):
            path=EVIDENCE / (role+'.original.'+claim)
            cls.sources[role]=(path/'source.java').read_bytes().decode('utf-8')
            cls.dependencies[role]=read_json(path/'package.json',package=True)
        cls.models={r:p['proofs']['source'] for r,p in cls.dependencies.items()}

    def command(self,*args):
        out,err=io.StringIO(),io.StringIO()
        with redirect_stdout(out),redirect_stderr(err): code=main([str(x) for x in args])
        return code,json.loads(out.getvalue()),err.getvalue()

    def setup_files(self,directory,wrapper=None):
        root=Path(directory)
        p=root/'program.json';p.write_text(json.dumps(wrapper or program()))
        s=root/'goal.json';s.write_text(json.dumps(specification()))
        for role,source in self.sources.items():
            (root/(role+'.java')).write_bytes(source.encode())
        return root,[p,'--descending-source',root/'descending.java','--ascending-source',root/'ascending.java'],s

    def test_templates_are_written_not_certified(self):
        with tempfile.TemporaryDirectory() as d:
            for command in ('spec','example'):
                path=Path(d)/(command+'.json')
                code,result,_=self.command(command,path)
                self.assertEqual(code,0);self.assertEqual(result['status'],'written')
                before=path.read_bytes()
                self.assertEqual(self.command(command,path)[0],64)
                self.assertEqual(path.read_bytes(),before)

    def test_verify_check_explain_and_portable_copy(self):
        with tempfile.TemporaryDirectory() as d:
            root,args,spec=self.setup_files(d)
            output=root/'answer'
            code,result,_=self.command('verify',*args,'--spec',spec,'--output',output)
            self.assertEqual(code,0)
            self.assertEqual(result['status'],'certified')
            copied=root/'moved.json';copied.write_bytes((output/'certificate.json').read_bytes())
            for command in ('check','explain'):
                code,result,_=self.command(command,*args,'--spec',spec,'--certificate',copied)
                self.assertEqual(code,0);self.assertEqual(result['status'],'certified')
            self.assertTrue(result['explanation']['replayed'])
            old=(output/'certificate.json').read_bytes()
            self.assertEqual(self.command('verify',*args,'--spec',spec,'--output',output)[0],64)
            self.assertEqual((output/'certificate.json').read_bytes(),old)

    def test_refutation_corruption_and_missing_external_inputs(self):
        with tempfile.TemporaryDirectory() as d:
            root,args,spec=self.setup_files(d,variants()['empty_at_maximum'])
            output=root/'answer'
            self.assertEqual(self.command('verify',*args,'--spec',spec,'--output',output)[0],1)
            certificate=output/'certificate.json'
            self.assertEqual(self.command('check',*args,'--spec',spec,'--certificate',certificate)[0],1)
            self.assertEqual(self.command('check',*args,'--certificate',certificate)[0],64)
            certificate.write_text('{}')
            self.assertEqual(self.command('check',*args,'--spec',spec,'--certificate',certificate)[0],3)
            certificate.write_text('{"a":1,"a":2}')
            self.assertEqual(self.command('check',*args,'--spec',spec,'--certificate',certificate)[0],3)

    def test_budget_refusals_and_output_protection(self):
        with tempfile.TemporaryDirectory() as d:
            root,args,spec=self.setup_files(d)
            output=root/'budget'
            code,result,_=self.command('verify',*args,'--spec',spec,'--output',output,'--max-orders',1)
            self.assertEqual(code,2);self.assertFalse((output/'certificate.json').exists())
            self.assertTrue((output/'result.json').is_file())
            for key,value in (('--max-orders',0),('--max-inputs',-1),('--max-witness-width',9)):
                code,result,_=self.command('verify',*args,'--spec',spec,'--output',root/'absent',key,value)
                self.assertEqual(code,64);self.assertFalse((root/'absent').exists())
            for path in (args[0],spec,root/'ascending.java'):
                before=path.read_bytes()
                self.assertEqual(self.command('verify',*args,'--spec',spec,'--output',path)[0],64)
                self.assertEqual(path.read_bytes(),before)
            (root/'symlink').symlink_to(root/'absent')
            self.assertEqual(self.command('verify',*args,'--spec',spec,'--output',root/'symlink')[0],64)

    def test_concrete_execution_is_not_a_universal_verdict(self):
        with tempfile.TemporaryDirectory() as d:
            root,args,_=self.setup_files(d)
            models=root/'models.json';models.write_text(json.dumps(self.models))
            inputs=root/'input.json';inputs.write_text(json.dumps(dict(width=3,must=0,may=5,bound=2)))
            code,result,_=self.command('run',*args,'--models',models,'--input',inputs)
            self.assertEqual(code,0);self.assertEqual(result['status'],'executed')
            self.assertEqual(result['result'],{'kind':'value','value':4})
            self.assertNotIn('all_positive_payload_widths',result)
            inputs.write_text(json.dumps(dict(width=0,must=0,may=5,bound=2)))
            self.assertEqual(self.command('run',*args,'--models',models,'--input',inputs)[0],64)

    def test_unresolved_and_unexpected_failure_are_distinct(self):
        with tempfile.TemporaryDirectory() as d:
            root,args,spec=self.setup_files(d,variants()['wrong_successor_seed'])
            code,result,_=self.command('verify',*args,'--spec',spec,'--output',root/'unresolved','--max-witness-width',1)
            self.assertEqual(code,5);self.assertEqual(result['status'],'unresolved')
            self.assertFalse((root/'unresolved'/'certificate.json').exists())
            with patch('research.observations.composition_producer.synthesize',side_effect=RuntimeError('control')):
                code,result,stderr=self.command('verify',*args,'--spec',spec,'--output',root/'unexpected')
            self.assertEqual(code,70);self.assertEqual(result['status'],'internal_error')
            self.assertIn('RuntimeError',stderr)


if __name__=='__main__':unittest.main()
