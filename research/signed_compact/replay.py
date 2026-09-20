"""Fresh compact replay; guards installed before importing any proof checker."""
import importlib.abc
import json
import sys

class Guard(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname in {'subprocess','platform','z3','cvc5','pysmt','research.unified.run',
                        'research.unified.v6','research.unified.v7','research.observations.run_package'} or (
                fullname.startswith('research.') and fullname.rsplit('.',1)[-1].startswith('producer')):
            raise ImportError('forbidden during compact replay: '+fullname)

if __name__=='__main__':
    if len(sys.argv)!=2:raise ValueError('one compact experiment directory')
    sys.meta_path.insert(0,Guard())
    from .experiment import run
    print(json.dumps(run(sys.argv[1],replay=True),sort_keys=True))
