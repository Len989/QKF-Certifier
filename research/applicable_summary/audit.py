"""Actual-call guards, including modules loaded before the guard."""
import sys


class ExecutionGuard:
    def __init__(self, *, checking=False, application=False, witness=False):
        self.checking, self.application, self.witness = checking, application, witness
        self.calls = 0

    def profile(self, frame, event, arg):
        if event != 'call':
            return
        module = frame.f_globals.get('__name__', '')
        name = frame.f_code.co_name
        path = frame.f_code.co_filename.replace('\\', '/')
        self.calls += int('/research/' in path)
        forbidden = name in ('source_quotient', 'replay_rows') or (
            module.endswith(('.producer', '_producer')) and
            not module.startswith(('research.source_lemmas.', 'research.source_planner.',
                                   'research.source_query.', 'research.ground_query.',
                                   'research.source_forcing.', 'research.pure_rows.',
                                   'research.applicable_summary.')))
        forbidden |= module == 'subprocess' and name == '__init__'
        forbidden |= module == 'os' and name in ('system', 'popen', 'spawnv')
        if self.checking:
            forbidden |= module.endswith(('.producer', '_producer')) or module in (
                'research.source_planner.language', 'research.source_planner.native',
                'research.source_query.facts', 'research.source_query.ordinary',
                'research.source_forcing.native', 'research.source_forcing.direct')
            forbidden |= name == 'source_cell'
            forbidden |= (not self.witness and name == 'evaluate' and module in (
                'research.signed_predicates.semantics', 'research.wordexpr.semantics'))
        if self.application:
            forbidden |= name in ('read', 'prepare', 'compile_source', 'source_cell', 'evaluate') and (
                module.startswith('research.') or module in ('carry_kernel', 'lower_source'))
        if forbidden:
            raise RuntimeError('summary route forbids actual call ' + module + '.' + name)
        if self.previous is not None:
            self.previous(frame, event, arg)

    def __enter__(self):
        self.previous = sys.getprofile()
        sys.setprofile(self.profile)
        return self

    def __exit__(self, *args):
        sys.setprofile(self.previous)
