from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from .checker import check
from .fixtures import encode, examples, gap, shared_example, term, unary_signature
from .preserve import provenance
from .producer import prove, search
from .schema import canonical, digest, load_json, parse, save_json


class QueryTests(unittest.TestCase):
    def setUp(self):
        self.request = gap()
        self.cert, _ = prove(self.request, 'exact_threshold')

    def reject(self, change, request=None):
        cert = deepcopy(self.cert)
        change(cert)
        with self.assertRaises(ValueError):
            check(self.request if request is None else request, cert)

    def test_examples(self):
        for name, req in examples():
            for mode in ('entailment', 'exact_threshold'):
                with self.subTest(name=name, mode=mode):
                    cert, stats = prove(req, mode)
                    self.assertEqual(len(check(req, cert)['goals']), len(req['queries']))
                    self.assertEqual(stats['added_terms'], 0)

    def test_gap_two_sided(self):
        result = check(self.request, self.cert)
        self.assertEqual(result['goals'][0]['exact_threshold'], 2)
        self.assertEqual(self.cert['models'][0]['horizon'], 1)

    def test_entailment_does_not_claim_minimality(self):
        cert, _ = prove(self.request)
        self.assertIsNone(check(self.request, cert)['goals'][0]['exact_threshold'])
        self.assertEqual(cert['models'], [])

    def test_nonminimal_entailment_proof_is_allowed(self):
        req = dict(examples())['flattened']
        cert = deepcopy(self.cert)
        cert['mode'] = 'entailment'
        cert['request_sha256'] = digest(req)
        cert['models'] = []
        cert['goals'][0]['lower_model'] = None
        self.assertEqual(check(req, cert)['goals'][0]['proof_depth'], 2)

    def test_bounded_separation_is_not_nonconsequence(self):
        cert, _ = prove(self.request, horizon=1)
        self.assertEqual(check(self.request, cert)['goals'][0]['status'], 'not_visible')
        cert['goals'][0]['status'] = 'not_entailed'
        with self.assertRaises(ValueError):
            check(self.request, cert)

    def test_final_nonconsequence(self):
        req = dict(examples())['nonconsequence']
        cert, _ = prove(req)
        self.assertEqual(check(req, cert)['goals'][0]['status'], 'not_entailed')

    def test_shared_typed_partition(self):
        inp, ts, run = search(shared_example())
        query_terms = list(dict.fromkeys(ts[i] for pair in inp.queries for i in pair))
        self.assertEqual([len(run.partition(query_terms, d)) for d in (1, 2)], [5, 3])

    def test_empty_sort_gets_default(self):
        req = dict(examples())['empty_sort']
        cert, _ = prove(req)
        self.assertEqual(cert['models'][0]['domains']['Empty'], 1)
        check(req, cert)

    def test_same_name_different_sort_rejected(self):
        req = shared_example()
        req['signature']['b']['result'] = 'A'
        with self.assertRaises(ValueError):
            parse(req)

    def test_wrong_equation_sort_rejected(self):
        req = shared_example()
        nodes = req['nodes']
        b = next(i for i, n in enumerate(nodes) if n['op'] == 'b')
        a = next(i for i, n in enumerate(nodes) if n['op'] == '0')
        req['equations'].append([a, b])
        with self.assertRaises(ValueError):
            parse(req)

    def test_input_topological_order(self):
        req = deepcopy(self.request)
        req['nodes'][2]['args'] = [2]
        with self.assertRaises(ValueError):
            parse(req)

    def test_unknown_symbol(self):
        req = deepcopy(self.request)
        req['nodes'][0]['op'] = 'unknown'
        with self.assertRaises(ValueError):
            parse(req)

    def test_duplicate_node(self):
        req = deepcopy(self.request)
        req['nodes'].append(deepcopy(req['nodes'][0]))
        with self.assertRaises(ValueError):
            parse(req)

    def test_orphan_node(self):
        req = deepcopy(self.request)
        req['signature']['unused'] = {'args': [], 'result': 'A'}
        req['nodes'].append({'op': 'unused', 'args': []})
        with self.assertRaises(ValueError):
            parse(req)

    def test_bool_node_index(self):
        req = deepcopy(self.request)
        req['equations'][0][0] = False
        with self.assertRaises(ValueError):
            parse(req)

    def test_declared_depth_limit(self):
        req = {'schema': self.request['schema'], 'sorts': ['A'], 'signature': unary_signature([term('a')]),
               'nodes': [{'op': 'a', 'args': []}] + [{'op': 'f', 'args': [i]} for i in range(129)],
               'equations': [], 'queries': [[129, 129]]}
        with self.assertRaises(ValueError):
            parse(req)

    def test_circular_congruence_premise(self):
        def change(cert):
            i = next(i for i, e in enumerate(cert['events']) if e['rule'] == 'congruence')
            cert['events'][i]['premises'] = [[i]]
        self.reject(change)

    def test_future_congruence_premise(self):
        self.reject(lambda c: c['events'][-1].update(premises=[[len(c['events'])]]))

    def test_missing_congruence_argument(self):
        self.reject(lambda c: c['events'][-1].update(premises=[]))

    def test_wrong_actual_axiom(self):
        self.reject(lambda c: c['events'][0].update(equation=1))

    def test_unbound_axiom_index(self):
        self.reject(lambda c: c['events'][0].update(equation=999))

    def test_proof_depth_tamper(self):
        self.reject(lambda c: c['events'][0].update(depth=0))

    def test_goal_depth_tamper(self):
        self.reject(lambda c: c['goals'][0].update(depth=1))

    def test_disconnected_goal_path(self):
        self.reject(lambda c: c['goals'][0].update(path=[]))

    def test_omitted_goal(self):
        self.reject(lambda c: c.update(goals=[]))

    def test_receipt_is_not_proof(self):
        with self.assertRaises(ValueError):
            check(self.request, {'status': 'passed', 'sha256': digest(self.cert)})

    def test_changed_request(self):
        req = deepcopy(self.request)
        req['equations'].reverse()
        with self.assertRaises(ValueError):
            check(req, self.cert)

    def test_missing_lower_model(self):
        self.reject(lambda c: c.update(models=[]))

    def test_omitted_active_lower_axiom(self):
        # The old depth-2 positive proof remains sound after adding this lower
        # axiom. Its old separating model no longer models ALL of E_1.
        req = deepcopy(self.request)
        req['equations'].append(req['queries'][0])
        self.reject(lambda c: c.update(request_sha256=digest(req)), request=req)

    def test_wrong_lower_horizon(self):
        self.reject(lambda c: c['models'][0].update(horizon=0))

    def test_model_signature_is_total(self):
        self.reject(lambda c: c['models'][0]['operations'].pop('f'))

    def test_model_empty_domain(self):
        self.reject(lambda c: c['models'][0]['domains'].update(A=0))

    def test_model_bool_domain(self):
        self.reject(lambda c: c['models'][0]['domains'].update(A=True))

    def test_model_wrong_output_range(self):
        self.reject(lambda c: c['models'][0]['operations']['f'].update(default=999))

    def test_duplicate_model_tuple(self):
        def change(c):
            rows = c['models'][0]['operations']['f']['rows']
            rows.append(deepcopy(rows[0]))
        self.reject(change)

    def test_model_must_separate(self):
        def change(c):
            m = c['models'][0]
            m['domains']['A'] = 1
            for op in m['operations'].values():
                op.update(default=0, rows=[])
        self.reject(change)

    def test_duplicate_json_key(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / 'bad.json'
            p.write_text('{"schema":1,"schema":2}')
            with self.assertRaises(ValueError):
                load_json(p)

    def test_reused_prototype_provenance(self):
        self.assertEqual(provenance(), 3)

    def test_standalone_checker_under_optimized_python(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'request.json').write_text(json.dumps(self.request))
            (root / 'certificate.json').write_text(json.dumps(self.cert))
            script = '''
import json,sys
from research.ground_query.replay import NoSearch
sys.meta_path.insert(0,NoSearch())
from research.ground_query.checker import check
from research.ground_query.schema import load_json
print(json.dumps(check(load_json(sys.argv[1]),load_json(sys.argv[2])),sort_keys=True))
'''
            for flags in ([], ['-O']):
                result = subprocess.run([sys.executable, *flags, '-c', script,
                                         str(root / 'request.json'), str(root / 'certificate.json')],
                                        text=True, capture_output=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout), check(self.request, self.cert))

    def test_replay_rejects_preloaded_search_modules(self):
        from .replay import run
        # This test process imported producer above; a meta-path hook cannot
        # intercept that cached import. Reject before reading any artifact.
        with self.assertRaisesRegex(ValueError, 'preloaded search modules'):
            run(Path('no-artifact-should-be-read'))

    def test_deterministic_across_hash_seeds(self):
        script = '''
from research.ground_query.fixtures import shared_example
from research.ground_query.producer import prove
from research.ground_query.schema import digest
print(digest(prove(shared_example(),'exact_threshold')[0]))
'''
        outputs = []
        for seed in ('1', '19'):
            result = subprocess.run([sys.executable, '-c', script], text=True, capture_output=True,
                                    env=dict(os.environ, PYTHONHASHSEED=seed), timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            outputs.append(result.stdout)
        self.assertEqual(outputs[0], outputs[1])

    def test_shared_dag_does_not_unfold_exponentially(self):
        req = {'schema': self.request['schema'], 'sorts': ['A'],
               'signature': {'a': {'args': [], 'result': 'A'},
                             'f': {'args': ['A', 'A'], 'result': 'A'}},
               'nodes': [{'op': 'a', 'args': []}] +
                        [{'op': 'f', 'args': [i, i]} for i in range(128)],
               'equations': [], 'queries': [[128, 128]]}
        cert, stats = prove(req, 'exact_threshold')
        self.assertEqual(stats['input_nodes'], 129)
        self.assertEqual(stats['added_terms'], 0)
        self.assertEqual(check(req, cert)['goals'][0]['exact_threshold'], 128)

    def test_shared_congruence_paths(self):
        nodes = [{'op': 'a', 'args': []}, {'op': 'b', 'args': []}]
        for i in range(70):
            nodes.extend([{'op': 'f', 'args': [2*i, 2*i]},
                          {'op': 'f', 'args': [2*i+1, 2*i+1]}])
        req = {'schema': self.request['schema'], 'sorts': ['A'],
               'signature': {'a': {'args': [], 'result': 'A'}, 'b': {'args': [], 'result': 'A'},
                             'f': {'args': ['A', 'A'], 'result': 'A'}},
               'nodes': nodes, 'equations': [[0, 1]], 'queries': [[140, 141]]}
        cert, _ = prove(req, 'exact_threshold')
        self.assertEqual(check(req, cert)['goals'][0]['exact_threshold'], 70)
        cert['events'][-1]['premises'].pop()
        with self.assertRaises(ValueError):
            check(req, cert)

    def test_ternary_typed_congruence(self):
        a, b, c = (term(s) for s in 'abc')
        sig = {s: {'args': [], 'result': 'A' if s != 'c' else 'B'} for s in 'abc'}
        sig['g'] = {'args': ['A', 'B', 'A'], 'result': 'C'}
        req = encode(sig, [(a, b)], [(term('g', a, c, a), term('g', b, c, b))], ('A', 'B', 'C'))
        cert, _ = prove(req, 'exact_threshold')
        self.assertEqual(check(req, cert)['goals'][0]['exact_threshold'], 1)

    def test_inactive_query_rejected(self):
        with self.assertRaises(ValueError):
            prove(self.request, horizon=0)

    def test_boolean_proof_reference_rejected(self):
        self.reject(lambda c: c['goals'][0].update(path=[True]))

    def test_boolean_model_reference_rejected(self):
        self.reject(lambda c: c['goals'][0].update(lower_model=False))

    def test_duplicate_model_horizon(self):
        self.reject(lambda c: c['models'].append(deepcopy(c['models'][0])))

    def test_model_wrong_argument_range(self):
        self.reject(lambda c: c['models'][0]['operations']['f']['rows'][0].update(args=[999]))

    def test_wrong_congruence_head(self):
        def mutate(c):
            c['events'][-1]['right'] = c['events'][0]['left']
        self.reject(mutate)

    def test_input_snapshot_detaches_signature(self):
        req = deepcopy(self.request)
        inp = parse(req)
        req['signature']['f']['args'].clear()
        self.assertEqual(inp.signature['f']['args'], ['A'])

    def test_json_nonfinite_and_fractional_numbers(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / 'bad.json'
            for text in ('NaN', 'Infinity', '1.0'):
                p.write_text(text)
                with self.assertRaises(ValueError):
                    load_json(p)

    def test_json_cycles_and_nonplain_objects(self):
        cyclic = []; cyclic.append(cyclic)
        for value in (cyclic, {1: 'wrong-key'}, {'x': (1, 2)}, {'x': float('nan')}, {'x': 2**300}):
            with self.assertRaises(ValueError):
                canonical(value)

    def test_cli_preserves_input_and_existing_output(self):
        from .cli import main
        from contextlib import redirect_stdout
        from io import StringIO
        with tempfile.TemporaryDirectory() as folder, redirect_stdout(StringIO()):
            p, c = Path(folder) / 'input.json', Path(folder) / 'cert.json'
            save_json(p, self.request)
            original = p.read_bytes()
            self.assertEqual(main(['build', str(p), str(p)]), 2)
            self.assertEqual(p.read_bytes(), original)
            self.assertEqual(main(['build', str(p), str(c)]), 0)
            saved = c.read_bytes()
            self.assertEqual(main(['build', str(p), str(c)]), 2)
            self.assertEqual(c.read_bytes(), saved)
            self.assertEqual(main(['check', str(p), str(c)]), 0)
            self.assertEqual(main(['check', str(p), str(c), '--horizon', '0']), 2)
            self.assertEqual(main(['build', str(p.parent / 'missing'), str(c)]), 2)

    def test_registration_matches_definitions(self):
        from .fixtures import registered_cases
        recorded = load_json(Path(__file__).with_name('REGISTRATION.json'))
        current = [dict(meta, request_sha256=digest(req)) for meta, req in registered_cases()]
        self.assertEqual(recorded['cases'], current)
        self.assertEqual(len(current), 203)

    def test_sequential_rewrite_reference(self):
        from .reference import rewrite_gap
        self.assertEqual(rewrite_gap(), {'congruence': 2, 'sequential_rewrite': 3})


if __name__ == '__main__':
    unittest.main()
