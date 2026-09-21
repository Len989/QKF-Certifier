"""Process-local checked action. No source, IR, planner or native evaluator."""
from dataclasses import dataclass
from .contract import (SIGNED, PHASE, canonical, snapshot, request, signed_spec,
                       target_value, require, integer)
import json

_KEY = object()


class NotApplicable(ValueError):
    pass


class OutsideDomain(ValueError):
    pass


@dataclass(frozen=True, slots=True, init=False)
class CheckedSummary:
    _request: str
    _action: str
    _result: str
    _explanations: str
    _packet: str

    def __init__(self, key=None, **values):
        require(key is _KEY, 'check source and certificate before obtaining a summary')
        for k in self.__slots__:
            object.__setattr__(self, k, values[k])

    def __reduce_ex__(self, protocol):
        raise TypeError('export portable foundations and check them in the new process')

    def result(self):
        return json.loads(self._result)

    def interface(self):
        return json.loads(self._action)

    def export(self):
        return json.loads(self._packet)

    def request(self):
        return json.loads(self._request)

    def apply(self, value, *, width=None):
        """Evaluate the proved action, with exact runtime domain checks."""
        action = self.interface()
        if action['kind'] == 'phase_cells':
            require(width is None, 'local phase application has no whole-word width')
            integer(value, 0, 7, 'phase subset')
            for target, output, _ in action['cells']:
                if value == target:
                    return output
            raise NotApplicable('phase cell not in the checked sufficient interface; refinement required')
        integer(width, 1, 4096, 'runtime width 1..4096')
        if action['width']['kind'] == 'fixed' and width != action['width']['bits']:
            raise OutsideDomain('runtime width differs from the checked fixed width')
        integer(value, 0, (1 << width) - 1, 'unsigned word encoding within the declared width')
        state = [min(action['count_cap'], value.bit_count()), value >> (width - 1)]
        if state not in action['states']:
            raise OutsideDomain('input does not satisfy the checked guard domain')
        if action['values'] is None:
            raise NotApplicable('no proved Boolean action; refinement required')
        return action['values'][action['states'].index(state)]

    def assess(self, new_request):
        """Prove sufficient target agreement over exact source-free classes."""
        new = request(new_request)
        old, action = self.request(), self.interface()
        base = dict(schema='qkf-summary-sufficiency-v1', source_sha256=self.result()['source_sha256'])
        def decline(reason):
            return dict(base, status='unresolved', reason=reason, refinement_required=True)
        if new['profile'] != old['profile']:
            return decline('different_semantic_profile')
        if new['profile'] == PHASE:
            if new['query']['label'] != old['query']['label']:
                return decline('different_local_cell')
            values = {p: v for p, v, _ in action['cells']}
            if any(values.get(p) != v for p, v in new['query']['goals']):
                return decline('phase_obligation_not_covered')
            return dict(base, status='certified', reason='checked_phase_cells', refinement_required=False)
        for query in new['query']['requests']:
            spec, selected = signed_spec(query)
            if canonical([selected, query['width'], query['guards']]) != canonical(
                    [action['selection'], action['width'], action['guards']]):
                return decline('different_selection_guard_or_width')
            if not action['states']:
                return dict(base, status='verified_empty_domain', reason='empty_guard', refinement_required=False)
            if action['values'] is None:
                return decline('no_checked_action')
            if [target_value(spec['target'], *s) for s in action['states']] != action['values']:
                # A target-class mismatch is not exported as a concrete source witness.
                return decline('consumer_not_established_by_summary')
        return dict(base, status='certified', reason='exact_target_class_agreement',
                    refinement_required=False, basis_goal=action['basis_goal'], checked_classes=len(action['states']))

    def explain(self, goal=0, *, consumer=None):
        explanations = json.loads(self._explanations)
        integer(goal, 0, len(explanations) - 1, 'consumer index')
        value = dict(profile=self.result()['profile'], source_sha256=self.result()['source_sha256'],
                     request=self.request(), goal=goal, result=self.result()['goals'][goal],
                     dependencies=explanations[goal])
        if consumer is not None:
            value['sufficiency'] = self.assess(consumer)
            if value['sufficiency']['status'] == 'certified' and self.interface()['kind'] == 'guarded_boolean':
                basis = self.interface()['basis_goal']
                value['goal'], value['result'], value['dependencies'] = basis, self.result()['goals'][basis], explanations[basis]
                value['target_classes'] = self.interface()['states']
        return snapshot(value)


def _issue(r, action, result, explanations, packet):
    return CheckedSummary(_KEY, _request=canonical(r), _action=canonical(action),
                          _result=canonical(result), _explanations=canonical(explanations), _packet=canonical(packet))
