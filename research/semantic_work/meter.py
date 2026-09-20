"""Single-thread, additive accounting, including failed attempts and built-in checks.

Work is Python call entries in research modules, NOT CPU instructions or proof
complexity. Structural counters use explicit pinned hook meanings. Imported aliases
are caught through executing frames, not monkeypatched module names. Diagnostic
telemetry is not a cryptographic proof of past execution or a hostile-code sandbox.
"""
from collections import Counter
from contextlib import contextmanager
import sys
import threading
import time
import tracemalloc
from .contract import canonical, digest, need, snapshot

# Fail closed in routes that promise not to enumerate an old source carrier.
FULL_BUILDERS = {
    ('research.signed_bridge.producer', 'derive'),
    ('research.signed_predicates.producer', 'derive'),
    ('research.wordexpr.producer', 'derive'),
}


class StopWork(BaseException):
    """Bypass old catch(Exception) wrappers; the owning runner emits unresolved."""


class ForbiddenWork(BaseException):
    pass


def formula_nodes(term):
    return 1 + sum(formula_nodes(x) for x in term[1:] if type(x) is list)


class Meter:
    def __init__(self, max_work=2_000_000, max_attempts=64, *, forbid_full=False):
        from .contract import integer
        integer(max_work, 0, 20_000_000)
        integer(max_attempts, 0, 64)
        self.max_work, self.max_attempts = max_work, max_attempts
        self.forbid_full = forbid_full
        self.counts = Counter()
        self.calls = Counter()
        self.phases = []
        self.phase = None
        self.ir_ids, self.point_ids, self.fact_ids = set(), set(), set()
        self.pending = {}
        self.active = False
        self.blocked = None
        self.report = None

    def _profile(self, frame, event, arg):
        module = frame.f_globals.get('__name__', '')
        if not module.startswith('research.') or module.startswith('research.semantic_work.'):
            return
        name = frame.f_code.co_name
        key = (module, name)
        label = module + '.' + name
        if event == 'call':
            self.counts['work_calls'] += 1
            self.calls[label] += 1
            if key in FULL_BUILDERS:
                self.counts['old_full_builder_calls'] += 1
                if self.forbid_full:
                    self.blocked = label
                    raise ForbiddenWork('forbidden full construction: ' + label)
            if self.counts['work_calls'] > self.max_work:
                raise StopWork('global research-call budget')
            if key == ('research.signed_coverage.producer', 'edge_candidate'):
                self.counts['discovery_branch_attempts'] += 1
            if key == ('research.signed_reduction.rules', 'rewrite'):
                self.counts['rewrite_calls_including_replay'] += 1
            if key == ('research.signed_coverage.local', 'replay_edge'):
                self.counts['coverage_edge_rechecks'] += 1
            if key == ('research.observations.atomic_rows', 'check_completion'):
                self.counts['atomic_row_rechecks'] += 1
            if key == ('research.signed_predicates.frontend', 'read_source'):
                self.counts['source_parse_attempts'] += 1
            if key == ('research.signed_predicates.semantics', 'evaluate'):
                self.counts['whole_word_evaluation_calls'] += 1
                loc = frame.f_locals
                ident = digest([loc['ir'], loc['x'], loc['width']])
                self.point_ids.add(ident)
            if key in {('research.signed_coverage.producer', 'build'),
                       ('research.signed_targets.producer', 'discover'),
                       ('research.observations.producer', 'synthesize')}:
                self.pending[id(frame)] = frame
        elif event == 'return':
            loc = frame.f_locals
            if key == ('research.signed_predicates.frontend', 'read_source') and type(arg) is dict:
                self.counts['source_parse_completions'] += 1
                self.counts['ir_word_nodes_produced_total'] += len(arg['nodes'])
                self.counts['ir_atoms_produced_total'] += len(arg['atoms'])
                self.counts['ir_formula_nodes_produced_total'] += formula_nodes(arg['formula'])
                ident = digest(arg)
                if ident not in self.ir_ids:
                    self.ir_ids.add(ident)
                    self.counts['unique_ir_word_nodes'] += len(arg['nodes'])
                    self.counts['unique_ir_atoms'] += len(arg['atoms'])
            if id(frame) in self.pending:
                self._harvest(key, loc)
                del self.pending[id(frame)]

    def _harvest(self, key, loc):
        if key == ('research.signed_coverage.producer', 'build'):
            self.counts['coverage_build_attempts'] += 1
            self.counts['discovered_states'] += len(loc.get('states', []))
            self.counts['completed_discovery_branches'] += len(loc.get('edges', []))
            self.counts['discovery_local_rewrites'] += loc.get('counts', {}).get('local_rewrite_steps', 0)
        elif key == ('research.signed_targets.producer', 'discover'):
            self.counts['target_product_attempts'] += 1
            self.counts['target_states_created'] += len(loc.get('states', []))
        elif key == ('research.observations.producer', 'synthesize'):
            self.counts['observation_build_attempts'] += 1
            self.counts['observation_questions_created'] += len(loc.get('predicates', []))
            self.counts['pullbacks_attempted'] += loc.get('pullbacks', 0)
            self.counts['separators_materialized'] += len(loc.get('separators', []))

    def __enter__(self):
        need(not self.active and sys.getprofile() is None, 'non-nested exclusive profiler required')
        need(threading.current_thread() is threading.main_thread(), 'main-thread measurement only')
        need(not tracemalloc.is_tracing(), 'exclusive tracemalloc session required')
        self.active = True
        self.start = time.perf_counter_ns()
        tracemalloc.start()
        sys.setprofile(self._profile)
        return self

    def __exit__(self, typ, exc, tb):
        sys.setprofile(None)
        for frame in self.pending.values():
            self._harvest((frame.f_globals.get('__name__'), frame.f_code.co_name), frame.f_locals)
        self.pending.clear()
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        self.active = False
        self.report = {'schema': 'qkf-semantic-work-v1', 'is_certificate': False,
            'counts': dict(sorted((k, v) for k, v in self.counts.items() if v)), 'calls': dict(sorted(self.calls.items())),
            'unique_whole_word_points': len(self.point_ids),
            'phases': snapshot(self.phases), 'elapsed_ns': time.perf_counter_ns() - self.start,
            'python_traced_peak_bytes': peak, 'python_traced_remaining_bytes': current,
            'memory_scope': 'Python allocations since measurement entry; includes meter; not RSS',
            'timing_scope': 'instrumented API including validation/imports/work/checks; excludes CLI I/O',
            'mechanisms': {'paper_I_new_forcing': 'not_invoked', 'paper_II_query_dag': 'not_implemented',
                           'lemma_preparation': 'not_implemented'},
            'ground_input_terms': None, 'added_ground_terms': None,
            'lemma_preparations': 0, 'lemma_reuses': 0, 'blocked_call': self.blocked,
            'work_unit': 'research Python function call entry; not CPU instructions',
            'limits': {'max_work': self.max_work, 'max_attempts': self.max_attempts}}
        return False

    @contextmanager
    def stage(self, name, *, attempt=False):
        need(self.active and self.phase is None, 'flat active accounting stage required')
        self.phase = name
        before = self.counts.copy()
        started = time.perf_counter_ns()
        record = {'name': name, 'attempt': attempt, 'outcome': 'completed'}
        try:
            if attempt:
                self.counts['route_attempts'] += 1
                if self.counts['route_attempts'] > self.max_attempts:
                    raise StopWork('global attempt budget')
            yield record
        except BaseException as exc:
            record['outcome'] = type(exc).__name__
            raise
        finally:
            # A global-budget exception disables CPython's profiler. Account for
            # still-live construction frames even on that path, before the delta.
            for frame in self.pending.values():
                self._harvest((frame.f_globals.get('__name__'), frame.f_code.co_name), frame.f_locals)
            self.pending.clear()
            record['counts'] = dict(sorted((self.counts - before).items()))
            record['elapsed_ns'] = time.perf_counter_ns() - started
            self.phases.append(record)
            self.phase = None

    def fact_request(self, identity, *, cache_hit=False):
        """Future adapters use this ledger; it asserts no truth of a requested fact."""
        need(self.active and type(cache_hit) is bool, 'active fact request')
        self.counts['fact_requests'] += 1
        key = digest(identity)
        if key not in self.fact_ids:
            self.fact_ids.add(key)
            self.counts['unique_fact_requests'] += 1
        self.counts['fact_cache_hits' if cache_hit else 'direct_fact_attempts'] += 1

    def note_fallback(self):
        self.counts['fallbacks'] += 1
