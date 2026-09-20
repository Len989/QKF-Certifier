"""Actual Python call trace. Diagnostic accounting, not a proof of execution."""
from collections import Counter
from contextlib import contextmanager
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


class Audit:
    def __init__(self, route):
        self.route = route
        self.counts = Counter()
        self.calls = Counter()
        self.trace = []
        self.timings = Counter()
        self.current = 'setup'

    def profile(self, frame, event, arg):
        if event != 'call':
            return
        path = frame.f_code.co_filename.replace('\\', '/')
        name = frame.f_code.co_name
        module = frame.f_globals.get('__name__', '')
        # Reject the actual call even when a module was imported before the guard.
        forbidden = (name in ('source_quotient', 'replay_rows') or
                     (str(ROOT) in path and ('/signed_coverage/' in path or '/signed_runtime/' in path)) or
                     (module == 'subprocess' and name == '__init__') or
                     (module == 'os' and name in ('system', 'popen', 'spawnv')))
        if forbidden:
            raise RuntimeError('local source route forbids ' + module + '.' + name)
        if str(ROOT) not in path:
            return
        self.counts['python_calls_in_research'] += 1
        if '/source_forcing/' in path or '/pure_rows/' in path:
            self.calls[module + '.' + name] += 1
        key = {
            'compile_source': 'source_admissions', 'source_cell': 'source_cell_evaluations',
            'verify_branch': 'branch_replays', 'native_seed': 'seed_queries',
            'verify_seed': 'seed_replays', 'build_entry': 'native_table_entries_built',
            'check_entry': 'native_table_entries_checked', 'check_boolean_row': 'compatibility_rows_checked',
            'verify_descent': 'descent_checks', 'action_cell': 'direct_action_queries',
            'direct_membership': 'direct_memberships', 'range_value': 'range_goal_derivations',
        }.get(name)
        if key:
            self.counts[key] += 1
        if name == 'action_cell' and self.route != 'direct_cell':
            raise RuntimeError('direct target action query forbidden on ' + self.route)
        if name == 'native_seed':
            target = frame.f_locals['target']
            if target not in (0, 2, 6, 7):
                raise RuntimeError('unregistered seed query')
            self.trace.append(dict(stage=self.current, call='seed', input=target))
        if name == 'source_cell':
            self.trace.append(dict(stage=self.current, call='source_cell',
                                   phase=list(frame.f_locals['phase']),
                                   label=[frame.f_locals[k] for k in ('m', 'a', 'g')]))
        if name == 'action_cell':
            self.trace.append(dict(stage=self.current, call='target', input=frame.f_locals['target']))

    @contextmanager
    def stage(self, name):
        previous = self.current
        self.current = name
        start = time.perf_counter_ns()
        try:
            yield
        finally:
            self.timings[name] += time.perf_counter_ns() - start
            self.current = previous

    def __enter__(self):
        self.previous = sys.getprofile()
        self.started = time.perf_counter_ns()
        sys.setprofile(self.profile)
        return self

    def __exit__(self, *args):
        sys.setprofile(self.previous)
        self.elapsed = time.perf_counter_ns() - self.started

    def report(self):
        return dict(counts=dict(self.counts), calls=dict(self.calls), trace=self.trace,
                    elapsed_ns=self.elapsed, stages_ns=dict(self.timings),
                    scope='instrumented producer plus builtin source/pure-row checking; excludes CLI I/O and separately charged fresh replay; diagnostic, not execution evidence')
