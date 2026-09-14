"""Reproduce source-derived vocabulary, shared slices and consumer factors."""
import argparse
import json

from pathlib import Path
from .context_factor import explain
from .java_words import pinned_source
from .model import require
from .source_factor import check, synthesize
from .source_validation import validate
from .word_kernel import compiled_model


def variants():
    original = pinned_source()
    marker = '(value | bit) <= bound'
    return {'original': original,
            'plus_one': original.replace(marker, '(value | bit) <= bound + 1'),
            'plus_three': original.replace(marker, '(value | bit) <= bound + 3'),
            'shared_input': original.replace(marker, '(value | bit) <= initialValue')}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('output', type=Path); p.add_argument('--native', action='store_true')
    args = p.parse_args(); args.output.mkdir(parents=True, exist_ok=False)
    results = {}
    for name, source in variants().items():
        proposal = synthesize(source); require(proposal['status'] == 'candidate', 'source experiment budget')
        cert = proposal['certificate']; result = check(source, cert)
        result['execution_validation'] = validate(source, cert, native=args.native)
        model = compiled_model(source, cert['word'])
        for suffix, value in [('certificate', cert), ('source_ir', cert['word']['source_ir']), ('model', model),
                              ('explanation', explain(model, cert['factor']))]:
            (args.output / f'{name}.{suffix}.json').write_text(json.dumps(value, indent=2) + '\n')
        (args.output / f'{name}.java').write_text(source)
        results[name] = result
        print(json.dumps({'case': name, 'contexts': result['word']['context_values'],
                          'suffix_actions': result['word']['suffix_actions'],
                          'residuals': result['factor']['residual_states'], 'classes': result['factor']['classes'],
                          'validation': result['execution_validation']}), flush=True)
    results['insufficient_budget'] = synthesize(variants()['plus_three'], max_contexts=3)
    (args.output / 'RESULTS.json').write_text(json.dumps(results, indent=2) + '\n')


if __name__ == '__main__': main()
