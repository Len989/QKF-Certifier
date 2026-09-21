"""All cold-series work, including failed candidates, packing and built-in load."""
from research.source_planner.audit import Audit as Previous, BudgetStop


class Audit(Previous):
    def report(self):
        out = super().report()
        out.update(schema='qkf-source-lemmas-work-v1', paper_I_forcing=False,
                   scope='actual research calls and instrumented elapsed, including all source/target '
                         'admission, failed/native/lemma work, packing and built-in cold replay; '
                         'excludes diagnostic serialization, CLI I/O and external replay')
        return out
