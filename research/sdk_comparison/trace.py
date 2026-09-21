"""Common call audit, with SDK preparation/packaging hooks; never a proof."""
from research.causal_comparison.trace import Trace as OldTrace

HOOKS = {
    ('research.source_query.context', 'prepare'): 'source_context_preparations',
    ('research.source_lemmas.context', 'prepare'): 'batch_context_preparations',
    ('research.source_lemmas.checker', 'load_presentation'): 'presentation_loads',
    ('research.applicable_summary.export', 'extract'): 'dependency_exports',
    ('research.applicable_summary.checker', 'components'): 'component_replays',
    ('research.applicable_summary.checker', 'check'): 'SDK_cold_checks',
    ('research.applicable_summary.checker', 'package'): 'SDK_packages',
    ('research.applicable_summary.checker', 'from_certificate'): 'SDK_native_imports',
}


class Trace(OldTrace):
    def describe(self, frame):
        module = frame.f_globals.get('__name__', '')
        if module.startswith('research.sdk_comparison.'):
            return None
        meta = super().describe(frame)
        hook = HOOKS.get((module, frame.f_code.co_name))
        if meta is not None and hook:
            meta = (meta[0], hook, *meta[2:])
        return meta
