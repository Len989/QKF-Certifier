"""Guarded fresh-process replay; install guards BEFORE any checker imports."""
import importlib.abc
import json
import sys


class Guard(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if (fullname in {'subprocess','z3','cvc5','pysmt','research.unified.run',
                         'research.unified.v6','research.unified.v5','research.unified.v4',
                         'research.observations.run_package'}
            or fullname.startswith(('research.graal','research.knownbits','research.inference'))
            or (fullname.startswith('research.') and fullname.rsplit('.',1)[-1].startswith('producer'))):
            raise ImportError('forbidden during context replay: '+fullname)


def main():
    if len(sys.argv)!=2:raise ValueError('one experiment directory required')
    sys.meta_path.insert(0,Guard())
    from research.signed_context.experiment import run
    print(json.dumps(run(sys.argv[1],replay=True),sort_keys=True))


if __name__=='__main__':main()
