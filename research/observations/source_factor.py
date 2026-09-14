"""Checker for source-derived observations followed by the existing factor chain."""
from .context_factor import Runner as FactorRunner, check as check_factor
from .model import require
from .word_kernel import check_word, compiled_model

SCHEMA = 'qkf-source-derived-factor-v1'


def check(source, cert):
    require(type(cert) is dict and set(cert) == {'schema', 'word', 'factor'} and cert['schema'] == SCHEMA,
            'source-to-factor certificate fields')
    word = check_word(source, cert['word'])
    model = compiled_model(source, cert['word'])
    factor = check_factor(model, cert['factor'])
    return {'status': 'certified', 'word': word, 'factor': factor,
            'scope': 'restricted source profile, exact integer observations and finite shared-context factor; not full Java verification'}


class Runner:
    def __init__(self, source, cert):
        check(source, cert)
        self.runner = FactorRunner(compiled_model(source, cert['word']), cert['factor'])

    def run(self, word):
        return self.runner.run(word)


def synthesize(source, **word_budgets):
    # Producer imports are deliberately lazy; replay never needs them.
    from .factor_producer import synthesize as factor
    from .word_producer import synthesize as words
    p = words(source, **word_budgets)
    if p['status'] != 'candidate': return {**p, 'stage': 'word'}
    model = compiled_model(source, p['certificate'])
    q = factor(model, context_row_encoding='atomic')
    if q['status'] != 'candidate': return {**q, 'stage': 'factor'}
    return {'status': 'candidate', 'certificate': {'schema': SCHEMA, 'word': p['certificate'], 'factor': q['certificate']}}
