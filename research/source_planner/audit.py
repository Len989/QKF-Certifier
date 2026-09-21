"""PR41 actual-call accounting plus planner decisions and model lifetimes."""
from research.source_query.audit import Audit as Previous, BudgetStop
from .context import LANGUAGE, require


class Audit(Previous):
    def __init__(self, options):
        super().__init__(options)
        self.closed = False
        self.decisions = []
        self.checkpoints = []
        self.diagnosis = None
        self.rounds = 0
        self.origin = None

    def fact(self, candidate, derive):
        require(not self.closed, 'native question after the consumer closed')
        self.decisions.append(dict(event='native_question', candidate=dict(candidate),
                                   origin=self.origin or dict(kind='PR41_eager_policy')))
        return super().fact(candidate, derive)

    def checkpoint(self):
        self.rounds += 1
        if self.rounds > self.options['max_rounds']:
            raise BudgetStop('planner checkpoint budget')

    def report(self):
        out = super().report()
        out.update(schema='qkf-source-planner-work-v1', automatic_observation_planner=True,
                   candidate_language=LANGUAGE, decisions=self.decisions,
                   checkpoints=self.checkpoints, diagnosis=self.diagnosis,
                   planner_rounds=self.rounds, paper_I_forcing=False)
        return out
