"""Run registered test modules on THIS tree. Update the registry, not snapshots."""
import argparse
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = Path(__file__).with_name('SUITES.json')


def modules(value, group='all', root=ROOT):
    if type(value) is not dict or set(value) != {'schema','prior','new'} or value['schema'] != 'qkf-current-regressions-v1':
        raise ValueError('current regression registry format')
    seen=set()
    for key in ('prior','new'):
        if type(value[key]) is not list or not value[key]: raise ValueError('nonempty test group')
        for name in value[key]:
            if type(name) is not str or re.fullmatch(r'research\.(?:[A-Za-z_][A-Za-z_0-9]*\.)*test_[A-Za-z_0-9]+',name) is None:
                raise ValueError('test module name')
            if name in seen: raise ValueError('duplicate registered suite')
            if not (root / (name.replace('.','/')+'.py')).is_file(): raise ValueError('missing registered suite: '+name)
            seen.add(name)
    if group not in {'all','new','prior'}: raise ValueError('test group')
    return value['prior']+value['new'] if group=='all' else list(value[group])


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--group',choices=('all','new','prior'),default='all')
    args=parser.parse_args(argv)
    names=modules(json.loads(REGISTRY.read_text()),args.group)
    suite=unittest.defaultTestLoader.loadTestsFromNames(names)
    if not suite.countTestCases(): raise ValueError('no tests selected')
    return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1


if __name__=='__main__':raise SystemExit(main())
