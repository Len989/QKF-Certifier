"""Reproduce independent maximum/bound claims and their native counterexamples."""
import argparse
import json
from pathlib import Path

from .java_words import pinned_source
from .model import require
from .property_kernel import check
from .property_producer import synthesize
from .property_validation import validate
from .source_factor import check as check_source, synthesize as derive_source
from .upper_spec import specification


def variants():
    source = pinned_source(); marker = '(value | bit) <= bound'
    require(source.count(marker) == 1, 'one pinned source guard')
    return {'original': source,
            'plus_one': source.replace(marker, '(value | bit) <= bound + 1'),
            'strict': source.replace(marker, '(value | bit) < bound'),
            'shared_input': source.replace(marker, '(value | bit) <= initialValue')}


def write(path, value):
    path.write_text(json.dumps(value, separators=(',', ':'), ensure_ascii=False) + '\n')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('output', type=Path); p.add_argument('--native', action='store_true')
    args = p.parse_args(); args.output.mkdir(parents=True, exist_ok=False)
    specs = {claim: specification(claim) for claim in ['maximum', 'bound']}
    for claim, spec in specs.items(): write(args.output / f'{claim}.spec.json', spec)
    results = {}
    for name, source in variants().items():
        proposal = derive_source(source); require(proposal['status'] == 'candidate', 'source budget')
        source_cert = proposal['certificate']; source_result = check_source(source, source_cert)
        (args.output / f'{name}.java').write_text(source)
        write(args.output / f'{name}.source_certificate.json', source_cert)
        results[name] = {'source_model': {'status': source_result['status'], 'claim': source_result['claim']}}
        for claim, spec in specs.items():
            proposal = synthesize(source, source_cert, spec)
            require(proposal['status'] == 'candidate', 'property experiment budget')
            cert = proposal['certificate']; results[name][claim] = check(source, source_cert, spec, cert)
            write(args.output / f'{name}.{claim}.certificate.json', cert)
        results[name]['validation'] = validate(source, source_cert, specs['maximum'], native=args.native)
        print(json.dumps({'case': name, 'maximum': results[name]['maximum']['status'],
                          'bound': results[name]['bound']['status'], 'validation': results[name]['validation']}), flush=True)
    write(args.output / 'RESULTS.json', results)


if __name__ == '__main__': main()
