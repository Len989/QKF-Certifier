"""Trust-boundary attacks, unchanged cold acceptance, and matched controls."""
from copy import deepcopy
from dataclasses import FrozenInstanceError
import hashlib
import json
from pathlib import Path
import pickle
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from research.source_lemmas.fixtures import cases as lemma_cases
from research.source_lemmas.context import digest, canonical
from research.source_lemmas.checker import check as cold
from research.source_lemmas.producer import prove as old_prove
from research.source_query.encoding import Graph
from research.ground_query.fixtures import examples, gap
from research.ground_query.schema import parse
from research.ground_query.checker import check as cold_ground
from research.signed_compact import dag
from .checker import open_context, native_entry, Presentation, CheckedGoal, Obligation
from .producer import prove, active_basis
from .ground import admit, Parsed
from .ground_check import check as warm_ground
from .values import plain
from . import ordinary, query


class Prepared(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = {c['name']: c for c in lemma_cases()}
        cls.cache = {}

    def sample(self, name='mask_all_4', backend='query', policy='no_lemmas'):
        key = name, backend, policy
        if key not in self.cache:
            c = self.cases[name]
            self.cache[key] = prove(c['source'], c['request'], backend=backend, policy=policy, limits=c['limits'])
        return deepcopy(self.cache[key])

    def prefix(self, n=None):
        c = self.cases['mask_all_4']
        p, requests = open_context(c['source'], c['request'])
        rows = self.sample()[2]['foundations']['E']
        for row in rows[:n]:
            p = p.add_native(row)
        return p, requests, rows

    def positive(self):
        p, requests, _ = self.prefix()
        row = self.sample()[2]['checkpoints'][-1]
        ctx = p.target(row['request'])
        item = row['item']
        obligation = p.prepare(ctx, item['basis'], item['epoch'], item['via_lemma'])
        return p, row['request'], item, obligation, p.verify(row['request'], item, prepared=obligation)

    def negative(self):
        p, requests, _ = self.prefix(0)
        ctx = p.target(requests[0])
        obligation = p.prepare(ctx, dict(native=[], lemmas=[]))
        proof, _ = ordinary.prove(obligation.ground)
        item = dict(kind='ground', basis=plain(obligation.basis), epoch=p.epoch(), via_lemma=None, certificate=proof)
        return p, requests, obligation, item, p.verify(requests[0], item, prepared=obligation)

    @staticmethod
    def extend(p):
        graph = Graph(p.context())
        child = graph.node('w.input')
        node = graph.node('w.pos', child)
        row = native_entry(p, graph, dict(rule='local', law='word-positive', term=node), (node, child))
        return p.add_native(row)

    def test_input_mutation_after_admission(self):
        c = deepcopy(self.cases['mask_all_4'])
        p, requests = open_context(c['source'], c['request'])
        before = p.scope()
        c['request']['requests'][0]['guards'].clear()
        c['request']['requests'][0]['target']['goal'][0] = 'positive'
        requests[0]['width'] = dict(kind='fixed', bits=1)
        self.assertEqual(p.scope(), before)
        self.assertEqual(plain(p.context().request), self.cases['mask_all_4']['request']['requests'][0])

    def test_deep_context_immutability(self):
        p, _, _ = self.prefix(0)
        ctx = p.context()
        with self.assertRaises(FrozenInstanceError): ctx.width = 8
        with self.assertRaises(TypeError): ctx.ir['nodes'][0][0] = 'const'
        with self.assertRaises(TypeError): ctx.request['guards'][0][1] = 3
        with self.assertRaises(TypeError): p._admission.scope['native_algebra']['w.input']['args'] += ('Word',)
        with self.assertRaises(TypeError): p._admission.contexts[ctx.key] = ctx

    def test_all_goals_share_admitted_source(self):
        p, requests, _ = self.prefix(0)
        contexts = [p.target(r) for r in requests]
        self.assertTrue(all(ctx.ir is contexts[0].ir and ctx.guards is contexts[0].guards for ctx in contexts))
        self.assertIs(p.context(), p.context())

    def test_native_checked_once_at_insertion(self):
        p, _, rows = self.prefix(0)
        from .checker import check_fact
        with patch('research.prepared_context.checker.check_fact', wraps=check_fact) as replay:
            q = p.add_native(rows[0])
            basis = active_basis(q, False)
            for _ in range(3): q.prepare(q.context(), basis)
            self.assertEqual(replay.call_count, 1)
        broken = deepcopy(rows[0]); broken['evidence']['rule'] = 'fake'
        broken['id'] = digest({k:v for k,v in broken.items() if k != 'id'})
        with self.assertRaises(ValueError): p.add_native(broken)

    def test_native_foreign_scope_fields_rejected_with_repaired_ids(self):
        p, _, rows = self.prefix(0)
        variants = []
        for key in ('source_sha256', 'ir_sha256', 'selection'):
            row = deepcopy(rows[0]); row['scope']['source'][key] = 'foreign'; variants.append(row)
        for key, value in [('profile', 'foreign'), ('native_ruleset', 'foreign'),
                           ('guards', []), ('width', dict(kind='fixed', bits=8)), ('native_algebra', {})]:
            row = deepcopy(rows[0]); row['scope'][key] = value; variants.append(row)
        for row in variants:
            with self.subTest(scope=row['scope']):
                row['id'] = digest({k:v for k,v in row.items() if k != 'id'})
                with self.assertRaises(ValueError): p.add_native(row)

    def test_foundation_mutation_cannot_change_issued_obligation(self):
        p, requests, rows = self.prefix(0)
        p = p.add_native(rows[0])
        before = p.native()
        obligation = p.prepare(p.context(), active_basis(p, False))
        wire = obligation.ground.request()
        rows[0]['claim'][0][0] = 'fake'
        exported = p.native(); exported[0]['evidence']['rule'] = 'fake'
        wire['signature'].clear(); wire['equations'].clear()
        self.assertEqual(p.native(), before)
        self.assertTrue(obligation.ground.signature)
        self.assertTrue(obligation.ground.equations)
        with self.assertRaises(TypeError): p._E[0]['claim'][0][0] = 'fake'
        with self.assertRaises(TypeError): obligation.ground.signature['b.true']['result'] = 'Word'

    def test_no_json_receipts_or_pickled_capabilities(self):
        p, request, item, obligation, checked = self.positive()
        for cls in (Presentation, CheckedGoal, Obligation, Parsed):
            with self.assertRaises(ValueError): cls(checked=True)
        for value in (p, p.context(), obligation, obligation.ground, checked):
            with self.assertRaises(TypeError): pickle.dumps(value)
        with self.assertRaises(ValueError): p.promote(dict(checked=True, item=item))
        with self.assertRaises(ValueError): p.verify(request, dict(item, checked=True))
        with self.assertRaises(ValueError): warm_ground(obligation.ground.request(), item['certificate'])

    def test_prepared_input_reused_without_context_restore_or_parse(self):
        p, request, item, obligation, _ = self.positive()
        with patch('research.source_lemmas.context.from_context_json', side_effect=AssertionError('restore')):
            with patch('research.prepared_context.ground.parse', side_effect=AssertionError('reparse')):
                with patch('research.prepared_context.context.target_context', side_effect=AssertionError('recompile')):
                    for backend in (ordinary, query):
                        proof, _ = backend.prove(obligation.ground)
                        p.verify(request, dict(item, certificate=proof), prepared=obligation)

    def test_only_one_parse_per_prepared_obligation(self):
        p, _, _ = self.prefix(0)
        with patch('research.prepared_context.ground.parse', wraps=parse) as parsed:
            obligation = p.prepare(p.context(), dict(native=[], lemmas=[]))
            proof, _ = ordinary.prove(obligation.ground)
            warm_ground(obligation.ground, proof)
            self.assertEqual(parsed.call_count, 1)

    def test_prepared_binding_rejects_request_basis_epoch_substitution(self):
        p, request, item, obligation, _ = self.positive()
        other = self.cases['mask_all_4']['request']['requests'][0]
        with self.assertRaises(ValueError): p.verify(other, item, prepared=obligation)
        for key, value in [('basis', dict(native=[], lemmas=[])),
                           ('epoch', dict(native=0, lemmas=0)), ('via_lemma', 'foreign')]:
            with self.assertRaises(ValueError): p.verify(request, dict(item, **{key:value}), prepared=obligation)
        q, _, _ = self.prefix()
        with self.assertRaises(ValueError): q.verify(request, item, prepared=obligation)
        with self.assertRaises(ValueError): q.prepare(p.context(), dict(native=[], lemmas=[]))

    def test_boolean_epoch_cannot_alias_integer(self):
        p, requests, rows = self.prefix(1)
        obligation = p.prepare(p.context(), dict(native=[rows[0]['id']], lemmas=[]))
        proof, _ = ordinary.prove(obligation.ground)
        item = dict(kind='ground', basis=plain(obligation.basis), epoch=dict(native=True, lemmas=False),
                    via_lemma=None, certificate=proof)
        with self.assertRaises(ValueError): p.verify(requests[0], item, prepared=obligation)

    def test_forward_or_foreign_foundation_references(self):
        p, _, rows = self.prefix()
        with self.assertRaises(ValueError): p.prepare(p.context(), dict(native=[rows[-1]['id']], lemmas=[]), dict(native=1, lemmas=0))
        with self.assertRaises(ValueError): p.prepare(p.context(), dict(native=['foreign'], lemmas=[]))
        with self.assertRaises(ValueError): p.prepare(p.context(), dict(native=[], lemmas=['future']))
        with self.assertRaises(ValueError): p.prepare(p.context(), dict(native=[], lemmas=[]), via='future')

    def test_stale_foreign_and_repeated_promotion(self):
        p, request, item, obligation, checked = self.positive()
        q, _ = p.promote(checked)
        for changed in (q, self.extend(p), self.prefix()[0]):
            with self.assertRaises(ValueError): changed.promote(checked)
        self.assertEqual(len(p._plus), 0)
        self.assertEqual(len(q._plus), 1)
        with self.assertRaises(TypeError): q._plus[0]['claim'][0][0] = 'fake'

    def test_goal_and_lemma_export_mutation_isolated(self):
        p, request, item, obligation, checked = self.positive()
        item['certificate']['events'].clear()
        result = checked.result(); result['status'] = 'refuted'
        q, lemma = p.promote(checked)
        lemma['claim'][0][0] = 'fake'
        self.assertEqual(checked.result()['status'], 'certified')
        self.assertNotEqual(q.lemmas()[0]['claim'], lemma['claim'])

    def test_old_E_lower_model_cannot_be_reused_or_promoted(self):
        p, requests, obligation, item, checked = self.negative()
        self.assertEqual(checked.result()['status'], 'unresolved')
        model = p.model_for(obligation, checked)
        model['operations'].clear()
        self.assertTrue(p.model_for(obligation, checked)['operations'])
        with self.assertRaises(ValueError): self.extend(p).model_for(obligation, checked)
        with self.assertRaises(ValueError): p.promote(checked)
        other = p.prepare(p.target(requests[1]), dict(native=[], lemmas=[]))
        with self.assertRaises(ValueError): p.model_for(other, checked)
        # Even an equivalent freshly issued obligation is not the checked owner.
        equivalent = p.prepare(p.context(), dict(native=[], lemmas=[]))
        with self.assertRaises(ValueError): p.model_for(equivalent, checked)

    def test_ground_algorithms_and_checker_preserved_at_full_horizon(self):
        from research.source_query.ordinary import prove as old_ordinary
        from research.ground_query.producer import prove as old_query
        for name, raw in examples():
            raw = deepcopy(raw)
            with self.subTest(case=name):
                inp = admit(raw)
                for new, old in ((ordinary.prove, old_ordinary), (query.prove, old_query)):
                    proof, stats = new(inp)
                    self.assertEqual((proof, stats), old(raw))
                    self.assertEqual(warm_ground(inp, proof), cold_ground(raw, proof))
                raw['signature'].clear()
                self.assertTrue(inp.signature)

    def test_bounded_ordinary_is_plain_active_CC_without_query_fallback(self):
        raw = gap(); inp = admit(raw)
        with patch('research.prepared_context.query.prove', side_effect=AssertionError('hidden fallback')):
            bounded, stats = ordinary.prove(inp, horizon=1)
        self.assertEqual(stats['activation_layers'], 0)
        self.assertEqual(cold_ground(raw, bounded)['goals'][0]['status'], 'not_visible')
        self.assertEqual(cold_ground(raw, ordinary.prove(inp)[0])['goals'][0]['status'], 'equal')
        with self.assertRaises(ValueError): ordinary.prove(inp, horizon=0)

    def test_ground_proof_mutations_rejected_by_both_checkers(self):
        raw = gap(); inp = admit(raw); proof, _ = query.prove(inp)
        mutations = []
        bad = deepcopy(proof); bad['request_sha256'] = 'foreign'; mutations.append(bad)
        bad = deepcopy(proof); bad['events'][0]['equation'] = 100; mutations.append(bad)
        bad = deepcopy(proof); bad['goals'][0]['path'] = [len(proof['events'])]; mutations.append(bad)
        bounded, _ = ordinary.prove(inp, horizon=1)
        bad = deepcopy(bounded); bad['goals'][0]['status'] = 'not_entailed'; mutations.append(bad)
        bad = deepcopy(bounded); bad['models'][0]['domains']['A'] = 1; mutations.append(bad)
        for bad in mutations:
            with self.assertRaises(ValueError): warm_ground(inp, bad)
            with self.assertRaises(ValueError): cold_ground(raw, bad)

    def test_old_producer_wire_and_native_policy_match(self):
        c = self.cases['mask_all_4']
        for backend, policy, route in [('query','no_lemmas','no_lemmas'),
                                       ('query','reuse','reuse'), ('ordinary','reuse','direct_cache')]:
            new = self.sample(backend=backend, policy=policy)
            old = old_prove(c['source'], c['request'], route=route, limits=c['limits'])
            self.assertEqual(new[:2], old[:2])
            self.assertEqual(new[2]['fact_attempts'], old[2]['fact_attempts'])
            self.assertEqual(cold(c['source'], c['request'], new[0]), new[1]['goals'])

    def test_matrix_shares_native_policy_and_terminal_cache(self):
        attempts = []
        for backend in ('ordinary','query'):
            for policy in ('no_lemmas','reuse'):
                proof, _, work = self.sample('exact_repeats_16', backend, policy)
                attempts.append(work['fact_attempts'])
                self.assertEqual(work['counts']['exact_goal_cache_hits'], 15)
                self.assertEqual(bool(work['foundations']['E_plus']), policy == 'reuse')
                self.assertTrue(all(item['kind']=='cached_goal' for item in dag.unpack(proof)['items'][1:]))
        self.assertTrue(all(a == attempts[0] for a in attempts))

    def test_inactive_and_structural_budget_statuses(self):
        for backend in ('ordinary','query'):
            self.assertEqual(self.sample('inactive_horizon', backend)[1]['goals'][0]['reason'], 'insufficient_horizon')
            self.assertEqual(self.sample('fact_budget', backend)[1]['status'], 'budget_exhausted')

    def test_entire_registered_signed_sdk_population(self):
        from research.sdk_comparison.fixtures import cases
        from .sdk import build
        count = 0
        for c in cases():
            if c['group'] == 'phase': continue
            count += 1
            expected = next(iter(c['expected'].values()))
            for backend in ('ordinary', 'query'):
                for policy in ('no_lemmas', 'reuse'):
                    with self.subTest(case=c['name'], backend=backend, policy=policy):
                        _, result, _ = build(c['source'], c['request'], backend=backend, policy=policy, limits=c['limits'])
                        self.assertEqual(result['status'], expected)
        self.assertEqual(count, 27)

    def test_registration_and_original_input_bytes(self):
        from .common import registered, validate_case
        from .fixtures import cases
        from research.sdk_comparison.fixtures import cases as old_cases
        originals = {c['name']:c for c in old_cases()}
        protocol, reg = registered()
        self.assertEqual(len(reg['cases']), 5)
        self.assertEqual(sum(len(c['routes']) for c in reg['cases']), 38)
        self.assertEqual(protocol['measurement']['timing_repeats'], 7)
        for c, entry in zip(cases(), reg['cases']):
            validate_case(c, entry)
            for key in ('source','request','limits','applications','followups'):
                self.assertEqual(c[key], originals[c['pr47_case']][key])

    def test_algorithm_provenance(self):
        root = Path(__file__).resolve().parents[2]
        records = json.loads(Path(__file__).with_name('ALGORITHMS.json').read_text())
        for dest, record in records.items():
            source = (root/record['source']).read_text()
            self.assertEqual(hashlib.sha256(source.encode()).hexdigest(), record['sha256'])
            if dest == 'ordinary.py': continue  # Bounded extension tested above against cold semantics.
            for old, new in record['changes']: source = source.replace(old,new)
            if dest == 'ground_check.py':
                source = source[:source.index('\ndef check_model(')] + source[source.index('\ndef check(request, certificate):'):]
            self.assertEqual(Path(__file__).with_name(dest).read_text(),
                '# PR48: retained algorithm, admitted-input entry only. See ALGORITHMS.json.\n' + source)


if __name__ == '__main__': unittest.main()
