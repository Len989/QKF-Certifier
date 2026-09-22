"""PR47/48 call accounting, including the new emitter and envelope path."""
from research.prepared_context.trace import Trace as Previous


class Trace(Previous):
    def describe(self, frame):
        module = frame.f_globals.get('__name__', '')
        if module in {__package__ + '.' + n for n in ('worker', 'common', 'trace')}:
            return None
        return super().describe(frame)
