"""PR47 accounting extended to the new entry points, including preparation."""
from research.sdk_comparison.trace import Trace as Previous

SEARCH = {('research.prepared_context.ordinary', 'prove'): 'ordinary_CC_searches',
          ('research.prepared_context.query', 'prove'): 'II_searches'}


class Trace(Previous):
    def describe(self, frame):
        module, name = frame.f_globals.get('__name__', ''), frame.f_code.co_name
        if module in {__package__ + '.' + n for n in ('worker', 'common', 'trace')}:
            return None
        meta = super().describe(frame)
        if meta is not None and (module, name) in SEARCH:
            return (meta[0], SEARCH[(module, name)], 'ground_search_roots_ns', True, None)
        if meta is not None and module == __package__ + '.ground_check' and name == 'check':
            return (meta[0], None, 'semantic_check_roots_ns', False, None)
        return meta

    def event(self, frame, event, arg):
        result = super().event(frame, event, arg)
        if (event == 'return' and frame.f_globals.get('__name__') == __package__ + '.query'
                and frame.f_code.co_name == 'prove' and type(arg) is tuple and type(arg[0]) is dict):
            self.events[-1]['backend'] = 'II'
        return result
