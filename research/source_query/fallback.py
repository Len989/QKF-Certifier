"""Explicit covered fallback with a guard- and width-aware consumer product."""
from research.ground_query.schema import fields, require
from research.signed_predicates.frontend import target_value
from .context import MAX_WIDTH


class GuardedMonitor:
    def __init__(self, runner, ctx):
        self.runner, self.ctx, self.spec = runner, ctx, ctx.spec
        self.initial = (runner.machine.initial, 0, 0, 0)
        self.alphabet = ('0', '1')
        self.last_position = 1 if ctx.width is None else ctx.width + 1

    def valid(self, raw):
        return (type(raw) is list and len(raw) == 4 and all(type(v) is int for v in raw)
                and 0 <= raw[0] < self.runner.machine.classes and 0 <= raw[1] <= self.ctx.limit
                and raw[2] in (0, 1) and 0 <= raw[3] <= self.last_position)

    def step(self, state, symbol):
        require(type(symbol) is str and symbol in self.alphabet, 'guarded product binary symbol')
        if self.ctx.width is not None and state[3] >= self.ctx.width:
            # Widths after the fixed obligation are an explicit absorbing sink.
            return (self.runner.machine.initial, 0, 0, self.ctx.width + 1)
        output, following = self.runner.machine.step(state[0], symbol)
        require(output == '_', 'terminal source output')
        bit = int(symbol)
        pos = min(state[3] + 1, self.last_position)
        return following, min(self.ctx.limit, state[1] + bit), bit, pos

    def bad(self, state):
        in_scope = state[3] == (1 if self.ctx.width is None else self.ctx.width)
        if not in_scope or not self.ctx.guard(state[1], state[2]):
            return False
        label = self.runner.machine.terminal[state[0]]
        require(label in ('true', 'false'), 'positive-width source terminal')
        return (label == 'true') != target_value(self.spec['target'], state[1], state[2])


def check_covered(source, ctx, evidence):
    fields(evidence, ('observations', 'obligation'), 'covered conditional evidence')
    from research.signed_coverage.runtime import load
    from research.signed_targets.checker import check_product
    runner, receipt = load(source, ctx.selection, evidence['observations'])
    checked = check_product(GuardedMonitor(runner, ctx), evidence['obligation'])
    # Do not reuse the old checker's unqualified prose claim: monitor.bad now
    # checks only G and the explicitly selected width scope.
    return {'source_receipt': receipt, 'product_states': checked['product_states'],
            'checked_transitions': checked['checked_transitions'],
            'guard_checked': True, 'width_checked': True}


def discover(source, ctx, options, audit):
    from research.signed_coverage.producer import infer
    from research.signed_coverage.runtime import load
    from research.signed_targets.producer import discover as product, ProductLimit
    from .checker import envelope
    observation, outcome = infer(source, ctx.selection, max_states=options['max_source_states'])
    if observation is None:
        return None, {'status': 'budget_exhausted', 'stage': 'covered_source', 'detail': outcome}
    audit.counts['fallback_source_certificates'] += 1
    runner, _ = load(source, ctx.selection, observation)
    audit.counts['fallback_classes'] += runner.machine.classes
    try:
        obligation = product(GuardedMonitor(runner, ctx), options['max_product_states'], MAX_WIDTH)
    except ProductLimit as error:
        return None, {'status': 'budget_exhausted', 'stage': 'guarded_product', 'reason': str(error)}
    if obligation['kind'] == 'counterexample':
        word = obligation['word']
        return envelope(ctx, 'witness', {'width': len(word),
                        'input': sum(int(b) << i for i, b in enumerate(word))}), None
    audit.counts['fallback_product_states'] += len(obligation['states'])
    return envelope(ctx, 'covered', {'observations': observation, 'obligation': obligation}), None
