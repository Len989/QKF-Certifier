"""Independent and adversarial checks of exact forcing, not completion guesses."""
from __future__ import annotations
from copy import deepcopy
import importlib.util
import itertools
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest

from .checker import check, check_completion, explain
from .closure import check_closure
from .common import (DSU, InputError, InvalidCertificate, blocks, canonical, digest, encoded,
                     presentation, read_json, records, write_json)
from .fixtures import examples, make
from .producer import Budget, derive_closure, produce, prove
from .reference import ground

ROOT = Path(__file__).resolve().parents[2]
CASES = dict(examples())


def original():
    path = ROOT / 'papers/paper_I/verification/verify_article.py'
    spec = importlib.util.spec_from_file_location('paper_I_finite_reference', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PureRowsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = CASES['I_6_2_obstruction']
        cls.r, cls.c = prove(cls.p)

    def bad(self, change, p=None, c=None):
        q = deepcopy(self.c if c is None else c)
        change(q)
        with self.assertRaises(InvalidCertificate):
            check(self.p if p is None else p, q)

    def compare(self, p):
        r, c = prove(p)
        self.assertIsNotNone(c, r)
        self.assertEqual(check(p, c), r)
        for h in (1, 2):
            self.assertEqual(c['levels'][h-1]['equality']['partition'], ground(p, h)['partition'])
        return r, c

    def test_amplification_without_carrier_confusion(self):
        r, _ = self.compare(CASES['I_6_1_amplification'])
        self.assertEqual(r['carrier_partition'], [[0],[1],[2]])
        self.assertEqual(r['rows'][0]['generated_domain'], [0,2])
        self.assertEqual(r['rows'][0]['forced_domain'], [0,1,2])
        self.assertEqual(r['rows'][0]['forced_values'], [0,0,0])
        self.assertTrue(r['carrier_protected'])

    def test_exact_obstruction_not_universal_carrier_collapse(self):
        r = self.r
        self.assertEqual(r['carrier_partition'], [[0,2],[1],[3]])
        self.assertEqual(r['rows'][0]['ambient_kernel'], [[0,1,2]])
        self.assertEqual(r['interface']['horizon1_partition'], [[0,4,7],[1],[2,6],[3],[5]])
        self.assertEqual(r['interface']['horizon2_partition'], [[0,2,4,5,6,7],[1],[3]])

    def test_external_despite_identity_completion(self):
        p = CASES['I_6_3_external_completion']
        r, _ = self.compare(p)
        witness = dict(schema='qkf-pure-row-completion-v1', input_sha256=digest(p),
                       carrier_partition=[0,1], actions=[[0,1]])
        self.assertEqual(check_completion(p, witness)['status'], 'completion_verified')
        self.assertEqual(r['rows'][0]['forced_domain'], [])
        self.assertEqual(r['rows'][0]['external_classes'], [[0],[1]])
        self.assertFalse(r['completion_checked'])

    def test_sharp_synchronous_feedback_not_term_depth(self):
        for n in range(2,9):
            r, _ = self.compare(CASES[f'I_5_5_sharp_{n}'])
            self.assertEqual(r['strict_feedback_rounds'], n-1)
            self.assertEqual(r['interface']['stabilization_horizon'], 2)
            for k, stage in enumerate(r['feedback_trajectory']):
                self.assertEqual(stage, [list(range(k+1))]+[[a] for a in range(k+1,n)])

    def test_inconsistent_and_repeated_occurrences(self):
        r, _ = self.compare(CASES['inconsistent_occurrences'])
        self.assertEqual(r['carrier_partition'], [[0,1]])
        self.assertEqual(r['rows'][0]['forced_values'], [0])
        self.assertEqual(r['rows'][1]['forced_values'], [None])

    def test_all_empty_rows_remain_distinct(self):
        r, _ = self.compare(CASES['unspecified_rows_disjoint'])
        self.assertEqual(r['interface']['N2'], 12)
        self.assertEqual([x['external_count'] for x in r['rows']], [3,3,3])

    def test_empty_native_signature(self):
        r, _ = self.compare(make(3, [], 2, [(0,0,1),(0,0,2)]))
        self.assertEqual(r['carrier_partition'], [[0],[1,2]])

    def test_positive_arities_three_four(self):
        for k in (3,4):
            tab = [sum(xs)%2 for xs in itertools.product(range(2), repeat=k)]
            self.compare(make(2, [(k,tab)], 2, [(0,0,1),(1,1,0)]))

    def test_multi_native_operations(self):
        self.compare(make(3, [(1,[1,2,0]),(2,[max(a,b) for a in range(3) for b in range(3)])],
                          2, [(0,0,1),(1,2,0)]))

    def test_operator_algebra_not_action_composition(self):
        p = make(2, [(1,[0,1])], 2, [], [(1,[1,0]),(2,[0,1,1,0])])
        r, _ = self.compare(p)
        self.assertEqual(r['interface']['N2'], 6)

    def test_sort_names_may_coincide_without_coupling(self):
        p = make(2, [(1,[0,1])], 2, [], [(1,[1,0])])
        p['operators']['names'] = list(p['carrier']['names'])
        p['operators']['operations'][0]['name'] = p['carrier']['operations'][0]['name']
        self.assertEqual(self.compare(p)[0]['interface']['N2'], 6)

    def test_complete_tables_agree_with_reference(self):
        for tau in itertools.product(range(2), repeat=2):
            self.compare(make(2, [(2,[0,1,1,1])], cells=[(0,a,c) for a,c in enumerate(tau)]))

    def test_every_small_unary_table_all_single_cells(self):
        for tab in itertools.product(range(2), repeat=2):
            for b,a,c in itertools.product(range(2),repeat=3):
                self.compare(make(2, [(1,tab)], 2, [(b,a,c)]))

    def test_seeded_ground_comparison(self):
        rng = random.Random(3801)
        for _ in range(40):
            p = make(3, [(1,[rng.randrange(3) for _ in range(3)]),
                         (2,[rng.randrange(3) for _ in range(9)])], 3,
                     [tuple(rng.randrange(3) for _ in range(3)) for _ in range(rng.randrange(8))])
            self.compare(p)

    def test_preserved_prototype_all_examples(self):
        oracle = original()
        for p in CASES.values():
            r,c = self.compare(p)
            n, nb = len(p['carrier']['names']), len(p['operators']['names'])
            ops = [(op['arity'],op['table']) for op in p['carrier']['operations']]
            labels,theta,trajectory,rows = oracle.structural_interface(n,ops,nb,p['cells'])
            self.assertEqual(list(labels),c['levels'][1]['equality']['partition'])
            self.assertEqual(oracle.blocks(theta),r['carrier_partition'])
            self.assertEqual(len(trajectory)-1,r['strict_feedback_rounds'])
            for predicted, observed in zip(rows,r['rows']):
                self.assertEqual(predicted['forced_domain'],observed['forced_domain'])

    def test_repair_kernel_gap_not_forced_confusion(self):
        p = CASES['I_7_6_repair_kernel_gap']
        r,_ = self.compare(p)
        o = original()
        self.assertTrue(r['carrier_protected'])
        self.assertIsNone(o.completions(4,[(1,[1,1,1,2])],1,p['cells'],(0,1,2,3)))
        w = dict(schema='qkf-pure-row-completion-v1',input_sha256=digest(p),
                 carrier_partition=[0,1,0,2],actions=[[0,1,2]])
        self.assertEqual(check_completion(p,w)['status'],'completion_verified')
        self.assertEqual(r['rows'][0]['forced_domain'],[0,1,2])

    def test_no_least_repair_kept_separate(self):
        p = CASES['I_7_4_no_least_repair']
        r,_ = self.compare(p)
        self.assertTrue(r['carrier_protected'])
        for theta,action in [([0,1,0,2],[0,0,0]),([0,1,1,2],[0,1,2])]:
            w=dict(schema='qkf-pure-row-completion-v1',input_sha256=digest(p),
                   carrier_partition=theta,actions=[action])
            self.assertFalse(check_completion(p,w)['least_quotient_checked'])

    def test_carrier_contact_horizons(self):
        self.assertEqual(self.r['interface']['carrier_contact_horizons'],[[1,2,1,1]])
        r,_=self.compare(CASES['I_6_3_external_completion'])
        self.assertEqual(r['interface']['carrier_contact_horizons'],[[None,None]])

    def test_models_do_not_impose_a_variety_on_unnamed_elements(self):
        p=CASES['I_6_3_external_completion'];_,c=prove(p)
        m=c['levels'][1]['model'];op=m['A_operations'][0]
        table={tuple(xs):out for xs,out in op['entries']}
        f=lambda a,b:table.get((a,b),op['default'])
        self.assertNotEqual(f(f(2,0),1),f(2,f(0,1)))
        self.assertEqual(check(p,c)['status'],'certified')

    def test_coherent_h_still_requires_kernel_extension_stability(self):
        from .geometry import verify_geometry
        p=self.p;ops=p['carrier']['operations']
        kernel=derive_closure(4,records(4,ops),[(0,3)],Budget())
        candidate=dict(generation=[['cell',0],['cell',1],['cell',2]],h=[0,None,2,0],
                       kernel=kernel,forced_values=[0,0,0,0],external_classes=[])
        with self.assertRaisesRegex(ValueError,'kernel-extension obstruction'):
            verify_geometry(4,ops,[(0,0),(2,2),(3,0)],candidate)

    def test_lower_horizon_separator_need_not_satisfy_deeper_axioms(self):
        from .model import verify_model
        level=self.c['levels'][0]
        with self.assertRaisesRegex(ValueError,'compatibility axiom false'):
            verify_model(self.p,level['model'],2,level['equality']['partition'])

    def test_integer_token_and_nesting_limits_before_replay(self):
        with tempfile.TemporaryDirectory() as t:
            path=Path(t)/'bad.json'
            for raw in ['{"x":'+'9'*1000+'}', '['*100+'0'+']'*100]:
                path.write_text(raw)
                with self.assertRaises(ValueError):read_json(path)

    def test_canonical_roundtrip_and_determinism(self):
        r,c=prove(self.p)
        self.assertEqual(encoded(c),encoded(self.c))
        self.assertEqual(check(self.p,json.loads(encoded(c))),r)

    def test_supplied_result_cannot_be_trusted(self):
        self.bad(lambda c:c['result'].__setitem__('carrier_protected',True))
        self.bad(lambda c:c['result'].__setitem__('strict_feedback_rounds',True))

    def test_binding_changed_native_table(self):
        p=deepcopy(self.p);p['carrier']['operations'][0]['table'][0]=1
        with self.assertRaises(InvalidCertificate):check(p,self.c)
        c=deepcopy(self.c);c['input_sha256']=digest(p);c['result']['input_sha256']=digest(p)
        with self.assertRaises(InvalidCertificate):check(p,c)

    def test_changed_occurrences_even_with_rehash(self):
        p=deepcopy(self.p);p['cells']=[(0,0,0)]
        p['cells']=[list(x) for x in p['cells']]
        c=deepcopy(self.c);c['input_sha256']=digest(p);c['result']['input_sha256']=digest(p)
        with self.assertRaises(InvalidCertificate):check(p,c)

    def test_not_starting_at_diagonal(self):
        self.bad(lambda c:c['feedback'][0].__setitem__('carrier_partition',[0,0,0,0]))

    def test_feedback_missing_final_fixed_point(self):
        self.bad(lambda c:c['feedback'].pop())

    def test_extra_feedback_or_missing_row(self):
        self.bad(lambda c:c['feedback'].append(deepcopy(c['feedback'][-1])))
        self.bad(lambda c:c['feedback'][0]['pushouts'].pop())

    def test_raw_pushout_does_not_allow_action_feedback(self):
        self.bad(lambda c:c['feedback'][0]['pushouts'][0]['events'].insert(0,['feedback',0,0,1]))

    def test_future_congruence_premise_rejected(self):
        p=make(2,[(1,[0,1])]);native=records(2,p['carrier']['operations'],2)
        proof=dict(partition=[0,1,0,1],events=[['native',0,2],['seed',0]])
        with self.assertRaises(ValueError):check_closure(4,native,[(0,2)],proof)

    def test_closure_is_required_even_if_all_events_sound(self):
        native=[(0,(0,),2),(0,(1,),3)]
        proof=dict(partition=[0,0,1,2],events=[['seed',0]])
        with self.assertRaisesRegex(ValueError,'closure incomplete'):
            check_closure(4,native,[(0,1)],proof)

    def test_feedback_coverage_required(self):
        proof=dict(partition=[0,0,1,2],events=[['seed',0]])
        with self.assertRaisesRegex(ValueError,'feedback incomplete'):
            check_closure(4,[],[(0,1)],proof,(2,1))

    def test_unjustified_overcollapse_rejected(self):
        self.bad(lambda c:c['levels'][1]['equality'].__setitem__('partition',[0]*8))

    def test_kernel_overcollapse_not_accepted(self):
        p=CASES['I_6_3_external_completion'];_,c=prove(p)
        self.bad(lambda x:x['rows'][0]['kernel'].__setitem__('partition',[0,0]),p,c)

    def test_generated_domain_has_derivations(self):
        self.bad(lambda c:c['rows'][0]['generation'].pop())
        self.bad(lambda c:c['rows'][0]['generation'].insert(0,['native',0,[1,2]]))

    def test_generated_map_wrong_value(self):
        self.bad(lambda c:c['rows'][0]['h'].__setitem__(0,1))

    def test_saturation_cannot_be_trimmed_or_filled_by_choice(self):
        p=CASES['I_6_1_amplification'];_,c=prove(p)
        self.bad(lambda x:x['rows'][0]['forced_values'].__setitem__(1,None),p,c)
        p=CASES['I_6_3_external_completion'];_,c=prove(p)
        self.bad(lambda x:x['rows'][0]['forced_values'].__setitem__(0,0),p,c)

    def test_external_classes_not_mergeable_by_row_name(self):
        p=CASES['unspecified_rows_disjoint'];_,c=prove(p)
        self.bad(lambda x:x['rows'][1].__setitem__('external_classes',[[0,1,2]]),p,c)

    def test_horizon_labels_cannot_be_switched(self):
        self.bad(lambda c:c['levels'].reverse())
        self.bad(lambda c:c['levels'][0].__setitem__('horizon',True))

    def test_finite_model_must_satisfy_all_input_equations(self):
        self.bad(lambda c:c['levels'][1]['model']['A_operations'][0]['entries'][0].__setitem__(1,1))
        self.bad(lambda c:c['levels'][1]['model']['alpha']['entries'][0].__setitem__(1,1))

    def test_model_missing_tuple_cannot_hide_behind_default(self):
        c=deepcopy(self.c)
        entries=c['levels'][1]['model']['A_operations'][0]['entries']
        victim=next(i for i,e in enumerate(entries) if e[1]!=0)
        del entries[victim]
        with self.assertRaises(InvalidCertificate):check(self.p,c)

    def test_model_must_separate_all_claimed_classes(self):
        self.bad(lambda c:c['levels'][1]['model'].__setitem__('A_size',1))
        self.bad(lambda c:c['levels'][1]['model'].__setitem__('carrier_values',[0,0,0,0]))

    def test_boolean_indices_rejected(self):
        self.bad(lambda c:c['feedback'][0]['pushouts'][0]['events'][0].__setitem__(1,False))
        self.bad(lambda c:c['rows'][0]['h'].__setitem__(0,False))

    def test_missing_extra_and_foreign_fields(self):
        self.bad(lambda c:c.__setitem__('completion',{}))
        self.bad(lambda c:c.pop('levels'))
        self.bad(lambda c:c.__setitem__('schema','qkf-unified-proof-v5'))

    def test_invalid_input_types_and_tables(self):
        for mutate in [lambda p:p['carrier']['operations'][0].__setitem__('arity',0),
                       lambda p:p['carrier']['operations'][0].__setitem__('table',[0]),
                       lambda p:p['cells'][0].__setitem__(2,True),
                       lambda p:p['carrier'].__setitem__('names',[]),
                       lambda p:p['operators'].__setitem__('names',['b','b'])]:
            p=deepcopy(self.p);mutate(p)
            with self.assertRaises(InputError):prove(p)

    def test_action_laws_and_one_sorted_theory_rejected(self):
        p=deepcopy(self.p);p['composition']=True
        with self.assertRaises(InputError):prove(p)
        p=deepcopy(self.p);p['theory']='one-sorted'
        with self.assertRaises(InputError):prove(p)

    def test_reindexing_carrier_preserves_labelled_equalities(self):
        p=deepcopy(self.p);n=4;perm=[2,0,3,1];inverse=[perm.index(i) for i in range(n)]
        p['carrier']['names']=[self.p['carrier']['names'][inverse[i]] for i in range(n)]
        old=self.p['carrier']['operations'][0]['table']
        p['carrier']['operations'][0]['table']=[perm[old[inverse[a]*n+inverse[b]]] for a in range(n) for b in range(n)]
        p['cells']=[[b,perm[a],perm[c]] for b,a,c in self.p['cells']]
        _,c=self.compare(p)
        for h in (0,1):
            labels=c['levels'][h]['equality']['partition']
            back=[labels[perm[a]] for a in range(n)]+[labels[n+perm[a]] for a in range(n)]
            self.assertEqual(canonical(back),self.c['levels'][h]['equality']['partition'])

    def test_more_observations_only_add_forced_equalities(self):
        p=CASES['I_6_3_external_completion'];_,base=prove(p)
        for observations in [[(0,0,0)],[(0,0,0),(0,0,1)],[(0,1,0)]]:
            q=deepcopy(p);q['cells']=[list(x) for x in observations];_,c=self.compare(q)
            left=base['levels'][1]['equality']['partition'];right=c['levels'][1]['equality']['partition']
            self.assertTrue(all(left[i]!=left[j] or right[i]==right[j] for i in range(4) for j in range(4)))

    def test_repair_feasibility_not_upward_closed(self):
        p=CASES['I_7_5_nonmonotone_repair']
        witness=dict(schema='qkf-pure-row-completion-v1',input_sha256=digest(p),
                     carrier_partition=[0,0,1,2],actions=[[0,1,1]])
        self.assertEqual(check_completion(p,witness)['status'],'completion_verified')
        witness['carrier_partition']=[0,0,1,0];witness['actions']=[[0,1]]
        with self.assertRaises(InvalidCertificate):check_completion(p,witness)
        witness['carrier_partition']=[0,0,0,0];witness['actions']=[[0]]
        self.assertEqual(check_completion(p,witness)['status'],'completion_verified')

    def test_budget_events_work_rounds_are_not_success(self):
        for limits in [{'max_events':0},{'max_work':0},{'max_rounds':0},{'max_rounds':1}]:
            r,c,d=produce(self.p,limits)
            self.assertEqual(r['status'],'budget_exhausted');self.assertIsNone(c)
            self.assertEqual(d['status'],'incomplete')

    def test_certificate_size_exhaustion_never_exports_partial_proof(self):
        from unittest.mock import patch
        with patch('research.pure_rows.common.MAX_JSON_BYTES', 1500):
            result, proof, _ = produce(self.p)
        self.assertIsNone(proof)
        self.assertEqual(result['status'], 'budget_exhausted')
        self.assertEqual(result['stage'], 'certificate_encoding')

    def test_exact_budget_boundary(self):
        r,c,d=produce(self.p)
        limits={'max_'+k:v for k,v in d['work'].items()}
        self.assertEqual(produce(self.p,limits)[0],r)
        limits['max_events']-=1
        self.assertIsNone(produce(self.p,limits)[1])

    def test_unknown_and_boolean_budgets(self):
        for limits in [{'timeout':1},{'max_events':True},{'max_work':-1}]:
            with self.assertRaises(InputError):prove(self.p,limits)

    def test_inputs_and_results_are_detached(self):
        p=deepcopy(self.p);r,c=prove(p)
        p['cells'].clear();r['rows'].clear()
        self.assertEqual(check(self.p,c),self.r)

    def test_completion_rejects_wrong_quotient_or_values(self):
        p=CASES['I_6_1_amplification']
        w=dict(schema='qkf-pure-row-completion-v1',input_sha256=digest(p),
               carrier_partition=[0,1,2],actions=[[0,0,0]])
        self.assertEqual(check_completion(p,w)['status'],'completion_verified')
        w['actions'][0][2]=1
        with self.assertRaises(InvalidCertificate):check_completion(p,w)
        w['actions']=[[0,0]];w['carrier_partition']=[0,1,0]
        with self.assertRaises(InvalidCertificate):check_completion(p,w)

    def test_forcing_and_completion_formats_are_not_interchanged(self):
        with self.assertRaises(InvalidCertificate):check_completion(self.p,self.c)

    def test_explanations_have_no_universal_disequality_claim(self):
