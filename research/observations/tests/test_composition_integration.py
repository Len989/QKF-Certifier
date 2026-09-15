"""Actual-source proofs, negative controls and no-search replay for composition."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from research.observations.composition_execution import CallDomainError, Execution
from research.observations.composition_kernel import binding, check, explain
from research.observations.composition_program import inspect, program, variants
from research.observations.composition_producer import bounded_inputs, synthesize
from research.observations.composition_spec import dependency_spec, specification
from research.observations.composition_validation import additional_inputs, oracle, wide_oracle
from research.observations.model import digest
from research.observations.run_io import read_json
from research.observations.run_package import RunError

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT / 'research/observations/evidence/typed_targets'


def source_case(role, name, claim):
    root = EVIDENCE / (role + '.' + name + '.' + claim)
    return root.joinpath('source.java').read_bytes().decode('utf-8'), read_json(root / 'package.json', package=True)


class CompositionIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources, cls.dependencies = {}, {}
        for role, claim in (('descending','maximum'),('ascending','cyclic_successor')):
            cls.sources[role],cls.dependencies[role] = source_case(role,'original',claim)
        cls.spec = specification()
        cls.variants = variants()
        cls.certificates = {}
        for name,p in cls.variants.items():
            proposal=synthesize(p,cls.sources,cls.spec,dependencies=cls.dependencies)
            if proposal['status']!='candidate': raise AssertionError(proposal)
            cls.certificates[name]=proposal['certificate']
        cls.models={r:d['proofs']['source'] for r,d in cls.dependencies.items()}

    def test_all_wrapper_variants_and_concrete_witnesses(self):
        results=[]
        for name,p in self.variants.items():
            result=check(p,self.sources,self.spec,self.certificates[name])
            results.append(result['status'])
            self.assertEqual(result['status'],'certified' if name in {'original','inclusive_minimum'} else 'refuted',name)
            if result['status']=='refuted':
                witness=result['counterexample']
                self.assertNotEqual(witness['result'],oracle(witness['input']))
                self.assertEqual(len(result['checked_by']),4)
        self.assertEqual(results.count('certified'),2)
        self.assertEqual(results.count('refuted'),8)

    def test_original_exhaustive_whole_wrapper_not_just_independent_regions(self):
        runner=Execution(self.sources,self.models)
        cases=list(bounded_inputs(4))
        self.assertEqual(len(cases),1554)
        for inputs in cases:
            expected=oracle(inputs)
            self.assertEqual(wide_oracle(inputs),expected)
            self.assertEqual(runner.run(program(),inputs)['result'],expected)

    def test_wide_words_singletons_fixed_ones_long_carries_and_empty(self):
        runner=Execution(self.sources,self.models)
        cases=additional_inputs()
        self.assertEqual(len(cases),360)
        for inputs in cases:
            self.assertEqual(runner.run(program(),inputs)['result'],wide_oracle(inputs))

    def test_every_small_real_execution_is_included_in_its_abstract_order_case(self):
        from research.observations.composition_order import domain_orders, evaluate
        runner=Execution(self.sources,self.models)
        names,_=domain_orders(program())
        checked=0
        for inputs in bounded_inputs(3):
            trace=runner.run(program(),inputs)
            values={name:0 for name in names}
            values.update({k:inputs[k] for k in ('must','may','bound')})
            for event in trace['trace']:
                if event['op']=='call': values[event['bind']]=event['output']
            for z in range(1 << inputs['width']):
                if z & inputs['must'] != inputs['must'] or z & ~inputs['may']: continue
                values['alternative']=z
                labels={v:i for i,v in enumerate(sorted(set(values.values())))}
                ranks=[labels[values[k]] for k in names]
                cell=evaluate(program(),names,ranks)
                self.assertEqual(cell['outcome'],trace['result']['kind'])
                if cell['outcome']=='value':
                    self.assertEqual(values[cell['word']],trace['result']['value'])
                checked+=1
        # Four legal (must, may, z) columns times two bound bits.
        self.assertEqual(checked,8 + 64 + 512)

    def test_fresh_dependencies_equal_frozen_run2_proofs(self):
        proposal=synthesize(program(),self.sources,self.spec)
        self.assertEqual(proposal['status'],'candidate')
        self.assertEqual(digest(proposal['certificate']),digest(self.certificates['original']))

    def test_weak_dependency_not_accepted_even_when_rehashed(self):
        for role,claim in (('descending','bound'),('ascending','membership')):
            _,weak=source_case(role,'original',claim)
            c=deepcopy(self.certificates['original'])
            c['dependencies'][role]=weak
            c['dependencies_sha256']=digest(c['dependencies'])
            with self.assertRaises((ValueError,RunError)): check(program(),self.sources,self.spec,c)
        # Change the source to a genuinely refuted strong dependency: not a
        # forged hash comparison alone. Its source-model proof is still valid.
        source,negative=source_case('ascending','first_or','cyclic_successor')
        sources={**self.sources,'ascending':source}
        c=deepcopy(self.certificates['original'])
        c['dependencies']['ascending']=negative
        c['dependencies_sha256']=digest(c['dependencies'])
        c['binding']=binding(program(),sources,self.spec)
        with self.assertRaises((ValueError,RunError)): check(program(),sources,self.spec,c)

    def test_incorrect_summary_or_order_table_cannot_claim_universal_proof(self):
        base=self.certificates['original']
        mutations=[lambda c:c.update(schema='x'),lambda c:c.update(assumptions=[True]),
                   lambda c:c['binding'].update(rules='x'),lambda c:c['names'].reverse(),
                   lambda c:c['cases'].pop(),lambda c:c['cases'].reverse(),
                   lambda c:c['cases'].__setitem__(1,deepcopy(c['cases'][0])),
                   lambda c:c['cases'][0]['order'].__setitem__(0,True),
                   lambda c:c['cases'][0]['result'].update(outcome='empty'),
                   lambda c:c['cases'][0].update(assumption=True)]
        for i,mutate in enumerate(mutations):
            c=deepcopy(base); mutate(c)
            with self.subTest(mutation=i),self.assertRaises((ValueError,RunError)):
                check(program(),self.sources,self.spec,c)

    def test_binding_includes_external_program_sources_and_goal(self):
        c=self.certificates['original']
        with self.assertRaises(ValueError):
            check(program(),{**self.sources,'ascending':self.sources['ascending']+'\n'},self.spec,c)
        with self.assertRaises(ValueError): check(self.variants['empty_at_maximum'],self.sources,self.spec,c)
        changed=deepcopy(self.spec); changed['preconditions'].append('bound <= may')
        with self.assertRaises(ValueError): check(program(),self.sources,changed,c)
        c=deepcopy(c)
        c['binding']=binding(self.variants['empty_at_maximum'],self.sources,self.spec)
        with self.assertRaises(ValueError): check(self.variants['empty_at_maximum'],self.sources,self.spec,c)

    def test_counterexample_corruption_and_whole_execution_are_checked(self):
        name='wrong_successor_seed'
        base=self.certificates[name]
        mutations=[lambda c:c['input'].update(width=True),lambda c:c.update(alternative=7),
                   lambda c:c['execution']['result'].update(value=7),
                   lambda c:c['execution']['trace'].pop(),lambda c:c.update(reason='wrong'),
                   lambda c:c['models']['ascending'].update(schema='x'),
                   lambda c:c.update(extra=False)]
        for i,mutate in enumerate(mutations):
            c=deepcopy(base); mutate(c)
            c['models_sha256']=digest(c['models'])
            with self.subTest(mutation=i),self.assertRaises((ValueError,RunError)):
                check(self.variants[name],self.sources,self.spec,c)
        with patch('research.observations.composition_execution.integer_value',return_value=123):
            with self.assertRaises(ValueError):
                check(self.variants[name],self.sources,self.spec,base)

    def test_non_proofs_remain_non_proofs(self):
        p=synthesize(program(),self.sources,self.spec,dependencies=self.dependencies,max_orders=1)
        self.assertEqual(p['status'],'budget_exhausted'); self.assertIsNone(p['certificate'])
        p=synthesize(self.variants['always_successor'],self.sources,self.spec,dependencies=self.dependencies,max_inputs=0)
        self.assertEqual(p['status'],'budget_exhausted'); self.assertIsNone(p['certificate'])
        # This flaw first appears at width 3; lower-width testing is not a proof.
        p=synthesize(self.variants['wrong_successor_seed'],self.sources,self.spec,
                     dependencies=self.dependencies,max_witness_width=1)
        self.assertEqual(p['status'],'unresolved'); self.assertIsNone(p['certificate'])
        for bad in (0,True,4684):
            with self.assertRaises(ValueError):
                synthesize(program(),self.sources,self.spec,dependencies=self.dependencies,max_orders=bad)

    def test_refuted_local_lemma_does_not_refute_whole_program(self):
        source,dep=source_case('descending','strict','maximum')
        p=synthesize(program(),{**self.sources,'descending':source},self.spec,
                     dependencies={**self.dependencies,'descending':dep},max_witness_width=4)
        self.assertEqual(p['status'],'unresolved')
        self.assertEqual(p['diagnostic']['kind'],'dependency_not_certified')
        self.assertEqual(p['search']['tested_inputs'],1554)
        self.assertIsNone(p['certificate'])

    def test_source_mutations_have_reachable_composed_counterexamples(self):
        for role,name,claim in [('ascending','clear_repair','cyclic_successor'),
                                ('ascending','first_or','cyclic_successor'),
                                ('ascending','first_four_bits','cyclic_successor'),
                                ('descending','plus_one','maximum'),
                                ('descending','shared_input','maximum')]:
            source,dep=source_case(role,name,claim)
            sources={**self.sources,role:source}
            p=synthesize(program(),sources,self.spec,dependencies={**self.dependencies,role:dep})
            self.assertEqual(p['status'],'candidate')
            result=check(program(),sources,self.spec,p['certificate'])
            self.assertEqual(result['status'],'refuted',(role,name))
            self.assertNotEqual(result['counterexample']['result'],oracle(result['counterexample']['input']))

    def test_irrelevant_register_dependency_is_reusable(self):
        source,dep=source_case('ascending','irrelevant_register','cyclic_successor')
        sources={**self.sources,'ascending':source}
        p=synthesize(program(),sources,self.spec,dependencies={**self.dependencies,'ascending':dep})
        self.assertEqual(check(program(),sources,self.spec,p['certificate'])['status'],'certified')

    def test_bad_call_entry_is_not_interpreted_as_numeric_counterexample(self):
        p=program()
        p['entry']['no']['no']['then']['no']['args']['seed']='bound'
        runner=Execution(self.sources,self.models)
        with self.assertRaises(CallDomainError):
            runner.run(p,dict(width=3,must=0,may=5,bound=2))

    def test_fresh_process_check_and_explain_without_search_templates_native_or_old_goal_kernels(self):
        cases=[[p,self.sources,self.spec,self.certificates[n]] for n,p in self.variants.items()]
        code='''
import builtins,json,sys
from copy import deepcopy
cases=json.load(open(sys.argv[1],encoding="utf-8"))
original=builtins.__import__
def guarded(name,*args,**kwargs):
    pieces=name.split(".")
    blocked={"composition_producer","composition_validation","composition_cli","target_templates",
             "property_kernel","successor_kernel","upper_spec","successor_spec","subprocess",
             "ascending_validation","property_validation","z3","cvc5","pysmt","sympy","bitwuzla"}
    if any("producer" in p or p in blocked for p in pieces):
        raise AssertionError("forbidden replay dependency: "+name)
    return original(name,*args,**kwargs)
builtins.__import__=guarded
from research.observations.composition_kernel import check,explain
statuses=[]
for args in cases:
    result=check(*args)
    if not explain(*args)["explanation"]["replayed"]: raise AssertionError("unreplayed")
    statuses.append(result["status"])
cases[0][3]["cases"].pop()
try: check(*cases[0])
except ValueError: pass
else: raise AssertionError("corruption accepted")
print(json.dumps(statuses))
'''
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'cases.json';path.write_text(json.dumps(cases),encoding='utf-8')
            for options in ([],['-O']):
                r=subprocess.run([sys.executable,*options,'-c',code,str(path)],cwd=ROOT,
                                 text=True,capture_output=True,timeout=60)
                self.assertEqual(r.returncode,0,r.stderr)
                self.assertEqual(json.loads(r.stdout),['certified','certified']+['refuted']*8)


if __name__ == '__main__': unittest.main()
