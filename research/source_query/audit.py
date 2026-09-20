"""Observable work ledger; diagnostic evidence, never a mathematical premise."""
from collections import Counter
from contextlib import contextmanager
import sys
import time

from .context import digest, require, snapshot, integer

BUILDERS = ('research.signed_coverage.producer', 'research.signed_bridge.producer',
            'research.signed_predicates.producer', 'research.wordexpr.producer',
            'research.signed_observations.producer', 'research.observations.producer')
DEFAULTS = {'max_fact_attempts': 10000, 'max_work': 2_000_000,
            'max_witness_width': 8, 'max_witness_evaluations': 510,
            'max_source_states': 64, 'max_product_states': 8192}


class BudgetStop(BaseException):
    pass


class ForbiddenConstruction(BaseException):
    pass


def limits(raw):
    raw = {} if raw is None else snapshot(raw)
    require(type(raw) is dict and set(raw) <= set(DEFAULTS), 'source-query limits')
    result = {**DEFAULTS, **raw}
    for name, maximum in [('max_fact_attempts', 20000), ('max_work', 20_000_000),
                          ('max_witness_width', 4096), ('max_witness_evaluations', 100000),
                          ('max_source_states', 64), ('max_product_states', 8192)]:
        integer(result[name], 0 if name not in ('max_source_states', 'max_product_states') else 1,
                maximum, name)
    return result


class Audit:
    def __init__(self, options):
        self.options = options
        self.calls, self.counts, self.cache = Counter(), Counter(), {}
        self.attempts, self.phases = [], []
        self.allow_builders = False

    def profile(self, frame, event, arg):
        module = frame.f_globals.get('__name__', '')
        if event == 'return' and module == 'research.source_query.context' and frame.f_code.co_name == 'target_domain':
            if type(arg) is tuple and len(arg) == 2:
                self.counts['guard_domain_builds_including_replay'] += 1
                self.counts['guard_domain_transitions_including_replay'] += arg[1]
        if event != 'call':
            return
        if not module.startswith('research.') or module == __name__:
            return
        name = module + '.' + frame.f_code.co_name
        self.calls[name] += 1
        self.counts['research_calls'] += 1
        if module in BUILDERS:
            self.counts['legacy_builder_calls'] += 1
            if not self.allow_builders:
                raise ForbiddenConstruction('legacy source construction forbidden: ' + name)
        if self.counts['research_calls'] > self.options['max_work']:
            raise BudgetStop('research-call budget')

    def __enter__(self):
        require(sys.getprofile() is None, 'exclusive work profiler')
        self.start = time.perf_counter_ns()
        sys.setprofile(self.profile)
        return self

    def __exit__(self, typ, exc, tb):
        sys.setprofile(None)
        self.elapsed_ns = time.perf_counter_ns() - self.start
        return False

    @contextmanager
    def stage(self, name):
        before = self.counts.copy()
        start = time.perf_counter_ns()
        row = {'name': name, 'outcome': 'completed'}
        try:
            yield
        except BaseException as error:
            row['outcome'] = type(error).__name__
            raise
        finally:
            row['counts'] = dict(self.counts - before)
            row['elapsed_ns'] = time.perf_counter_ns() - start
            self.phases.append(row)

    def fact(self, candidate, derive):
        self.counts['fact_requests'] += 1
        row = {'candidate': snapshot(candidate)}
        self.attempts.append(row)
        if len(self.attempts) > self.options['max_fact_attempts']:
            row['outcome'] = 'budget_exhausted'
            raise BudgetStop('native fact-attempt budget')
        key = digest(candidate)
        if key in self.cache:
            self.counts['fact_cache_hits'] += 1
            row['outcome'] = 'cache_hit'
            return self.cache[key]
        self.counts['native_rule_attempts'] += 1
        row['outcome'] = 'started'
        try:
            result = derive()
        except BaseException as error:
            row['outcome'] = type(error).__name__
            raise
        row['outcome'] = 'established' if result is not None else 'not_applicable'
        self.counts['native_rule_successes' if result is not None else 'native_rule_failures'] += 1
        self.cache[key] = result
        return result

    def report(self):
        return {'schema': 'qkf-source-query-work-v1', 'is_certificate': False,
                'counts': dict(self.counts), 'calls': dict(sorted(self.calls.items())),
                'fact_attempts': self.attempts, 'phases': self.phases, 'elapsed_ns': self.elapsed_ns,
                'limits': self.options,
                'units': 'research Python call entries and declared structural events; not CPU instructions',
                'scope': 'instrumented semantic work including parsing, unsuccessful attempts, fallback and checking; excludes diagnostic serialization, CLI I/O and external replay',
                'paper_I_forcing': False, 'automatic_observation_planner': False}
