"""Common actual-call audit alongside the retained exclusive profilers.

Only audit/memory children use this tracer. It never supplies proof premises and
never replaces accepted guards. Metadata is cached per code object; return events
are requested only for the structural hooks and phase roots that need them.
"""
from collections import Counter
import sys
import time

HOOKS = {
    ('research.signed_predicates.frontend', 'read_source'): 'source_parse_calls',
    ('research.signed_coverage.producer', 'edge_candidate'): 'legacy_branch_attempts',
    ('research.signed_coverage.local', 'replay_edge'): 'legacy_edge_rechecks',
    ('research.signed_predicates.semantics', 'evaluate'): 'whole_word_evaluations',
    ('research.source_query.ordinary', 'prove'): 'ordinary_CC_searches',
    ('research.ground_query.producer', 'prove'): 'II_searches',
    ('research.signed_coverage.producer', 'build'): 'legacy_coverage_builds',
}
SEARCH = {('research.ground_query.producer', 'prove'), ('research.source_query.ordinary', 'prove')}
HARVEST = {('research.signed_coverage.producer', 'build'): 'coverage',
           ('research.signed_targets.producer', 'discover'): 'target'}
CHECK_NAMES = {'check', 'verify', 'verify_fact', 'verify_branch', 'verify_seed'}
UNSEEN = object()


class Trace:
    def __init__(self):
        self.code_calls, self.counts = {}, Counter()
        self.events, self.stack = [], []
        self.durations, self.metadata = Counter(), {}
        self.total = 0

    def describe(self, frame):
        module = frame.f_globals.get('__name__', '')
        if not module.startswith('research.') or module.startswith('research.causal_comparison.'):
            return None
        name = frame.f_code.co_name
        key = module, name
        category = None
        if name in CHECK_NAMES and ('.checker' in module or module.startswith('research.source_')):
            category = 'semantic_check_roots_ns'
        elif key in SEARCH:
            category = 'ground_search_roots_ns'
        hook = 'global_source_quotient_calls' if name in ('source_quotient', 'replay_rows') else HOOKS.get(key)
        return (module + '.' + name, hook, category, key in SEARCH, HARVEST.get(key))

    def event(self, frame, event, arg):
        code = frame.f_code
        if event == 'call':
            meta = self.metadata.get(code, UNSEEN)
            if meta is UNSEEN:
                meta = self.metadata[code] = self.describe(frame)
            if meta is None:
                return None
            self.total += 1
            self.code_calls[code] = self.code_calls.get(code, 0) + 1
            _, hook, category, search, harvest = meta
            if hook:
                self.counts[hook] += 1
            root = category is not None and not any(r[1] == category for r in self.stack)
            if root:
                self.stack.append((id(frame), category, time.perf_counter_ns()))
            if root or search or harvest:
                frame.f_trace_lines = False
                return self.event
            return None
        if event != 'return':
            return self.event
        if self.stack and self.stack[-1][0] == id(frame):
            _, category, start = self.stack.pop()
            self.durations[category] += time.perf_counter_ns() - start
        label, _, _, search, harvest = self.metadata[code]
        if harvest:
            loc = frame.f_locals
            if harvest == 'coverage':
                self.counts['legacy_discovered_states'] += len(loc.get('states', []))
                self.counts['legacy_discovery_edges'] += len(loc.get('edges', []))
            else:
                self.counts['legacy_target_states'] += len(loc.get('states', []))
        if search and type(arg) is tuple and type(arg[0]) is dict:
            proof, stats = arg
            self.events.append(dict(backend='II' if 'ground_query' in label else 'ordinary',
                request_sha256=proof['request_sha256'], horizon=proof['horizon'],
                events=len(proof['events']), models=len(proof['models']), stats=stats))
        return self.event

    def __enter__(self):
        if sys.gettrace() is not None:
            raise RuntimeError('exclusive PR46 call tracer required')
        sys.settrace(self.event)
        return self

    def __exit__(self, *args):
        sys.settrace(None)

    def report(self):
        calls = Counter()
        for code, count in self.code_calls.items():
            calls[self.metadata[code][0]] += count
        return dict(counts=dict(self.counts, research_calls=self.total), calls=dict(sorted(calls.items())),
                    closure_trace=self.events, audit_phase_ns=dict(self.durations),
                    is_execution_certificate=False,
                    scope='actual research call entries including built-in checks and SDK export; not CPU instructions')
