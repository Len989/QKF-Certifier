from copy import deepcopy
import itertools
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from research.pure_rows.common import InvalidCertificate
from .audit import Audit
from .bridge import verify_branch, verify_descent
from .checker import check
from .context import PHASES, Unsupported, digest, legacy, prepare, read_json
from .fixtures import SOURCE, cases, request
from .producer import prove


class ForcingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SOURCE.read_text()
        cls.req = request()
        cls.proof, cls.result, cls.work = prove(cls.source, cls.req)
        cls.direct, cls.direct_result, _ = prove(cls.source, cls.req, route='direct_seeds')
        cls.cell, cls.cell_result, _ = prove(cls.source, cls.req, route='direct_cell')

    def reject(self, edit, proof=None, source=None, req=None):
        p = deepcopy(self.proof if proof is None else proof)
        edit(p)
        with self.assertRaises(InvalidCertificate):
            check(self.source if source is None else source, self.req if req is None else req, p)

    def test_actual_source_hash(self):
        self.assertEqual(self.proof['binding']['source_sha256'], '7a4b84d92654ef22c911dab503efd829b48a72156ff0de51129e767589ad0010')

    def test_source_bound_strict_saturation(self):
        self.assertEqual(self.result['status'], 'certified')
        self.assertEqual(self.result['generated_domain'], [0, 2, 6, 7])
        self.assertEqual(self.result['forced_domain'], list(range(8)))
        self.assertNotIn(3, self.result['generated_domain'])
        self.assertEqual(self.result['goals'][0]['derived_preimage'], 0)

    def test_physical_transitions(self):
        self.assertEqual([p['result'] for p in self.proof['preparation']['branches']], [[0, 2], [1, 1], [0, 2]])

    def test_seed_source_dependencies(self):
        self.assertEqual([[f['input'], f['output']] for f in self.proof['preparation']['seeds']], [[0, 0], [2, 0], [6, 5], [7, 5]])
        self.assertTrue(all(f['branches'] == [0, 1, 2] for f in self.proof['preparation']['seeds']))

    def test_same_seed_control(self):
        self.assertEqual(self.direct['preparation'], self.proof['preparation'])
        self.assertEqual(self.direct_result['goals'], self.result['goals'])
        self.assertEqual(self.direct['evidence']['atomic_images'], [0, 0, 5])

    def test_cold_direct_control(self):
        self.assertEqual(self.cell_result['goals'], self.result['goals'])
        self.assertEqual(self.cell['preparation']['seeds'], [])
        self.assertIsNone(self.cell['preparation']['compatibility'])

    def test_no_saturation_obligation(self):
        _, r, w = prove(self.source, self.req, route='no_saturation')
        self.assertEqual(r['status'], 'unresolved')
        self.assertIsNone(r['forced_domain'])
        self.assertEqual(w['counts'].get('direct_action_queries', 0), 0)

    def test_unresolved_is_not_source_refutation(self):
        req = request([[1, 1]], [1, 1, 1, 1])
        _, r, _ = prove(self.source, req)
        _, direct, _ = prove(self.source, req, route='direct_seeds')
        self.assertEqual(r['status'], 'unresolved')
        self.assertNotIn(1, r['forced_domain'])
        self.assertEqual(direct['status'], 'certified')

    def test_guard_zero_changes_real_value(self):
        _, r, _ = prove(self.source, request(label=[0, 1, 0, 0]))
        self.assertEqual(r['status'], 'refuted')
        self.assertEqual(r['goals'][0]['derived_preimage'], 2)
        self.assertEqual(r['goals'][0]['separating_phase'], 1)

    def test_output_guard_changes_real_value(self):
        _, r, _ = prove(self.source, request(label=[0, 1, 1, 1]))
        self.assertEqual(r['status'], 'refuted')
        self.assertEqual(r['goals'][0]['derived_preimage'], 2)

    def test_wrong_claim_is_not_accepted_receipt(self):
        _, r, _ = prove(self.source, request([[3, 5]]))
        self.assertEqual(r['status'], 'refuted')
        self.assertEqual(r['goals'][0]['separating_phase'], 0)

    def test_changed_guard_binding(self):
        self.reject(lambda p: None, req=request(label=[0, 1, 0, 0]))

    def test_changed_guard_with_rebound_header(self):
        req = request(label=[0, 1, 0, 0])
        self.reject(lambda p: p.update(binding=prepare(self.source, req)['binding']), req=req)

    def test_changed_output_with_rebound_header(self):
        req = request(label=[0, 1, 1, 1])
        self.reject(lambda p: p.update(binding=prepare(self.source, req)['binding']), req=req)

    def test_changed_source_with_rebound_header(self):
        source = next(c['source'] for c in cases() if c['name'] == 'first_or')
        self.reject(lambda p: p.update(binding=prepare(source, self.req)['binding']), source=source)

    def test_alpha_renaming_remains_bound(self):
        source = self.source.replace('newLowerBound', 'candidateFloor')
        p, r, _ = prove(source, self.req)
        self.assertEqual(r['status'], 'certified')
        self.assertNotEqual(p['binding']['source_sha256'], self.proof['binding']['source_sha256'])

    def test_unsupported_dead_shape(self):
        source = self.source.replace('return newLowerBound;', 'return ~newLowerBound;')
        p, r, _ = prove(source, self.req)
        self.assertIsNone(p)
        self.assertEqual(r['status'], 'unsupported')

    def test_false_seed(self):
        self.reject(lambda p: p['preparation']['seeds'][1].update(output=1))

    def test_omitted_seed_dependency(self):
        self.reject(lambda p: p['preparation']['seeds'][2].update(branches=[0, 2]))

    def test_reordered_seed_dependencies(self):
        self.reject(lambda p: p['preparation']['seeds'][2].update(branches=[2, 1, 0]))

    def test_receipt_cannot_replace_seed(self):
        self.reject(lambda p: p['preparation']['seeds'][2].update(checked=True))

    def test_physical_phase_collapse(self):
        self.reject(lambda p: p['preparation']['branches'].pop())

    def test_phase_relabel(self):
        self.reject(lambda p: p['preparation']['branches'][0].update(phase=2))

    def test_bool_as_phase_index(self):
        self.reject(lambda p: p['preparation']['branches'][0].update(phase=False))

    def test_false_incoming_sum(self):
        self.reject(lambda p: p['preparation']['branches'][2].update(total=1))

    def test_omitted_source_instruction(self):
        self.reject(lambda p: p['preparation']['branches'][0].update(steps=[]))

    def test_wrong_instruction(self):
        self.reject(lambda p: p['preparation']['branches'][0]['steps'][0].update(action='or'))

    def test_false_intermediate_state(self):
        self.reject(lambda p: p['preparation']['branches'][0]['steps'][0].update(state=[True, 0, 0]))

    def test_int_as_physical_bool(self):
        self.reject(lambda p: p['preparation']['branches'][0]['steps'][0].update(state=[1, 0, 1]))

    def test_spurious_source_instruction(self):
        self.reject(lambda p: p['preparation']['branches'][1]['steps'].append(deepcopy(p['preparation']['branches'][0]['steps'][0])))

    def test_false_phase_continuation(self):
        self.reject(lambda p: p['preparation']['branches'][2].update(result=[0, 1]))

    def test_compatibility_table_tamper(self):
        self.reject(lambda p: p['preparation']['compatibility']['boolean_rows'][4].__setitem__(3, 1))

    def test_missing_compatibility_case(self):
        self.reject(lambda p: p['preparation']['compatibility']['boolean_rows'].pop())

    def test_compatibility_physical_labels(self):
        self.reject(lambda p: p['preparation']['compatibility']['phases'].__setitem__(0, [True, 1]))

    def test_native_table_tamper(self):
        self.reject(lambda p: p['evidence']['presentation']['carrier']['operations'][0]['table'].__setitem__(1, 0))

    def test_extra_complement_not_assumed(self):
        def edit(p):
            p['evidence']['presentation']['carrier']['operations'].append(dict(name='complement', arity=1, table=[7 ^ i for i in range(8)]))
        self.reject(edit)
        # h(ABC)=5 while absolute complement of h(empty)=7.
        self.assertNotEqual(self.proof['preparation']['seeds'][3]['output'], 7)

    def test_carrier_labels_are_semantic(self):
        self.reject(lambda p: p['evidence']['presentation']['carrier']['names'].__setitem__(0, 'renamed'))

    def test_operator_label_bound(self):
        self.reject(lambda p: p['evidence']['presentation']['operators']['names'].__setitem__(0, 'other-source'))

    def test_artificial_supplied_cell(self):
        self.reject(lambda p: p['evidence']['presentation']['cells'].append([0, 3, 0]))

    def test_quotient_cannot_repair_source(self):
        self.reject(lambda p: p['evidence']['descent'].update(carrier_partition=[list(range(8))]))
        with self.assertRaises(ValueError):
            verify_descent(dict(rule='identity-on-physical-powerset', carrier_partition=[[i] for i in range(8)]),
                           dict(carrier_protected=False, carrier_partition=[list(range(8))]))

    def test_pure_row_saved_result_is_not_evidence(self):
        self.reject(lambda p: p['evidence']['pure_rows']['result']['rows'][0]['forced_values'].__setitem__(3, 1))

    def test_kernel_trace_is_required(self):
        self.reject(lambda p: p['evidence']['pure_rows']['rows'][0]['kernel'].update(events=[]))

    def test_ground_trace_is_required(self):
        self.reject(lambda p: p['evidence']['pure_rows']['levels'][1]['equality'].update(events=[]))

    def test_range_lemma_tamper(self):
        self.reject(lambda p: p['evidence'].update(atomic_images=[7, 0, 5]), self.direct)

    def test_direct_goal_tamper(self):
        self.reject(lambda p: p['evidence']['lookups'][0].update(output=1), self.direct)

    def test_direct_cell_tamper(self):
        self.reject(lambda p: p['evidence']['lookups'][0].update(output=1), self.cell)

    def test_direct_cell_no_hidden_seeds(self):
        self.reject(lambda p: p['preparation'].update(seeds=self.proof['preparation']['seeds']), self.cell)

    def test_no_target_query_and_full_costs(self):
        c = self.work['counts']
        self.assertEqual(c.get('direct_action_queries', 0), 0)
        self.assertEqual(c['source_cell_evaluations'], 3)
        self.assertEqual(c['seed_queries'], 4)
        self.assertEqual(c['native_table_entries_built'], 128)
        self.assertEqual(c['native_table_entries_checked'], 128)
        self.assertEqual(c['source_admissions'], 2)
        self.assertEqual(c['branch_replays'], 3)
        self.assertGreater(self.work['pure_rows']['work']['work'], 0)

    def test_actual_target_call_guard(self):
        from .direct import action_cell
        with self.assertRaisesRegex(RuntimeError, 'target action query'):
            with Audit('forcing'):
                action_cell(prepare(self.source, self.req), self.proof['preparation']['branches'], 3)

    def test_actual_full_quotient_guard(self):
        _, kernel = legacy()
        with self.assertRaisesRegex(RuntimeError, 'source_quotient'):
            with Audit('forcing'):
                kernel.source_quotient(prepare(self.source, self.req)['program'])

    def test_actual_replay_rows_guard(self):
        _, kernel = legacy()
        with self.assertRaisesRegex(RuntimeError, 'replay_rows'):
            with Audit('forcing'):
                kernel.replay_rows({}, [], [])

    def test_checker_does_not_execute_source_cells(self):
        _, kernel = legacy()
        with patch.object(kernel, 'source_cell', side_effect=AssertionError('producer execution')):
            self.assertEqual(check(self.source, self.req, self.proof), self.result)

    def test_budget_no_partial_proof(self):
        p, r, w = prove(self.source, self.req, limits=dict(max_work=0))
        self.assertIsNone(p)
        self.assertEqual(r['status'], 'budget_exhausted')
        self.assertEqual(w['counts']['seed_queries'], 4)
        self.assertEqual(w['counts']['native_table_entries_built'], 128)
        self.assertEqual(w['pure_rows']['status'], 'incomplete')

    def test_reuse_real_cache_for_all_routes(self):
        req = request([[3, 0], [1, 0], [4, 5], [5, 5]] * 4)
        for route in ('forcing', 'no_saturation', 'direct_seeds', 'direct_cell'):
            with self.subTest(route=route):
                _, _, w = prove(self.source, req, route=route)
                self.assertEqual(w['caches'], dict(goal_requests=16, distinct_goals=4, goal_cache_hits=12))
                self.assertEqual(w['counts']['source_cell_evaluations'], 3)

    def test_independent_integer_cell_semantics(self):
        from .native import explain_branch
        ctx = prepare(self.source, self.req)
        _, kernel = legacy()
        for mandatory, first in itertools.product(('add', 'or'), repeat=2):
            ctx['program'] = dict(mandatory_action=mandatory, forbidden_action='add', first_action=first)
            for m, a, g in ((0, 0, 0), (0, 1, 0), (0, 1, 1), (1, 1, 1)):
                ctx['request'] = request(label=[m, a, g, 0])
                for i, (inc, carry) in enumerate(PHASES):
                    value = g + carry
                    next_inc = inc
                    if inc:
                        if m and not value & 1:
                            value = value + 1 if mandatory == 'add' else value | 1
                        if not a and value & 1:
                            value += 1
                    elif a and not m:
                        value = value + 1 if first == 'add' else value | 1
                        next_inc = True
                    expected = [value & 1, PHASES.index((next_inc, value >> 1))]
                    proof = dict(phase=i, **explain_branch(ctx['program'], PHASES[i], m, a, g))
                    self.assertEqual(verify_branch(ctx, proof, i), expected)
                    bit, phase = kernel.source_cell(ctx['program'], PHASES[i], m, a, g)
                    self.assertEqual([bit, PHASES.index(phase)], expected)

    def test_strict_request(self):
        variants = [dict(self.req, width=64), request(label=[False, 1, 1, 0]),
                    request(label=[1, 0, 0, 0]), request([[8, 0]]),
                    dict(self.req, profile='modular-lsb-signed-word-predicates-v1')]
        for req in variants:
            with self.subTest(req=req), self.assertRaises(Unsupported):
                prepare(self.source, req)

    def test_duplicate_wire_json_key(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'bad.json'
            path.write_text('{"schema":1,"schema":2}')
            with self.assertRaises(ValueError):
                read_json(path)

    def test_exact_registration(self):
        reg = read_json(Path(__file__).with_name('REGISTRATION.json'))
        self.assertEqual(reg['protocol_sha256'], digest(read_json(Path(__file__).with_name('PROTOCOL.json'))))
        self.assertEqual([dict(name=c['name'], case_sha256=digest(c), expected=c['expected']) for c in cases()], reg['cases'])

    def test_fresh_independent_checker(self):
        script = '''
import json,sys
from research.source_forcing.replay import NoSearch
guard=NoSearch()
sys.meta_path.insert(0,guard)
from research.source_forcing.checker import check
from research.source_forcing.audit import Audit
data=json.load(open(sys.argv[1]))
with Audit('replay') as audit:
    result=check(data['source'],data['request'],data['proof'])
if result!=data['result'] or guard.loaded():raise RuntimeError('fresh replay')
if audit.counts.get('source_cell_evaluations',0):raise RuntimeError('source evaluator imported')
'''
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'portable.json'
            path.write_text(json.dumps(dict(source=self.source, request=self.req, proof=self.proof, result=self.result)))
            for flags in ([], ['-O']):
                process = subprocess.run([sys.executable, *flags, '-c', script, str(path)], capture_output=True, text=True)
                self.assertEqual(process.returncode, 0, process.stderr)

    def test_cli_portable_and_exclusive_output(self):
        with tempfile.TemporaryDirectory() as d:
            req, proof = Path(d) / 'request.json', Path(d) / 'proof.json'
            req.write_text(json.dumps(self.req))
            prefix = [sys.executable, '-m', 'research.source_forcing']
            args = [str(SOURCE), '--request', str(req), '--proof', str(proof)]
            first = subprocess.run(prefix + ['prove'] + args, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            repeat = subprocess.run(prefix + ['prove'] + args, capture_output=True, text=True)
            self.assertEqual(repeat.returncode, 2)
            replay = subprocess.run(prefix + ['check'] + args, capture_output=True, text=True)
            self.assertEqual(replay.returncode, 0, replay.stderr)


if __name__ == '__main__':
    unittest.main()
