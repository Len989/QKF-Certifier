"""Derive and check observations for exact Java ascending-region variants."""
import argparse
import hashlib
import json
from pathlib import Path

from .ascending_kernel import check
from .ascending_producer import synthesize
from .ascending_source import extract_region
from .ascending_validation import validate
from .java_words import pinned_source
from .model import require


def variants():
    source = pinned_source(); region = extract_region(source)['code']
    first = 'newLowerBound += bit;\n                            incremented = true;'
    forbidden = 'newLowerBound += bit;\n                            }'
    require(region.count(first) == region.count(forbidden) == 1, 'one source variant site')
    changes = {
        'original': region,
        'clear_repair': region.replace(forbidden, 'newLowerBound &= ~bit;\n                            }'),
        'first_or': region.replace(first, 'newLowerBound |= bit;\n                            incremented = true;'),
        'first_four_bits': region.replace(first, 'newLowerBound += bit << 2;\n                            incremented = true;'),
        'irrelevant_register': region.replace('boolean incremented = false;', 'boolean noise = false;\nboolean incremented = false;')
                                     .replace('long bit = 1L << position;', 'long bit = 1L << position;\nnoise = !noise;'),
    }
    return {name: source.replace(region, code) for name, code in changes.items()}


def write(path, value):
    path.write_text(json.dumps(value, separators=(',', ':'), ensure_ascii=False) + '\n')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('output', type=Path); p.add_argument('--native', action='store_true')
    args = p.parse_args(); args.output.mkdir(parents=True, exist_ok=False)
    results = {}
    for name, source in variants().items():
        proposal = synthesize(source); require(proposal['status'] == 'candidate', 'ascending experiment budget')
        cert = proposal['certificate']; result = check(source, cert)
        result['validation'] = validate(source, cert, native=args.native)
        results[name] = result
        (args.output / f'{name}.java').write_text(source)
        write(args.output / f'{name}.certificate.json', cert)
        print(json.dumps({'case': name, 'states': result['residual_states'], 'offsets': result['residual_offsets'],
                          'classes': result['observations']['classes'], 'validation': result['validation']}), flush=True)
    write(args.output / 'RESULTS.json', results)
    budget = synthesize(variants()['first_four_bits'], max_offset=1)
    require(budget['status'] == 'budget_exhausted' and budget['certificate'] is None, 'honest offset budget')
    write(args.output / 'BUDGET.json', budget)
    write(args.output / 'MANIFEST.json', {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                        for p in sorted(args.output.iterdir()) if p.is_file()})


if __name__ == '__main__': main()
